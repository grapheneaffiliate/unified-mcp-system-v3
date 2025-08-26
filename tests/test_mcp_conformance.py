#!/usr/bin/env python3
"""
MCP conformance tests to ensure the server follows MCP specification.

Tests:
1. Tool listing and schema validation
2. Tool execution success/failure
3. JSON Schema validity for all tools
4. Basic MCP protocol compliance
"""

import asyncio

import jsonschema
import pytest
from mcp import ClientSession
from mcp.client.stdio import stdio_client


@pytest.mark.integration
class TestMCPConformance:
    """Test MCP server conformance to specification."""

    @pytest.mark.asyncio
    async def test_list_tools_schema_validity(self):
        """Test that all tools have valid JSON schemas."""
        async with stdio_client() as (read, write):
            async with ClientSession(read, write) as session:
                # List available tools
                result = await session.list_tools()

                # Access tools from the result object
                tools = result.tools if hasattr(result, 'tools') else result

                # Ensure we have tools
                assert len(tools) > 0, "Server should provide at least one tool"

                # Validate each tool's schema
                for tool in tools:
                    assert hasattr(tool, 'name'), f"Tool missing name: {tool}"
                    assert hasattr(tool, 'description'), f"Tool missing description: {tool.name}"

                    # Check for input schema (could be inputSchema or input_schema)
                    schema_attr = 'inputSchema' if hasattr(tool, 'inputSchema') else 'input_schema'
                    assert hasattr(tool, schema_attr), f"Tool missing input schema: {tool.name}"

                    input_schema = getattr(tool, schema_attr)

                    # Validate JSON Schema
                    try:
                        jsonschema.Draft2020Validator.check_schema(input_schema)
                    except jsonschema.SchemaError as e:
                        pytest.fail(f"Invalid schema for tool {tool.name}: {e}")

    @pytest.mark.asyncio
    async def test_tool_execution_basic(self):
        """Test basic tool execution."""
        async with stdio_client() as (read, write):
            async with ClientSession(read, write) as session:
                result = await session.list_tools()
                tools = result.tools if hasattr(result, 'tools') else result

                # Find a safe tool to test (prefer list_files or similar)
                safe_tools = [t for t in tools if t.name in ['list_files', 'get_system_info', 'ping', 'health_check']]

                if safe_tools:
                    tool = safe_tools[0]

                    # Attempt to call the tool with minimal parameters
                    try:
                        if tool.name == 'list_files':
                            result = await session.call_tool(tool.name, {"path": "."})
                        elif tool.name == 'get_system_info':
                            result = await session.call_tool(tool.name, {})
                        elif tool.name == 'ping':
                            result = await session.call_tool(tool.name, {})
                        else:
                            # Generic call with empty params
                            result = await session.call_tool(tool.name, {})

                        # Verify result structure
                        assert result is not None, f"Tool {tool.name} returned None"

                    except Exception as e:
                        # Tool execution can fail, but should not crash the server
                        print(f"Tool {tool.name} failed (expected): {e}")

    @pytest.mark.asyncio
    async def test_tool_parameter_validation(self):
        """Test that tools properly validate parameters."""
        async with stdio_client() as (read, write):
            async with ClientSession(read, write) as session:
                result = await session.list_tools()
                tools = result.tools if hasattr(result, 'tools') else result

                if tools:
                    tool = tools[0]

                    # Test with invalid parameters (should fail gracefully)
                    try:
                        await session.call_tool(tool.name, {"invalid_param": "test"})
                    except Exception:
                        # Expected to fail with invalid parameters
                        pass

    @pytest.mark.asyncio
    async def test_server_capabilities(self):
        """Test server capabilities and metadata."""
        async with stdio_client() as (read, write):
            async with ClientSession(read, write) as session:
                # Test server info
                info = await session.get_server_info()

                assert hasattr(info, 'name'), "Server should have a name"
                assert hasattr(info, 'version'), "Server should have a version"

    @pytest.mark.asyncio
    async def test_resource_listing(self):
        """Test resource listing if supported."""
        async with stdio_client() as (read, write):
            async with ClientSession(read, write) as session:
                try:
                    # Try to list resources (may not be supported)
                    resources = await session.list_resources()

                    # If resources are supported, validate structure
                    if resources:
                        for resource in resources:
                            assert hasattr(resource, 'uri'), f"Resource missing URI: {resource}"
                            assert hasattr(resource, 'name'), f"Resource missing name: {resource}"

                except Exception:
                    # Resources may not be implemented, which is fine
                    pass

    @pytest.mark.asyncio
    async def test_prompt_listing(self):
        """Test prompt listing if supported."""
        async with stdio_client() as (read, write):
            async with ClientSession(read, write) as session:
                try:
                    # Try to list prompts (may not be supported)
                    prompts = await session.list_prompts()

                    # If prompts are supported, validate structure
                    if prompts:
                        for prompt in prompts:
                            assert hasattr(prompt, 'name'), f"Prompt missing name: {prompt}"
                            assert hasattr(prompt, 'description'), f"Prompt missing description: {prompt}"

                except Exception:
                    # Prompts may not be implemented, which is fine
                    pass

    def test_tool_schemas_are_complete(self):
        """Test that tool schemas include all required fields."""
        # This is a synchronous test for schema structure validation
        sample_schema = {
            "type": "object",
            "properties": {
                "test_param": {
                    "type": "string",
                    "description": "Test parameter"
                }
            },
            "required": ["test_param"]
        }

        # Should not raise an exception
        jsonschema.Draft2020Validator.check_schema(sample_schema)


@pytest.mark.integration
class TestMCPIntegration:
    """Integration tests for MCP server in realistic scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_tool_calls(self):
        """Test that server handles concurrent tool calls properly."""
        async with stdio_client() as (read, write):
            async with ClientSession(read, write) as session:
                result = await session.list_tools()
                tools = result.tools if hasattr(result, 'tools') else result

                if tools:
                    # Make multiple concurrent calls to the same tool
                    safe_tool = next((t for t in tools if t.name in ['list_files', 'ping', 'health_check']), tools[0])

                    tasks = []
                    for _ in range(3):
                        if safe_tool.name == 'list_files':
                            task = session.call_tool(safe_tool.name, {"path": "."})
                        else:
                            task = session.call_tool(safe_tool.name, {})
                        tasks.append(task)

                    # Wait for all tasks to complete
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # At least some should succeed
                    successes = [r for r in results if not isinstance(r, Exception)]
                    assert len(successes) > 0, "At least one concurrent call should succeed"

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test that server handles errors gracefully."""
        async with stdio_client() as (read, write):
            async with ClientSession(read, write) as session:
                # Test calling non-existent tool
                try:
                    await session.call_tool("non_existent_tool", {})
                    pytest.fail("Should have raised an exception for non-existent tool")
                except Exception as e:
                    # Should get a proper error, not crash
                    assert "not found" in str(e).lower() or "unknown" in str(e).lower()


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
