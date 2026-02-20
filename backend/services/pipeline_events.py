"""
Pipeline Events Service
Logs all stage transitions for audit, analytics, and tracker sync.
Every pipeline/tracker action generates an event for the tracker_events collection.
"""
import uuid
import logging
from datetime import datetime, timezone
from config import db

logger = logging.getLogger(__name__)

# Canonical stage order
PIPELINE_STAGES = [
    "applied",
    "shortlisted",
    "submitted_to_client",
    "interview",
    "offered",
    "hired",
    "joined",
]

PARALLEL_STATUSES = ["rejected", "on_hold"]

ALL_VALID_STAGES = PIPELINE_STAGES + PARALLEL_STATUSES

# Revenue probability mapping
STAGE_REVENUE_PROBABILITY = {
    "applied": 0,
    "shortlisted": 5,
    "submitted_to_client": 15,
    "interview": 30,
    "offered": 60,
    "hired": 85,
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
    """
    if new_stage not in ALL_VALID_STAGES:
        return False, f"Invalid stage: {new_stage}"

    # Parallel statuses can be set from any stage
    if new_stage in PARALLEL_STATUSES:
        return True, None

    # From parallel back to pipeline is allowed
    if current_stage in PARALLEL_STATUSES:
        return True, None

    # Cannot move to hired without going through offered
    if new_stage == "hired" and current_stage != "offered":
        cur_idx = get_stage_index(current_stage)
        offered_idx = get_stage_index("offered")
        if cur_idx < offered_idx:
            return False, "Cannot move to hired without going through offered stage first."

    # Cannot skip directly to joined without hired
    if new_stage == "joined" and current_stage != "hired":
        cur_idx = get_stage_index(current_stage)
        hired_idx = get_stage_index("hired")
        if cur_idx < hired_idx:
            return False, "Cannot move to joined without going through hired stage first."

    # Joined is terminal — cannot move back from joined
    if current_stage == "joined" and new_stage != "joined":
        return False, "Joined stage is locked. Cannot change stage."

    return True, None
