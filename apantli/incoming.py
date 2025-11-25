from typing import List
from apantli.auth import authenticated_route
from apantli.model_resolution import create_completion_request, filter_parameters_for_model, get_provider_for_model, get_model_for_name
from apantli.outbound import execute_request, execute_streaming_request, handle_llm_error
from apantli.config import ModelConfig, ProviderConfig
from apantli.log_config import logger
import time
from fastapi.responses import JSONResponse
from apantli.errors import build_error_response
from fastapi import Request, HTTPException

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
from apantli.types import ChatFunctionCallArgs


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
        request_data = create_completion_request(
            model,
            request_data,
            request.app.state.config
        )

        # Filter parameters based on model-specific constraints
        request_data = filter_parameters_for_model(request_data)

        # Create logging copy with final request_data (includes API key and all params)
        request_data_for_logging = request_data.model_copy()

        # Log request start
        is_streaming = request_data.stream or False
        stream_indicator = " [streaming]" if is_streaming else ""
        logger.info(f"→ LLM Request: {model}{stream_indicator}")

        # Call LiteLLM
        response = completion(**request_data.to_dict(), drop_params=True)

        # Route to appropriate handler based on streaming mode
        if is_streaming:
            return await execute_streaming_request(response, model, request_data, request_data_for_logging, start_time, db, request)
        else:
            return await execute_request(response, model, request_data, request_data_for_logging, start_time, db)

    except HTTPException as exc:
        # Model not found - log and return error
        duration_ms = int((time.time() - start_time) * 1000)
        await db.log_request(model, "unknown", None, duration_ms, request_data, error=f"UnknownModel: {exc.detail}") # pyright: ignore[reportPossiblyUnboundVariable]
        logger.info(f"✗ LLM Response: {model} (unknown) | {duration_ms}ms | Error: UnknownModel") # pyright: ignore[reportPossiblyUnboundVariable]
        error_response = build_error_response("invalid_request_error", exc.detail, "model_not_found")
        return JSONResponse(content=error_response, status_code=exc.status_code)

    except (RateLimitError, AuthenticationError, PermissionDeniedError, NotFoundError,
            Timeout, InternalServerError, ServiceUnavailableError, APIConnectionError,
            BadRequestError) as exc:
        return await handle_llm_error(exc, start_time, request_data, request_data_for_logging, db) # pyright: ignore[reportPossiblyUnboundVariable]

    except Exception as exc:
        # Catch-all for unexpected errors
        logger.exception(f"Unexpected error in chat completions: {exc}")
        return await handle_llm_error(exc, start_time, request_data, request_data_for_logging, db) # pyright: ignore[reportPossiblyUnboundVariable]



async def health():
    """Health check endpoint."""
    return {"status": "ok"}


# async def v1_models_info(request: Request):
#     """List available models in LiteLLM proxy format.

#     Returns a JSON object with a top-level 'data' property containing an array
#     of model objects with model_name, model_info, and litellm_params fields.
#     """
#     model_data = []
#     for model_name, litellm_params in request.app.state.model_map.items():
#         litellm_model = litellm_params['model']

#         # Build model_info from LiteLLM's cost database
#         model_info: dict[str, Any] = {}

#         try:
#             # Get model data from LiteLLM's cost database
#             llm_model_data = None
#             if litellm_model in litellm.model_cost:
#                 llm_model_data = litellm.model_cost[litellm_model]
#             elif '/' in litellm_model:
#                 # Try without provider prefix (e.g., "openai/gpt-4.1" -> "gpt-4.1")
#                 model_without_provider = litellm_model.split('/', 1)[1]
#                 if model_without_provider in litellm.model_cost:
#                     llm_model_data = litellm.model_cost[model_without_provider]

#             if llm_model_data:
#                 # Token limits
#                 if 'max_output_tokens' in llm_model_data:
#                     model_info['max_output_tokens'] = llm_model_data['max_output_tokens']
#                 elif 'max_tokens' in llm_model_data:
#                     model_info['max_tokens'] = llm_model_data['max_tokens']

#                 if 'max_input_tokens' in llm_model_data:
#                     model_info['max_input_tokens'] = llm_model_data['max_input_tokens']

#                 # Capability flags
#                 if 'supports_vision' in llm_model_data:
#                     model_info['supports_vision'] = llm_model_data['supports_vision']
#                 if 'supports_prompt_caching' in llm_model_data:
#                     model_info['supports_prompt_caching'] = llm_model_data['supports_prompt_caching']

#                 # Cost per token
#                 if 'input_cost_per_token' in llm_model_data:
#                     model_info['input_cost_per_token'] = llm_model_data['input_cost_per_token']
#                 if 'output_cost_per_token' in llm_model_data:
#                     model_info['output_cost_per_token'] = llm_model_data['output_cost_per_token']

#                 # Cache pricing
#                 if 'cache_creation_input_token_cost' in llm_model_data:
#                     model_info['cache_creation_input_token_cost'] = llm_model_data['cache_creation_input_token_cost']
#                 if 'cache_read_input_token_cost' in llm_model_data:
#                     model_info['cache_read_input_token_cost'] = llm_model_data['cache_read_input_token_cost']
#         except Exception:
#             pass

#         # Build litellm_params object
#         litellm_params_obj = {
#             'model': str(litellm_model)
#         }

#         # Include any additional parameters from config
#         for key in ['temperature', 'top_p', 'max_tokens', 'timeout', 'num_retries']:
#             if key in litellm_params and litellm_params[key] is not None:
#                 litellm_params_obj[key] = litellm_params[key]

#         model_entry = {
#             'model_name': model_name,
#             'model_info': model_info,
#             'litellm_params': litellm_params_obj
#         }

#         model_data.append(model_entry)

#     return {'data': model_data}


async def v1_models_openrouter(request: Request):
    """List available models in OpenRouter API format.
    
    Returns a JSON object with a top-level 'data' property containing an array
    of model objects following the OpenRouter API specification.
    """
    model_data = []
    
    for model_name, model_config in request.app.state.config.models.items():
        model_config: ModelConfig = get_model_for_name(model_name, request)
        provider_data: ProviderConfig = get_provider_for_model(model_config,request)
        entry = {
            "id": model_config.model_name,
            "context_length": model_config.context_window,
            "provider": provider_data.provider_name,
            "pricing": {},
            "top_provider": {
                "context_length": model_config.context_window,
            }
        }
        
        model_data.append(entry)
    return {'data': model_data}

#####
    # {
    #   "id": "anthropic/claude-opus-4.5",
    #   "canonical_slug": "anthropic/claude-4.5-opus-20251124",
    #   "hugging_face_id": "",
    #   "name": "Anthropic: Claude Opus 4.5",
    #   "created": 1764010580,
    #   "description": "Claude Opus 4.5 is Anthropic’s frontier reasoning model optimized for complex software engineering, agentic workflows, and long-horizon computer use. It offers strong multimodal capabilities, competitive performance across real-world coding and reasoning benchmarks, and improved robustness to prompt injection. The model is designed to operate efficiently across varied effort levels, enabling developers to trade off speed, depth, and token usage depending on task requirements. It comes with a new parameter to control token efficiency, which can be accessed using the OpenRouter Verbosity parameter with low, medium, or high.\n\nOpus 4.5 supports advanced tool use, extended context management, and coordinated multi-agent setups, making it well-suited for autonomous research, debugging, multi-step planning, and spreadsheet/browser manipulation. It delivers substantial gains in structured reasoning, execution reliability, and alignment compared to prior Opus generations, while reducing token overhead and improving performance on long-running tasks.",
    #   "context_length": 200000,
    #   "architecture": {
    #     "modality": "text+image->text",
    #     "input_modalities": [
    #       "file",
    #       "image",
    #       "text"
    #     ],
    #     "output_modalities": [
    #       "text"
    #     ],
    #     "tokenizer": "Claude",
    #     "instruct_type": null
    #   },
    #   "pricing": {
    #     "prompt": "0.000005",
    #     "completion": "0.000025",
    #     "request": "0",
    #     "image": "0",
    #     "web_search": "0.01",
    #     "internal_reasoning": "0",
    #     "input_cache_read": "0.0000005",
    #     "input_cache_write": "0.00000625"
    #   },
    #   "top_provider": {
    #     "context_length": 200000,
    #     "max_completion_tokens": 32000,
    #     "is_moderated": true
    #   },
    #   "per_request_limits": null,
    #   "supported_parameters": [
    #     "include_reasoning",
    #     "max_tokens",
    #     "reasoning",
    #     "response_format",
    #     "stop",
    #     "structured_outputs",
    #     "temperature",
    #     "tool_choice",
    #     "tools",
    #     "top_k",
    #     "verbosity"
    #   ],
    #   "default_parameters": {
    #     "temperature": null,
    #     "top_p": null,
    #     "frequency_penalty": null
    #   }
    # },
# asdf
# asdf
# asdf