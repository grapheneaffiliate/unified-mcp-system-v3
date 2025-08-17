#!/usr/bin/env python3
"""
Basic usage example for the Unified MCP System.

This example demonstrates how to:
1. Connect to the MCP server directly
2. Use the OpenAI-compatible gateway
3. Call tools through both interfaces
"""

import asyncio

import openai
from mcp import ClientSession
from mcp.client.stdio import stdio_client


async def test_mcp_direct():
    """Test direct MCP server connection."""
    print("🔌 Testing direct MCP server connection...")

    # Connect to MCP server (adjust transport as needed)
    async with stdio_client() as (read, write):
        async with ClientSession(read, write) as session:
            # List available tools
            tools = await session.list_tools()
            print(f"✓ Found {len(tools)} tools: {[t.name for t in tools]}")

            # Call a safe tool (list_files)
            if any(t.name == "list_files" for t in tools):
                result = await session.call_tool("list_files", {"path": "."})
                print(f"✓ list_files result: {result}")


def test_openai_gateway():
    """Test OpenAI-compatible gateway."""
    print("🌐 Testing OpenAI-compatible gateway...")

    # Configure OpenAI client to use our gateway
    client = openai.OpenAI(
        base_url="http://localhost:8001/v1",
        api_key="your-api-key"  # Replace with actual API key
    )

    # Test basic chat completion
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": "List the files in the current directory"}
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files in a directory",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Directory path to list"
                            }
                        },
                        "required": ["path"]
                    }
                }
            }
        ]
    )

    print(f"✓ Chat completion response: {response.choices[0].message.content}")

    # Test streaming
    print("🌊 Testing streaming response...")
    stream = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hello, world!"}],
        stream=True
    )

    print("✓ Streaming response: ", end="")
    for chunk in stream:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="")
    print()


async def main():
    """Run all examples."""
    print("🚀 Unified MCP System - Basic Usage Examples")
    print("=" * 50)

    try:
        await test_mcp_direct()
        print()
        test_openai_gateway()
        print()
        print("✅ All examples completed successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("Make sure both services are running:")
        print("  - MCP Server: http://localhost:8000")
        print("  - LC MCP App: http://localhost:8001")


if __name__ == "__main__":
    asyncio.run(main())
