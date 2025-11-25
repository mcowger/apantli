#!/usr/bin/env python3
"""
Lightweight LLM proxy with SQLite cost tracking.
Compatible with OpenAI API format, uses LiteLLM SDK for provider routing.
"""

import os

import time
import argparse
import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import litellm

from incoming import chat_completions, health, models, v1_models_info, v1_models_openrouter
import uvicorn
from dotenv import load_dotenv
# Import from local modules
from apantli.database import Database
from apantli.config import LOG_INDENT, Config
from apantli.errors import build_error_response
from stats import stats, stats_daily, stats_date_range, stats_hourly, requests
from apantli.ui import dashboard, compare_page

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and load config on startup."""
    # Get config values from app.state if set by main(), otherwise use defaults
    config_path = getattr(app.state, 'config_path', 'config.yaml')
    db_path = getattr(app.state, 'db_path', 'requests.db')
    app.state.timeout = getattr(app.state, 'timeout', 120)
    app.state.retries = getattr(app.state, 'retries', 3)

    # Load configuration
    config = Config(config_path)
    app.state.config = config
    app.state.model_map = config.get_model_map({
        'timeout': app.state.timeout,
        'num_retries': app.state.retries
    })

    # Initialize database
    db = Database(db_path)
    await db.init()
    app.state.db = db
    yield
app = FastAPI(title="LLM Proxy", lifespan=lifespan)

# Mount static files directory
app.mount("/static", StaticFiles(directory="apantli/static"), name="static")

# Add CORS middleware - allow all origins by using regex
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Convert FastAPI HTTPException to OpenAI-compatible error format."""
    error_response = build_error_response(
        "invalid_request_error",
        exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        f"http_{exc.status_code}"
    )
    return JSONResponse(content=error_response, status_code=exc.status_code)

# Register UI routes
app.add_route("/ui", dashboard, methods=["GET"])
app.add_route("/compare", compare_page, methods=["GET"])

app.add_route("/v1/models", v1_models_openrouter, methods=["GET"])
app.add_route("/v1/model/info", v1_models_info, methods=["GET"])
app.add_route("/models", models, methods=["GET"])
app.add_route("/health", health, methods=["GET"])
app.add_route("/stats", stats, methods=["GET"])
app.add_route("/errors", stats, methods=["DELETE"])
app.add_route("/stats/daily", stats_daily, methods=["GET"])
app.add_route("/stats/hourly", stats_hourly, methods=["GET"])
app.add_route("/stats/hourly", stats_hourly, methods=["GET"])
app.add_route("/stats/date-range", stats_date_range, methods=["GET"])
app.add_route("/requests", requests, methods=["GET"])
app.add_route("/v1/chat/completions", chat_completions, methods=["POST"])


def main():
    """Entry point for the proxy server."""
    parser = argparse.ArgumentParser(
        description="Apantli - Lightweight LLM proxy with SQLite cost tracking"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=4000,
        help="Port to bind to (default: 4000)"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)"
    )
    parser.add_argument(
        "--db",
        default="requests.db",
        help="Path to SQLite database (default: requests.db)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Default request timeout in seconds (default: 120)"
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Default number of retry attempts (default: 3)"
    )
    parser.add_argument(
        "--env",
        default=None,
        help="Path to .env file (default: None, loads from current directory)"
    )


    # Load environment variables from specified .env file


    args = parser.parse_args()
    load_dotenv(dotenv_path=args.env)

    # Suppress LiteLLM's verbose logging and feedback messages
    os.environ['LITELLM_LOG'] = 'ERROR'
    litellm.suppress_debug_info = True
    litellm.set_verbose = False # pyright: ignore[reportPrivateImportUsage]

    # Store config values in app.state for lifespan to access
    app.state.config_path = args.config
    app.state.db_path = args.db
    app.state.timeout = args.timeout
    app.state.retries = args.retries

    # Configure logging format with timestamps
    log_config = uvicorn.config.LOGGING_CONFIG # pyright: ignore[reportAttributeAccessIssue]
    # Update default formatter (for startup/info logs)
    log_config["formatters"]["default"]["fmt"] = '%(asctime)s %(levelprefix)s %(message)s'
    log_config["formatters"]["default"]["datefmt"] = '%Y-%m-%d %H:%M:%S'
    # Update access formatter (for HTTP request logs)
    log_config["formatters"]["access"]["fmt"] = '%(asctime)s %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s'
    log_config["formatters"]["access"]["datefmt"] = '%Y-%m-%d %H:%M:%S'

    # Add filter to suppress noisy dashboard endpoints
    class DashboardFilter(logging.Filter):
        """Filter out noisy dashboard GET requests from access logs."""
        def filter(self, record):
            # Suppress logs for dashboard polling endpoints
            # Check the formatted message since uvicorn log records vary
            message = record.getMessage() if hasattr(record, 'getMessage') else str(record.msg)

            # Filter out all dashboard-related GET requests
            noisy_patterns = [
                'GET / ',  # Dashboard homepage
                'GET /stats?',
                'GET /stats/daily?',
                'GET /stats/date-range',
                'GET /static/',
                'GET /requests',  # Requests endpoint
                'GET /models',  # Models endpoint
                'GET /errors',  # Errors endpoint
                'GET /health',  # Health check
            ]
            return not any(pattern in message for pattern in noisy_patterns)

    # Apply filter to access logger
    logging.getLogger("uvicorn.access").addFilter(DashboardFilter())

    # Print available URLs
    print(f"\n🚀 Apantli server starting...")

    print(f"   Server at http://{args.host}:{args.port}/\n")

    if args.reload:
        # Reload mode requires import string
        uvicorn.run(
            "apantli.server:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_config=log_config
        )
    else:
        # Production mode can use app object directly
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_config=log_config
        )


if __name__ == "__main__":
    main()
