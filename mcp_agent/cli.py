"""
Command-line interface for MCP Agent server and client.
"""

import argparse
import sys
from pathlib import Path

import uvicorn

from .config import settings
from .observability.logging import get_logger, setup_logging


def server_main():
    """Main entry point for the MCP Agent server."""
    parser = argparse.ArgumentParser(
        description="MCP Agent Server - Production-ready Model Context Protocol server"
    )

    parser.add_argument(
        "--host",
        default=settings.host,
        help=f"Host to bind to (default: {settings.host})"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=settings.port,
        help=f"Port to bind to (default: {settings.port})"
    )

    parser.add_argument(
        "--environment",
        choices=["development", "production", "testing"],
        default=settings.environment,
        help=f"Environment mode (default: {settings.environment})"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=settings.log_level,
        help=f"Log level (default: {settings.log_level})"
    )

    parser.add_argument(
        "--log-format",
        choices=["json", "text"],
        default=settings.log_format,
        help=f"Log format (default: {settings.log_format})"
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file"
    )

    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)"
    )

    args = parser.parse_args()

    # Override settings with command line arguments
    settings.host = args.host
    settings.port = args.port
    settings.environment = args.environment
    settings.log_level = args.log_level
    settings.log_format = args.log_format

    # Setup logging with new settings
    setup_logging()
    logger = get_logger("cli.server")

    logger.info(
        "Starting MCP Agent server",
        host=args.host,
        port=args.port,
        environment=args.environment,
        log_level=args.log_level,
        workers=args.workers
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
            "mcp_agent.server:app",
            host=args.host,
            port=args.port,
            log_level=args.log_level.lower(),
            reload=args.reload or settings.is_development,
            workers=args.workers if not (args.reload or settings.is_development) else 1,
        )
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error("Server startup failed", error=str(e))
        sys.exit(1)


def client_main():
    """Main entry point for the MCP Agent client."""
    parser = argparse.ArgumentParser(
        description="MCP Agent Client - Test and interact with MCP servers"
    )

    parser.add_argument(
        "--server",
        default="http://localhost:8081",
        help="MCP server URL (default: http://localhost:8081)"
    )

    parser.add_argument(
        "--api-key",
        help="API key for authentication"
    )

    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List available tools"
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
        "--health",
        action="store_true",
        help="Check server health"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # Setup logging for client
    if args.verbose:
        settings.log_level = "DEBUG"
    setup_logging()
    logger = get_logger("cli.client")

    # Import client functionality
    try:
        import json

        import requests
    except ImportError as e:
        logger.error("Missing required dependencies for client", error=str(e))
        sys.exit(1)

    # Prepare headers
    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"

    try:
        if args.health:
            # Health check
            response = requests.get(f"{args.server}/health", headers=headers, timeout=10)
            response.raise_for_status()

            health_data = response.json()
            print(f"Server Status: {health_data['status']}")
            print(f"Version: {health_data['version']}")
            print(f"Environment: {health_data['environment']}")

            if args.verbose:
                print(json.dumps(health_data, indent=2))

        elif args.list_tools:
            # List capabilities
            payload = {
                "jsonrpc": "2.0",
                "method": "capabilities/list",
                "params": {},
                "id": 1
            }

            response = requests.post(
                f"{args.server}/jsonrpc",
                headers=headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()

            result = response.json()
            if "result" in result:
                capabilities = result["result"]["capabilities"]
                print(f"Available tools ({len(capabilities)}):")
                for cap in capabilities:
                    if cap["type"] == "tool":
                        print(f"  - {cap['name']}: {cap['description']}")
            else:
                print("Error:", result.get("error", "Unknown error"))

        elif args.call_tool:
            # Call specific tool
            params = {}
            if args.params:
                try:
                    params = json.loads(args.params)
                except json.JSONDecodeError as e:
                    logger.error("Invalid JSON parameters", error=str(e))
                    sys.exit(1)

            payload = {
                "jsonrpc": "2.0",
                "method": f"tool/{args.call_tool}",
                "params": params,
                "id": 1
            }

            response = requests.post(
                f"{args.server}/jsonrpc",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            result = response.json()
            if "result" in result:
                print("Tool result:")
                print(json.dumps(result["result"], indent=2))
            else:
                print("Error:", result.get("error", "Unknown error"))

        else:
            parser.print_help()

    except requests.exceptions.RequestException as e:
        logger.error("Request failed", error=str(e))
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
