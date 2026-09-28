"""
Pipeline Events Service
Logs all stage transitions for audit, analytics, and tracker sync.
Every pipeline/tracker action generates an event for the tracker_events collection.
"""
import uuid
import re
import logging
from typing import Optional
from datetime import datetime, timezone
from config import db

logger = logging.getLogger(__name__)

# Canonical stage order (simplified flow, no employer approval gate)
# Sourced → Submitted → Shortlisted → Interviewed → Offered → Hired → Joined
PIPELINE_STAGES = [
    "sourced",
    "submitted_to_client",
    "shortlisted",
    "interview",
    "offered",
    "hired",
    "joined",
]

# Parallel statuses shown at the bottom. `rejected` auto-hides after 7 days (display filter).
PARALLEL_STATUSES = ["rejected", "on_hold"]

ALL_VALID_STAGES = PIPELINE_STAGES + PARALLEL_STATUSES

# Revenue probability mapping
STAGE_REVENUE_PROBABILITY = {
    "sourced": 0,
    "submitted_to_client": 10,
    "shortlisted": 20,
    "interview": 40,
    "offered": 70,
    "hired": 90,
    "joined": 100,
    "rejected": 0,
    "on_hold": 0,
}


def get_stage_index(stage: str) -> int:
    """Return the ordinal position of a stage in the pipeline. -1 for parallel."""
    try:
        return PIPELINE_STAGES.index(stage)
    except ValueError:
        return -1


REJECTED_VISIBLE_DAYS = 7


def rejected_cutoff() -> str:
    """Rejections drop off the board after 7 days (data is kept)."""
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=REJECTED_VISIBLE_DAYS)).isoformat()


def stage_display_clause(stage: str) -> Optional[dict]:
    """Extra match clause for a single-stage board query.

    Only rejections age out, so every other stage needs no clause at all —
    which keeps the query on the `job_id + stage + updated_at` index instead
    of falling back to a collection scan (a `$nor` filter cost 7s on the
    employer board; this costs 0.4s).
    """
    if stage != "rejected":
        return None
    return {"updated_at": {"$gte": rejected_cutoff()}}


def candidate_search_filter(q: Optional[str]) -> Optional[dict]:
    """Name / email / phone match for the pipeline search box.

    Returns None when there is nothing to search, so callers can drop the
    clause entirely instead of matching everything.
    """
    term = (q or "").strip()
    if len(term) < 2:
        return None
    rx = re.escape(term)
    return {"$or": [
        {"candidate_name": {"$regex": rx, "$options": "i"}},
        {"candidate_email": {"$regex": rx, "$options": "i"}},
        {"candidate_phone": {"$regex": rx, "$options": "i"}},
    ]}


def pipeline_display_filter() -> dict:
    """MongoDB filter to hide noise from pipeline views.

    Extension captures ARE part of the pipeline: a profile captured against
    the selected mandate lands in that mandate's Sourced column (user spec,
    Sep 2026). The only thing hidden is a rejection older than 7 days —
    the data stays, it just leaves the board.
    """
    from datetime import timedelta
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    return {
        "$nor": [
            {"$and": [
                {"stage": "rejected"},
                {"updated_at": {"$lt": seven_days_ago}},
            ]},
        ]
    }


async def log_pipeline_event(
    candidate_id: str,
    mandate_id: str,
    application_id: str,
    previous_stage: str,
    new_stage: str,
    source: str,
    user_id: str = "",
    user_name: str = "",
    metadata: dict = None,
):
    """
    Log a pipeline stage transition event.
    source: 'tracker' | 'pipeline' | 'system' | 'user' | 'revenue'
    """
    event = {
        "id": str(uuid.uuid4()),
        "candidate_id": candidate_id,
        "mandate_id": mandate_id,
        "application_id": application_id,
        "previous_stage": previous_stage,
        "new_stage": new_stage,
        "source": source,
        "user_id": user_id,
        "user_name": user_name,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.tracker_events.insert_one(event)
        logger.info(
            f"[PipelineEvent] {application_id}: {previous_stage} → {new_stage} (source={source})"
        )
    except Exception as e:
        logger.error(f"[PipelineEvent] Failed to log event: {e}")
    return event


def validate_stage_transition(current_stage: str, new_stage: str) -> tuple:
    """
    Validate whether a stage transition is allowed.
    Returns (is_valid: bool, error_message: str | None)
    
    All transitions are allowed freely for admin/employer/recruiter.
    Only checks that the target stage is a known valid stage.
    """
    if new_stage not in ALL_VALID_STAGES:
        return False, f"Invalid stage: {new_stage}"

    return True, None
