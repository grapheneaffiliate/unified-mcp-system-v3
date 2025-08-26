"""Main FastAPI server application with all middleware and endpoints."""

import inspect
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .config import settings
from .database.operations import get_database_manager, initialize_database
from .observability.logging import get_logger, http_logging_middleware, setup_logging
from .observability.metrics import (
    get_metrics_content,
    http_metrics_middleware,
    setup_metrics,
)
from .security.auth import AuthMiddleware
from .security.rate_limiting import http_rate_limit_middleware


# Lightweight JSON-RPC helpers to avoid external dependency on jsonrpcserver
class Success:
    def __init__(self, result):
        self.result = result


class Error:
    def __init__(self, code: int, message: str, data=None):
        self.code = code
        self.message = message
        self.data = data


# Setup logging first
setup_logging()
logger = get_logger("server")

# Setup metrics
setup_metrics()

# Initialize database
initialize_database()

# Store registered methods
methods_dict = {}


def method(name: str):
    """Register a method name in our local registry."""
    def decorator(func):
        methods_dict[name] = func
        return func
    return decorator


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    # Validate production settings
    if settings.is_production:
        try:
            settings.validate_required_for_production()
        except ValueError as e:
            logger.error("Production validation failed", error=str(e))
            raise

    app = FastAPI(
        title="MCP Agent Server",
        description="Production-ready Model Context Protocol server with comprehensive tool support",
        version="1.0.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add custom middleware (order matters!)
    if settings.is_production:
        app.middleware("http")(AuthMiddleware)

    app.middleware("http")(http_rate_limit_middleware)
    app.middleware("http")(http_metrics_middleware)
    app.middleware("http")(http_logging_middleware)

    # Register routes
    register_routes(app)

    # Register MCP methods
    register_mcp_methods()

    logger.info(
        "FastAPI application created",
        environment=settings.environment,
        debug=settings.debug,
        host=settings.host,
        port=settings.port,
    )

    return app


def register_routes(app: FastAPI):
    """Register HTTP routes."""

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        db_manager = get_database_manager()
        db_health = db_manager.health_check()

        return {
            "status": "healthy" if db_health["status"] == "healthy" else "degraded",
            "version": "1.0.0",
            "environment": settings.environment,
            "database": db_health,
            "sandbox": {
                "enabled": settings.sandbox_enabled,
                "network_restrictions": settings.network_restrictions,
            },
        }

    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint."""
        if not settings.metrics_enabled:
            raise HTTPException(status_code=404, detail="Metrics disabled")

        content, content_type = get_metrics_content()
        return Response(content=content, media_type=content_type)

    @app.post("/tools/read_file")
    async def read_file_tool(request: Request):
        """Read file tool endpoint for smoke tests."""
        import os.path

        try:
            request_data = await request.json()
            path = request_data.get("path", "")

            if not path:
                return {"error": "path parameter required"}

            # Security: restrict to safe files for smoke test
            allowed_files = {"README.md", "pyproject.toml", ".gitignore"}
            base_path = "/app"  # container working directory

            # Normalize and validate path
            if path not in allowed_files:
                return {"error": f"Access denied. Allowed files: {', '.join(allowed_files)}"}

            safe_path = os.path.join(base_path, path)
            normalized_path = os.path.normpath(safe_path)

            # Ensure path is within base directory
            if not normalized_path.startswith(base_path):
                return {"error": "Path traversal not allowed"}

            try:
                with open(normalized_path, encoding='utf-8') as f:
                    content = f.read()
                return {"content": content, "path": path}
            except FileNotFoundError:
                return {"error": f"File not found: {path}"}
            except Exception as e:
                logger.error("Failed to read file in read_file_tool", path=path, error=str(e), exc_info=True)
                return {"error": "Failed to read file"}
        except Exception as e:
            logger.error("Invalid request in read_file_tool", error=str(e), exc_info=True)
            return {"error": "Invalid request"}

    @app.post("/mcp")
    async def mcp_endpoint(request: Request):
        """MCP protocol endpoint."""
        return await jsonrpc_endpoint(request)

    @app.post("/jsonrpc")
    async def jsonrpc_endpoint(request: Request):
        """JSON-RPC endpoint for MCP protocol."""
        request_body = await request.body()
        request_str = request_body.decode("utf-8")

        logger.debug("Received JSON-RPC request", request_size=len(request_str))

        try:
            request_data = json.loads(request_str)
            method_name = request_data.get("method")
            params = request_data.get("params", {})
            request_id = request_data.get("id")

            if not method_name or method_name not in methods_dict:
                response_str = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": -32601, "message": "Method not found"},
                        "id": request_id,
                    }
                )
            else:
                target_method = methods_dict[method_name]

                if inspect.iscoroutinefunction(target_method):
                    # Handle async methods
                    try:
                        result = await target_method(**params)

                        if isinstance(result, Success | Error):
                            # Convert to proper JSON-RPC response
                            if isinstance(result, Success):
                                response_str = json.dumps(
                                    {
                                        "jsonrpc": "2.0",
                                        "result": result.result,
                                        "id": request_id,
                                    }
                                )
                            else:
                                response_str = json.dumps(
                                    {
                                        "jsonrpc": "2.0",
                                        "error": {
                                            "code": result.code,
                                            "message": result.message,
                                            "data": result.data,
                                        },
                                        "id": request_id,
                                    }
                                )
                        else:
                            # Assume successful result
                            response_str = json.dumps(
                                {"jsonrpc": "2.0", "result": result, "id": request_id}
                            )

                    except Exception:
                        logger.error("Error executing async method", method=method_name, exc_info=True)
                        response_str = json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "error": {"code": -32603, "message": "Internal error"},
                                "id": request_id,
                            }
                        )
                else:
                    # Handle sync methods without external dispatcher
                    try:
                        result = target_method(**params)

                        if isinstance(result, Success):
                            response_str = json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "result": result.result,
                                    "id": request_id,
                                }
                            )
                        elif isinstance(result, Error):
                            response_str = json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "error": {
                                        "code": result.code,
                                        "message": result.message,
                                        "data": result.data,
                                    },
                                    "id": request_id,
                                }
                            )
                        else:
                            # Assume successful result
                            response_str = json.dumps(
                                {"jsonrpc": "2.0", "result": result, "id": request_id}
                            )
                    except Exception as e:
                        logger.error("Error executing method", method=method_name, error=str(e))
                        response_str = json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "error": {"code": -32603, "message": "Internal error", "data": str(e)},
                                "id": request_id,
                            }
                        )

        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON-RPC request", error=str(e))
            response_str = json.dumps(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None}
            )
        except Exception as e:
            logger.error("Unexpected error processing JSON-RPC request", error=str(e))
            response_str = json.dumps(
                {"jsonrpc": "2.0", "error": {"code": -32603, "message": "Internal error"}, "id": None}
            )

        logger.debug("Sending JSON-RPC response", response_size=len(response_str))
        return Response(content=response_str, media_type="application/json")


def register_mcp_methods():
    """Register MCP protocol methods."""

    @method(name="initialize")
    def initialize(**kwargs):
        """Handles the MCP initialize handshake."""
        logger.info("MCP initialize method called", params=kwargs)

        # Return proper MCP protocol version and capabilities
        return Success({
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {}
            },
            "serverInfo": {
                "name": "mcp-agent-server",
                "version": "1.0.0"
            }
        })

    @method(name="tools/list")
    def tools_list(**kwargs):
        """Lists available tools following MCP protocol."""
        logger.info("MCP tools/list method called")

        # Define tools with proper MCP schema
        tools = [
            {
                "name": "health_check",
                "description": "Check server health status",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False
                },
            },
            {
                "name": "read_file",
                "description": "Read contents of a file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to read"
                        }
                    },
                    "required": ["path"],
                    "additionalProperties": False
                },
            }
        ]

        return Success({"tools": tools})

    @method(name="tools/call")
    async def tools_call(**kwargs):
        """Execute a tool following MCP protocol."""
        tool_name = kwargs.get("name")
        arguments = kwargs.get("arguments", {})

        logger.info("MCP tools/call method called", tool=tool_name, arguments=arguments)

        if tool_name == "health_check":
            db_manager = get_database_manager()
            db_health = db_manager.health_check()

            result = {
                "status": "healthy" if db_health["status"] == "healthy" else "degraded",
                "database": db_health,
                "environment": settings.environment,
            }

            return Success({"content": [{"type": "text", "text": json.dumps(result, indent=2)}]})

        elif tool_name == "read_file":
            import os.path

            path = arguments.get("path", "")
            if not path:
                return Error(-32602, "Invalid params", "path parameter required")

            # Security: restrict to safe files
            allowed_files = {"README.md", "pyproject.toml", ".gitignore"}
            base_path = "/app"  # container working directory

            if path not in allowed_files:
                return Error(-32602, "Invalid params", f"Access denied. Allowed files: {', '.join(allowed_files)}")

            safe_path = os.path.join(base_path, path)
            normalized_path = os.path.normpath(safe_path)

            if not normalized_path.startswith(base_path):
                return Error(-32602, "Invalid params", "Path traversal not allowed")

            try:
                with open(normalized_path, encoding='utf-8') as f:
                    content = f.read()
                return Success({"content": [{"type": "text", "text": content}]})
            except FileNotFoundError:
                return Error(-32602, "Invalid params", f"File not found: {path}")
            except Exception as e:
                logger.error("Failed to read file", path=path, error=str(e))
                return Error(-32603, "Internal error", "Failed to read file")

        else:
            return Error(-32601, "Method not found", f"Unknown tool: {tool_name}")

    @method(name="resources/list")
    def resources_list(**kwargs):
        """List available resources."""
        logger.info("MCP resources/list method called")
        # No resources for now
        return Success({"resources": []})

    @method(name="prompts/list")
    def prompts_list(**kwargs):
        """List available prompts."""
        logger.info("MCP prompts/list method called")
        # No prompts for now
        return Success({"prompts": []})


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    logger.info(
        "Starting MCP Agent server",
        host=settings.host,
        port=settings.port,
        environment=settings.environment,
    )

    uvicorn.run(
        "mcp_agent.server:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.is_development,
    )
