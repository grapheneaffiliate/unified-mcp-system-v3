from __future__ import annotations

import time

from ..clients.mcp_client import MCPClientError, get_mcp_client
from ..middleware.metrics import record_error, record_tool_execution
from ..observability.logging import get_logger
from .base import BaseTool
from .superconductivity_calculator import SuperconductivityCalculatorTool

logger = get_logger("tools.registry")

# Register tool instances here.
TOOLS: dict[str, BaseTool] = {
    "superconductivity_calculator": SuperconductivityCalculatorTool(),
}


def get_tool(name: str) -> BaseTool:
    tool = TOOLS.get(name)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")
    return tool


def execute_tool(name: str, params: dict) -> dict:
    """Execute a registered tool and record metrics."""
    t0 = time.time()
    try:
        result = get_tool(name)(params)
        record_tool_execution(name, time.time() - t0, ok=True)
        return result  # type: ignore[return-value]
    except MCPClientError as exc:
        record_error("tool", name, str(exc))
        logger.exception("Tool execution failed: %s", name)
        raise
