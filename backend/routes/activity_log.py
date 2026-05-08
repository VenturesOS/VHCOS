"""
Activity Log API routes.
Endpoints for fetching candidate-level and global activity feeds.
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from utils.auth import get_current_user
from services.activity_log_service import (
    get_candidate_activity,
    get_global_activity,
    get_activity_stats,
    ACTION_LABELS,
    ACTION_STYLES,
)

activity_router = APIRouter(prefix="/api/activity", tags=["Activity Log"])


@activity_router.get("/candidate/{candidate_id}")
async def candidate_activity_log(
    candidate_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    action: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Get activity timeline for a specific candidate."""
    return await get_candidate_activity(candidate_id, page, limit, action)


@activity_router.get("/feed")
async def global_activity_feed(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Get global activity feed across all candidates."""
    return await get_global_activity(page, limit, action, user_id)


@activity_router.get("/stats")
async def activity_statistics(
    candidate_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Get activity statistics, optionally scoped to a candidate."""
    return await get_activity_stats(candidate_id)


@activity_router.get("/actions")
async def available_actions(user: dict = Depends(get_current_user)):
    """Get available action types for filtering."""
    return {
        "actions": [
            {"value": k, "label": v, "style": ACTION_STYLES.get(k, {})}
            for k, v in ACTION_LABELS.items()
        ]
    }
