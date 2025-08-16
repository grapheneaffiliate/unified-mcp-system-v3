#!/usr/bin/env python3
"""
MCP contract test using official MCP Python SDK.

Validates:
- Tool listing works
- Tool schemas are valid JSON Schema
- Basic tool execution works
"""

import os
import asyncio
import json
from typing import Any, Dict, Optional

import pytest
import jsonschema

# MCP Python SDK (official)
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# --------- Config ---------
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")
MCP_HEALTH_URL = os.getenv("MCP_HEALTH_URL", "http://localhost:8000/health")
SCHEMA_DRAFT = jsonschema.Draft2020Validator  # MCP uses JSON Schema (draft 2020)

# --------- Helpers ---------
def _extract_schema(tool: Any) -> Optional[Dict[str, Any]]:
    """
    Tools may expose input schema as either `input_schema` (snake) or
    `inputSchema` (camel), depending on transport/SDK versions.
    """
    if isinstance(tool, dict):
        return tool.get("input_schema") or tool.get("inputSchema")
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
    # Some SDK builds may put the schema under .schema or .parameters (defensive)
    if schema is None:
        schema = getattr(tool, "schema", None) or getattr(tool, "parameters", None)
    return schema

def _extract_name(tool: Any) -> str:
    if isinstance(tool, dict):
        return tool.get("name") or ""
    return getattr(tool, "name", "") or ""

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
        except Exception as e:  # noqa: BLE001 - keep simple for CI
            last_exc = e
        await asyncio.sleep(0.25)
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Health check never passed for {url}")

# --------- Tests ---------
@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_list_tools_and_validate_schemas():
    """Test MCP server tool listing and schema validation."""
    await _wait_healthy(MCP_HEALTH_URL)

    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            # Initialize session (safe no-op if already initialized)
            await session.initialize()

            tools_resp = await session.list_tools()
            # Some SDK versions return an object with .tools; be defensive:
            tools = getattr(tools_resp, "tools", None)
            if tools is None and isinstance(tools_resp, dict):
                tools = tools_resp.get("tools")

            assert tools, "MCP server returned no tools"

            invalid: list[tuple[str, str]] = []
            for tool in tools:
                name = _extract_name(tool)
                assert name, f"Tool missing name: {tool!r}"

                schema = _extract_schema(tool)
                if schema:
                    try:
                        SCHEMA_DRAFT.check_schema(schema)
                    except Exception as e:  # noqa: BLE001
                        invalid.append((name, str(e)))

            assert not invalid, f"Invalid JSON Schemas: {json.dumps(invalid, indent=2)}"

            # Try to call the first tool that requires no args
            for tool in tools:
                name = _extract_name(tool)
                schema = _extract_schema(tool) or {}
                required = set(schema.get("required", [])) if isinstance(schema, dict) else set()
                # If no required fields, try a call with {}
                if not required:
                    result = await session.call_tool(name, arguments={})
                    # Result shape can vary: accept any non-empty reply
                    assert result is not None, f"call_tool returned None for {name}"
                    # If the SDK returns a content list, ensure it has something
                    contents = getattr(result, "content", None) or getattr(result, "contents", None)
                    if contents is not None:
                        assert len(contents) > 0, f"Empty content from tool {name}"
                    break
            else:
                pytest.skip("No zero-argument tools to safely call; schema validation still passed.")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
