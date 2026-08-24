"""
Middleware + CORS + security headers + global exception handler.

Extracted from server.py in the 2026-08 split. Registration order MUST match
the original for identical runtime behaviour: gzip, correlation, rate limit,
zero trust, API metrics — then CORS via add_middleware — then the security-
headers middleware via @app.middleware("http") (runs FIRST at request time
because Starlette wraps middleware LIFO).

Public surface:
    register_middleware(app)          — registers all standard middleware + CORS
    register_exception_handler(app)   — global 500 handler that logs to system_errors
"""
import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from .routers import log_system_error

logger = logging.getLogger(__name__)


def register_middleware(app: FastAPI) -> None:
    """Attach every non-CORS middleware then wire CORS."""

    # Phase 54.13 — Gzip compression. Drops admin/pipeline JSON from
    # 2.5 MB → ~380 KB on the wire. Threshold 500 bytes avoids overhead on
    # small responses.
    from fastapi.middleware.gzip import GZipMiddleware
    app.add_middleware(GZipMiddleware, minimum_size=500)

    from middleware.correlation import CorrelationIdMiddleware
    app.add_middleware(CorrelationIdMiddleware)

    from middleware.rate_limiter import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)

    from middleware.zero_trust import ZeroTrustMiddleware
    app.add_middleware(ZeroTrustMiddleware)

    from middleware.api_metrics import APIMetricsMiddleware
    app.add_middleware(APIMetricsMiddleware)

    _register_cors(app)
    _register_security_headers(app)


def _register_cors(app: FastAPI) -> None:
    _hardcoded_origins = [
        "https://ventureshrd.com",
        "https://www.ventureshrd.com",
    ]
    _site_url = os.environ.get("SITE_URL", "").strip().rstrip("/")
    if _site_url and _site_url not in _hardcoded_origins:
        _hardcoded_origins.append(_site_url)
    _env_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

    # SEC-4: Never allow wildcard with credentials — enumerate origins explicitly
    _env_origins = [o for o in _env_origins if o != "*"]
    _all_origins = list(set(_hardcoded_origins + _env_origins))

    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=_all_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _register_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def seo_security_headers(request: Request, call_next):
        try:
            response = await call_next(request)
        except RuntimeError as e:
            # Only swallow the specific Starlette "No response returned" case
            # (a downstream middleware/handler returned without producing a
            # response). Any other RuntimeError should bubble up to the
            # global exception handler so system_errors captures it.
            if "No response returned" not in str(e):
                raise
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # M-09: Content-Security-Policy to prevent stored XSS
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob: https://*.r2.dev https://*.cloudflare.com; "
            "connect-src 'self' https://api.ventureshrd.com https://*.upstash.io; "
            "frame-src https://challenges.cloudflare.com; "
            "frame-ancestors 'none';"
        )

        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.headers["CDN-Cache-Control"] = "no-store"
            response.headers["Cloudflare-CDN-Cache-Control"] = "no-store"

        return response


def register_exception_handler(app: FastAPI) -> None:
    """Global 500 handler that logs to routes.system_errors when available."""
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        import traceback as tb
        if isinstance(exc, HTTPException):
            # Delegate to Starlette's default HTTPException handler so it
            # returns a proper JSON response even when raised from inside
            # middleware (where `raise exc` would escape as a raw 500).
            return await http_exception_handler(request, exc)

        error_msg = str(exc)
        stack_str = "".join(tb.format_exception(type(exc), exc, exc.__traceback__))

        user_id = None
        user_role = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from utils import verify_token
                payload = verify_token(auth_header.split(" ")[1])
                user_id = payload.get("sub")
                user_role = payload.get("role")
            except Exception:
                pass

        try:
            await log_system_error(
                source="backend",
                error_type=type(exc).__name__,
                message=error_msg,
                stack_trace=stack_str,
                endpoint=str(request.url.path),
                method=request.method,
                status_code=500,
                user_id=user_id,
                user_role=user_role,
            )
        except Exception:
            pass

        logger.error(f"Unhandled exception on {request.method} {request.url.path}: {error_msg}")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
