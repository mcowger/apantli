from typing import Any, Dict, List, Optional, Tuple
from apantli.auth import authenticated_route
from apantli.model_resolution import create_completion_request, create_embedding_request, filter_parameters_for_model, get_provider_for_model, get_model_for_name
from apantli.outbound import execute_request, execute_streaming_request, handle_llm_error, execute_embedding_request, handle_embedding_error
from apantli.config import ModelConfig, ProviderConfig
from apantli.log_config import logger
import time
from fastapi.responses import JSONResponse
from apantli.errors import build_error_response
from fastapi import Request, HTTPException

from litellm import completion, embedding
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
from apantli.types import ChatFunctionCallArgs, EmbeddingFunctionCallArgs


def get_pricing_params(model_name: str, request: Request) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, float]]]:
    """Get catwalk_name, costing_model, and pricing_override for a model.
    
    Args:
        model_name: The model name to look up
        request: FastAPI request object
        
    Returns:
        Tuple of (catwalk_name, costing_model, pricing_override), all may be None if model not found
    """
    try:
        model_config = get_model_for_name(model_name, request)
        provider_config = get_provider_for_model(model_config, request)
        return provider_config.catwalk_name, model_config.costing_model, model_config.pricing_override
    except (KeyError, HTTPException):
        return None, None, None


@authenticated_route
async def chat_completions(request: Request):
    """OpenAI-compatible chat completions endpoint."""
    db = request.app.state.db
    pricing_service = request.app.state.pricing_service
    start_time = time.time()
    request_data = await request.json()
    catwalk_name: Optional[str] = None
    costing_model: Optional[str] = None
    pricing_override: Optional[Dict[str, float]] = None
 
    try:
        # Validate model parameter
        model = request_data.get('model')
        if not model:
            error_response = build_error_response("invalid_request_error", "Model is required", "missing_model")
            return JSONResponse(content=error_response, status_code=400)

        # Get pricing parameters before model resolution might fail
        catwalk_name, costing_model, pricing_override = get_pricing_params(model, request)

        # Resolve model configuration and merge with request
        request_data = create_completion_request(
            model,
            request_data,
            request
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
            return await execute_streaming_request(
                response, model, request_data, request_data_for_logging, start_time, db, request,
                pricing_service=pricing_service,
                catwalk_name=catwalk_name,
                costing_model=costing_model,
                pricing_override=pricing_override,
            )
        else:
            return await execute_request(
                response, model, request_data, request_data_for_logging, start_time, db,
                pricing_service=pricing_service,
                catwalk_name=catwalk_name,
                costing_model=costing_model,
                pricing_override=pricing_override,
            )

    except HTTPException as exc:
        # Model not found - log and return error
        duration_ms = int((time.time() - start_time) * 1000)
        await db.log_request(
            model, "unknown", None, duration_ms, request_data,  # pyright: ignore[reportPossiblyUnboundVariable]
            error=f"UnknownModel: {exc.detail}",
            pricing_service=pricing_service,
            catwalk_name=catwalk_name,
            costing_model=costing_model,
            pricing_override=pricing_override,
        )
        logger.info(f"✗ LLM Response: {model} (unknown) | {duration_ms}ms | Error: UnknownModel") # pyright: ignore[reportPossiblyUnboundVariable]
        error_response = build_error_response("invalid_request_error", exc.detail, "model_not_found")
        return JSONResponse(content=error_response, status_code=exc.status_code)

    except (RateLimitError, AuthenticationError, PermissionDeniedError, NotFoundError,
            Timeout, InternalServerError, ServiceUnavailableError, APIConnectionError,
            BadRequestError) as exc:
        return await handle_llm_error(
            exc, start_time, request_data, request_data_for_logging, db,  # pyright: ignore[reportPossiblyUnboundVariable]
            pricing_service=pricing_service,
            catwalk_name=catwalk_name,
            costing_model=costing_model,
            pricing_override=pricing_override,
        )

    except Exception as exc:
        # Catch-all for unexpected errors
        logger.exception(f"Unexpected error in chat completions: {exc}")
        return await handle_llm_error(
            exc, start_time, request_data, request_data_for_logging, db,  # pyright: ignore[reportPossiblyUnboundVariable]
            pricing_service=pricing_service,
            catwalk_name=catwalk_name,
            costing_model=costing_model,
            pricing_override=pricing_override,
        )


@authenticated_route
async def embeddings(request: Request):
    """OpenAI-compatible embeddings endpoint."""
    db = request.app.state.db
    pricing_service = request.app.state.pricing_service
    start_time = time.time()
    request_data = await request.json()
    catwalk_name: Optional[str] = None
    costing_model: Optional[str] = None
    pricing_override: Optional[Dict[str, float]] = None
 
    try:
        # Validate model parameter
        model = request_data.get('model')
        if not model:
            error_response = build_error_response("invalid_request_error", "Model is required", "missing_model")
            return JSONResponse(content=error_response, status_code=400)

        # Validate input parameter
        input_data = request_data.get('input')
        if not input_data:
            error_response = build_error_response("invalid_request_error", "Input is required", "missing_input")
            return JSONResponse(content=error_response, status_code=400)

        # Get pricing parameters before model resolution might fail
        catwalk_name, costing_model, pricing_override = get_pricing_params(model, request)

        # Resolve model configuration and merge with request
        request_data_obj = create_embedding_request(
            model,
            request_data,
            request
        )

        # Create logging copy with final request_data (includes API key and all params)
        request_data_for_logging = request_data_obj.model_copy()

        # Log request start
        logger.info(f"→ Embedding Request: {model}")

        # Call LiteLLM embedding
        response = embedding(**request_data_obj.to_dict())

        # Execute and return response
        return await execute_embedding_request(
            response, model, request_data_obj, request_data_for_logging, start_time, db,
            pricing_service=pricing_service,
            catwalk_name=catwalk_name,
            costing_model=costing_model,
            pricing_override=pricing_override,
        )

    except HTTPException as exc:
        # Model not found - log and return error
        duration_ms = int((time.time() - start_time) * 1000)
        await db.log_request(
            model, "unknown", None, duration_ms, request_data_obj,  # pyright: ignore[reportPossiblyUnboundVariable]
            error=f"UnknownModel: {exc.detail}",
            pricing_service=pricing_service,
            catwalk_name=catwalk_name,
            costing_model=costing_model,
            pricing_override=pricing_override,
        )
        logger.info(f"✗ Embedding Response: {model} (unknown) | {duration_ms}ms | Error: UnknownModel") # pyright: ignore[reportPossiblyUnboundVariable]
        error_response = build_error_response("invalid_request_error", exc.detail, "model_not_found")
        return JSONResponse(content=error_response, status_code=exc.status_code)

    except (RateLimitError, AuthenticationError, PermissionDeniedError, NotFoundError,
            Timeout, InternalServerError, ServiceUnavailableError, APIConnectionError,
            BadRequestError) as exc:
        return await handle_embedding_error(
            exc, start_time, request_data_obj, request_data_for_logging, db,  # pyright: ignore[reportPossiblyUnboundVariable]
            pricing_service=pricing_service,
            catwalk_name=catwalk_name,
            costing_model=costing_model,
            pricing_override=pricing_override,
        )

    except Exception as exc:
        # Catch-all for unexpected errors
        logger.exception(f"Unexpected error in embeddings: {exc}")
        return await handle_embedding_error(
            exc, start_time, request_data_obj, request_data_for_logging, db,  # pyright: ignore[reportPossiblyUnboundVariable]
            pricing_service=pricing_service,
            catwalk_name=catwalk_name,
            costing_model=costing_model,
            pricing_override=pricing_override,
        )


async def health():
    """Health check endpoint."""
    return {"status": "ok"}


async def v1_model_info(request: Request):
    """List available models in LiteLLM proxy format.

    Returns a JSON object with a top-level 'data' property containing an array
    of model objects with model_name, model_info, and litellm_params fields.
    """
    model_data = []
    
    for model_name, model_config in request.app.state.config.models.items():
        model_config: ModelConfig = model_config
        
        # Build model_info from ModelConfig
        model_info: Dict[str, Any] = {}
        
        # Context window / token limits
        if model_config.context_window is not None:
            model_info['max_input_tokens'] = model_config.context_window
        
        # Pricing override if available
        if model_config.pricing_override:
            if 'cost_per_1m_in' in model_config.pricing_override:
                # Convert from cost per 1M to cost per token
                model_info['input_cost_per_token'] = model_config.pricing_override['cost_per_1m_in'] / 1_000_000
            if 'cost_per_1m_out' in model_config.pricing_override:
                model_info['output_cost_per_token'] = model_config.pricing_override['cost_per_1m_out'] / 1_000_000
        
        # Build litellm_params object
        litellm_params_obj: Dict[str, Any] = {
            'model': model_config.litellm_model
        }
        
        # Include temperature if set
        if model_config.temperature is not None:
            litellm_params_obj['temperature'] = model_config.temperature
        
        # Include custom_llm_provider if set
        if model_config.custom_llm_provider is not None:
            litellm_params_obj['custom_llm_provider'] = model_config.custom_llm_provider
        
        # Include any additional litellm_params from config
        for key, value in model_config.litellm_params.items():
            if value is not None:
                litellm_params_obj[key] = value
        
        # Get provider config for timeout and retries
        provider_config = request.app.state.config.providers.get(model_config.provider_name)
        if provider_config:
            if provider_config.timeout is not None:
                litellm_params_obj['timeout'] = provider_config.timeout
            if provider_config.num_retries is not None:
                litellm_params_obj['num_retries'] = provider_config.num_retries
        
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
    model_data = []
    
    for model_name, model_config in request.app.state.config.models.items():
        model_config: ModelConfig = get_model_for_name(model_name, request)
        entry = {
            "id": model_config.model_name,
            "context_length": model_config.context_window,
            "provider": model_config.provider_name,
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