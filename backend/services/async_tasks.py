"""
Async Task Service — Fire-and-forget background tasks with polling support.
Used for heavy operations (CV parsing, batch imports) that would otherwise
block Gunicorn workers and cause 502s.
"""
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from config import db

logger = logging.getLogger(__name__)


async def create_task(task_type: str, user_id: str, metadata: dict = None) -> str:
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.parse_tasks.insert_one({
        "id": task_id,
        "type": task_type,
        "status": "processing",
        "created_at": now,
        "updated_at": now,
        "created_by": user_id,
        "metadata": metadata or {},
        "result": None,
        "error": None,
    })
    return task_id


async def complete_task(task_id: str, result: dict):
    await db.parse_tasks.update_one(
        {"id": task_id},
        {"$set": {
            "status": "completed",
            "result": result,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )


async def fail_task(task_id: str, error: str):
    await db.parse_tasks.update_one(
        {"id": task_id},
        {"$set": {
            "status": "failed",
            "error": error,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )


async def get_task(task_id: str) -> dict | None:
    return await db.parse_tasks.find_one({"id": task_id}, {"_id": 0})


def fire_and_forget(coro):
    """Schedule a coroutine as a background task with error logging."""
    task = asyncio.create_task(coro)
    task.add_done_callback(_handle_task_exception)
    return task


def _handle_task_exception(task: asyncio.Task):
    try:
        exc = task.exception()
        if exc:
            logger.error(f"[AsyncTask] Background task failed: {exc}", exc_info=exc)
    except asyncio.CancelledError:
        pass
