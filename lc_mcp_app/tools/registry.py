# lc_mcp_app/tools/registry.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional
import importlib
import os

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # optional in tests

@dataclass
class ToolSpec:
    name: str
    description: str = ""
    handler: Optional[Callable[..., Any]] = None
    input_schema: Optional[dict] = None

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def all(self) -> Dict[str, ToolSpec]:
        return dict(self._tools)

    def get_tool_info(self) -> Dict[str, Any]:
        """Return tool registry information for health checks."""
        return {
            "count": len(self._tools),
            "tools": list(self._tools.keys())
        }

    async def get_capabilities(self) -> list[dict]:
        """Return MCP-style capabilities for tools."""
        capabilities = []
        for tool in self._tools.values():
            cap = {
                "type": "tool",
                "name": tool.name,
                "description": tool.description
            }
            if tool.input_schema:
                cap["inputSchema"] = tool.input_schema
            capabilities.append(cap)
        return capabilities

# module-level singleton used by the app/tests
_registry = ToolRegistry()

def get_registry() -> ToolRegistry:
    """Return the process-global tool registry (used by the app and tests)."""
    return _registry

async def initialize_tools(config_path: Optional[str | Path] = None) -> None:
    """
    Load tools from a YAML config (optional), import handlers, and register them.
    No-op if the file is missing (health tests don't require tools).
    """
    path = Path(config_path) if config_path else Path(__file__).resolve().parents[2] / "config" / "tools.yaml"
    if path.exists() and yaml is not None:
        try:
            data = yaml.safe_load(path.read_text()) or {}
            modules = data.get("modules", [])
            for item in modules:
                if not item.get("enabled", True):
                    continue
                
                name = item.get("name", "unknown")
                module_name = item["module"]
                register_fn = item.get("register", "register_toolset")
                strict = item.get("strict", True)
                
                try:
                    mod = importlib.import_module(module_name)
                    register_func = getattr(mod, register_fn)
                    register_func(_registry)
                except Exception as e:
                    if strict:
                        raise RuntimeError(f"Failed to register {module_name}.{register_fn}: {e}")
                    # In non-strict mode, just log and continue
                    print(f"Warning: Skipping {module_name}.{register_fn} due to error: {e}")
        except Exception as e:
            print(f"Warning: Failed to load tools config from {path}: {e}")
