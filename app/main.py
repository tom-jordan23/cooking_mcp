"""
Main FastAPI application for the MCP Cooking Lab Notebook system.

This module creates and configures the FastAPI application with all necessary
middleware, routers, error handlers, and startup/shutdown events.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
import uvicorn

from .utils.config import get_settings, validate_environment
from .utils.logging import (
    setup_logging,
    RequestLoggingMiddleware,
    get_logger,
    log_startup_info,
    log_shutdown_info
)
from .routers import health, mcp


# Initialize logging first
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events.

    Handles initialization and cleanup of resources like database
    connections, background tasks, and external service clients.
    """
    # Startup
    logger.info("Starting up MCP Cooking Lab Notebook application")

    try:
        # Validate environment configuration
        validate_environment()

        # Log startup information
        log_startup_info()

        # TODO: Initialize database connection pool
        # TODO: Initialize Redis connection pool
        # TODO: Initialize MCP client connection
        # TODO: Start background tasks (e.g., cleanup jobs)

        logger.info("Application startup completed successfully")

        yield

    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise

    finally:
        # Shutdown
        logger.info("Shutting down application")

        # TODO: Close database connections
        # TODO: Close Redis connections
        # TODO: Close MCP client connections
        # TODO: Stop background tasks
        # TODO: Cleanup temporary files

        log_shutdown_info()
        logger.info("Application shutdown completed")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        FastAPI: Configured application instance
    """
    settings = get_settings()

    # Create FastAPI app with metadata
    app = FastAPI(
        title=settings.app.name,
        description=settings.app.description,
        version=settings.app.version,
        debug=settings.app.debug,
        lifespan=lifespan,
        # Custom OpenAPI configuration
        openapi_url="/api/openapi.json" if not settings.app.is_production else None,
        docs_url="/api/docs" if not settings.app.is_production else None,
        redoc_url="/api/redoc" if not settings.app.is_production else None
    )


    # Configure middleware
    configure_middleware(app, settings)

    # Configure routers
    configure_routers(app, settings)

    # Configure error handlers
    configure_error_handlers(app, settings)

    # Configure OpenAPI
    configure_openapi(app, settings)

    return app


def configure_middleware(app: FastAPI, settings) -> None:
    """
    Configure application middleware.

    Args:
        app: FastAPI application instance
        settings: Application settings
    """
    # Security middleware - Trusted Host (prevents Host header injection)
    if settings.app.is_production:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["*"]  # Configure with actual allowed hosts in production
        )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.auth.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        max_age=600  # Cache preflight responses for 10 minutes
    )

    # Request logging middleware (custom)
    app.add_middleware(RequestLoggingMiddleware)

    # Request size limiting middleware
    @app.middleware("http")
    async def limit_request_size(request: Request, call_next):
        """Limit request size to prevent abuse."""
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > settings.app.max_request_size:
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={
                            "status": "error",
                            "code": "E_REQUEST_SIZE",
                            "message": f"Request size too large. Maximum: {settings.app.max_request_size} bytes"
                        }
                    )
            except ValueError:
                pass

        return await call_next(request)

    # Request timeout middleware
    @app.middleware("http")
    async def timeout_middleware(request: Request, call_next):
        """Apply request timeout to prevent hanging requests."""
        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=settings.app.request_timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Request timeout",
                path=request.url.path,
                method=request.method,
                timeout=settings.app.request_timeout
            )
            return JSONResponse(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                content={
                    "status": "error",
                    "code": "E_TIMEOUT",
                    "message": f"Request timeout after {settings.app.request_timeout} seconds"
                }
            )


def configure_routers(app: FastAPI, settings) -> None:
    """
    Configure application routers.

    Args:
        app: FastAPI application instance
        settings: Application settings
    """
    # Health check endpoints (no auth required)
    app.include_router(health.router)

    # MCP bridge endpoints (auth required)
    app.include_router(mcp.router)

    # Root endpoint
    @app.get("/", include_in_schema=False)
    async def root():
        """Root endpoint providing basic API information."""
        return {
            "name": settings.app.name,
            "version": settings.app.version,
            "environment": settings.app.environment,
            "status": "operational",
            "docs_url": "/api/docs" if not settings.app.is_production else None,
            "health_url": "/health"
        }

    # API info endpoint
    @app.get("/api/info", include_in_schema=False)
    async def api_info():
        """API information endpoint."""
        return {
            "name": settings.app.name,
            "version": settings.app.version,
            "description": settings.app.description,
            "environment": settings.app.environment,
            "endpoints": {
                "health": "/health",
                "mcp": "/mcp",
                "docs": "/api/docs" if not settings.app.is_production else None
            }
        }


def configure_error_handlers(app: FastAPI, settings) -> None:
    """
    Configure global error handlers.

    Args:
        app: FastAPI application instance
        settings: Application settings
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions with structured error responses."""
        logger.warning(
            "HTTP exception",
            status_code=exc.status_code,
            detail=exc.detail,
            path=request.url.path,
            method=request.method
        )

        # If detail is already a dict (from our error responses), use it directly
        if isinstance(exc.detail, dict):
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail
            )

        # Otherwise, wrap it in our standard error format
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "code": f"HTTP_{exc.status_code}",
                "message": str(exc.detail)
            }
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """Handle ValueError exceptions as bad requests."""
        logger.warning(
            "Value error",
            error=str(exc),
            path=request.url.path,
            method=request.method
        )

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": "error",
                "code": "E_SCHEMA",
                "message": str(exc)
            }
        )

    @app.exception_handler(FileNotFoundError)
    async def file_not_found_handler(request: Request, exc: FileNotFoundError):
        """Handle FileNotFoundError exceptions as not found."""
        logger.warning(
            "File not found",
            error=str(exc),
            path=request.url.path,
            method=request.method
        )

        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "status": "error",
                "code": "E_NOT_FOUND",
                "message": "Resource not found"
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions."""
        logger.error(
            "Unexpected error",
            error=str(exc),
            error_type=type(exc).__name__,
            path=request.url.path,
            method=request.method,
            exc_info=True
        )

        # Don't expose internal error details in production
        if settings.app.is_production:
            message = "An internal error occurred"
        else:
            message = str(exc)

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "code": "E_INTERNAL",
                "message": message
            }
        )


def configure_openapi(app: FastAPI, settings) -> None:
    """
    Configure OpenAPI schema and documentation.

    Args:
        app: FastAPI application instance
        settings: Application settings
    """

    def custom_openapi():
        """Generate custom OpenAPI schema."""
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title=settings.app.name,
            version=settings.app.version,
            description=settings.app.description,
            routes=app.routes,
        )

        # Add custom info
        openapi_schema["info"]["contact"] = {
            "name": "MCP Cooking Lab Notebook API",
            "url": "https://github.com/your-repo/cooking_mcp"
        }

        # Add security schemes
        openapi_schema["components"]["securitySchemes"] = {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Bearer token authentication"
            },
            "SlackSignature": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Slack-Signature",
                "description": "Slack request signature verification"
            }
        }

        # Add global security requirement
        openapi_schema["security"] = [
            {"BearerAuth": []}
        ]

        # Add server information
        openapi_schema["servers"] = [
            {
                "url": f"http://localhost:{settings.app.port}",
                "description": "Local development server"
            }
        ]

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi


# Create the application instance
app = create_app()


def run_server():
    """
    Run the development server.

    This function is used for development and testing.
    In production, use a proper ASGI server like Gunicorn + Uvicorn.
    """
    settings = get_settings()

    # Configure uvicorn
    config = uvicorn.Config(
        app=app,
        host=settings.app.host,
        port=settings.app.port,
        log_level=settings.logging.level.lower(),
        reload=settings.app.is_development,
        access_log=False,  # We handle logging with our middleware
        server_header=False,  # Don't expose server info
        date_header=False  # Don't include date header
    )

    server = uvicorn.Server(config)

    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise


if __name__ == "__main__":
    # Run the server when script is executed directly
    run_server()