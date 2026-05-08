"""
VHC Talent OS — Rate Limiting Middleware
Unified Redis-backed rate limiting (CRIT-2).
All routes go through this middleware. Uses Upstash Redis sorted-set sliding
window when available; falls back to a bounded in-memory store (single-worker
only) when Redis is not configured.

Replaces the old dual in-memory stores that were per-worker and unbounded.
"""
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Route-specific limits: (requests, window_seconds)
ROUTE_LIMITS = {
    "/api/auth/login": (30, 60),
    "/api/auth/register": (15, 60),
    "/api/public/parse-resume": (10, 60),
    "/api/public/apply": (5, 60),
    "/api/public/upload-resume": (3, 60),
}

HIGH_PRIORITY_ROUTES = {
    "/api/extension/ai-extract": (30, 60),
    "/api/extension/capture": (30, 60),
    "/api/extension/check-existing": (60, 60),
}

BULK_ROUTE_LIMITS = {
    "/api/candidate-bank/batch-parse": (60, 60),
    "/api/candidate-bank/batch-save": (60, 60),
    "/api/admin/bulk-import/save": (60, 60),
    "/api/cv-upload/parse": (60, 60),
    "/api/candidate-bank/upload": (60, 60),
}

# High-frequency client-side polling endpoints. Multiple browser tabs × 20s
# polling will easily breach the 60/min default and create false-positive
# "rate_limit_exceeded" security events. Bumped to 240/min (4/sec/IP) which
# still blocks abuse but allows ~12 tabs comfortably.
POLL_ROUTE_LIMITS = {
    "/api/notifications/unread-count": (240, 60),
    "/api/admin/llm/live-banner": (240, 60),
    "/api/admin/llm/failure-stats": (240, 60),
    "/api/admin/runpod/health": (240, 60),
    "/api/extension/my-version-status": (240, 60),
    "/api/candidate-bank/data-quality/bulk-re-enrich/status": (240, 60),
}

PREFIX_LIMITS = {
    "/api/admin/": (45, 60),
}

DEFAULT_LIMIT = (60, 60)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Shared Redis-backed checker ──────────────────────────────────────────────

_redis = None
_redis_checked = False


def _get_redis():
    global _redis, _redis_checked
    if not _redis_checked:
        _redis_checked = True
        try:
            from services.redis_client import get_redis
            _redis = get_redis()
            if _redis:
                logger.info("[RateLimit] Using shared Redis client")
        except Exception as e:
            logger.warning(f"[RateLimit] Redis unavailable ({e}) — using bounded in-memory fallback")
            _redis = None
    return _redis


# ── Bounded in-memory fallback (capped at 50k keys) ─────────────────────────

import time
_mem_store: dict[str, list[float]] = {}
_MAX_MEM_KEYS = 50_000


def _check_redis(key: str, limit: int, window: int) -> bool:
    """Sliding-window check via Redis sorted set."""
    r = _get_redis()
    now = int(time.time())
    window_start = now - window
    pipe_key = f"rl:{key}"
    try:
        r.zremrangebyscore(pipe_key, 0, window_start)
        current = r.zcard(pipe_key)
        if current >= limit:
            return False
        r.zadd(pipe_key, {str(now): now})
        r.expire(pipe_key, window + 10)
        return True
    except Exception as e:
        logger.warning(f"[RateLimit] Redis error: {e}, allowing request")
        return True


def _check_mem(key: str, limit: int, window: int) -> bool:
    """Bounded in-memory fallback."""
    now = time.time()
    bucket = _mem_store.get(key)
    if bucket is None:
        bucket = []
        _mem_store[key] = bucket
    # Prune expired timestamps
    bucket[:] = [t for t in bucket if now - t < window]
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    # Evict oldest keys if store grows too large
    if len(_mem_store) > _MAX_MEM_KEYS:
        oldest_keys = sorted(_mem_store, key=lambda k: _mem_store[k][0] if _mem_store[k] else 0)[:(_MAX_MEM_KEYS // 4)]
        for k in oldest_keys:
            _mem_store.pop(k, None)
    return True


def check_limit(ip: str, path: str, limit: int, window: int) -> bool:
    """Public helper used by both middleware and standalone callers."""
    key = f"{ip}:{path}"
    if _get_redis():
        return _check_redis(key, limit, window)
    return _check_mem(key, limit, window)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        ip = _get_client_ip(request)

        # Resolve applicable limit
        limit, window = DEFAULT_LIMIT
        if path in ROUTE_LIMITS:
            limit, window = ROUTE_LIMITS[path]
        elif path in HIGH_PRIORITY_ROUTES:
            limit, window = HIGH_PRIORITY_ROUTES[path]
        elif path in BULK_ROUTE_LIMITS:
            limit, window = BULK_ROUTE_LIMITS[path]
        elif path in POLL_ROUTE_LIMITS:
            limit, window = POLL_ROUTE_LIMITS[path]
        else:
            for prefix, lw in PREFIX_LIMITS.items():
                if path.startswith(prefix):
                    limit, window = lw
                    break

        if not check_limit(ip, path, limit, window):
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

        return await call_next(request)
