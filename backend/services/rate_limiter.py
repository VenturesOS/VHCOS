"""
VHC Talent OS — Rate Limiter Service (CRIT-2 unified)
Thin wrapper around the centralized Redis-backed middleware store.
Routes that call `rate_limiter.check_rate_limit(request, "auth")` now
route through the same Redis sorted-set as the middleware, eliminating
the old per-worker in-memory store.
"""
import logging
from typing import Dict
from fastapi import Request, HTTPException
from functools import wraps

logger = logging.getLogger(__name__)

# Named rate limit buckets
RATE_LIMITS = {
    # Mirrors ROUTE_LIMITS["/api/auth/login"] — the middleware and this
    # service-level check both fire on a login, so a lower number here
    # would silently become the real limit.
    "auth": {"requests": 180, "window": 60},
    "search": {"requests": 240, "window": 60},
    "ai_match": {"requests": 120, "window": 60},
    "api": {"requests": 600, "window": 60},
    "upload": {"requests": 10, "window": 60},
}


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Delegates to the unified middleware/rate_limiter.check_limit()."""

    def check_rate_limit(self, request: Request, limit_type: str = "api") -> bool:
        config = RATE_LIMITS.get(limit_type, RATE_LIMITS["api"])
        max_requests = config["requests"]
        window_seconds = config["window"]
        from middleware.rate_limiter import get_client_identity
        ip = get_client_identity(request)
        path = f"svc:{limit_type}"

        from middleware.rate_limiter import check_limit
        if not check_limit(ip, path, max_requests, window_seconds):
            logger.warning(f"[RateLimit] Exceeded for {ip} on {limit_type}")
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {window_seconds} seconds.",
                headers={"Retry-After": str(window_seconds)},
            )
        return True

    def get_remaining(self, request: Request, limit_type: str = "api") -> Dict:
        config = RATE_LIMITS.get(limit_type, RATE_LIMITS["api"])
        return {
            "X-RateLimit-Limit": str(config["requests"]),
            "X-RateLimit-Remaining": "unknown",
            "X-RateLimit-Reset": str(config["window"]),
        }


# Global singleton
rate_limiter = RateLimiter()


def rate_limit(limit_type: str = "api"):
    """Decorator for rate limiting endpoints."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            if request:
                rate_limiter.check_rate_limit(request, limit_type)
            return await func(*args, **kwargs)
        return wrapper
    return decorator
