"""
Rate limiting middleware using token bucket algorithm.
"""

import time

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

    def is_allowed(self, client_id: str, tokens: int = 1) -> tuple[bool, dict[str, any]]:
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
    """FastAPI middleware for rate limiting."""

    def __init__(self, app):
        self.app = app
        self.logger = get_logger("middleware.rate_limiting")
        self.rate_limiter = rate_limiter

        # Endpoints exempt from rate limiting
        self.exempt_endpoints = {
            "/health",
            "/metrics",
        }

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]

        # Skip rate limiting for exempt endpoints
        if path in self.exempt_endpoints:
            await self.app(scope, receive, send)
            return

        # Get client identifier
        client_id = self._get_client_id(scope)

        # Check rate limit
        allowed, rate_info = self.rate_limiter.is_allowed(client_id)

        if not allowed:
            self.logger.warning(
                "Rate limit exceeded",
                client_id=client_id,
                path=path,
                remaining=rate_info["remaining"],
                limit=rate_info["limit"]
            )
            await self._send_rate_limited(send, rate_info)
            return

        # Add rate limit headers to response
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    [b"x-ratelimit-limit", str(rate_info["limit"]).encode()],
                    [b"x-ratelimit-remaining", str(rate_info["remaining"]).encode()],
                    [b"x-ratelimit-reset", str(rate_info["reset_time"]).encode()],
                ])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

    def _get_client_id(self, scope) -> str:
        """Get client identifier for rate limiting."""
        # Try to get real IP from headers (for reverse proxy setups)
        headers = dict(scope.get("headers", []))

        # Check common forwarded headers
        forwarded_headers = [
            b"x-forwarded-for",
            b"x-real-ip",
            b"cf-connecting-ip",  # Cloudflare
        ]

        for header in forwarded_headers:
            if header in headers:
                ip = headers[header].decode().split(",")[0].strip()
                if ip:
                    return ip

        # Fall back to direct client IP
        client = scope.get("client")
        if client:
            return client[0]

        return "unknown"

    async def _send_rate_limited(self, send, rate_info: dict[str, any]):
        """Send 429 Too Many Requests response."""
        headers = [
            [b"content-type", b"application/json"],
            [b"x-ratelimit-limit", str(rate_info["limit"]).encode()],
            [b"x-ratelimit-remaining", str(rate_info["remaining"]).encode()],
            [b"x-ratelimit-reset", str(rate_info["reset_time"]).encode()],
            [b"retry-after", str(rate_info["reset_time"] - int(time.time())).encode()],
        ]

        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": headers,
        })

        body = {
            "error": "Rate limit exceeded",
            "message": f"Too many requests. Limit: {rate_info['limit']} per minute",
            "retry_after": rate_info["reset_time"] - int(time.time()),
        }

        import json
        await send({
            "type": "http.response.body",
            "body": json.dumps(body).encode(),
        })


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
