#!/usr/bin/env python3
"""
Lightweight LLM proxy with SQLite cost tracking.
Compatible with OpenAI API format, uses LiteLLM SDK for provider routing.
"""

import os
import argparse
from apantli.log_config import logger
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from typing import Optional
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import litellm
import uvicorn
from dotenv import load_dotenv
# Import from local modules
from apantli.database import Database
from apantli.config import Config
from apantli.errors import build_error_response
from apantli.stats import stats, stats_daily, stats_date_range, stats_hourly, requests, clear_errors
from apantli.ui import dashboard, compare_page
from apantli.incoming import chat_completions, health, v1_models_openrouter #,v1_models_info

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and load config on startup."""
    # Get config values from app.state if set by main(), otherwise use defaults
    config_path = getattr(app.state, 'config_path', 'config.jsonc')
    db_path = getattr(app.state, 'db_path', 'requests.db')
    app.state.timeout = getattr(app.state, 'timeout', 120)
    app.state.retries = getattr(app.state, 'retries', 3)

    # Load configuration
    config = Config(config_path)
    app.state.config = config

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

@app.get("/v1/models")
async def _(request: Request):
    return await v1_models_openrouter(request)

# @app.get("/v1/model/info")
# async def _(request: Request):
#     return await v1_models_info(request)

@app.get("/health")
async def _():
    return await health()

@app.get("/stats")
async def _(request: Request, hours: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, timezone_offset: Optional[int] = None):
    return await stats(request, hours, start_date, end_date, timezone_offset)

@app.delete("/errors")
async def _(request: Request):
    return await clear_errors(request)

@app.get("/stats/daily")
async def _(request: Request, start_date: Optional[str] = None, end_date: Optional[str] = None, timezone_offset: Optional[int] = None):
    return await stats_daily(request, start_date, end_date, timezone_offset)

@app.get("/stats/hourly")
async def _(request: Request, date: str = None, timezone_offset: Optional[int] = None): # pyright: ignore[reportArgumentType]
    return await stats_hourly(request, date, timezone_offset)

@app.get("/stats/date-range")
async def _(request: Request):
    return await stats_date_range(request)

@app.get("/requests")
async def _(request: Request, hours: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, timezone_offset: Optional[int] = None, offset: int = 0, limit: int = 50, provider: Optional[str] = None, model: Optional[str] = None, min_cost: Optional[float] = None, max_cost: Optional[float] = None, search: Optional[str] = None):
    return await requests(request, hours, start_date, end_date, timezone_offset, offset, limit, provider, model, min_cost, max_cost, search)

@app.post("/v1/chat/completions")
async def _(request: Request):
    return await chat_completions(request)


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
        default="config.jsonc",
        help="Path to config file (default: config.jsonc)"
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

    
    # Print available URLs
    logger.info(f"🚀 Apantli server starting...")
    logger.info(f"Server at http://{args.host}:{args.port}/ui\n")

    if args.reload:
        # Reload mode requires import string
        uvicorn.run(
            "apantli.server:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    else:
        # Production mode can use app object directly
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
        )


if __name__ == "__main__":
    main()
