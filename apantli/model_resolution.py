

from fastapi import HTTPException, Request
from apantli.config import ProviderConfig, ModelConfig
import os
import logging
import litellm

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
    config = request.app.state.config

    # Get the provider name from the model config
    provider_name = model.provider_name
    
    # Get the provider configuration
    provider_config = config.providers.get(provider_name)
    if not provider_config:
        raise HTTPException(status_code=500, detail=f"Provider '{provider_name}' not found in configuration for model '{model}'")
    
    return provider_config

def resolve_model_config(model: str, request_data: dict, request: Request) -> dict:
    """Resolve model configuration and merge with request parameters.

    Args:
        model: Model name from request
        request_data: Request data dict (will be modified)
        model_map: Model configuration map from app.state

    Returns:
        Updated request_data dict

    Raises:
        HTTPException: If model not found in configuration
    """
    if model not in request.app.state.config.models:
        available_models = sorted(request.app.state.config.models.keys())
        error_msg = f"Model '{model}' not found in configuration."
        if available_models:
            error_msg += f" Available models: {', '.join(available_models)}"
        raise HTTPException(status_code=404, detail=error_msg)

    model_config: ModelConfig = request.app.state.config.models[model]
    provider_config: ProviderConfig = get_provider_for_model(model_config, request)
    
    # Replace model with LiteLLM format
    request_data['model'] = model_config.litellm_model

    # Handle api_key from config (get from config or resolve environment variable)
    api_key = provider_config.api_key
    if api_key.startswith('os.environ/'):
        env_var = api_key.split('/', 1)[1]
        api_key = os.environ.get(env_var, '')
    if api_key:
        request_data['api_key'] = api_key

    # Pass through all other litellm_params (timeout, num_retries, temperature, etc.)
    # Config provides defaults; client values (except null) always win
    for key, value in model_config.litellm_params.items():
        if key not in ('model', 'api_key'):
            # Use config value only if client didn't provide, or provided None/null
            # This allows: config defaults, client override, null → use config
            if key not in request_data or request_data.get(key) is None:
                request_data[key] = value
    
    request_data['context_window'] = model_config.context_window

    # Apply provider defaults if not specified
    if 'timeout' not in request_data and 'timeout' in provider_config:
        request_data['timeout'] = provider_config.timeout
    if 'num_retries' not in request_data and 'num_retries' in provider_config:
        request_data['num_retries'] = provider_config.num_retries
    
    request_data['base_url'] = provider_config.base_url
    
    if 'custom_llm_provider' in provider_config:
        request_data['custom_llm_provider'] = provider_config.custom_llm_provider
    
    if 'headers' in provider_config:
        request_data['extra_headers'] = provider_config.headers
    
    

    return request_data




def filter_parameters_for_model(request_data: dict) -> dict:
    
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
    litellm_model = request_data.get('model', '')

    # Check if this is an Anthropic model with strict parameter constraints
    is_strict_model = any(
        strict_model in litellm_model
        for strict_model in ANTHROPIC_STRICT_MODELS
    )

    if is_strict_model:
        # If both temperature and top_p are present, remove top_p
        # (Anthropic recommends using temperature over top_p)
        has_temperature = 'temperature' in request_data and request_data['temperature'] is not None
        has_top_p = 'top_p' in request_data and request_data['top_p'] is not None

        if has_temperature and has_top_p:
            removed_value = request_data.pop('top_p')
            logging.info(f"Removed top_p={removed_value} for {litellm_model} (model constraint: cannot specify both temperature and top_p)")

    # Remove None/null values from request_data to avoid sending them to provider
    request_data = {k: v for k, v in request_data.items() if v is not None}

    return request_data


def calculate_cost(response) -> float:
    """Calculate cost for a completion response, returning 0.0 on error."""
    try:
        return litellm.completion_cost(completion_response=response) # pyright: ignore[reportPrivateImportUsage]
    except Exception as e:
        logging.debug(f"Failed to calculate cost: {e}")
        return 0.0
