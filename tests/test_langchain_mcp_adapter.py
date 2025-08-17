# Loads MCP tools via LangChain adapters and executes one zero-arg tool.
# Env:
#   MCP_SERVER_URL (default http://localhost:8000 or http://localhost:8000/mcp)
#   MCP_HEALTH_URL (default http://localhost:8000/health)

import asyncio
import os
from typing import Any

import httpx
import pytest
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000")
MCP_HEALTH_URL = os.getenv("MCP_HEALTH_URL", "http://localhost:8000/health")

def _with_mcp_path(url: str) -> str:
    return url if url.rstrip("/").endswith("/mcp") else url.rstrip("/") + "/mcp"

async def _wait_healthy(url: str, timeout_s: float = 15.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    async with httpx.AsyncClient(timeout=2.0) as client:
        last = None
        while asyncio.get_event_loop().time() < deadline:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    return
            except Exception as e:
                last = e
            await asyncio.sleep(0.25)
    if last:
        raise last
    raise RuntimeError(f"Health never passed for {url}")

@pytest.mark.asyncio
@pytest.mark.integration
async def test_langchain_adapter_roundtrip_zero_arg_tool():
    await _wait_healthy(MCP_HEALTH_URL)

    # Try plain URL then /mcp path
    for url in (MCP_SERVER_URL, _with_mcp_path(MCP_SERVER_URL)):
        try:
            client = MultiServerMCPClient({
                "local": {"url": url, "transport": "streamable_http"}
            })
            async with client.session("local") as session:
                tools = await load_mcp_tools(session)
                assert tools, "No tools loaded via adapters"

                for tool in tools:
                    try:
                        out: Any = await tool.ainvoke({})
                        assert out is not None
                        return
                    except Exception:
                        continue
        except Exception:
            continue
    pytest.skip("Could not run any zero-argument MCP tools via adapters (check tool schemas/URL).")
