"""
Main FastAPI server with OpenAI-compatible endpoints and ASGI lifespan management.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .clients.mcp_client import close_mcp_client, get_mcp_client
from .config import settings
from .middleware.auth import require_api_key
from .middleware.metrics import metrics_endpoint, record_metrics
from .middleware.rate_limit import periodic_cleanup, rate_limit
from .observability.logging import configure_logging, get_logger, set_correlation_id
from .openai_models import (
    ChatCompletionRequest,
    create_non_streaming_response,
    create_streaming_response,
    validate_chat_request,
)
from .tools.registry import get_registry, initialize_tools

logger = get_logger("server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """ASGI lifespan management for startup and shutdown."""
    # Startup
    logger.info("Starting LC MCP App server", version="0.1.0", environment=settings.environment)

    # Configure logging
    configure_logging(settings.app_log_level)

    # Validate production settings
    if settings.is_production:
        try:
            settings.validate_required_for_production()
            logger.info("Production validation passed")
        except ValueError as e:
            logger.error("Production validation failed", error=str(e))
            raise

    # Initialize MCP client and tools
    try:
        await initialize_tools()
        logger.info("Tools initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize tools", error=str(e))
        # Continue startup even if tool initialization fails

    # Start background tasks
    cleanup_task = asyncio.create_task(periodic_cleanup())

    logger.info("Server startup complete")

    yield

    # Shutdown
    logger.info("Shutting down LC MCP App server")

    # Cancel background tasks
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # Close MCP client
    await close_mcp_client()

    logger.info("Server shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="LC MCP App",
        description="LangChain MCP Intermediary with OpenAI-compatible API",
        version="0.1.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan
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
    app.middleware("http")(record_metrics)
    app.middleware("http")(rate_limit)

    # Only add auth in production or if API keys are configured
    if settings.is_production or settings.api_keys:
        app.middleware("http")(require_api_key)

    # Register routes
    register_routes(app)

    return app


def register_routes(app: FastAPI):
    """Register all HTTP routes."""

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        mcp_client = await get_mcp_client()
        mcp_healthy = await mcp_client.health()

        registry = get_registry()
        tool_info = registry.get_tool_info()

        status = "healthy" if mcp_healthy else "degraded"

        return {
            "status": status,
            "version": "0.1.0",
            "environment": settings.environment,
            "mcp_server": {
                "url": settings.mcp_server_base_url,
                "healthy": mcp_healthy
            },
            "tools": tool_info,
            "timestamp": time.time()
        }

    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint."""
        return await metrics_endpoint()

    @app.get("/v1/models")
    async def list_models():
        """
        Minimal OpenAI-compatible models endpoint.
        Returns a static list including your default model and an MCP proxy id.
        """
        default_id = getattr(settings, "openai_default_model", "mcp-proxy")
        data = [
            {"id": "mcp-proxy", "object": "model", "created": 0, "owned_by": "local"},
        ]
        if default_id != "mcp-proxy":
            data.append({"id": default_id, "object": "model", "created": 0, "owned_by": "local"})
        return {"object": "list", "data": data}

    @app.post("/v1/chat/completions")
    async def chat_completions(request: ChatCompletionRequest, raw_request: Request):
        """OpenAI-compatible chat completions endpoint."""
        # Set correlation ID for request tracing
        correlation_id = set_correlation_id()

        start_time = time.perf_counter()

        try:
            # Validate request
            validate_chat_request(request)

            # Use configured model if client doesn't specify a valid one
            model = request.model if request.model else settings.openai_default_model

            logger.info(
                "Chat completion request",
                model=model,
                stream=request.stream,
                message_count=len(request.messages),
                correlation_id=correlation_id
            )

            # TODO: Replace with actual agent execution
            # For now, use placeholder responses

            if request.stream:
                # Streaming response
                async def stream_generator() -> AsyncIterator[bytes]:
                    async for chunk in create_streaming_response(
                        messages=[msg.dict() for msg in request.messages],
                        model=model
                    ):
                        yield chunk

                return StreamingResponse(
                    stream_generator(),
                    media_type="text/plain",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no"  # Disable nginx buffering
                    }
                )

            else:
                # Non-streaming response
                response = create_non_streaming_response(
                    messages=[msg.dict() for msg in request.messages],
                    model=model
                )

                return JSONResponse(content=response.dict())

        except ValueError as e:
            logger.warning("Invalid request", error=str(e), correlation_id=correlation_id)
            raise HTTPException(status_code=400, detail=str(e)) from e

        except Exception as e:
            logger.error("Chat completion error", error=str(e), correlation_id=correlation_id)
            raise HTTPException(status_code=500, detail="Internal server error") from e

        finally:
            duration = time.perf_counter() - start_time
            logger.info(
                "Chat completion completed",
                duration=duration,
                correlation_id=correlation_id
            )

    @app.post("/tools/{tool_name}")
    async def run_tool(tool_name: str, request: Request):
        """Direct tool execution endpoint."""
        correlation_id = set_correlation_id()

        try:
            registry = get_registry()
            tool = registry.get(tool_name)

            if not tool:
                raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

            payload = await request.json()

            logger.info(
                "Direct tool execution",
                tool_name=tool_name,
                params_count=len(payload),
                correlation_id=correlation_id
            )

            result = await tool.run(**payload)

            return JSONResponse(content={"result": result})

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Tool execution error", tool_name=tool_name, error=str(e))
            raise HTTPException(status_code=500, detail=f"Tool execution failed: {str(e)}") from e

    @app.get("/tools")
    async def list_tools():
        """List available tools."""
        registry = get_registry()
        capabilities = await registry.get_capabilities()

        tools = []
        for cap in capabilities:
            if cap.get("type") == "tool":
                tools.append({
                    "name": cap.get("name"),
                    "description": cap.get("description"),
                    "schema": cap.get("inputSchema", {})
                })

        return {
            "tools": tools,
            "total": len(tools),
            "registry_info": registry.get_tool_info()
        }


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    logger.info(
        "Starting LC MCP App server directly",
        host=settings.app_host,
        port=settings.app_port,
        environment=settings.environment
    )

    uvicorn.run(
        "lc_mcp_app.server:app",
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.app_log_level,
        reload=settings.app_reload,
        workers=settings.app_workers if not settings.app_reload else 1,
        loop="uvloop" if not settings.is_development else "auto"
    )
