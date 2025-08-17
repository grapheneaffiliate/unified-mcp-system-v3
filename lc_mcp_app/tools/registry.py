from __future__ import annotations

import time
from typing import Any

from ..clients.mcp_client import MCPClientError
from ..middleware.metrics import record_error, record_tool_execution
from ..observability.logging import get_logger
from .base import BaseTool
from .superconductivity_calculator import SuperconductivityCalculatorTool

logger = get_logger("tools.registry")

# Register tool instances here.
TOOLS: dict[str, Any] = {
    "superconductivity_calculator": SuperconductivityCalculatorTool(),
}


def get_tool(name: str) -> Any:
    tool = TOOLS.get(name)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")
    return tool


def execute_tool(name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a registered tool and record metrics."""
    t0 = time.time()
    try:
        result = get_tool(name)(params)
        record_tool_execution(name, "success", time.time() - t0)
        return result
    except MCPClientError as exc:
        record_error("MCPClientError", "tool")
        logger.exception("Tool execution failed: %s", name)
        raise
