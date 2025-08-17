"""
Command-line interface for LC MCP App server and client.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import httpx
import orjson
import uvicorn

from .config import settings
from .observability.logging import configure_logging, get_logger


def server_main():
    """Main entry point for the LC MCP App server."""
    parser = argparse.ArgumentParser(
        description="LC MCP App Server - LangChain MCP Intermediary with OpenAI-compatible API"
    )

    parser.add_argument(
        "--host",
        default=settings.app_host,
        help=f"Host to bind to (default: {settings.app_host})"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=settings.app_port,
        help=f"Port to bind to (default: {settings.app_port})"
    )

    parser.add_argument(
        "--environment",
        choices=["development", "production", "testing"],
        default=settings.environment,
        help=f"Environment mode (default: {settings.environment})"
    )

    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default=settings.app_log_level,
        help=f"Log level (default: {settings.app_log_level})"
    )

    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=settings.app_workers,
        help=f"Number of worker processes (default: {settings.app_workers})"
    )

    args = parser.parse_args()

    # Override settings with command line arguments
    settings.app_host = args.host
    settings.app_port = args.port
    settings.environment = args.environment
    settings.app_log_level = args.log_level
    settings.app_reload = args.reload
    settings.app_workers = args.workers

    # Setup logging
    configure_logging(settings.app_log_level)
    logger = get_logger("cli.server")

    logger.info(
        "Starting LC MCP App server",
        host=args.host,
        port=args.port,
        environment=args.environment,
        log_level=args.log_level,
        workers=args.workers,
        reload=args.reload
    )

    # Validate production settings
    if settings.is_production:
        try:
            settings.validate_required_for_production()
            logger.info("Production validation passed")
        except ValueError as e:
            logger.error("Production validation failed", error=str(e))
            sys.exit(1)

    # Start the server
    try:
        uvicorn.run(
            "lc_mcp_app.server:app",
            host=args.host,
            port=args.port,
            log_level=args.log_level,
            reload=args.reload,
            workers=args.workers if not args.reload else 1,
            loop="uvloop" if not settings.is_development else "auto"
        )
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error("Server startup failed", error=str(e))
        sys.exit(1)


def client_main():
    """Main entry point for the LC MCP App client."""
    parser = argparse.ArgumentParser(
        description="LC MCP App Client - Test and interact with the intermediary server"
    )

    parser.add_argument(
        "--server",
        default="http://localhost:8001",
        help="LC MCP App server URL (default: http://localhost:8001)"
    )

    parser.add_argument(
        "--api-key",
        help="API key for authentication"
    )

    parser.add_argument(
        "--health",
        action="store_true",
        help="Check server health"
    )

    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available models"
    )

    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List available tools"
    )

    parser.add_argument(
        "--chat",
        help="Send a chat message"
    )

    parser.add_argument(
        "--stream",
        action="store_true",
        help="Use streaming for chat"
    )

    parser.add_argument(
        "--call-tool",
        help="Call a specific tool"
    )

    parser.add_argument(
        "--params",
        help="JSON parameters for tool call"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # Setup logging for client
    log_level = "debug" if args.verbose else "info"
    configure_logging(log_level)
    logger = get_logger("cli.client")

    # Run async client
    asyncio.run(run_client(args, logger))


async def run_client(args, logger):
    """Run the async client operations."""
    # Prepare headers
    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"

    timeout = httpx.Timeout(30.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:

            if args.health:
                # Health check
                response = await client.get(f"{args.server}/health", headers=headers)
                response.raise_for_status()

                health_data = response.json()
                print(f"Server Status: {health_data['status']}")
                print(f"Version: {health_data['version']}")
                print(f"Environment: {health_data['environment']}")
                print(f"MCP Server: {'✓' if health_data['mcp_server']['healthy'] else '✗'}")
                print(f"Tools: {health_data['tools']['total_tools']}")

                if args.verbose:
                    print("\nDetailed health info:")
                    print(orjson.dumps(health_data, option=orjson.OPT_INDENT_2).decode())

            elif args.list_models:
                # List models
                response = await client.get(f"{args.server}/v1/models", headers=headers)
                response.raise_for_status()

                models_data = response.json()
                print(f"Available models ({len(models_data['data'])}):")
                for model in models_data["data"]:
                    print(f"  - {model['id']} (owned by: {model['owned_by']})")

            elif args.list_tools:
                # List tools
                response = await client.get(f"{args.server}/tools", headers=headers)
                response.raise_for_status()

                tools_data = response.json()
                print(f"Available tools ({tools_data['total']}):")
                for tool in tools_data["tools"]:
                    print(f"  - {tool['name']}: {tool['description']}")

                if args.verbose:
                    print(f"\nRegistry info: {tools_data['registry_info']}")

            elif args.chat:
                # Send chat message
                payload = {
                    "model": settings.openai_default_model,
                    "messages": [{"role": "user", "content": args.chat}],
                    "stream": args.stream
                }

                if args.stream:
                    # Streaming chat
                    print("Streaming response:")
                    async with client.stream(
                        "POST",
                        f"{args.server}/v1/chat/completions",
                        headers=headers,
                        json=payload
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data = line[6:]  # Remove "data: " prefix
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = orjson.loads(data)
                                    if chunk["choices"][0]["delta"].get("content"):
                                        print(chunk["choices"][0]["delta"]["content"], end="", flush=True)
                                except Exception:
                                    pass
                    print()  # New line after streaming
                else:
                    # Non-streaming chat
                    response = await client.post(
                        f"{args.server}/v1/chat/completions",
                        headers=headers,
                        json=payload
                    )
                    response.raise_for_status()

                    chat_data = response.json()
                    print("Response:")
                    print(chat_data["choices"][0]["message"]["content"])

            elif args.call_tool:
                # Call specific tool
                params = {}
                if args.params:
                    try:
                        params = orjson.loads(args.params)
                    except orjson.JSONDecodeError as e:
                        logger.error("Invalid JSON parameters", error=str(e))
                        sys.exit(1)

                response = await client.post(
                    f"{args.server}/tools/{args.call_tool}",
                    headers=headers,
                    json=params
                )
                response.raise_for_status()

                result = response.json()
                print("Tool result:")
                print(orjson.dumps(result, option=orjson.OPT_INDENT_2).decode())

            else:
                # parser.print_help() - parser not defined in this scope
                print("Usage: lc-mcp-app [command] [options]")

    except httpx.HTTPStatusError as e:
        logger.error("HTTP error", status_code=e.response.status_code, response=e.response.text)
        sys.exit(1)
    except httpx.RequestError as e:
        logger.error("Request error", error=str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Client interrupted")
    except Exception as e:
        logger.error("Client error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    # Determine which command to run based on script name
    script_name = Path(sys.argv[0]).name
    if "server" in script_name:
        server_main()
    elif "client" in script_name:
        client_main()
    else:
        # Default to server
        server_main()
