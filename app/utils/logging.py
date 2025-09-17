"""
Structured logging configuration for the MCP Cooking Lab Notebook system.

Implements JSON logging for production, console logging for development,
request correlation IDs, security event logging, and performance metrics.
"""

import logging
import sys
import json
import time
import uuid
import contextvars
from pathlib import Path
from typing import Any, Dict, Optional, Union, Literal
from datetime import datetime, timezone
import traceback

from loguru import logger as loguru_logger
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings


# Context variable for correlation ID tracking
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    'correlation_id', default=None
)


class CorrelationIdFilter:
    """Filter to add correlation ID to log records."""

    def __call__(self, record: Dict[str, Any]) -> bool:
        """Add correlation ID to log record."""
        correlation_id = correlation_id_var.get(None)
        if correlation_id:
            record["extra"]["correlation_id"] = correlation_id
        return True


class SecurityLogFilter:
    """Filter for security-related log events."""

    def __call__(self, record: Dict[str, Any]) -> bool:
        """Filter security events based on log record."""
        extra = record.get("extra", {})
        return extra.get("security_event", False)


class StructuredFormatter:
    """Custom formatter for structured JSON logging."""

    def __init__(self, include_traceback: bool = True):
        self.include_traceback = include_traceback

    def format(self, record: Dict[str, Any]) -> str:
        """Format log record as JSON."""
        # Base log structure
        log_entry = {
            "timestamp": record["time"].isoformat(),
            "level": record["level"].name,
            "logger": record["name"],
            "message": record["message"],
            "module": record.get("module"),
            "function": record.get("function"),
            "line": record.get("line"),
        }

        # Add extra fields
        extra = record.get("extra", {})
        if extra:
            log_entry.update(extra)

        # Add exception information
        exception = record.get("exception")
        if exception and self.include_traceback:
            log_entry["exception"] = {
                "type": exception.type.__name__ if exception.type else None,
                "value": str(exception.value) if exception.value else None,
                "traceback": traceback.format_exception(
                    exception.type, exception.value, exception.traceback
                ) if exception.traceback else None
            }

        return json.dumps(log_entry, default=str, ensure_ascii=False)


def setup_logging() -> None:
    """Configure application logging based on settings."""
    settings = get_settings()

    # Remove default loguru handler
    loguru_logger.remove()

    # Configure based on format preference
    if settings.logging.format == "json":
        # Production JSON logging
        loguru_logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message} | {extra}",
            level=settings.logging.level,
            serialize=True,  # JSON output
            filter=CorrelationIdFilter(),
            backtrace=True,
            diagnose=True
        )
    else:
        # Development console logging
        loguru_logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                   "<level>{message}</level> | "
                   "{extra}",
            level=settings.logging.level,
            colorize=True,
            filter=CorrelationIdFilter(),
            backtrace=True,
            diagnose=True
        )

    # Add file logging if enabled
    if settings.logging.file_enabled and settings.logging.file_path:
        loguru_logger.add(
            settings.logging.file_path,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message} | {extra}",
            level=settings.logging.level,
            rotation=settings.logging.file_max_size,
            retention=settings.logging.file_backup_count,
            serialize=True,  # Always JSON for file logs
            filter=CorrelationIdFilter(),
            backtrace=True,
            diagnose=True
        )

    # Security logging if enabled
    if settings.logging.security_log_enabled:
        # Separate file for security events
        security_log_path = Path("logs/security.log")
        security_log_path.parent.mkdir(exist_ok=True)

        loguru_logger.add(
            security_log_path,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | SECURITY | {message} | {extra}",
            level="INFO",
            rotation="10 MB",
            retention="30 days",
            serialize=True,
            filter=SecurityLogFilter(),
            backtrace=True,
            diagnose=True
        )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests with correlation IDs and metrics."""

    async def dispatch(self, request: Request, call_next):
        """Process request with logging and timing."""
        # Generate correlation ID
        correlation_id = str(uuid.uuid4())
        correlation_id_var.set(correlation_id)

        # Add correlation ID to request headers for downstream services
        request.state.correlation_id = correlation_id

        # Start timing
        start_time = time.time()

        # Log request start
        await self._log_request_start(request, correlation_id)

        # Process request
        try:
            response = await call_next(request)

            # Calculate processing time
            process_time = time.time() - start_time

            # Add timing header
            response.headers["X-Process-Time"] = str(process_time)
            response.headers["X-Correlation-ID"] = correlation_id

            # Log successful response
            await self._log_request_end(request, response, process_time, correlation_id)

            return response

        except Exception as e:
            # Calculate processing time for error
            process_time = time.time() - start_time

            # Log error
            await self._log_request_error(request, e, process_time, correlation_id)

            # Re-raise exception
            raise

    async def _log_request_start(self, request: Request, correlation_id: str):
        """Log request start with details."""
        # Extract client info
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        # Get user info if available
        user_id = getattr(request.state, "user_id", None)

        loguru_logger.info(
            "Request started",
            method=request.method,
            url=str(request.url),
            path=request.url.path,
            query_params=dict(request.query_params),
            client_ip=client_ip,
            user_agent=user_agent,
            user_id=user_id,
            correlation_id=correlation_id,
            request_id=correlation_id,
            event_type="request_start"
        )

    async def _log_request_end(
        self,
        request: Request,
        response: Response,
        process_time: float,
        correlation_id: str
    ):
        """Log successful request completion."""
        # Extract user info
        user_id = getattr(request.state, "user_id", None)

        loguru_logger.info(
            "Request completed",
            method=request.method,
            url=str(request.url),
            path=request.url.path,
            status_code=response.status_code,
            process_time_ms=round(process_time * 1000, 2),
            user_id=user_id,
            correlation_id=correlation_id,
            request_id=correlation_id,
            event_type="request_end"
        )

    async def _log_request_error(
        self,
        request: Request,
        error: Exception,
        process_time: float,
        correlation_id: str
    ):
        """Log request error."""
        # Extract user info
        user_id = getattr(request.state, "user_id", None)

        loguru_logger.error(
            "Request failed",
            method=request.method,
            url=str(request.url),
            path=request.url.path,
            error_type=type(error).__name__,
            error_message=str(error),
            process_time_ms=round(process_time * 1000, 2),
            user_id=user_id,
            correlation_id=correlation_id,
            request_id=correlation_id,
            event_type="request_error"
        )


class SecurityLogger:
    """Specialized logger for security events."""

    @staticmethod
    def log_authentication_attempt(
        user_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        success: bool = False,
        method: str = "bearer_token",
        details: Optional[Dict[str, Any]] = None
    ):
        """Log authentication attempt."""
        correlation_id = correlation_id_var.get("unknown")

        loguru_logger.info(
            "Authentication attempt",
            user_id=user_id,
            source_ip=source_ip,
            success=success,
            auth_method=method,
            details=details or {},
            correlation_id=correlation_id,
            security_event=True,
            event_type="auth_attempt"
        )

    @staticmethod
    def log_authorization_failure(
        user_id: Optional[str] = None,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        source_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log authorization failure."""
        correlation_id = correlation_id_var.get("unknown")

        loguru_logger.warning(
            "Authorization failure",
            user_id=user_id,
            resource=resource,
            action=action,
            source_ip=source_ip,
            details=details or {},
            correlation_id=correlation_id,
            security_event=True,
            event_type="authz_failure"
        )

    @staticmethod
    def log_rate_limit_exceeded(
        user_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        endpoint: Optional[str] = None,
        limit: Optional[int] = None,
        window: Optional[int] = None
    ):
        """Log rate limit exceeded event."""
        correlation_id = correlation_id_var.get("unknown")

        loguru_logger.warning(
            "Rate limit exceeded",
            user_id=user_id,
            source_ip=source_ip,
            endpoint=endpoint,
            limit=limit,
            window_seconds=window,
            correlation_id=correlation_id,
            security_event=True,
            event_type="rate_limit_exceeded"
        )

    @staticmethod
    def log_suspicious_activity(
        event_type: str,
        user_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: Literal["low", "medium", "high", "critical"] = "medium"
    ):
        """Log suspicious activity."""
        correlation_id = correlation_id_var.get("unknown")

        loguru_logger.warning(
            f"Suspicious activity: {event_type}",
            user_id=user_id,
            source_ip=source_ip,
            severity=severity,
            details=details or {},
            correlation_id=correlation_id,
            security_event=True,
            event_type="suspicious_activity"
        )


class PerformanceLogger:
    """Logger for performance metrics and monitoring."""

    @staticmethod
    def log_database_operation(
        operation: str,
        table: Optional[str] = None,
        duration_ms: Optional[float] = None,
        affected_rows: Optional[int] = None,
        query_type: Optional[str] = None
    ):
        """Log database operation metrics."""
        correlation_id = correlation_id_var.get("unknown")

        loguru_logger.info(
            "Database operation",
            operation=operation,
            table=table,
            duration_ms=duration_ms,
            affected_rows=affected_rows,
            query_type=query_type,
            correlation_id=correlation_id,
            event_type="db_operation"
        )

    @staticmethod
    def log_external_api_call(
        service: str,
        endpoint: str,
        method: str,
        status_code: Optional[int] = None,
        duration_ms: Optional[float] = None,
        success: bool = True
    ):
        """Log external API call metrics."""
        correlation_id = correlation_id_var.get("unknown")

        loguru_logger.info(
            "External API call",
            service=service,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
            success=success,
            correlation_id=correlation_id,
            event_type="external_api_call"
        )

    @staticmethod
    def log_git_operation(
        operation: str,
        repo_path: Optional[str] = None,
        commit_sha: Optional[str] = None,
        duration_ms: Optional[float] = None,
        success: bool = True,
        error: Optional[str] = None
    ):
        """Log Git operation metrics."""
        correlation_id = correlation_id_var.get("unknown")

        loguru_logger.info(
            "Git operation",
            operation=operation,
            repo_path=repo_path,
            commit_sha=commit_sha,
            duration_ms=duration_ms,
            success=success,
            error=error,
            correlation_id=correlation_id,
            event_type="git_operation"
        )


def get_logger(name: str = None) -> Any:
    """Get configured logger instance."""
    if name:
        # Create a bound logger with the module name
        return loguru_logger.bind(name=name)
    return loguru_logger


def get_correlation_id() -> Optional[str]:
    """Get current request correlation ID."""
    return correlation_id_var.get(None)


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID for current context."""
    correlation_id_var.set(correlation_id)


def log_startup_info():
    """Log application startup information."""
    settings = get_settings()

    loguru_logger.info(
        "Application starting",
        app_name=settings.app.name,
        version=settings.app.version,
        environment=settings.app.environment,
        debug=settings.app.debug,
        host=settings.app.host,
        port=settings.app.port,
        database_url=settings.get_database_url(hide_password=True),
        redis_url=settings.get_redis_url(hide_password=True),
        git_repo=str(settings.git.repo_root),
        log_level=settings.logging.level,
        log_format=settings.logging.format,
        event_type="app_startup"
    )


def log_shutdown_info():
    """Log application shutdown information."""
    loguru_logger.info(
        "Application shutting down",
        event_type="app_shutdown"
    )


# Convenience exports
security_logger = SecurityLogger()
performance_logger = PerformanceLogger()

__all__ = [
    "setup_logging",
    "RequestLoggingMiddleware",
    "SecurityLogger",
    "PerformanceLogger",
    "get_logger",
    "get_correlation_id",
    "set_correlation_id",
    "log_startup_info",
    "log_shutdown_info",
    "security_logger",
    "performance_logger"
]