"""
VHC Talent OS — Rate Limiting Middleware
Per-route rate limiting with security event logging.
"""
import time
import logging
from collections import defaultdict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_store = defaultdict(list)

# Route-specific limits: (requests, window_seconds)
ROUTE_LIMITS = {
    "/api/auth/login": (5, 60),
    "/api/auth/register": (5, 60),
    "/api/public/parse-resume": (10, 60),
    "/api/public/apply": (5, 60),
    "/api/public/upload-resume": (3, 60),
}

# High-priority routes exempt from default limits (user-facing, latency-sensitive)
HIGH_PRIORITY_ROUTES = {
    "/api/extension/ai-extract": (30, 60),
    "/api/extension/capture": (30, 60),
    "/api/extension/check-existing": (60, 60),
}

# Prefix-based limits
PREFIX_LIMITS = {
    "/api/admin/": (30, 60),
}

DEFAULT_LIMIT = (60, 60)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check(key: str, limit: int, window: int) -> bool:
    now = time.time()
    _store[key] = [t for t in _store[key] if now - t < window]
    if len(_store[key]) >= limit:
        return False
    _store[key].append(now)
    return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        ip = _get_client_ip(request)

        # Find applicable limit
        limit, window = DEFAULT_LIMIT
        if path in ROUTE_LIMITS:
            limit, window = ROUTE_LIMITS[path]
        elif path in HIGH_PRIORITY_ROUTES:
            limit, window = HIGH_PRIORITY_ROUTES[path]
        else:
            for prefix, lw in PREFIX_LIMITS.items():
                if path.startswith(prefix):
                    limit, window = lw
                    break

        key = f"rl:{ip}:{path}"
        if not _check(key, limit, window):
            # Log security event asynchronously
            try:
                from services.security_service import log_security_event
                import asyncio
                asyncio.ensure_future(log_security_event(
                    "rate_limit_exceeded", ip, "MEDIUM",
                    f"Rate limit exceeded on {path}", {"path": path, "limit": limit, "window": window}
                ))
            except Exception:
                pass
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
            )

        response = await call_next(request)
        return response
