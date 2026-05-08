"""
Activity Log Service.
Centralized logging of ALL actions on candidate profiles.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from config import db

logger = logging.getLogger(__name__)

# Action types
ACTION_CAPTURED = "captured"
ACTION_UPDATED = "updated"
ACTION_CV_UPLOADED = "cv_uploaded"
ACTION_CV_REPLACED = "cv_replaced"
ACTION_APPLIED = "applied"
ACTION_LINKED = "linked"
ACTION_STAGE_CHANGED = "stage_changed"
ACTION_NOTE_ADDED = "note_added"
ACTION_APPROVAL = "approval"
ACTION_MATCH_SCORED = "match_scored"
ACTION_VIEWED = "viewed"
ACTION_SHORTLISTED = "shortlisted"
ACTION_REJECTED = "rejected"
ACTION_PROFILE_EDITED = "profile_edited"

# Human-readable labels
ACTION_LABELS = {
    ACTION_CAPTURED: "Profile Captured",
    ACTION_UPDATED: "Profile Updated",
    ACTION_CV_UPLOADED: "CV Uploaded",
    ACTION_CV_REPLACED: "CV Replaced",
    ACTION_APPLIED: "Applied to Job",
    ACTION_LINKED: "Linked to Job",
    ACTION_STAGE_CHANGED: "Stage Changed",
    ACTION_NOTE_ADDED: "Note Added",
    ACTION_APPROVAL: "Approval Decision",
    ACTION_MATCH_SCORED: "Match Score Generated",
    ACTION_VIEWED: "Profile Viewed",
    ACTION_SHORTLISTED: "Shortlisted",
    ACTION_REJECTED: "Rejected",
    ACTION_PROFILE_EDITED: "Profile Edited",
}

# Action icons/colors for frontend
ACTION_STYLES = {
    ACTION_CAPTURED: {"icon": "UserPlus", "color": "emerald"},
    ACTION_UPDATED: {"icon": "RefreshCw", "color": "blue"},
    ACTION_CV_UPLOADED: {"icon": "Upload", "color": "violet"},
    ACTION_CV_REPLACED: {"icon": "Replace", "color": "violet"},
    ACTION_APPLIED: {"icon": "Send", "color": "sky"},
    ACTION_LINKED: {"icon": "Link", "color": "sky"},
    ACTION_STAGE_CHANGED: {"icon": "ArrowRight", "color": "amber"},
    ACTION_NOTE_ADDED: {"icon": "MessageSquare", "color": "slate"},
    ACTION_APPROVAL: {"icon": "CheckCircle", "color": "green"},
    ACTION_MATCH_SCORED: {"icon": "Target", "color": "orange"},
    ACTION_VIEWED: {"icon": "Eye", "color": "gray"},
    ACTION_SHORTLISTED: {"icon": "Star", "color": "yellow"},
    ACTION_REJECTED: {"icon": "XCircle", "color": "red"},
    ACTION_PROFILE_EDITED: {"icon": "Edit", "color": "indigo"},
}


async def log_activity(
    candidate_id: str,
    action: str,
    description: str,
    performed_by: Optional[str] = None,
    performed_by_name: Optional[str] = None,
    performed_by_role: Optional[str] = None,
    candidate_name: Optional[str] = None,
    details: Optional[dict] = None,
):
    """Log an activity for a candidate. Fire-and-forget — never raises."""
    try:
        doc = {
            "id": str(uuid.uuid4()),
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "action": action,
            "action_label": ACTION_LABELS.get(action, action),
            "description": description,
            "details": details or {},
            "style": ACTION_STYLES.get(action, {"icon": "Activity", "color": "gray"}),
            "performed_by": performed_by or "system",
            "performed_by_name": performed_by_name or "System",
            "performed_by_role": performed_by_role or "system",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await db.activity_logs.insert_one(doc)
    except Exception as e:
        logger.error(f"[ActivityLog] Failed to log activity: {e}")


async def get_candidate_activity(candidate_id: str, page: int = 1, limit: int = 50, action_filter: Optional[str] = None):
    """Get activity log for a specific candidate."""
    query = {"candidate_id": candidate_id}
    if action_filter:
        query["action"] = action_filter

    total = await db.activity_logs.count_documents(query)
    skip = (page - 1) * limit

    cursor = db.activity_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit)
    entries = await cursor.to_list(length=limit)

    return {"total": total, "page": page, "limit": limit, "entries": entries}


async def get_global_activity(page: int = 1, limit: int = 50, action_filter: Optional[str] = None, user_filter: Optional[str] = None):
    """Get global activity feed across all candidates."""
    query = {}
    if action_filter:
        query["action"] = action_filter
    if user_filter:
        query["performed_by"] = user_filter

    # Exclude 'viewed' from global feed by default to reduce noise
    if not action_filter:
        query["action"] = {"$ne": ACTION_VIEWED}

    total = await db.activity_logs.count_documents(query)
    skip = (page - 1) * limit

    cursor = db.activity_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit)
    entries = await cursor.to_list(length=limit)

    return {"total": total, "page": page, "limit": limit, "entries": entries}


async def get_activity_stats(candidate_id: Optional[str] = None):
    """Get activity statistics."""
    match = {}
    if candidate_id:
        match["candidate_id"] = candidate_id

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$action",
            "count": {"$sum": 1},
            "last_at": {"$max": "$timestamp"},
        }},
        {"$sort": {"count": -1}},
    ]

    results = await db.activity_logs.aggregate(pipeline).to_list(length=50)
    stats = {}
    for r in results:
        stats[r["_id"]] = {
            "count": r["count"],
            "last_at": r["last_at"],
            "label": ACTION_LABELS.get(r["_id"], r["_id"]),
        }

    total = sum(s["count"] for s in stats.values())
    return {"total_actions": total, "by_action": stats}


async def ensure_activity_indexes():
    """Create indexes for activity log queries."""
    try:
        await db.activity_logs.create_index([("candidate_id", 1), ("timestamp", -1)])
        await db.activity_logs.create_index([("action", 1), ("timestamp", -1)])
        await db.activity_logs.create_index([("performed_by", 1), ("timestamp", -1)])
        await db.activity_logs.create_index("timestamp")
        logger.info("[ActivityLog] Indexes created")
    except Exception as e:
        logger.warning(f"[ActivityLog] Index creation failed: {e}")
