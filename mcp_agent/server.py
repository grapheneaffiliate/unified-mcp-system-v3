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

        # In production, you might want to validate the secret key here
        # For now, we'll accept any initialization

        return Success({"protocol_version": "2024-11-05"})

    @method(name="capabilities/list")
    def capabilities_list(**kwargs):
        """Lists the capabilities offered by the server."""
        logger.info("MCP capabilities/list method called")

        # This is a simplified version - in the full implementation,
        # you would import and register all your tools here
        capabilities = [
            {
                "type": "tool",
                "name": "health_check",
                "description": "Check server health status",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            }
        ]

        return Success({"capabilities": capabilities})

    @method(name="tool/health_check")
    def tool_health_check(**kwargs):
        """Simple health check tool."""
        logger.info("Health check tool called")

        db_manager = get_database_manager()
        db_health = db_manager.health_check()

        result = {
            "status": "healthy" if db_health["status"] == "healthy" else "degraded",
            "timestamp": "2025-01-01T00:00:00Z",  # You'd use actual timestamp
            "database": db_health,
            "environment": settings.environment,
        }

        return Success(result)


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
