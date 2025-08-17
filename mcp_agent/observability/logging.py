"""
Structured logging with correlation IDs and JSON formatting.
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.types import FilteringBoundLogger

from ..config import settings

# Context variable for correlation ID
correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def add_correlation_id(logger: FilteringBoundLogger, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Add correlation ID to log events."""
    corr_id = correlation_id.get()
    if corr_id:
        event_dict["correlation_id"] = corr_id
    return event_dict


def add_service_info(logger: FilteringBoundLogger, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Add service information to log events."""
    event_dict["service"] = "mcp-agent"
    event_dict["version"] = "1.0.0"
    event_dict["environment"] = settings.environment
    return event_dict


def sanitize_sensitive_data(logger: FilteringBoundLogger, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Sanitize sensitive data from log events."""
    sensitive_keys = {
        "password", "token", "key", "secret", "auth", "authorization",
        "api_key", "refresh_token", "access_token", "client_secret"
    }

    def sanitize_dict(d: dict[str, Any]) -> dict[str, Any]:
        sanitized = {}
        for k, v in d.items():
            if any(sensitive in k.lower() for sensitive in sensitive_keys):
                sanitized[k] = "***REDACTED***"
            elif isinstance(v, dict):
                sanitized[k] = sanitize_dict(v)
            elif isinstance(v, str) and len(v) > 20 and any(sensitive in k.lower() for sensitive in sensitive_keys):
                sanitized[k] = f"{v[:4]}***{v[-4:]}"
            else:
                sanitized[k] = v
        return sanitized

    return sanitize_dict(event_dict)


def setup_logging() -> None:
    """Setup structured logging with appropriate configuration."""
    # Configure structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        add_correlation_id,
        add_service_info,
        sanitize_sensitive_data,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.extend([
            structlog.dev.ConsoleRenderer(colors=True),
        ])

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level)
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level),
    )

    # Set up file logging if specified
    if settings.log_file:
        file_handler = logging.FileHandler(settings.log_file)
        file_handler.setLevel(getattr(logging, settings.log_level))
        logging.getLogger().addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("docker").setLevel(logging.WARNING)


def get_logger(name: str) -> FilteringBoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def set_correlation_id(corr_id: str | None = None) -> str:
    """Set correlation ID for the current context."""
    if corr_id is None:
        corr_id = str(uuid.uuid4())
    correlation_id.set(corr_id)
    return corr_id


def get_correlation_id() -> str | None:
    """Get the current correlation ID."""
    return correlation_id.get()


class LoggingMiddleware:
    """FastAPI middleware for request/response logging."""

    def __init__(self, app):
        self.app = app
        self.logger = get_logger("middleware.logging")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Set correlation ID for this request
        corr_id = set_correlation_id()

        # Log request
        request_info = {
            "method": scope["method"],
            "path": scope["path"],
            "query_string": scope.get("query_string", b"").decode(),
            "client": scope.get("client"),
            "headers": dict(scope.get("headers", [])),
        }

        self.logger.info("Request started", **request_info)

        # Wrap send to capture response
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                self.logger.info(
                    "Request completed",
                    status_code=message["status"],
                    correlation_id=corr_id,
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)
