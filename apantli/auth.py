"""
Authentication and authorization decorators.
"""

import base64
import os
import secrets
from functools import wraps
from typing import Callable, Any

from fastapi import HTTPException, status, Request
from fastapi.responses import JSONResponse


# UI Basic Auth fixed username
UI_USERNAME = "admin"


def _get_api_token_required() -> str | None:
    """Get the API token from environment variable."""
    return os.environ.get("API_TOKEN_REQUIRED", None)


def _get_ui_password() -> str | None:
    """Get the UI password from environment variable."""
    return os.environ.get("UI_PASSWORD", None)


def is_authentication_required() -> bool:
    """
    Check if authentication is required based on the presence of API_TOKEN_REQUIRED.
    """
    return _get_api_token_required() is not None


def is_ui_authentication_required() -> bool:
    """
    Check if UI authentication is required based on the presence of UI_PASSWORD.
    """
    return _get_ui_password() is not None


def get_current_user(request: Request) -> str:
    """
    Validate the bearer token and return the user if valid.
    """
    if not is_authentication_required():
        # If no token is set, authentication is not required.
        return "authenticated"

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        scheme, token = auth_header.split()
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication scheme",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token != _get_api_token_required():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return "authenticated"


def _basic_auth_response(detail: str) -> JSONResponse:
    """Create a 401 response with WWW-Authenticate header for Basic auth."""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error": {"message": detail, "type": "invalid_request_error", "code": "http_401"}},
        headers={"WWW-Authenticate": 'Basic realm="apantli"'},
    )


def get_current_ui_user(request: Request) -> str | JSONResponse:
    """
    Validate HTTP Basic Auth credentials and return the username if valid,
    or a JSONResponse with 401 status if authentication fails.
    """
    if not is_ui_authentication_required():
        # If no password is set, authentication is not required.
        return "authenticated"

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return _basic_auth_response("Authorization header is missing")

    try:
        scheme, credentials = auth_header.split()
        if scheme.lower() != "basic":
            return _basic_auth_response("Invalid authentication scheme")
    except ValueError:
        return _basic_auth_response("Invalid authorization header format")

    try:
        decoded = base64.b64decode(credentials).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return _basic_auth_response("Invalid credentials format")

    # Use secrets.compare_digest for timing-safe comparison
    ui_password = _get_ui_password()
    if not (
        secrets.compare_digest(username, UI_USERNAME)
        and ui_password is not None
        and secrets.compare_digest(password, ui_password)
    ):
        return _basic_auth_response("Invalid username or password")

    return username


def authenticated_route(func: Callable) -> Callable:
    """
    Decorator to protect routes that require authentication.
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if is_authentication_required():
            # If authentication is required, `get_current_user` will raise an exception if the user is not authenticated.
            request = kwargs.get("request")
            if not request:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Request object not found in endpoint",
                )
            get_current_user(request)

        return await func(*args, **kwargs)

    return wrapper


def authenticated_ui_route(func: Callable) -> Callable:
    """
    Decorator to protect UI routes that require HTTP Basic authentication.
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if is_ui_authentication_required():
            # If UI authentication is required, `get_current_ui_user` will return a response if the user is not authenticated.
            request = kwargs.get("request")
            if not request:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Request object not found in endpoint",
                )
            result = get_current_ui_user(request)
            if isinstance(result, JSONResponse):
                return result

        return await func(*args, **kwargs)

    return wrapper
