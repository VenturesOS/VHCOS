"""
VHC Talent OS — API Metrics Middleware
Captures per-request metrics (endpoint, method, status code, response time)
and stores them in MongoDB for the System Health Dashboard.
Uses in-memory batching to minimize DB write overhead.
"""
import time
import logging
import asyncio
from collections import deque
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# In-memory buffer: flush to DB every N seconds or N records
_metrics_buffer: deque = deque(maxlen=5000)
_FLUSH_INTERVAL = 10  # seconds
_FLUSH_BATCH_SIZE = 100
_flush_task = None

# Endpoints to skip tracking (health checks, static files, metrics itself)
_SKIP_PREFIXES = ("/api/health", "/api/system-health/api-metrics", "/favicon", "/static", "/assets")


async def _flush_metrics():
    """Background task: flush buffered metrics to MongoDB."""
    while True:
        await asyncio.sleep(_FLUSH_INTERVAL)
        if not _metrics_buffer:
            continue
        try:
            from config import db
            batch = []
            while _metrics_buffer and len(batch) < _FLUSH_BATCH_SIZE:
                batch.append(_metrics_buffer.popleft())
            if batch:
                await db.api_metrics.insert_many(batch, ordered=False)
        except Exception as e:
            logger.warning(f"[Metrics] Flush failed: {e}")


def start_metrics_flusher():
    """Start the background flush task. Call once after DB init."""
    global _flush_task
    if _flush_task is None:
        _flush_task = asyncio.create_task(_flush_metrics())
        logger.info("[Metrics] Background flusher started")


class APIMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip non-API and internal endpoints
        if not path.startswith("/api/") or any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        start = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 1)
            # Normalize path: replace UUIDs and IDs with {id}
            normalized = _normalize_path(path)
            _metrics_buffer.append({
                "endpoint": normalized,
                "method": request.method,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "is_error": status_code >= 400,
                "is_server_error": status_code >= 500,
                "timestamp": time.time(),
            })


def _normalize_path(path: str) -> str:
    """Replace UUIDs and numeric IDs in paths with {id} for aggregation."""
    import re
    # UUID pattern
    path = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '{id}', path)
    # Numeric IDs (standalone segments of 5+ digits)
    path = re.sub(r'/\d{5,}/', '/{id}/', path)
    # Mongo ObjectIDs (24-char hex)
    path = re.sub(r'/[0-9a-f]{24}/', '/{id}/', path)
    return path


# ──────────────────────────────────────────────
# Aggregation queries for dashboard
# ──────────────────────────────────────────────

async def get_api_overview(time_range_seconds: int = 3600):
    """Get overview stats: total requests, error rate, avg response time."""
    from config import db
    cutoff = time.time() - time_range_seconds

    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {
            "_id": None,
            "total_requests": {"$sum": 1},
            "error_count": {"$sum": {"$cond": ["$is_error", 1, 0]}},
            "server_error_count": {"$sum": {"$cond": ["$is_server_error", 1, 0]}},
            "avg_duration": {"$avg": "$duration_ms"},
            "p95_duration": {"$percentile": {"input": "$duration_ms", "p": [0.95], "method": "approximate"}},
            "max_duration": {"$max": "$duration_ms"},
        }},
    ]
    try:
        # FIX: Add allowDiskUse to prevent memory errors on large datasets
        results = await db.api_metrics.aggregate(pipeline, allowDiskUse=True).to_list(1)
        if results:
            r = results[0]
            total = r["total_requests"]
            p95_val = r.get("p95_duration")
            if isinstance(p95_val, list):
                p95_val = p95_val[0] if p95_val else 0
            return {
                "total_requests": total,
                "error_count": r["error_count"],
                "server_error_count": r["server_error_count"],
                "error_rate": round((r["error_count"] / total) * 100, 1) if total > 0 else 0,
                "server_error_rate": round((r["server_error_count"] / total) * 100, 1) if total > 0 else 0,
                "avg_response_ms": round(r["avg_duration"], 1),
                "p95_response_ms": round(p95_val, 1) if p95_val else 0,
                "max_response_ms": round(r["max_duration"], 1),
                "time_range_seconds": time_range_seconds,
            }
        return {
            "total_requests": 0, "error_count": 0, "server_error_count": 0,
            "error_rate": 0, "server_error_rate": 0,
            "avg_response_ms": 0, "p95_response_ms": 0, "max_response_ms": 0,
            "time_range_seconds": time_range_seconds,
        }
    except Exception as e:
        logger.warning(f"[Metrics] Overview aggregation failed: {e}")
        return {"total_requests": 0, "error_count": 0, "error_rate": 0, "avg_response_ms": 0, "time_range_seconds": time_range_seconds}


async def get_timeseries(time_range_seconds: int = 3600, bucket_count: int = 30):
    """Get time-series data: error rate and response time over time."""
    from config import db
    cutoff = time.time() - time_range_seconds
    bucket_size = max(time_range_seconds // bucket_count, 60)

    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {
            "_id": {"$subtract": ["$timestamp", {"$mod": ["$timestamp", bucket_size]}]},
            "requests": {"$sum": 1},
            "errors": {"$sum": {"$cond": ["$is_error", 1, 0]}},
            "server_errors": {"$sum": {"$cond": ["$is_server_error", 1, 0]}},
            "avg_ms": {"$avg": "$duration_ms"},
        }},
        {"$sort": {"_id": 1}},
    ]
    try:
        # FIX: Add allowDiskUse to prevent memory errors
        results = await db.api_metrics.aggregate(pipeline, allowDiskUse=True).to_list(200)
        from datetime import datetime, timezone
        return [{
            "time": datetime.fromtimestamp(r["_id"], tz=timezone.utc).strftime("%H:%M"),
            "timestamp": r["_id"],
            "requests": r["requests"],
            "errors": r["errors"],
            "server_errors": r["server_errors"],
            "error_rate": round((r["errors"] / r["requests"]) * 100, 1) if r["requests"] > 0 else 0,
            "avg_ms": round(r["avg_ms"], 1),
        } for r in results]
    except Exception as e:
        logger.warning(f"[Metrics] Timeseries aggregation failed: {e}")
        return []


async def get_top_endpoints(time_range_seconds: int = 3600, sort_by: str = "errors", limit: int = 15):
    """Get top endpoints by error count or response time."""
    from config import db
    cutoff = time.time() - time_range_seconds


    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {
            "_id": {"endpoint": "$endpoint", "method": "$method"},
            "count": {"$sum": 1},
            "errors": {"$sum": {"$cond": ["$is_error", 1, 0]}},
            "server_errors": {"$sum": {"$cond": ["$is_server_error", 1, 0]}},
            "avg_ms": {"$avg": "$duration_ms"},
            "max_ms": {"$max": "$duration_ms"},
        }},
        {"$sort": {"errors" if sort_by == "errors" else "avg_ms": -1}},
        {"$limit": limit},
    ]
    try:
        # FIX: Add allowDiskUse to prevent memory errors
        results = await db.api_metrics.aggregate(pipeline, allowDiskUse=True).to_list(limit)
        return [{
            "endpoint": r["_id"]["endpoint"],
            "method": r["_id"]["method"],
            "count": r["count"],
            "errors": r["errors"],
            "server_errors": r["server_errors"],
            "error_rate": round((r["errors"] / r["count"]) * 100, 1) if r["count"] > 0 else 0,
            "avg_ms": round(r["avg_ms"], 1),
            "max_ms": round(r["max_ms"], 1),
        } for r in results]
    except Exception as e:
        logger.warning(f"[Metrics] Top endpoints aggregation failed: {e}")
        return []


async def get_db_health():
    """Get MongoDB connection pool stats and health."""
    from config import client, db, db_name
    try:
        start = time.monotonic()
        await client.admin.command("ping")
        ping_ms = round((time.monotonic() - start) * 1000, 1)

        # Server status for connection pool info
        server_info = await client.admin.command("serverStatus")
        connections = server_info.get("connections", {})

        # Collection stats
        collections = await db.list_collection_names()

        return {
            "status": "connected",
            "ping_ms": ping_ms,
            "db_name": db_name,
            "connections": {
                "current": connections.get("current", 0),
                "available": connections.get("available", 0),
                "total_created": connections.get("totalCreated", 0),
            },
            "collections_count": len(collections),
        }
    except Exception as e:
        return {
            "status": "error",
            "ping_ms": -1,
            "error": str(e),
            "db_name": "",
            "connections": {"current": 0, "available": 0, "total_created": 0},
            "collections_count": 0,
        }


async def ensure_metrics_indexes():
    """Create TTL and query indexes for the api_metrics collection."""
    from config import db
    try:
        # TTL: auto-delete metrics older than 7 days
        await db.api_metrics.create_index("timestamp", expireAfterSeconds=604800)
        # Query indexes
        await db.api_metrics.create_index([("timestamp", -1)])
        await db.api_metrics.create_index([("endpoint", 1), ("timestamp", -1)])
        await db.api_metrics.create_index([("is_error", 1), ("timestamp", -1)])
        logger.info("[Metrics] Indexes ensured on api_metrics collection")
    except Exception as e:
        logger.warning(f"[Metrics] Index creation failed: {e}")
