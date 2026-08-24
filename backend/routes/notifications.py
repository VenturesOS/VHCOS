"""
VHC Talent OS - In-App Notification Center
"""
import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from config import db
from utils.auth import get_current_user, get_current_user_from_token

notification_router = APIRouter(prefix="/api/notifications", tags=["Notifications"])
logger = logging.getLogger(__name__)


# ── SSE pub/sub (in-process; per-worker) ─────────────────────────────
# Same-worker mutations push instantly (< 100ms). Cross-worker mutations
# are picked up by the 60s heartbeat fallback below — still 2x faster
# than the old 120s HTTP poll and, unlike polling, incurs one Mongo
# `count_documents` per user per minute regardless of tab count.
_user_events: dict[str, set[asyncio.Queue]] = defaultdict(set)


def _publish_unread_change(user_id: str) -> None:
    """Signal every SSE subscriber for user_id that their count may have changed."""
    for q in list(_user_events.get(user_id, [])):
        try:
            q.put_nowait(None)
        except asyncio.QueueFull:
            pass  # subscriber is slow — heartbeat will catch it


class NotificationPreferences(BaseModel):
    new_application: bool = True
    status_change: bool = True
    job_posted: bool = True
    job_assigned: bool = True
    candidate_assigned: bool = True
    am_company_assigned: bool = True


NOTIFICATION_TYPES = {
    "new_application": "New Application",
    "status_change": "Status Change",
    "job_posted": "Job Posted",
    "job_assigned": "Job Assigned",
    "candidate_assigned": "Candidate Assigned",
    "am_company_assigned": "Account Assignment",
    "system": "System",
}


async def create_notification(
    user_id: str,
    notification_type: str,
    title: str,
    message: str,
    link: str = None,
    metadata: dict = None,
):
    """Helper to create a notification for a user. Respects user preferences."""
    # Check user preferences
    prefs = await db.notification_preferences.find_one(
        {"user_id": user_id}, {"_id": 0}
    )
    if prefs:
        pref_key = notification_type
        if not prefs.get(pref_key, True):
            return None

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "type": notification_type,
        "title": title,
        "message": message,
        "link": link,
        "metadata": metadata or {},
        "is_read": False,
        "created_at": now,
    }
    await db.notifications.insert_one(doc)
    _publish_unread_change(user_id)
    return doc["id"]


@notification_router.get("")
async def get_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    """Get notifications for the current user."""
    try:
        query = {"user_id": current_user["id"]}
        if unread_only:
            query["is_read"] = False

        total = await db.notifications.count_documents(query)
        notifications = (
            await db.notifications.find(query, {"_id": 0})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
            .to_list(limit)
        )

        return {"notifications": notifications, "total": total}
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[Notifications] Transient DB error on list: {e}")
        return {"notifications": [], "total": 0}


@notification_router.get("/unread-count")
async def get_unread_count(current_user: dict = Depends(get_current_user)):
    """
    Get unread notification count with caching to reduce DB load.
    Cache TTL: 30 seconds (reduces rate limit errors from aggressive polling)
    """
    user_id = current_user["id"]
    cache_key = f"notifications:unread:{user_id}"
    
    try:
        # Try Redis cache first (if available)
        from services.redis_client import get_redis
        redis_client = get_redis()
        if redis_client:
            cached = redis_client.get(cache_key)
            if cached is not None:
                return {"count": int(cached), "cached": True}
    except Exception:
        pass  # Redis not available, fallback to DB
    
    try:
        # Query database
        count = await db.notifications.count_documents(
            {"user_id": user_id, "is_read": False}
        )
        
        # Cache the result for 30 seconds
        try:
            if redis_client:
                redis_client.setex(cache_key, 30, count)
        except Exception:
            pass  # Cache write failure is non-critical
        
        return {"count": count, "cached": False}
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[Notifications] Transient DB error on unread-count: {e}")
        return {"count": 0, "cached": False}


@notification_router.get("/stream")
async def notification_stream(
    request: Request,
    token: Optional[str] = Query(None, description="JWT — required because EventSource cannot set headers"),
):
    """
    SSE stream that pushes the unread notification count to the browser.
    Replaces the 120s HTTP polling loop.

    Auth: `?token=<jwt>` (EventSource can't set Authorization headers).
    Falls back to the Authorization header if a client sends one (fetch-based EventSource polyfills).

    Wire protocol:
      • On connect: emits `event: count` with the current unread count.
      • On any create/read/delete for this user (same worker): emits a
        fresh `event: count` within ~100ms.
      • Every 60s: emits either an updated `event: count` (if it changed
        cross-worker) or a `: ping` comment to keep the connection alive
        through proxies. The `count_documents` query hits Mongo at most
        once/minute per open tab — same as the old polling load, but
        with far better UX (instant same-worker updates + no HTTP
        request/response overhead).
    """
    current_user = await get_current_user_from_token(request, token_param=token)
    user_id = current_user["id"]

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        _user_events[user_id].add(queue)
        last_count = None

        async def read_count() -> int:
            try:
                return await db.notifications.count_documents(
                    {"user_id": user_id, "is_read": False}
                )
            except Exception as e:
                logger.warning(f"[Notifications SSE] count query failed: {e}")
                return last_count if last_count is not None else 0

        try:
            # Initial push so the badge is correct the moment the tab opens.
            count = await read_count()
            last_count = count
            yield f"event: count\ndata: {count}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                # Wait for either a same-worker push or the 60s heartbeat.
                try:
                    await asyncio.wait_for(queue.get(), timeout=60.0)
                    triggered_by_push = True
                except asyncio.TimeoutError:
                    triggered_by_push = False

                count = await read_count()
                if count != last_count:
                    last_count = count
                    yield f"event: count\ndata: {count}\n\n"
                elif not triggered_by_push:
                    # Heartbeat comment — keeps proxies (nginx, cloudflare)
                    # from closing an idle connection. Clients ignore it.
                    yield ": ping\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            # Browser aborted the connection (tab close / route change).
            # Swallowing here stops the h11 "state is ERROR" tracebacks
            # from polluting backend.err.log.
            return
        finally:
            _user_events[user_id].discard(queue)
            if not _user_events[user_id]:
                _user_events.pop(user_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Disable nginx response buffering — critical for SSE.
            "X-Accel-Buffering": "no",
        },
    )


@notification_router.put("/{notification_id}/read")
async def mark_as_read(notification_id: str, current_user: dict = Depends(get_current_user)):
    """Mark a single notification as read."""
    result = await db.notifications.update_one(
        {"id": notification_id, "user_id": current_user["id"]},
        {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    _publish_unread_change(current_user["id"])
    return {"success": True}


@notification_router.put("/read-all")
async def mark_all_read(current_user: dict = Depends(get_current_user)):
    """Mark all notifications as read."""
    result = await db.notifications.update_many(
        {"user_id": current_user["id"], "is_read": False},
        {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
    )
    _publish_unread_change(current_user["id"])
    return {"success": True, "marked": result.modified_count}


@notification_router.delete("/{notification_id}")
async def delete_notification(notification_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a notification."""
    result = await db.notifications.delete_one(
        {"id": notification_id, "user_id": current_user["id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    _publish_unread_change(current_user["id"])
    return {"success": True}


@notification_router.get("/preferences")
async def get_preferences(current_user: dict = Depends(get_current_user)):
    """Get notification preferences."""
    prefs = await db.notification_preferences.find_one(
        {"user_id": current_user["id"]}, {"_id": 0}
    )
    if not prefs:
        prefs = {
            "user_id": current_user["id"],
            "new_application": True,
            "status_change": True,
            "job_posted": True,
            "job_assigned": True,
            "candidate_assigned": True,
            "am_company_assigned": True,
        }
    return prefs


@notification_router.put("/preferences")
async def update_preferences(
    prefs: NotificationPreferences,
    current_user: dict = Depends(get_current_user),
):
    """Update notification preferences."""
    await db.notification_preferences.update_one(
        {"user_id": current_user["id"]},
        {"$set": {
            "user_id": current_user["id"],
            **prefs.model_dump(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return {"success": True, "message": "Preferences updated"}
