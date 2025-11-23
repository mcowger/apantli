"""""
Authentication and authorization decorators.
"""""

import os
from functools import wraps
from typing import Callable, Any

from fastapi import HTTPException, status, Request


# Initially, no token is required. This can be updated by a call to `set_required_token`.
API_TOKEN_REQUIRED = os.environ.get("API_TOKEN_REQUIRED", None)


def is_authentication_required() -> bool:
    """""
    Check if authentication is required based on the presence of API_TOKEN_REQUIRED.
    """""
    return API_TOKEN_REQUIRED is not None


def get_current_user(request: Request) -> str:
    """""
    Validate the bearer token and return the user if valid.
    """""
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

    if token != API_TOKEN_REQUIRED:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return "authenticated"


def authenticated_route(func: Callable) -> Callable:
    """""
    Decorator to protect routes that require authentication.
    """""

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
