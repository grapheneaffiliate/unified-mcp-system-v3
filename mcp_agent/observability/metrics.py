"""
Prometheus metrics for monitoring and observability.
"""

import time
from collections.abc import Callable
from typing import Any, TypeVar

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    Info,
    generate_latest,
)
from prometheus_client.core import CollectorRegistry

from ..config import settings

F = TypeVar('F', bound=Callable[..., Any])

# Global registry for metrics
registry = CollectorRegistry()

# Application info
app_info = Info(
    "mcp_agent_info",
    "Information about the MCP Agent application",
    registry=registry
)

# Request metrics
request_count = Counter(
    "mcp_agent_requests_total",
    "Total number of requests",
    ["method", "endpoint", "status_code"],
    registry=registry
)

request_duration = Histogram(
    "mcp_agent_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"],
    registry=registry
)

# Tool execution metrics
tool_execution_count = Counter(
    "mcp_agent_tool_executions_total",
    "Total number of tool executions",
    ["tool_name", "status"],
    registry=registry
)

tool_execution_duration = Histogram(
    "mcp_agent_tool_execution_duration_seconds",
    "Tool execution duration in seconds",
    ["tool_name"],
    registry=registry
)

# Error metrics
error_count = Counter(
    "mcp_agent_errors_total",
    "Total number of errors",
    ["error_type", "component"],
    registry=registry
)

# Database metrics
database_operations = Counter(
    "mcp_agent_database_operations_total",
    "Total number of database operations",
    ["operation", "table"],
    registry=registry
)

database_operation_duration = Histogram(
    "mcp_agent_database_operation_duration_seconds",
    "Database operation duration in seconds",
    ["operation", "table"],
    registry=registry
)

# External service metrics
external_service_requests = Counter(
    "mcp_agent_external_service_requests_total",
    "Total number of external service requests",
    ["service", "status"],
    registry=registry
)

external_service_duration = Histogram(
    "mcp_agent_external_service_duration_seconds",
    "External service request duration in seconds",
    ["service"],
    registry=registry
)


class MetricsCollector:
    """Centralized metrics collection."""

    def __init__(self) -> None:
        self.setup_app_info()

    def setup_app_info(self) -> None:
        """Set up application information metrics."""
        app_info.info({
            "version": "1.0.0",
            "environment": settings.environment,
            "python_version": "3.11+",
        })

    def record_request(self, method: str, endpoint: str, status_code: int, duration: float) -> None:
        """Record HTTP request metrics."""
        request_count.labels(
            method=method,
            endpoint=endpoint,
            status_code=str(status_code)
        ).inc()

        request_duration.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)

    def record_tool_execution(self, tool_name: str, status: str, duration: float) -> None:
        """Record tool execution metrics."""
        tool_execution_count.labels(
            tool_name=tool_name,
            status=status
        ).inc()

        tool_execution_duration.labels(
            tool_name=tool_name
        ).observe(duration)

    def record_error(self, error_type: str, component: str) -> None:
        """Record error metrics."""
        error_count.labels(
            error_type=error_type,
            component=component
        ).inc()

    def record_database_operation(self, operation: str, table: str, duration: float) -> None:
        """Record database operation metrics."""
        database_operations.labels(
            operation=operation,
            table=table
        ).inc()

        database_operation_duration.labels(
            operation=operation,
            table=table
        ).observe(duration)

    def record_external_service_request(self, service: str, status: str, duration: float) -> None:
        """Record external service request metrics."""
        external_service_requests.labels(
            service=service,
            status=status
        ).inc()

        external_service_duration.labels(
            service=service
        ).observe(duration)


# Global metrics collector instance
metrics_collector = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector."""
    return metrics_collector


def setup_metrics() -> None:
    """Setup metrics collection."""
    # Metrics are set up when the module is imported
    pass


def get_metrics_content() -> tuple[bytes, str]:
    """Get Prometheus metrics content."""
    return generate_latest(registry), CONTENT_TYPE_LATEST


class MetricsMiddleware:
    """FastAPI middleware for automatic metrics collection."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.metrics = get_metrics()

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        method = scope["method"]
        path = scope["path"]
        status_code = 500  # Default to error

        async def send_wrapper(message: Any) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            self.metrics.record_error(
                error_type=type(e).__name__,
                component="middleware"
            )
            raise
        finally:
            duration = time.time() - start_time
            self.metrics.record_request(method, path, status_code, duration)


class ToolMetricsDecorator:
    """Decorator for automatic tool metrics collection."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        self.metrics = get_metrics()

    def __call__(self, func: F) -> F:
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            status = "success"

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                self.metrics.record_error(
                    error_type=type(e).__name__,
                    component=f"tool.{self.tool_name}"
                )
                raise
            finally:
                duration = time.time() - start_time
                self.metrics.record_tool_execution(self.tool_name, status, duration)

        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            status = "success"

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                self.metrics.record_error(
                    error_type=type(e).__name__,
                    component=f"tool.{self.tool_name}"
                )
                raise
            finally:
                duration = time.time() - start_time
                self.metrics.record_tool_execution(self.tool_name, status, duration)

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        else:
            return sync_wrapper  # type: ignore[return-value]


def tool_metrics(tool_name: str) -> ToolMetricsDecorator:
    """Decorator for tool metrics collection."""
    return ToolMetricsDecorator(tool_name)


class DatabaseMetricsDecorator:
    """Decorator for database operation metrics."""

    def __init__(self, operation: str, table: str) -> None:
        self.operation = operation
        self.table = table
        self.metrics = get_metrics()

    def __call__(self, func: F) -> F:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                self.metrics.record_error(
                    error_type=type(e).__name__,
                    component="database"
                )
                raise
            finally:
                duration = time.time() - start_time
                self.metrics.record_database_operation(self.operation, self.table, duration)

        return wrapper  # type: ignore[return-value]


def database_metrics(operation: str, table: str) -> DatabaseMetricsDecorator:
    """Decorator for database metrics collection."""
    return DatabaseMetricsDecorator(operation, table)
