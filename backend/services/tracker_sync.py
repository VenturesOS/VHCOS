"""
Tracker ↔ Pipeline Bidirectional Sync Service
- Tracker actions update pipeline stages
- Pipeline changes update tracker rows
- All changes logged to tracker_events
"""
import logging
from datetime import datetime, timezone
from config import db
from services.pipeline_events import log_pipeline_event, validate_stage_transition

logger = logging.getLogger(__name__)

# Tracker submission_status → pipeline stage mapping
TRACKER_TO_PIPELINE = {
    "submitted": "submitted_to_client",
    "interview_scheduled": "interview",
    "interviewed": "interview",
    "offer_issued": "offered",
    "offer_accepted": "hired",
    "joining_confirmed": "joined",
}

# Pipeline stage → tracker submission_status mapping
PIPELINE_TO_TRACKER = {
    "submitted_to_client": "submitted",
    "interview": "interviewed",
    "offered": "offer_issued",
    "hired": "offer_accepted",
    "joined": "joining_confirmed",
    "rejected": "rejected",
    "on_hold": "on_hold",
}


async def sync_tracker_to_pipeline(
    row_id: str,
    application_id: str,
    new_submission_status: str,
    user_id: str = "",
    user_name: str = "",
):
    """
    Rule A: Tracker action → Pipeline stage update.
    Called when tracker row submission_status changes.
    """
    target_stage = TRACKER_TO_PIPELINE.get(new_submission_status)
    if not target_stage:
        return  # No mapping for this status

    application = await db.applications.find_one(
        {"id": application_id}, {"_id": 0, "stage": 1, "candidate_id": 1, "job_id": 1}
    )
    if not application:
        logger.warning(f"[TrackerSync] Application {application_id} not found")
        return

    current_stage = application.get("stage", "applied")
    if current_stage == target_stage:
        return  # Already at correct stage

    is_valid, error = validate_stage_transition(current_stage, target_stage)
    if not is_valid:
        logger.warning(f"[TrackerSync] Invalid transition {current_stage}→{target_stage}: {error}")
        return

    now = datetime.now(timezone.utc).isoformat()
    await db.applications.update_one(
        {"id": application_id},
        {"$set": {"stage": target_stage, "updated_at": now}}
    )

    await log_pipeline_event(
        candidate_id=application.get("candidate_id", ""),
        mandate_id=application.get("job_id", ""),
        application_id=application_id,
        previous_stage=current_stage,
        new_stage=target_stage,
        source="tracker",
        user_id=user_id,
        user_name=user_name,
        metadata={"tracker_row_id": row_id, "submission_status": new_submission_status},
    )

    logger.info(f"[TrackerSync] Tracker→Pipeline: {application_id} {current_stage}→{target_stage}")


async def sync_pipeline_to_tracker(
    application_id: str,
    new_stage: str,
    user_id: str = "",
    user_name: str = "",
):
    """
    Rule B: Pipeline stage change → Tracker row update.
    Called when pipeline stage changes (from applications.py).
    Updates all tracker rows for this application.
    """
    new_status = PIPELINE_TO_TRACKER.get(new_stage)
    if not new_status:
        return  # No tracker mapping for this stage

    now = datetime.now(timezone.utc).isoformat()
    result = await db.tracker_rows.update_many(
        {"application_id": application_id},
        {"$set": {
            "pipeline_stage": new_stage,
            "submission_status": new_status,
            "updated_at": now,
        }}
    )

    if result.modified_count > 0:
        logger.info(
            f"[TrackerSync] Pipeline→Tracker: {application_id} → {new_status} ({result.modified_count} rows)"
        )


async def add_candidate_to_tracker(
    tracker_id: str,
    candidate_id: str,
    application_id: str,
    mandate_id: str,
    row_data: dict,
    user_id: str = "",
    user_name: str = "",
):
    """
    Add a candidate to a submission tracker.
    Auto-moves pipeline to submitted_to_client.
    Returns the created row.
    """
    import uuid

    # Check duplicate: same candidate + same mandate in this tracker
    existing = await db.tracker_rows.find_one(
        {"tracker_id": tracker_id, "candidate_id": candidate_id, "mandate_id": mandate_id},
        {"_id": 0, "id": 1}
    )
    if existing:
        return None, "Candidate already submitted for this mandate in this tracker."

    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": str(uuid.uuid4()),
        "tracker_id": tracker_id,
        "candidate_id": candidate_id,
        "application_id": application_id,
        "mandate_id": mandate_id,
        "pipeline_stage": "submitted_to_client",
        "submission_status": "submitted",
        "data": row_data,
        "created_by": user_id,
        "created_at": now,
        "updated_at": now,
    }
    await db.tracker_rows.insert_one(row)

    # Sync: move pipeline to submitted_to_client
    await sync_tracker_to_pipeline(
        row_id=row["id"],
        application_id=application_id,
        new_submission_status="submitted",
        user_id=user_id,
        user_name=user_name,
    )

    # Remove _id before returning
    row.pop("_id", None)
    return row, None
