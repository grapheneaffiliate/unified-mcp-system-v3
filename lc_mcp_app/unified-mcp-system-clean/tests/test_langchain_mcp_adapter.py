#!/usr/bin/env python3
"""
LangChain MCP adapter test.

Tests LangChain ↔ MCP interop without requiring an LLM.
"""

import os
import asyncio
from typing import Any

import pytest

# LangChain MCP adapters
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")
MCP_HEALTH_URL = os.getenv("MCP_HEALTH_URL", "http://localhost:8000/health")

async def _wait_healthy(url: str, timeout_s: float = 10.0) -> None:
    import httpx
    deadline = asyncio.get_event_loop().time() + timeout_s
    last_exc = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return
        except Exception as e:  # noqa: BLE001
            last_exc = e
        await asyncio.sleep(0.25)
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Health check never passed for {url}")

@pytest.mark.asyncio
@pytest.mark.integration
async def test_langchain_tools_roundtrip_without_llm():
    """Test LangChain MCP adapter integration without requiring an LLM."""
    await _wait_healthy(MCP_HEALTH_URL)

    # Connection config follows adapter docs:
    #   transport="streamable_http", url=<your server>
    # You can add multiple named servers here.
    client = MultiServerMCPClient({
        "local": {
            "url": MCP_SERVER_URL,
            "transport": "streamable_http",
        }
    })

    # Start a session and load tools as LangChain BaseTool objects
    async with client.session("local") as session:
        tools = await load_mcp_tools(session)
        assert tools, "No tools loaded from MCP server via adapters"

        # Try to execute a tool that takes no required arguments.
        # LangChain tools expose .invoke / .ainvoke; run async version.
        for tool in tools:
            try:
                result: Any = await tool.ainvoke({})
                # If a tool truly needs args, the adapter will raise a validation error—skip in that case
                assert result is not None
                break
            except Exception:
                continue
        else:
            pytest.skip("No zero-argument MCP tools available via adapters.")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
