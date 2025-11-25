

from fastapi import HTTPException
import os
import logging
import litellm


def resolve_model_config(model: str, request_data: dict, model_map: dict,
                        timeout: int, retries: int) -> dict:
    """Resolve model configuration and merge with request parameters.

    Args:
        model: Model name from request
        request_data: Request data dict (will be modified)
        model_map: Model configuration map from app.state
        timeout: Default timeout from app.state
        retries: Default retries from app.state

    Returns:
        Updated request_data dict

    Raises:
        HTTPException: If model not found in configuration
    """
    if model not in model_map:
        available_models = sorted(model_map.keys())
        error_msg = f"Model '{model}' not found in configuration."
        if available_models:
            error_msg += f" Available models: {', '.join(available_models)}"
        raise HTTPException(status_code=404, detail=error_msg)

    model_config = model_map[model]

    # Replace model with LiteLLM format
    request_data['model'] = model_config['model']

    # Handle api_key from config (resolve environment variable)
    api_key = model_config.get('api_key', '')
    if api_key.startswith('os.environ/'):
        env_var = api_key.split('/', 1)[1]
        api_key = os.environ.get(env_var, '')
    if api_key:
        request_data['api_key'] = api_key

    # Pass through all other litellm_params (timeout, num_retries, temperature, etc.)
    # Config provides defaults; client values (except null) always win
    for key, value in model_config.items():
        if key not in ('model', 'api_key'):
            # Use config value only if client didn't provide, or provided None/null
            # This allows: config defaults, client override, null → use config
            if key not in request_data or request_data.get(key) is None:
                request_data[key] = value

    # Apply global defaults if not specified
    if 'timeout' not in request_data:
        request_data['timeout'] = timeout
    if 'num_retries' not in request_data:
        request_data['num_retries'] = retries

    return request_data


# Models that reject temperature + top_p being specified together
# This is a constraint introduced in late 2025 for newest Anthropic models
ANTHROPIC_STRICT_MODELS = [
    'claude-sonnet-4-5-20250929',
    'claude-opus-4',  # Prefix match for all Opus 4.x versions
]


def filter_parameters_for_model(request_data: dict) -> dict:
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
