"""
Rate limiting middleware using token bucket algorithm.
"""

import time
from typing import Any

from fastapi.responses import JSONResponse

from ..config import settings
from ..observability.logging import get_logger

logger = get_logger("security.rate_limiting")


class TokenBucket:
    """Token bucket for rate limiting."""

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.time()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens from the bucket."""
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill

        # Add tokens based on elapsed time
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now


class RateLimiter:
    """Rate limiter using token bucket algorithm."""

    def __init__(self, requests_per_minute: int = 100, window_seconds: int = 60):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self.buckets: dict[str, TokenBucket] = {}
        self.cleanup_interval = 300  # Clean up old buckets every 5 minutes
        self.last_cleanup = time.time()

    def is_allowed(self, client_id: str, tokens: int = 1) -> tuple[bool, dict[str, Any]]:
        """Check if request is allowed for client."""
        self._cleanup_old_buckets()

        # Get or create bucket for client
        if client_id not in self.buckets:
            refill_rate = self.requests_per_minute / 60.0  # tokens per second
            self.buckets[client_id] = TokenBucket(self.requests_per_minute, refill_rate)

        bucket = self.buckets[client_id]
        allowed = bucket.consume(tokens)

        # Return rate limit info
        info = {
            "allowed": allowed,
            "remaining": int(bucket.tokens),
            "limit": self.requests_per_minute,
            "reset_time": int(time.time() + (self.requests_per_minute - bucket.tokens) / bucket.refill_rate),
        }

        return allowed, info

    def _cleanup_old_buckets(self):
        """Remove old, unused buckets to prevent memory leaks."""
        now = time.time()
        if now - self.last_cleanup < self.cleanup_interval:
            return

        # Remove buckets that haven't been used recently
        cutoff_time = now - self.cleanup_interval
        to_remove = []

        for client_id, bucket in self.buckets.items():
            if bucket.last_refill < cutoff_time:
                to_remove.append(client_id)

        for client_id in to_remove:
            del self.buckets[client_id]

        self.last_cleanup = now

        if to_remove:
            logger.debug(f"Cleaned up {len(to_remove)} old rate limit buckets")


# Global rate limiter instance
rate_limiter = RateLimiter(
    requests_per_minute=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window
)


class RateLimitMiddleware:
    """Legacy class-style middleware kept for backwards compatibility with ASGI signature."""

    def __init__(self, app):
        self.app = app
        self.logger = get_logger("middleware.rate_limiting")
        self.rate_limiter = rate_limiter
        self.exempt_endpoints = {"/health", "/metrics"}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if path in self.exempt_endpoints:
            await self.app(scope, receive, send)
            return

        client_id = _get_client_id_from_scope(scope)
        allowed, rate_info = self.rate_limiter.is_allowed(client_id)

        if not allowed:
            self.logger.warning(
                "Rate limit exceeded",
                client_id=client_id,
                path=path,
                remaining=rate_info["remaining"],
                limit=rate_info["limit"],
            )
            await _send_rate_limited(send, rate_info)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        [b"x-ratelimit-limit", str(rate_info["limit"]).encode()],
                        [b"x-ratelimit-remaining", str(rate_info["remaining"]).encode()],
                        [b"x-ratelimit-reset", str(rate_info["reset_time"]).encode()],
                    ]
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

def _get_client_id_from_scope(scope) -> str:
    """Get client identifier for rate limiting from ASGI scope."""
    headers = dict(scope.get("headers", []))
    forwarded_headers = [b"x-forwarded-for", b"x-real-ip", b"cf-connecting-ip"]
    for header in forwarded_headers:
        if header in headers:
            ip = headers[header].decode().split(",")[0].strip()
            if ip:
                return ip
    client = scope.get("client")
    if client:
        return client[0]
    return "unknown"


async def _send_rate_limited(send, rate_info: dict[str, Any]):
    """Send 429 Too Many Requests response for ASGI pipeline."""
    headers = [
        [b"content-type", b"application/json"],
        [b"x-ratelimit-limit", str(rate_info["limit"]).encode()],
        [b"x-ratelimit-remaining", str(rate_info["remaining"]).encode()],
        [b"x-ratelimit-reset", str(rate_info["reset_time"]).encode()],
        [b"retry-after", str(rate_info["reset_time"] - int(time.time())).encode()],
    ]
    await send({"type": "http.response.start", "status": 429, "headers": headers})

    body = {
        "error": "Rate limit exceeded",
        "message": f"Too many requests. Limit: {rate_info['limit']} per minute",
        "retry_after": rate_info["reset_time"] - int(time.time()),
    }

    import json

    await send({"type": "http.response.body", "body": json.dumps(body).encode()})


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    return rate_limiter


def rate_limit(requests_per_minute: int = None, window_seconds: int = None):
    """Decorator for custom rate limiting on specific endpoints."""
    def decorator(func):
        # Create custom rate limiter for this endpoint
        custom_limiter = RateLimiter(
            requests_per_minute or settings.rate_limit_requests,
            window_seconds or settings.rate_limit_window
        )

        async def async_wrapper(*args, **kwargs):
            # In a real implementation, you'd extract client ID from request context
            # For now, we'll use a placeholder
            client_id = "endpoint_specific"
            allowed, _ = custom_limiter.is_allowed(client_id)

            if not allowed:
                from fastapi import HTTPException
                raise HTTPException(status_code=429, detail="Rate limit exceeded")

            return await func(*args, **kwargs)

        def sync_wrapper(*args, **kwargs):
            client_id = "endpoint_specific"
            allowed, _ = custom_limiter.is_allowed(client_id)

            if not allowed:
                from fastapi import HTTPException
                raise HTTPException(status_code=429, detail="Rate limit exceeded")

            return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# Function-style middleware compatible with app.middleware("http")(func)
async def http_rate_limit_middleware(request, call_next):  # type: ignore[no-untyped-def]
    path = str(getattr(request, "url", "/"))
    # Exempt endpoints
    if path.endswith("/health") or path.endswith("/metrics"):
        return await call_next(request)

    # Determine client id
    headers = getattr(request, "headers", {})
    client_id = None
    for key in ("x-forwarded-for", "x-real-ip", "cf-connecting-ip"):
        if key in headers:
            client_id = headers.get(key).split(",")[0].strip()
            break
    if not client_id:
        client = getattr(request, "client", None)
        client_id = getattr(client, "host", "unknown") if client else "unknown"

    allowed, rate_info = rate_limiter.is_allowed(client_id)
    if not allowed:
        retry_after = max(0, rate_info["reset_time"] - int(time.time()))
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": f"Too many requests. Limit: {rate_info['limit']} per minute",
                "retry_after": retry_after,
            },
            headers={
                "X-RateLimit-Limit": str(rate_info["limit"]),
                "X-RateLimit-Remaining": str(rate_info["remaining"]),
                "X-RateLimit-Reset": str(rate_info["reset_time"]),
                "Retry-After": str(retry_after),
            },
        )

    response = await call_next(request)
    try:
        response.headers["X-RateLimit-Limit"] = str(rate_info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(rate_info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(rate_info["reset_time"])
    except Exception:
        pass
    return response
