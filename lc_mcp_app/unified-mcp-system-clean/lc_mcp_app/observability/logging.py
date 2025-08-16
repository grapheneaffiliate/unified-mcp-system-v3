"""
Structured logging configuration with correlation IDs.
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

import structlog
from structlog.types import FilteringBoundLogger

from ..config import settings

# Context variable for correlation ID
correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def add_correlation_id(logger: FilteringBoundLogger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add correlation ID to log events."""
    corr_id = correlation_id.get()
    if corr_id:
        event_dict["correlation_id"] = corr_id
    return event_dict


def add_service_info(logger: FilteringBoundLogger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add service information to log events."""
    event_dict["service"] = "lc-mcp-app"
    event_dict["version"] = "0.1.0"
    event_dict["environment"] = settings.environment
    return event_dict


def sanitize_sensitive_data(logger: FilteringBoundLogger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize sensitive data from log events."""
    sensitive_keys = {
        "password", "token", "key", "secret", "auth", "authorization",
        "api_key", "openai_api_key", "mcp_password"
    }
    
    def sanitize_dict(d: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = {}
        for k, v in d.items():
            if any(sensitive in k.lower() for sensitive in sensitive_keys):
                if isinstance(v, str) and len(v) > 8:
                    sanitized[k] = f"{v[:4]}***{v[-4:]}"
                else:
                    sanitized[k] = "***REDACTED***"
            elif isinstance(v, dict):
                sanitized[k] = sanitize_dict(v)
            else:
                sanitized[k] = v
        return sanitized
    
    return sanitize_dict(event_dict)


def configure_logging(level: str = "info") -> None:
    """Configure structured logging with appropriate settings."""
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
            getattr(logging, level.upper())
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)


def get_logger(name: str) -> FilteringBoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def set_correlation_id(corr_id: Optional[str] = None) -> str:
    """Set correlation ID for the current context."""
    if corr_id is None:
        corr_id = str(uuid.uuid4())
    correlation_id.set(corr_id)
    return corr_id


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID."""
    return correlation_id.get()
