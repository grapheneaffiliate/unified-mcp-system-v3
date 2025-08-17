"""
Prometheus metrics middleware for monitoring.
"""

import time

from fastapi import Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

from ..config import settings
from ..observability.logging import get_logger

logger = get_logger("middleware.metrics")

# HTTP request metrics
http_requests_total = Counter(
    "lc_mcp_app_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"]
)

http_request_duration_seconds = Histogram(
    "lc_mcp_app_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"]
)

# Agent execution metrics
agent_requests_total = Counter(
    "lc_mcp_app_agent_requests_total",
    "Total agent requests",
    ["model", "stream"]
)

agent_request_duration_seconds = Histogram(
    "lc_mcp_app_agent_request_duration_seconds",
    "Agent request duration in seconds",
    ["model", "stream"]
)

# Tool execution metrics
tool_executions_total = Counter(
    "lc_mcp_app_tool_executions_total",
    "Total tool executions",
    ["tool_name", "status"]
)

tool_execution_duration_seconds = Histogram(
    "lc_mcp_app_tool_execution_duration_seconds",
    "Tool execution duration in seconds",
    ["tool_name"]
)

# MCP client metrics
mcp_requests_total = Counter(
    "lc_mcp_app_mcp_requests_total",
    "Total MCP requests",
    ["method", "status"]
)

mcp_request_duration_seconds = Histogram(
    "lc_mcp_app_mcp_request_duration_seconds",
    "MCP request duration in seconds",
    ["method"]
)

# Error metrics
errors_total = Counter(
    "lc_mcp_app_errors_total",
    "Total errors",
    ["error_type", "component"]
)


async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    if not settings.metrics_enabled:
        return Response("Metrics disabled", status_code=404)

    content = generate_latest()
    return Response(content=content, media_type=CONTENT_TYPE_LATEST)


async def record_metrics(request: Request, call_next):
    """Middleware to record HTTP request metrics."""
    if not settings.metrics_enabled:
        return await call_next(request)

    method = request.method
    path = request.url.path
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
        status_code = response.status_code

        # Record successful request
        http_requests_total.labels(
            method=method,
            path=path,
            status=str(status_code)
        ).inc()

        return response

    except Exception as e:
        # Record error
        http_requests_total.labels(
            method=method,
            path=path,
            status="error"
        ).inc()

        errors_total.labels(
            error_type=type(e).__name__,
            component="http"
        ).inc()

        raise

    finally:
        # Record duration
        duration = time.perf_counter() - start_time
        http_request_duration_seconds.labels(
            method=method,
            path=path
        ).observe(duration)


def record_agent_request(model: str, stream: bool, duration: float):
    """Record agent request metrics."""
    if not settings.metrics_enabled:
        return

    agent_requests_total.labels(
        model=model,
        stream=str(stream).lower()
    ).inc()

    agent_request_duration_seconds.labels(
        model=model,
        stream=str(stream).lower()
    ).observe(duration)


def record_tool_execution(tool_name: str, status: str, duration: float):
    """Record tool execution metrics."""
    if not settings.metrics_enabled:
        return

    tool_executions_total.labels(
        tool_name=tool_name,
        status=status
    ).inc()

    tool_execution_duration_seconds.labels(
        tool_name=tool_name
    ).observe(duration)


def record_mcp_request(method: str, status: str, duration: float):
    """Record MCP request metrics."""
    if not settings.metrics_enabled:
        return

    mcp_requests_total.labels(
        method=method,
        status=status
    ).inc()

    mcp_request_duration_seconds.labels(
        method=method
    ).observe(duration)


def record_error(error_type: str, component: str):
    """Record error metrics."""
    if not settings.metrics_enabled:
        return

    errors_total.labels(
        error_type=error_type,
        component=component
    ).inc()


class MetricsCollector:
    """Centralized metrics collection."""

    @staticmethod
    def record_agent_request(model: str, stream: bool, duration: float):
        record_agent_request(model, stream, duration)

    @staticmethod
    def record_tool_execution(tool_name: str, status: str, duration: float):
        record_tool_execution(tool_name, status, duration)

    @staticmethod
    def record_mcp_request(method: str, status: str, duration: float):
        record_mcp_request(method, status, duration)

    @staticmethod
    def record_error(error_type: str, component: str):
        record_error(error_type, component)


# Global metrics collector
metrics = MetricsCollector()
