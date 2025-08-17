"""
Authentication middleware for API key validation.
"""

from fastapi import HTTPException, Request

from ..config import settings
from ..observability.logging import get_logger

logger = get_logger("middleware.auth")


async def require_api_key(request: Request, call_next):
    """Middleware to require API key authentication."""
    # Skip auth for public endpoints
    public_endpoints = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}

    if request.url.path in public_endpoints:
        return await call_next(request)

    # Skip auth if no API keys configured (development mode)
    if not settings.api_keys:
        logger.debug("No API keys configured, skipping authentication")
        return await call_next(request)

    # Extract authorization header
    auth_header = request.headers.get("authorization", "")

    if not auth_header:
        logger.warning("Missing authorization header", path=request.url.path)
        raise HTTPException(
            status_code=401,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Parse Bearer token
    if not auth_header.startswith("Bearer "):
        logger.warning("Invalid authorization scheme", path=request.url.path)
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization scheme",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = auth_header[7:].strip()  # Remove "Bearer " prefix

    # Validate token
    if token not in settings.api_keys:
        logger.warning("Invalid API key", path=request.url.path, token_prefix=token[:8])
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"}
        )

    logger.debug("Authentication successful", path=request.url.path)
    return await call_next(request)
