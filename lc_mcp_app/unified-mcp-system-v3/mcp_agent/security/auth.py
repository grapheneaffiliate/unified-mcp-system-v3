"""
Authentication and authorization middleware.
"""

import secrets

from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import settings
from ..observability.logging import get_logger

logger = get_logger("security.auth")
security = HTTPBearer(auto_error=False)


class AuthenticationError(Exception):
    """Authentication error."""
    pass


def verify_api_key(api_key: str) -> bool:
    """Verify API key against configured secret."""
    if not api_key:
        return False

    # In production, use constant-time comparison
    if settings.is_production:
        return secrets.compare_digest(api_key, settings.secret_key)
    else:
        # In development, allow more flexible comparison
        return api_key == settings.secret_key


def extract_api_key(authorization: HTTPAuthorizationCredentials | None) -> str | None:
    """Extract API key from authorization header."""
    if not authorization:
        return None

    if authorization.scheme.lower() != "bearer":
        return None

    return authorization.credentials


class AuthMiddleware:
    """FastAPI middleware for API key authentication."""

    def __init__(self, app):
        self.app = app
        self.logger = get_logger("middleware.auth")

        # Endpoints that don't require authentication
        self.public_endpoints = {
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
        }

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        method = scope["method"]

        # Skip authentication for public endpoints
        if path in self.public_endpoints:
            await self.app(scope, receive, send)
            return

        # Skip authentication for OPTIONS requests (CORS preflight)
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # Extract authorization header
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization")

        if not auth_header:
            self.logger.warning("Missing authorization header", path=path, method=method)
            await self._send_unauthorized(send)
            return

        # Parse authorization header
        try:
            auth_str = auth_header.decode("utf-8")
            if not auth_str.startswith("Bearer "):
                self.logger.warning("Invalid authorization scheme", path=path, method=method)
                await self._send_unauthorized(send)
                return

            api_key = auth_str[7:]  # Remove "Bearer " prefix

            if not verify_api_key(api_key):
                self.logger.warning("Invalid API key", path=path, method=method)
                await self._send_unauthorized(send)
                return

            self.logger.debug("Authentication successful", path=path, method=method)

        except Exception as e:
            self.logger.error("Authentication error", error=str(e), path=path, method=method)
            await self._send_unauthorized(send)
            return

        await self.app(scope, receive, send)

    async def _send_unauthorized(self, send):
        """Send 401 Unauthorized response."""
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                [b"content-type", b"application/json"],
                [b"www-authenticate", b"Bearer"],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": b'{"error": "Unauthorized", "message": "Valid API key required"}',
        })


def get_current_user(credentials: HTTPAuthorizationCredentials = security) -> dict:
    """FastAPI dependency for getting current authenticated user."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    api_key = extract_api_key(credentials)
    if not api_key or not verify_api_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Return user info (in a real system, this would come from a database)
    return {
        "user_id": "system",
        "permissions": ["read", "write", "execute"],
        "authenticated": True,
    }


def require_permission(permission: str):
    """Decorator to require specific permission."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            # In a real system, check user permissions here
            return await func(*args, **kwargs)

        def sync_wrapper(*args, **kwargs):
            # In a real system, check user permissions here
            return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
