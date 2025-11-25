from typing import Any
from apantli.auth import authenticated_route
from model_resolution import resolve_model_config, filter_parameters_for_model
from outbound import execute_request, execute_streaming_request, handle_llm_error
import time
from fastapi.responses import JSONResponse
from apantli.errors import build_error_response
from fastapi import Request, HTTPException
from apantli.config import LOG_INDENT
import logging
import litellm
from litellm import completion
from litellm.exceptions import (
    RateLimitError,
    InternalServerError,
    ServiceUnavailableError,
    APIConnectionError,
    AuthenticationError,
    Timeout,
    PermissionDeniedError,
    NotFoundError,
    BadRequestError,
)


@authenticated_route
async def chat_completions(request: Request):
    """OpenAI-compatible chat completions endpoint."""
    db = request.app.state.db
    start_time = time.time()
    request_data = await request.json()
 
    try:
        # Validate model parameter
        model = request_data.get('model')
        if not model:
            error_response = build_error_response("invalid_request_error", "Model is required", "missing_model")
            return JSONResponse(content=error_response, status_code=400)

        # Resolve model configuration and merge with request
        request_data = resolve_model_config(
            model,
            request_data,
            request.app.state.model_map,
            request.app.state.timeout,
            request.app.state.retries
        )

        # Filter parameters based on model-specific constraints
        request_data = filter_parameters_for_model(request_data)

        # Create logging copy with final request_data (includes API key and all params)
        request_data_for_logging = request_data.copy()

        # Log request start
        is_streaming = request_data.get('stream', False)
        stream_indicator = " [streaming]" if is_streaming else ""
        print(f"{LOG_INDENT}→ LLM Request: {model}{stream_indicator}")

        # Call LiteLLM
        response = completion(**request_data)

        # Route to appropriate handler based on streaming mode
        if is_streaming:
            return await execute_streaming_request(response, model, request_data, request_data_for_logging, start_time, db, request)
        else:
            return await execute_request(response, model, request_data, request_data_for_logging, start_time, db)

    except HTTPException as exc:
        # Model not found - log and return error
        duration_ms = int((time.time() - start_time) * 1000)
        await db.log_request(model, "unknown", None, duration_ms, request_data, error=f"UnknownModel: {exc.detail}") # pyright: ignore[reportPossiblyUnboundVariable]
        print(f"{LOG_INDENT}✗ LLM Response: {model} (unknown) | {duration_ms}ms | Error: UnknownModel") # pyright: ignore[reportPossiblyUnboundVariable]
        error_response = build_error_response("invalid_request_error", exc.detail, "model_not_found")
        return JSONResponse(content=error_response, status_code=exc.status_code)

    except (RateLimitError, AuthenticationError, PermissionDeniedError, NotFoundError,
            Timeout, InternalServerError, ServiceUnavailableError, APIConnectionError,
            BadRequestError) as exc:
        return await handle_llm_error(exc, start_time, request_data, request_data_for_logging, db) # pyright: ignore[reportPossiblyUnboundVariable]

    except Exception as exc:
        # Catch-all for unexpected errors
        logging.exception(f"Unexpected error in chat completions: {exc}")
        return await handle_llm_error(exc, start_time, request_data, request_data_for_logging, db) # pyright: ignore[reportPossiblyUnboundVariable]



async def health():
    """Health check endpoint."""
    return {"status": "ok"}



async def models(request: Request):
    """List available models from config."""
    model_list = []
    for model_name, litellm_params in request.app.state.model_map.items():
        # Try to get pricing info from LiteLLM
        litellm_model = litellm_params['model']
        input_cost = None
        output_cost = None

        try:
            # Get per-token costs from LiteLLM's cost database
            # Try with full model name first, then without provider prefix
            model_data = None
            if litellm_model in litellm.model_cost:
                model_data = litellm.model_cost[litellm_model]
            elif '/' in litellm_model:
                # Try without provider prefix (e.g., "openai/gpt-4.1" -> "gpt-4.1")
                model_without_provider = litellm_model.split('/', 1)[1]
                if model_without_provider in litellm.model_cost:
                    model_data = litellm.model_cost[model_without_provider]

            if model_data:
                input_cost_per_token = model_data.get('input_cost_per_token', 0)
                output_cost_per_token = model_data.get('output_cost_per_token', 0)

                # Convert to per-million
                if input_cost_per_token:
                    input_cost = input_cost_per_token * 1000000
                if output_cost_per_token:
                    output_cost = output_cost_per_token * 1000000
        except Exception as exc:
            pass

        model_info = {
            'name': model_name,
            'litellm_model': litellm_params['model'],
            'provider': litellm_params['model'].split('/')[0] if '/' in litellm_params['model'] else 'unknown',
            'input_cost_per_million': round(input_cost, 2) if input_cost else None,
            'output_cost_per_million': round(output_cost, 2) if output_cost else None
        }

        # Include predefined parameters if they exist in config
        if 'temperature' in litellm_params:
            model_info['temperature'] = litellm_params['temperature']
        if 'top_p' in litellm_params:
            model_info['top_p'] = litellm_params['top_p']
        if 'max_tokens' in litellm_params:
            model_info['max_tokens'] = litellm_params['max_tokens']

        model_list.append(model_info)

    return {'models': model_list}


async def v1_models_info(request: Request):
    """List available models in LiteLLM proxy format.

    Returns a JSON object with a top-level 'data' property containing an array
    of model objects with model_name, model_info, and litellm_params fields.
    """
    model_data = []
    for model_name, litellm_params in request.app.state.model_map.items():
        litellm_model = litellm_params['model']

        # Build model_info from LiteLLM's cost database
        model_info: dict[str, Any] = {}

        try:
            # Get model data from LiteLLM's cost database
            llm_model_data = None
            if litellm_model in litellm.model_cost:
                llm_model_data = litellm.model_cost[litellm_model]
            elif '/' in litellm_model:
                # Try without provider prefix (e.g., "openai/gpt-4.1" -> "gpt-4.1")
                model_without_provider = litellm_model.split('/', 1)[1]
                if model_without_provider in litellm.model_cost:
                    llm_model_data = litellm.model_cost[model_without_provider]

            if llm_model_data:
                # Token limits
                if 'max_output_tokens' in llm_model_data:
                    model_info['max_output_tokens'] = llm_model_data['max_output_tokens']
                elif 'max_tokens' in llm_model_data:
                    model_info['max_tokens'] = llm_model_data['max_tokens']

                if 'max_input_tokens' in llm_model_data:
                    model_info['max_input_tokens'] = llm_model_data['max_input_tokens']

                # Capability flags
                if 'supports_vision' in llm_model_data:
                    model_info['supports_vision'] = llm_model_data['supports_vision']
                if 'supports_prompt_caching' in llm_model_data:
                    model_info['supports_prompt_caching'] = llm_model_data['supports_prompt_caching']

                # Cost per token
                if 'input_cost_per_token' in llm_model_data:
                    model_info['input_cost_per_token'] = llm_model_data['input_cost_per_token']
                if 'output_cost_per_token' in llm_model_data:
                    model_info['output_cost_per_token'] = llm_model_data['output_cost_per_token']

                # Cache pricing
                if 'cache_creation_input_token_cost' in llm_model_data:
                    model_info['cache_creation_input_token_cost'] = llm_model_data['cache_creation_input_token_cost']
                if 'cache_read_input_token_cost' in llm_model_data:
                    model_info['cache_read_input_token_cost'] = llm_model_data['cache_read_input_token_cost']
        except Exception:
            pass

        # Build litellm_params object
        litellm_params_obj = {
            'model': str(litellm_model)
        }

        # Include any additional parameters from config
        for key in ['temperature', 'top_p', 'max_tokens', 'timeout', 'num_retries']:
            if key in litellm_params and litellm_params[key] is not None:
                litellm_params_obj[key] = litellm_params[key]

        model_entry = {
            'model_name': model_name,
            'model_info': model_info,
            'litellm_params': litellm_params_obj
        }

        model_data.append(model_entry)

    return {'data': model_data}


async def v1_models_openrouter(request: Request):
    """List available models in OpenRouter API format.
    
    Returns a JSON object with a top-level 'data' property containing an array
    of model objects following the OpenRouter API specification.
    """
    import time
    
    model_data = []
    current_time = int(time.time())
    
    for model_name, litellm_params in request.app.state.model_map.items():
        litellm_model = litellm_params['model']
        
        # Extract provider from model name
        provider = litellm_model.split('/')[0] if '/' in litellm_model else 'unknown'
        
        # Build model info from LiteLLM's cost database
        model_info = {}
        pricing = {
            'prompt': '0',
            'completion': '0', 
            'request': '0',
            'image': '0',
            'web_search': '0',
            'internal_reasoning': '0'
        }
        
        try:
            # Get model data from LiteLLM's cost database
            llm_model_data = None
            if litellm_model in litellm.model_cost:
                llm_model_data = litellm.model_cost[litellm_model]
            elif '/' in litellm_model:
                # Try without provider prefix (e.g., "openai/gpt-4.1" -> "gpt-4.1")
                model_without_provider = litellm_model.split('/', 1)[1]
                if model_without_provider in litellm.model_cost:
                    llm_model_data = litellm.model_cost[model_without_provider]

            if llm_model_data:
                # Context length
                context_length = llm_model_data.get('max_input_tokens', 128000)
                
                # Pricing information
                input_cost_per_token = llm_model_data.get('input_cost_per_token', 0)
                output_cost_per_token = llm_model_data.get('output_cost_per_token', 0)
                
                if input_cost_per_token:
                    pricing['prompt'] = str(input_cost_per_token)
                if output_cost_per_token:
                    pricing['completion'] = str(output_cost_per_token)
                    
                # Cache pricing if available
                if 'cache_read_input_token_cost' in llm_model_data:
                    pricing['input_cache_read'] = str(llm_model_data['cache_read_input_token_cost'])
                if 'cache_creation_input_token_cost' in llm_model_data:
                    pricing['input_cache_write'] = str(llm_model_data['cache_creation_input_token_cost'])
                    
                # Architecture information
                supports_vision = llm_model_data.get('supports_vision', False)
                
                model_info = {
                    'context_length': context_length,
                    'architecture': {
                        'modality': 'text+image->text' if supports_vision else 'text->text',
                        'input_modalities': ['file', 'image', 'text'] if supports_vision else ['text'],
                        'output_modalities': ['text'],
                        'tokenizer': provider.title() if provider != 'unknown' else 'Other',
                        'instruct_type': None
                    },
                    'top_provider': {
                        'context_length': context_length,
                        'max_completion_tokens': llm_model_data.get('max_output_tokens', None),
                        'is_moderated': False
                    }
                }
            else:
                # Default values when no cost data is available
                model_info = {
                    'context_length': 128000,
                    'architecture': {
                        'modality': 'text->text',
                        'input_modalities': ['text'],
                        'output_modalities': ['text'],
                        'tokenizer': provider.title() if provider != 'unknown' else 'Other',
                        'instruct_type': None
                    },
                    'top_provider': {
                        'context_length': 128000,
                        'max_completion_tokens': None,
                        'is_moderated': False
                    }
                }
        except Exception:
            # Fallback to default values
            model_info = {
                'context_length': 128000,
                'architecture': {
                    'modality': 'text->text',
                    'input_modalities': ['text'],
                    'output_modalities': ['text'],
                    'tokenizer': provider.title() if provider != 'unknown' else 'Other',
                    'instruct_type': None
                },
                'top_provider': {
                    'context_length': 128000,
                    'max_completion_tokens': None,
                    'is_moderated': False
                }
            }
        
        # Determine supported parameters based on provider and model
        supported_parameters = ['max_tokens', 'response_format', 'structured_outputs']
        
        # Add provider-specific parameters
        if provider in ['openai', 'anthropic']:
            supported_parameters.extend(['temperature', 'top_p', 'frequency_penalty'])
        if provider == 'anthropic':
            supported_parameters.extend(['include_reasoning', 'reasoning', 'stop', 'tool_choice', 'tools', 'top_k', 'verbosity'])
        
        # Build default parameters from config
        default_parameters = {}
        for param in ['temperature', 'top_p', 'frequency_penalty']:
            if param in litellm_params and litellm_params[param] is not None:
                default_parameters[param] = litellm_params[param]
        
        # Create the model entry in OpenRouter format
        model_entry = {
            'id': f"{model_name}",
            'canonical_slug': f"{model_name}",
            'hugging_face_id': '',
            'name': f"{provider.title()}: {model_name.replace('-', ' ').title()}",
            'created': current_time,
            'description': f"{provider.title()} model {model_name}."
                          f"This model supports various text generation tasks and is accessible "
                          f"through the OpenAI-compatible API.",
            'context_length': model_info['context_length'],
            'architecture': model_info['architecture'],
            'pricing': pricing,
            'top_provider': model_info['top_provider'],
            'per_request_limits': None,
            'supported_parameters': supported_parameters,
            'default_parameters': default_parameters
        }
        
        model_data.append(model_entry)
    
    return {'data': model_data}

