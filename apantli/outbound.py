
import json
import time
from apantli.database import Database
from apantli.llm import infer_provider_from_model
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from litellm.exceptions import (
    RateLimitError,
    InternalServerError,
    ServiceUnavailableError,
    APIConnectionError,
    Timeout,
    BadRequestError,
)
from apantli.errors import build_error_response, get_error_details, extract_error_message
from apantli.log_config import logger
from apantli.model_resolution import calculate_cost
from apantli.types import ChatFunctionCallArgs

async def execute_streaming_request(
    response,
    model: str,
    request_data: ChatFunctionCallArgs,
    request_data_for_logging: ChatFunctionCallArgs,
    start_time: float,
    db: Database,
    request: Request
) -> StreamingResponse:
    """Execute and stream LiteLLM response with logging.

    Args:
        response: LiteLLM streaming response
        model: Original model name from request
        request_data: Request data dict
        request_data_for_logging: Copy of request data for logging
        start_time: Request start time
        db: Database instance
        request: FastAPI Request object for disconnect detection

    Returns:
        StreamingResponse with SSE format
    """
    # Extract provider before creating generator (from remapped litellm model name)
    litellm_model = request_data.model
    provider = infer_provider_from_model(litellm_model)

    # Collect chunks for logging
    full_response = {
        'id': None,
        'model': request_data.model,  # Use full LiteLLM model name for cost calculation
        'choices': [{'message': {'role': 'assistant', 'content': ''}, 'finish_reason': None}],
        'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
    }
    socket_error_logged = False

    async def generate():
        nonlocal full_response, socket_error_logged
        stream_error = None

        try:
            for chunk in response:
                # Check if client has disconnected before processing
                if await request.is_disconnected():
                    if not socket_error_logged:
                        logger.info("Client disconnected during streaming")
                        socket_error_logged = True
                    return

                chunk_dict = chunk.model_dump() if hasattr(chunk, 'model_dump') else dict(chunk)

                # Accumulate content
                if 'choices' in chunk_dict and len(chunk_dict['choices']) > 0:
                    delta = chunk_dict['choices'][0].get('delta', {})
                    if 'content' in delta and delta['content'] is not None:
                        full_response['choices'][0]['message']['content'] += delta['content']
                    if 'finish_reason' in chunk_dict['choices'][0]:
                        full_response['choices'][0]['finish_reason'] = chunk_dict['choices'][0]['finish_reason']

                # Capture ID and usage
                if 'id' in chunk_dict and chunk_dict['id']:
                    full_response['id'] = chunk_dict['id']
                if 'usage' in chunk_dict:
                    full_response['usage'] = chunk_dict['usage']

                yield f"data: {json.dumps(chunk_dict)}\n\n"

        except (BrokenPipeError, ConnectionError, ConnectionResetError) as exc:
            # Client disconnected - stop streaming
            if not socket_error_logged:
                logger.info(f"Client disconnected during streaming: {type(exc).__name__}")
                socket_error_logged = True
            return

        except (RateLimitError, InternalServerError, ServiceUnavailableError, Timeout, APIConnectionError, BadRequestError) as exc:
            # Provider error during streaming - send error event with clean message
            clean_msg = extract_error_message(exc)
            stream_error = f"{type(exc).__name__}: {clean_msg}"
            error_event = build_error_response("stream_error", clean_msg, type(exc).__name__.lower())
            # Only try to send error if client is still connected
            if not await request.is_disconnected():
                yield f"data: {json.dumps(error_event)}\n\n"

        except Exception as exc:
            # Unexpected error during streaming
            clean_msg = extract_error_message(exc)
            stream_error = f"UnexpectedStreamError: {clean_msg}"
            error_event = build_error_response("stream_error", clean_msg, "internal_error")
            # Only try to send error if client is still connected
            if not await request.is_disconnected():
                yield f"data: {json.dumps(error_event)}\n\n"

        finally:
            # Send [DONE] only if client is still connected
            if not await request.is_disconnected():
                yield "data: [DONE]\n\n"

            # Log to database
            try:
                duration_ms = int((time.time() - start_time) * 1000)
                await db.log_request(model, provider, full_response, duration_ms, request_data_for_logging, error=stream_error)

                # Log completion
                if stream_error:
                    logger.info(f"✗ LLM Response: {model} ({provider}) | {duration_ms}ms | Error: {stream_error}")
                else:
                    usage = full_response.get('usage', {})
                    prompt_tokens = usage.get('prompt_tokens', 0)
                    completion_tokens = usage.get('completion_tokens', 0)
                    total_tokens = usage.get('total_tokens', 0)
                    cost = calculate_cost(full_response)
                    logger.info(f"✓ LLM Response: {model} ({provider}) | {duration_ms}ms | {prompt_tokens}→{completion_tokens} tokens ({total_tokens} total) | ${cost:.4f} [streaming]")
            except Exception as exc:
                logger.error(f"Error logging streaming request to database: {exc}")

    return StreamingResponse(generate(), media_type="text/event-stream")

async def execute_request(
    response,
    model: str,
    request_data: ChatFunctionCallArgs,
    request_data_for_logging: ChatFunctionCallArgs,
    start_time: float,
    db: Database
) -> JSONResponse:
    """Execute non-streaming LiteLLM request with logging.

    Args:
        response: LiteLLM response object
        model: Original model name from request
        request_data: Request data dict
        request_data_for_logging: Copy of request data for logging
        start_time: Request start time
        db: Database instance

    Returns:
        JSONResponse with completion data
    """
    # Convert to dict for logging and response
    if hasattr(response, 'model_dump'):
        response_dict = response.model_dump()
    elif hasattr(response, 'dict'):
        response_dict = response.dict()
    else:
        response_dict = json.loads(response.json())

    # Extract provider from request_data (which has the remapped litellm model name)
    litellm_model = request_data.get('model', '')
    provider = infer_provider_from_model(litellm_model)

    # Fallback: try response metadata if still unknown
    if provider == 'unknown' and hasattr(response, '_hidden_params'):
        provider = response._hidden_params.get('custom_llm_provider', 'unknown')

    # Calculate duration
    duration_ms = int((time.time() - start_time) * 1000)

    # Log to database
    await db.log_request(model, provider, response_dict, duration_ms, request_data_for_logging)

    # Log completion
    usage = response_dict.get('usage', {})
    prompt_tokens = usage.get('prompt_tokens', 0)
    completion_tokens = usage.get('completion_tokens', 0)
    total_tokens = usage.get('total_tokens', 0)
    cost = calculate_cost(response)
    logger.info(f"✓ LLM Response: {model} ({provider}) | {duration_ms}ms | {prompt_tokens}→{completion_tokens} tokens ({total_tokens} total) | ${cost:.4f}")

    return JSONResponse(content=response_dict)

async def handle_llm_error(e: Exception, start_time: float, request_data: ChatFunctionCallArgs,
                          request_data_for_logging: ChatFunctionCallArgs, db: Database) -> JSONResponse:
    """Handle LLM API errors with consistent logging and response formatting."""
    duration_ms = int((time.time() - start_time) * 1000)
    model_name = request_data.model
    provider = infer_provider_from_model(model_name)

    # Get error details from error mapping
    status_code, error_type, error_code = get_error_details(e)

    # Extract clean error message for logging and response
    clean_error_msg = extract_error_message(e)

    # Special handling for provider errors
    error_name = type(e).__name__
    if isinstance(e, (InternalServerError, ServiceUnavailableError)):
        error_name = "ProviderError"

    # Log to database with clean error message
    await db.log_request(
        model_name,
        provider,
        None,
        duration_ms,
        request_data_for_logging,
        error=f"{error_name}: {clean_error_msg}"
    )

    # Console log with clean error message
    logger.info(f"✗ LLM Response: {model_name} ({provider}) | {duration_ms}ms | Error: {error_name}: {clean_error_msg}")

    # Build and return error response with clean message
    error_response = build_error_response(error_type, clean_error_msg, error_code)
    return JSONResponse(content=error_response, status_code=status_code)
