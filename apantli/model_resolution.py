

from fastapi import HTTPException, Request
from apantli.config import ProviderConfig, ModelConfig
import os
import logging

from pydantic import BaseModel
from typing_extensions import Literal
import litellm
from apantli.types import ChatFunctionCallArgs

def get_model_for_name(model_name: str, request: Request) -> ModelConfig:
    model_config: ModelConfig = request.models[model_name] # pyright: ignore[reportAttributeAccessIssue]
    return model_config

def get_provider_for_model(model: ModelConfig, request: Request) -> ProviderConfig:
    """Get the provider configuration for a given model.
    
    Args:
        model: ModelConfig
        request: FastAPI request object
        
    Returns:
        ProviderConfig object for the model's provider
        
    Raises:
        HTTPException: If model or provider not found in configuration
    """

    # Get the provider name from the model config
    provider_name = model.provider_name
    
    # Get the provider configuration
    provider_config = request.providers.get(provider_name) # pyright: ignore[reportAttributeAccessIssue]
    if not provider_config:
        raise HTTPException(status_code=500, detail=f"Provider '{provider_name}' not found in configuration for model '{model}'")
    
    return provider_config

def create_completion_request(model: str, request_data: dict, request: Request) -> ChatFunctionCallArgs:
    """Resolve model configuration and merge with request parameters.

    Args:
        model: Model name from request
        request_data: Request data dict
        model_map: Model configuration map from app.state

    Returns:
        Updated request_data dict

    Raises:
        HTTPException: If model not found in configuration
    """

    try:
        model_config = get_model_for_name(model, request)
    except:
        available_models = sorted(request.models.keys()) # pyright: ignore[reportAttributeAccessIssue]
        error_msg = f"Model '{model}' not found in configuration."
        if available_models:
            error_msg += f" Available models: {', '.join(available_models)}"
        raise HTTPException(status_code=404, detail=error_msg)
    
    provider_config: ProviderConfig = get_provider_for_model(model_config, request)
    
    call_request = ChatFunctionCallArgs(
        model = model_config.litellm_model,
        messages=request_data['messages']
    )

    # Handle api_key from config (get from config or resolve environment variable)
    api_key = provider_config.api_key
    if api_key.startswith('os.environ/'):
        env_var = api_key.split('/', 1)[1]
        api_key = os.environ.get(env_var, '')
    if api_key:
        call_request.api_key = api_key

    # Pass through all other litellm_params (timeout, num_retries, temperature, etc.)
    # Config provides defaults; client values (except null) always win
    for key, value in model_config.litellm_params.items():
        if key not in ('model', 'api_key'):
            # Use config value only if client didn't provide, or provided None/null
            # This allows: config defaults, client override, null → use config
            current_value = getattr(call_request, key, None)
            if current_value is None:
                setattr(call_request, key, value)
    
    call_request.max_tokens = model_config.context_window

    # Apply provider defaults if not specified
    if provider_config.timeout:
        call_request.timeout = provider_config.timeout
    if provider_config.num_retries:
        call_request.timeout = provider_config.num_retries
    
    call_request.base_url = provider_config.base_url
    
    if provider_config.headers:
        call_request.extra_headers = provider_config.headers
    
    return call_request


def filter_parameters_for_model(call_request: ChatFunctionCallArgs) -> ChatFunctionCallArgs:
    
    # Models that reject temperature + top_p being specified together
# This is a constraint introduced in late 2025 for newest Anthropic models
    ANTHROPIC_STRICT_MODELS = [
        'claude-sonnet-4-5-20250929',
        'claude-opus-4',  # Prefix match for all Opus 4.x versions
    ]

    """Filter request parameters based on model-specific constraints.

    Some models (e.g., Claude Sonnet 4.5-20250929) reject having both
    temperature and top_p specified together. This function removes
    incompatible parameters before sending to LiteLLM.

    Args:
        request_data: Request data dict with 'model' and parameters

    Returns:
        Filtered request_data dict
    """
    litellm_model = call_request.model

    # Check if this is an Anthropic model with strict parameter constraints
    is_strict_model = any(
        strict_model in litellm_model
        for strict_model in ANTHROPIC_STRICT_MODELS
    )

    if is_strict_model:
        # If both temperature and top_p are present, remove top_p
        # (Anthropic recommends using temperature over top_p)
        call_request.top_p = None

    return call_request


def calculate_cost(response) -> float:
    """Calculate cost for a completion response, returning 0.0 on error."""
    return 0.0



