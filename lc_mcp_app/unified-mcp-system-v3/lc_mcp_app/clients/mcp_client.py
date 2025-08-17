"""
Enhanced MCP client with connection pooling and proper timeout handling.
"""

import time
from typing import Any

import httpx

from ..config import settings
from ..middleware.metrics import record_error, record_mcp_request
from ..observability.logging import get_logger

logger = get_logger("clients.mcp")


class MCPClientError(Exception):
    """Custom exception for MCP Client errors."""
    pass


class MCPClient:
    """
    Enhanced MCP client with connection pooling, timeouts, and metrics.
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._initialized = False

    async def _ensure_client(self):
        """Ensure HTTP client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.mcp_server_base_url,
                timeout=httpx.Timeout(settings.mcp_timeout_s),
                limits=httpx.Limits(
                    max_connections=settings.mcp_max_connections,
                    max_keepalive_connections=settings.mcp_max_keepalive
                ),
                headers={"User-Agent": "LC-MCP-APP/0.1.0"},
            )
            logger.info(
                "MCP client initialized",
                base_url=settings.mcp_server_base_url,
                timeout=settings.mcp_timeout_s,
                max_connections=settings.mcp_max_connections
            )

    async def health(self) -> bool:
        """Check MCP server health."""
        try:
            await self._ensure_client()
            response = await self._client.get("/health")
            is_healthy = response.status_code == 200

            logger.debug("MCP health check", healthy=is_healthy, status_code=response.status_code)
            return is_healthy

        except Exception as e:
            logger.error("MCP health check failed", error=str(e))
            record_error("HealthCheckError", "mcp_client")
            return False

    async def invoke_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Invoke a tool via JSON-RPC."""
        start_time = time.perf_counter()
        status = "error"

        try:
            await self._ensure_client()

            # Prepare JSON-RPC payload
            payload = {
                "jsonrpc": "2.0",
                "method": f"tool/{tool_name}",
                "params": params,
                "id": 1
            }

            logger.debug(
                "Invoking MCP tool",
                tool_name=tool_name,
                params_keys=list(params.keys()) if params else []
            )

            response = await self._client.post("/jsonrpc", json=payload)
            response.raise_for_status()

            response_data = response.json()

            # Handle JSON-RPC errors
            if "error" in response_data:
                error_info = response_data["error"]
                error_msg = f"MCP RPC Error ({error_info.get('code', 'N/A')}): {error_info.get('message', 'Unknown error')}"
                logger.error("MCP tool execution failed", tool_name=tool_name, error=error_msg)
                raise MCPClientError(error_msg)

            if "result" not in response_data:
                raise MCPClientError("Invalid JSON-RPC response: 'result' field missing")

            status = "success"
            result = response_data["result"]

            logger.info(
                "MCP tool executed successfully",
                tool_name=tool_name,
                result_type=type(result).__name__
            )

            return result

        except httpx.TimeoutException as e:
            logger.error("MCP tool timeout", tool_name=tool_name, timeout=settings.mcp_timeout_s)
            record_error("TimeoutError", "mcp_client")
            raise MCPClientError(f"MCP tool '{tool_name}' timed out after {settings.mcp_timeout_s}s") from e

        except httpx.HTTPStatusError as e:
            logger.error(
                "MCP HTTP error",
                tool_name=tool_name,
                status_code=e.response.status_code,
                response_text=e.response.text[:200]
            )
            record_error("HTTPError", "mcp_client")
            raise MCPClientError(f"MCP HTTP error {e.response.status_code}: {e.response.text}") from e

        except Exception as e:
            logger.error("Unexpected MCP error", tool_name=tool_name, error=str(e))
            record_error(type(e).__name__, "mcp_client")
            raise MCPClientError(f"Unexpected error calling MCP tool '{tool_name}': {e}") from e

        finally:
            duration = time.perf_counter() - start_time
            record_mcp_request(f"tool/{tool_name}", status, duration)

    async def get_capabilities(self) -> dict[str, Any]:
        """Get MCP server capabilities."""
        start_time = time.perf_counter()
        status = "error"

        try:
            await self._ensure_client()

            payload = {
                "jsonrpc": "2.0",
                "method": "capabilities/list",
                "params": {},
                "id": 1
            }

            response = await self._client.post("/jsonrpc", json=payload)
            response.raise_for_status()

            response_data = response.json()

            if "error" in response_data:
                error_info = response_data["error"]
                raise MCPClientError(f"MCP capabilities error: {error_info.get('message', 'Unknown error')}")

            status = "success"
            capabilities = response_data.get("result", {}).get("capabilities", [])

            logger.info("MCP capabilities retrieved", count=len(capabilities))
            return {"capabilities": capabilities}

        except Exception as e:
            logger.error("Failed to get MCP capabilities", error=str(e))
            record_error(type(e).__name__, "mcp_client")
            raise MCPClientError(f"Failed to get MCP capabilities: {e}") from e

        finally:
            duration = time.perf_counter() - start_time
            record_mcp_request("capabilities/list", status, duration)

    async def initialize(self) -> dict[str, Any]:
        """Initialize MCP connection."""
        start_time = time.perf_counter()
        status = "error"

        try:
            await self._ensure_client()

            payload = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {},
                "id": 1
            }

            response = await self._client.post("/jsonrpc", json=payload)
            response.raise_for_status()

            response_data = response.json()

            if "error" in response_data:
                error_info = response_data["error"]
                raise MCPClientError(f"MCP initialize error: {error_info.get('message', 'Unknown error')}")

            status = "success"
            result = response_data.get("result", {})

            logger.info("MCP connection initialized", protocol_version=result.get("protocol_version"))
            return result

        except Exception as e:
            logger.error("Failed to initialize MCP connection", error=str(e))
            record_error(type(e).__name__, "mcp_client")
            raise MCPClientError(f"Failed to initialize MCP connection: {e}") from e

        finally:
            duration = time.perf_counter() - start_time
            record_mcp_request("initialize", status, duration)

    async def aclose(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            logger.info("MCP client closed")


# Global MCP client instance
_mcp_client: MCPClient | None = None


async def get_mcp_client() -> MCPClient:
    """Get the global MCP client instance."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
        # Initialize connection on first use
        try:
            await _mcp_client.initialize()
        except MCPClientError as e:
            logger.warning("MCP initialization failed, will retry on first tool use", error=str(e))
    return _mcp_client


async def close_mcp_client():
    """Close the global MCP client."""
    global _mcp_client
    if _mcp_client:
        await _mcp_client.aclose()
        _mcp_client = None
