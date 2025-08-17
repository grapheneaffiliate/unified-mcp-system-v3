"""
Rate limiting middleware using token bucket algorithm.
"""

import asyncio
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from ..config import settings
from ..observability.logging import get_logger

logger = get_logger("middleware.rate_limit")

# Simple in-process token bucket per IP (good enough for single-instance)
buckets: dict[str, deque[float]] = defaultdict(deque)


def _now() -> float:
    """Get current timestamp."""
    return time.time()


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    # Try to get real IP from headers (for reverse proxy setups)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return "unknown"


async def rate_limit(request: Request, call_next):
    """Rate limiting middleware using token bucket algorithm."""
    # Skip rate limiting for health and metrics endpoints
    exempt_endpoints = {"/health", "/metrics"}

    if request.url.path in exempt_endpoints:
        return await call_next(request)

    ip = _get_client_ip(request)
    window = 60.0  # 1 minute window
    max_requests = settings.rate_limit_rpm
    burst_capacity = settings.rate_limit_burst

    # Get or create bucket for this IP
    bucket = buckets[ip]
    current_time = _now()

    # Remove old requests outside the window
    while bucket and current_time - bucket[0] > window:
        bucket.popleft()

    # Check if we're over the limit (including burst)
    if len(bucket) >= max_requests + burst_capacity:
        logger.warning(
            "Rate limit exceeded",
            client_ip=ip,
            path=request.url.path,
            current_requests=len(bucket),
            limit=max_requests,
            burst=burst_capacity
        )

        # Calculate retry after
        oldest_request = bucket[0] if bucket else current_time
        retry_after = int(oldest_request + window - current_time)

        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "limit": max_requests,
                "window": "1 minute",
                "retry_after": max(retry_after, 1)
            },
            headers={
                "Retry-After": str(max(retry_after, 1)),
                "X-RateLimit-Limit": str(max_requests),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(oldest_request + window))
            }
        )

    # Add current request to bucket
    bucket.append(current_time)

    # Calculate remaining requests
    remaining = max(0, max_requests - len(bucket))

    # Process request
    response = await call_next(request)

    # Add rate limit headers to response
    response.headers["X-RateLimit-Limit"] = str(max_requests)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(int(current_time + window))

    logger.debug(
        "Rate limit check passed",
        client_ip=ip,
        path=request.url.path,
        current_requests=len(bucket),
        remaining=remaining
    )

    return response


def cleanup_old_buckets():
    """Clean up old rate limit buckets to prevent memory leaks."""
    current_time = _now()
    cutoff_time = current_time - 300  # 5 minutes

    to_remove = []
    for ip, bucket in buckets.items():
        if not bucket or (bucket and current_time - bucket[-1] > cutoff_time):
            to_remove.append(ip)

    for ip in to_remove:
        del buckets[ip]

    if to_remove:
        logger.debug(f"Cleaned up {len(to_remove)} old rate limit buckets")


# Periodic cleanup (called from background task)
async def periodic_cleanup():
    """Periodic cleanup of rate limit buckets."""
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        cleanup_old_buckets()
