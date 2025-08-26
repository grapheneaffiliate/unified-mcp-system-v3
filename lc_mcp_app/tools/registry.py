from __future__ import annotations

import asyncio
import time
from typing import Any

from ..clients.mcp_client import MCPClientError
from ..middleware.metrics import record_error, record_tool_execution
from ..observability.logging import get_logger
from .superconductivity_calculator import SuperconductivityCalculatorTool

logger = get_logger("tools.registry")


class ToolAdapter:
    """
    Adapts simple callable tools to an async .run(**kwargs) interface
    expected by the server, and exposes optional JSON schema metadata.
    """

    def __init__(self, tool: Any, schema: dict | None = None):
        self._tool = tool
        self.name: str = getattr(tool, "name", tool.__class__.__name__.lower())
        self.description: str = getattr(tool, "description", "")
        self.schema: dict = schema or {"type": "object", "properties": {}, "required": []}

    async def run(self, **kwargs) -> Any:
        # Allow sync tools while providing async interface
        try:
            if asyncio.iscoroutinefunction(self._tool):
                return await self._tool(**kwargs)
            # Support tools that implement __call__(params: dict)
            if callable(self._tool):
                return self._tool(kwargs)
            # Fallback: pass kwargs directly if a run method exists
            if hasattr(self._tool, "run"):
                maybe = self._tool.run(**kwargs)
                if asyncio.iscoroutine(maybe):
                    return await maybe
                return maybe
            raise TypeError(f"Tool '{self.name}' is not callable")
        except MCPClientError:
            record_error("MCPClientError", "tool")
            logger.exception("Tool execution failed: %s", self.name)
            raise


class ToolRegistry:
    """Simple in-process tool registry with capability metadata."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolAdapter] = {}

    def register(self, adapter: ToolAdapter) -> None:
        self._tools[adapter.name] = adapter
        logger.info("Tool registered", tool=adapter.name)

    def get(self, name: str) -> ToolAdapter | None:
        return self._tools.get(name)

    def get_tool_info(self) -> dict:
        """Summary info for /health and /tools endpoints."""
        return {
            "total_tools": len(self._tools),
            "names": sorted(self._tools.keys()),
        }

    async def get_capabilities(self) -> list[dict]:
        """Return MCP-style capabilities list."""
        caps: list[dict] = []
        for tool in self._tools.values():
            caps.append(
                {
                    "type": "tool",
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.schema,
                }
            )
        return caps


# Global registry instance
_registry: ToolRegistry | None = None


def _default_tool_schemas() -> dict[str, dict]:
    """Define minimal JSON Schemas for tools we ship."""
    return {
        "superconductivity_calculator": {
            "type": "object",
            "properties": {
                "lambda": {"type": "number", "minimum": 0},
                "mu_star": {"type": "number"},
                "theta_log": {"type": "number", "minimum": 0},
            },
            "required": ["lambda", "theta_log"],
            "additionalProperties": False,
        }
    }


async def initialize_tools() -> None:
    """Initialize registry and register built-in tools."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()

        # Register superconductivity calculator
        schemas = _default_tool_schemas()
        _registry.register(
            ToolAdapter(
                SuperconductivityCalculatorTool(),
                schema=schemas.get("superconductivity_calculator"),
            )
        )

        logger.info("Tool registry initialized", count=len(_registry.get_tool_info().get("names", [])))


def get_registry() -> ToolRegistry:
    """Return the global registry; callers should call initialize_tools() during startup."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


# Backwards-compat shim functions in case other code calls these

def get_tool(name: str) -> ToolAdapter:
    tool = get_registry().get(name)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")
    return tool


def execute_tool(name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a registered tool and record metrics (sync wrapper for convenience)."""
    t0 = time.time()
    try:
        tool = get_tool(name)
        # Run synchronously by driving the adapter coroutine to completion
        result = asyncio.get_event_loop().run_until_complete(tool.run(**params))
        record_tool_execution(name, "success", time.time() - t0)
        return result  # type: ignore[return-value]
    except MCPClientError:
        record_error("MCPClientError", "tool")
        logger.exception("Tool execution failed: %s", name)
        raise
