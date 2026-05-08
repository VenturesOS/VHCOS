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

# Legacy stages kept in valid set so historical records still pass validation,
# but they no longer appear in new pipelines.
LEGACY_STAGES = ["applied", "employer_approved", "employer_rejected"]

ALL_VALID_STAGES = PIPELINE_STAGES + PARALLEL_STATUSES + LEGACY_STAGES

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
    # Legacy — kept so historical reports don't KeyError
    "applied": 0,
    "employer_approved": 25,
    "employer_rejected": 0,
}


def get_stage_index(stage: str) -> int:
    """Return the ordinal position of a stage in the pipeline. -1 for parallel."""
    try:
        return PIPELINE_STAGES.index(stage)
    except ValueError:
        return -1


def pipeline_display_filter() -> dict:
    """MongoDB filter to hide noise from pipeline views.

    Rules (per user spec, Apr 2026):
      1. Only "Added as Applicant" candidates appear in the Sourced column —
         extension auto-captures (source='extension_capture') stay in the
         Candidate Bank and DO NOT clutter the pipeline.
      2. Rejected applications auto-disappear after 7 days (data retained,
         just hidden from the board).
    """
    from datetime import timedelta
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    return {
        "$nor": [
            # Rule 1 — extension sourced clutter
            {"$and": [
                {"stage": "sourced"},
                {"source": "extension_capture"},
            ]},
            # Rule 2 — stale rejections
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
        
        # Notify employer when recruiter shortlists a candidate
        if new_stage == "shortlisted" and previous_stage != "shortlisted":
            try:
                # Find the job to get the employer/team info
                application = await db.applications.find_one({"id": application_id}, {"_id": 0})
                if application:
                    job = await db.jobs.find_one({"id": application.get("job_id")}, {"_id": 0})
                    if job:
                        # Find employer(s) in the team
                        team_id = job.get("team_id")
                        employer_ids = []
                        if team_id:
                            team = await db.teams.find_one({"id": team_id}, {"_id": 0})
                            if team and team.get("employer_id"):
                                employer_ids.append(team["employer_id"])
                        
                        # Also notify the job poster if they're an employer
                        if job.get("posted_by_role") == "employer" and job.get("posted_by") not in employer_ids:
                            employer_ids.append(job["posted_by"])
                        
                        # Create in-app notifications for employers
                        candidate_name = application.get("candidate_name", "A candidate")
                        job_title = job.get("title", "a job")
                        
                        for emp_id in employer_ids:
                            notification = {
                                "id": str(uuid.uuid4()),
                                "user_id": emp_id,
                                "type": "candidate_shortlisted",
                                "title": "Candidate Shortlisted - Approval Needed",
                                "message": f"{user_name} shortlisted {candidate_name} for '{job_title}'. Please review and approve/reject.",
                                "application_id": application_id,
                                "job_id": application.get("job_id"),
                                "read": False,
                                "created_at": datetime.now(timezone.utc).isoformat(),
                            }
                            await db.notifications.insert_one(notification)
                        
                        logger.info(f"[PipelineEvent] Notified {len(employer_ids)} employer(s) about shortlisted candidate")
            except Exception as notify_err:
                logger.error(f"[PipelineEvent] Failed to send employer notification: {notify_err}")
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
