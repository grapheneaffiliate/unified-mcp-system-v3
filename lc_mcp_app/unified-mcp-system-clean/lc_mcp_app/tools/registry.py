"""
Tool registry for dynamic tool discovery and management.
"""

from typing import Dict, List, Any, Optional
from ..clients.mcp_client import get_mcp_client, MCPClientError
from ..observability.logging import get_logger
from ..middleware.metrics import record_tool_execution, record_error
import time

logger = get_logger("tools.registry")


class BaseTool:
    """Base class for all tools."""
    
    def __init__(self, name: str, description: str, schema: Dict[str, Any]):
        self.name = name
        self.description = description
        self.schema = schema
    
    async def run(self, **kwargs) -> Any:
        """Execute the tool with given parameters."""
        raise NotImplementedError


class RemoteTool(BaseTool):
    """Tool that executes remotely via MCP server."""
    
    def __init__(self, name: str, description: str, schema: Dict[str, Any]):
        super().__init__(name, description, schema)
    
    async def run(self, **kwargs) -> Any:
        """Execute tool via MCP client."""
        start_time = time.perf_counter()
        status = "error"
        
        try:
            client = await get_mcp_client()
            result = await client.invoke_tool(self.name, kwargs)
            status = "success"
            
            logger.info(
                "Remote tool executed",
                tool_name=self.name,
                params_count=len(kwargs),
                result_type=type(result).__name__
            )
            
            return result
            
        except MCPClientError as e:
            logger.error("Remote tool execution failed", tool_name=self.name, error=str(e))
            record_error("MCPClientError", "remote_tool")
            raise
            
        except Exception as e:
            logger.error("Unexpected tool error", tool_name=self.name, error=str(e))
            record_error(type(e).__name__, "remote_tool")
            raise
            
        finally:
            duration = time.perf_counter() - start_time
            record_tool_execution(self.name, status, duration)


class ToolRegistry:
    """Registry for managing available tools."""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._capabilities_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_timestamp: float = 0
        self._cache_ttl: float = 300  # 5 minutes
    
    def register(self, tool: BaseTool) -> None:
        """Register a tool in the registry."""
        self._tools[tool.name] = tool
        logger.debug("Tool registered", tool_name=tool.name)
    
    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def all(self) -> List[BaseTool]:
        """Get all registered tools."""
        return list(self._tools.values())
    
    def list_names(self) -> List[str]:
        """Get list of all tool names."""
        return list(self._tools.keys())
    
    async def discover_mcp_tools(self) -> List[BaseTool]:
        """Discover tools from MCP server and register them."""
        try:
            client = await get_mcp_client()
            capabilities_response = await client.get_capabilities()
            capabilities = capabilities_response.get("capabilities", [])
            
            discovered_tools = []
            
            for capability in capabilities:
                if capability.get("type") == "tool":
                    tool_name = capability.get("name")
                    description = capability.get("description", "")
                    schema = capability.get("inputSchema", {})
                    
                    if tool_name:
                        tool = RemoteTool(tool_name, description, schema)
                        self.register(tool)
                        discovered_tools.append(tool)
            
            logger.info(
                "MCP tools discovered and registered",
                count=len(discovered_tools),
                tool_names=[t.name for t in discovered_tools]
            )
            
            return discovered_tools
            
        except MCPClientError as e:
            logger.error("Failed to discover MCP tools", error=str(e))
            record_error("MCPClientError", "tool_discovery")
            return []
        
        except Exception as e:
            logger.error("Unexpected error during tool discovery", error=str(e))
            record_error(type(e).__name__, "tool_discovery")
            return []
    
    async def get_capabilities(self) -> List[Dict[str, Any]]:
        """Get cached capabilities or fetch from MCP server."""
        current_time = time.time()
        
        # Return cached capabilities if still valid
        if (self._capabilities_cache is not None and 
            current_time - self._cache_timestamp < self._cache_ttl):
            return self._capabilities_cache
        
        try:
            client = await get_mcp_client()
            capabilities_response = await client.get_capabilities()
            capabilities = capabilities_response.get("capabilities", [])
            
            # Update cache
            self._capabilities_cache = capabilities
            self._cache_timestamp = current_time
            
            logger.debug("Capabilities cached", count=len(capabilities))
            return capabilities
            
        except Exception as e:
            logger.error("Failed to get capabilities", error=str(e))
            # Return empty list if we can't get capabilities
            return []
    
    def clear_cache(self):
        """Clear the capabilities cache."""
        self._capabilities_cache = None
        self._cache_timestamp = 0
        logger.debug("Capabilities cache cleared")
    
    def get_tool_info(self) -> Dict[str, Any]:
        """Get information about registered tools."""
        return {
            "total_tools": len(self._tools),
            "tool_names": list(self._tools.keys()),
            "cache_valid": (
                self._capabilities_cache is not None and
                time.time() - self._cache_timestamp < self._cache_ttl
            ),
            "cache_age": time.time() - self._cache_timestamp if self._cache_timestamp > 0 else None
        }


# Global tool registry instance
registry = ToolRegistry()


async def initialize_tools():
    """Initialize tools by discovering from MCP server."""
    logger.info("Initializing tool registry")
    
    # Discover and register MCP tools
    await registry.discover_mcp_tools()
    
    tool_info = registry.get_tool_info()
    logger.info("Tool registry initialized", **tool_info)


def get_registry() -> ToolRegistry:
    """Get the global tool registry."""
    return registry
