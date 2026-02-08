"""
VHC Talent OS - System Error Tracking
Auto-captures backend exceptions and provides endpoints for frontend error logging.
"""
import uuid
import logging
import traceback
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from config import db
from utils import require_role

logger = logging.getLogger(__name__)

system_errors_router = APIRouter(prefix="/api", tags=["System Errors"])


class FrontendErrorReport(BaseModel):
    error_message: str
    stack_trace: Optional[str] = None
    component: Optional[str] = None
    page_url: Optional[str] = None
    browser_info: Optional[str] = None
    user_action: Optional[str] = None


async def log_system_error(
    source: str,
    error_type: str,
    message: str,
    stack_trace: Optional[str] = None,
    endpoint: Optional[str] = None,
    method: Optional[str] = None,
    status_code: Optional[int] = None,
    user_id: Optional[str] = None,
    user_role: Optional[str] = None,
    page_url: Optional[str] = None,
    browser_info: Optional[str] = None,
    component: Optional[str] = None,
    extra: Optional[dict] = None,
):
    """Store an error in the system_errors collection."""
    try:
        # Deduplicate: hash of source + error_type + message first 200 chars
        import hashlib
        fingerprint = hashlib.md5(f"{source}:{error_type}:{message[:200]}".encode()).hexdigest()

        doc = {
            "id": str(uuid.uuid4()),
            "source": source,
            "error_type": error_type,
            "message": message[:2000],
            "stack_trace": (stack_trace or "")[:5000],
            "fingerprint": fingerprint,
            "endpoint": endpoint,
            "method": method,
            "status_code": status_code,
            "user_id": user_id,
            "user_role": user_role,
            "page_url": page_url,
            "browser_info": browser_info,
            "component": component,
            "extra": extra,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.system_errors.insert_one(doc)
    except Exception as e:
        logger.error(f"Failed to log system error: {e}")


# --- Frontend error reporting endpoint ---

@system_errors_router.post("/system-errors/frontend")
async def report_frontend_error(
    error: FrontendErrorReport,
    request: Request,
):
    """
    Receives auto-captured frontend errors (JS errors, unhandled rejections, API failures).
    No auth required — errors may occur before/during login.
    """
    # Extract user from token if available
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

    await log_system_error(
        source="frontend",
        error_type=error.component or "js_error",
        message=error.error_message,
        stack_trace=error.stack_trace,
        page_url=error.page_url,
        browser_info=error.browser_info,
        user_id=user_id,
        user_role=user_role,
        extra={"user_action": error.user_action} if error.user_action else None,
    )
    return {"status": "recorded"}


# --- Admin endpoints ---

@system_errors_router.get("/system-errors")
async def get_system_errors(
    source: Optional[str] = None,
    error_type: Optional[str] = None,
    limit: int = 100,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get system errors (admin only). Latest first."""
    query = {}
    if source:
        query["source"] = source
    if error_type:
        query["error_type"] = error_type
    docs = await db.system_errors.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return docs


@system_errors_router.get("/system-errors/stats")
async def get_system_error_stats(
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get error statistics for the System Health dashboard."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    h24 = (now - timedelta(hours=24)).isoformat()
    h1 = (now - timedelta(hours=1)).isoformat()

    total = await db.system_errors.count_documents({})
    last_24h = await db.system_errors.count_documents({"created_at": {"$gte": h24}})
    last_1h = await db.system_errors.count_documents({"created_at": {"$gte": h1}})
    frontend_count = await db.system_errors.count_documents({"source": "frontend"})
    backend_count = await db.system_errors.count_documents({"source": "backend"})

    # Most frequent errors (grouped by fingerprint)
    top_errors_pipeline = [
        {"$group": {
            "_id": "$fingerprint",
            "count": {"$sum": 1},
            "message": {"$first": "$message"},
            "source": {"$first": "$source"},
            "error_type": {"$first": "$error_type"},
            "latest": {"$max": "$created_at"},
        }},
        {"$sort": {"count": -1}},
        {"$limit": 10},
        {"$project": {"_id": 0, "fingerprint": "$_id", "count": 1, "message": 1,
                       "source": 1, "error_type": 1, "latest": 1}},
    ]
    top_errors = await db.system_errors.aggregate(top_errors_pipeline).to_list(10)

    # Errors by hour (last 24h)
    hourly_pipeline = [
        {"$match": {"created_at": {"$gte": h24}}},
        {"$addFields": {"hour": {"$substr": ["$created_at", 0, 13]}}},
        {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "hour": "$_id", "count": 1}},
    ]
    hourly = await db.system_errors.aggregate(hourly_pipeline).to_list(24)

    return {
        "total": total,
        "last_24h": last_24h,
        "last_1h": last_1h,
        "frontend": frontend_count,
        "backend": backend_count,
        "top_errors": top_errors,
        "hourly_trend": hourly,
    }


@system_errors_router.delete("/system-errors/clear")
async def clear_old_errors(
    days: int = 30,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Delete errors older than N days (default 30)."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    result = await db.system_errors.delete_many({"created_at": {"$lt": cutoff}})
    return {"deleted": result.deleted_count}
