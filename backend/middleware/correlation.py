"""
VHC Talent OS — Structured JSON Logging & Correlation ID Middleware (E-05)
Generates a UUID correlation_id per request and attaches it to all logs.
"""
import uuid
import logging
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

# Thread-local storage for correlation ID
import contextvars
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:12]
        correlation_id_var.set(req_id)

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)

        response.headers["X-Request-ID"] = req_id

        # Structured access log
        logger.info(
            "request_complete",
            extra={
                "correlation_id": req_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": elapsed_ms,
                "client_ip": request.headers.get("X-Forwarded-For", request.client.host if request.client else "-"),
            }
        )
        return response


class CorrelationFilter(logging.Filter):
    """Injects correlation_id into every log record."""
    def filter(self, record):
        record.correlation_id = correlation_id_var.get("-")
        return True
