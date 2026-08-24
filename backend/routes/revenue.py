"""
Revenue Routes — Forecast, offered/joined stage hooks, aggregation, role-based visibility.
Financial-critical. No silent fallbacks.
"""
import uuid
import logging
import copy
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from config import db
from utils import get_current_user, require_role
from services.revenue_engine import calculate_revenue, RevenueCalculationError

revenue_router = APIRouter(prefix="/api", tags=["Revenue"])
logger = logging.getLogger(__name__)


# ── Pydantic Models ──

class OfferStageInput(BaseModel):
    offered_ctc: float
    offer_date: str  # ISO date string


class JoinStageInput(BaseModel):
    join_date: str  # ISO date string


class HiredStageInput(BaseModel):
    date_of_joining: str  # Expected DOJ - ISO date string


class ForecastRequest(BaseModel):
    application_id: str
    expected_ctc: float


class RevenueAggregationQuery(BaseModel):
    from_date: str
    to_date: str


# ── Helper: Strip revenue fields for recruiter ──

def strip_revenue_fields(data: dict) -> dict:
    """Remove revenue-sensitive fields from dict."""
    for key in ["forecast_revenue", "final_revenue", "percentage_used",
                "slab_applied", "revenue_amount", "commercial_snapshot",
                "offered_ctc", "expected_ctc_at_offer"]:
        data.pop(key, None)
    return data


def _is_revenue_visible(user: dict) -> bool:
    """Only admin and employer can see revenue data."""
    return user.get("role") in ("admin", "employer")


# ── PART 2: Forecast Revenue ──

@revenue_router.post("/revenue/forecast")
async def calculate_forecast(
    req: ForecastRequest,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Calculate forecast revenue for a pipeline candidate. Not stored in revenue collection."""
    application = await db.applications.find_one({"id": req.application_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    job = await db.jobs.find_one({"id": application["job_id"]}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    company_id = job.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="Job has no company assigned")

    company = await db.companies.find_one({"id": company_id}, {"_id": 0, "commercial": 1, "name": 1})
    if not company or not company.get("commercial"):
        raise HTTPException(status_code=400, detail="Company has no commercial configured")

    try:
        result = calculate_revenue(req.expected_ctc, company["commercial"])
    except RevenueCalculationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Update application with forecast data (NOT in revenue collection)
    await db.applications.update_one(
        {"id": req.application_id},
        {"$set": {
            "expected_ctc": req.expected_ctc,
            "forecast_revenue": result["revenue_amount"],
            "forecast_slab": result["slab_applied"],
            "forecast_percentage": result["percentage_used"],
            "forecast_updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )

    return {
        "application_id": req.application_id,
        "expected_ctc": req.expected_ctc,
        **result,
    }


# ── PART 3: Offered Stage ──

@revenue_router.post("/revenue/offered/{app_id}")
async def process_offered_stage(
    app_id: str,
    req: OfferStageInput,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Process candidate moving to 'offered' stage.
    Creates revenue record with commercial snapshot. Logs slab changes.
    """
    if not req.offered_ctc or req.offered_ctc <= 0:
        raise HTTPException(status_code=400, detail="offered_ctc is required and must be > 0")
    if not req.offer_date:
        raise HTTPException(status_code=400, detail="offer_date is required")

    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Check if already joined — immutable
    existing_rev = await db.revenue.find_one({"application_id": app_id}, {"_id": 0})
    if existing_rev and existing_rev.get("revenue_status") == "joined":
        raise HTTPException(status_code=400, detail="Revenue record is locked after joined stage")

    job = await db.jobs.find_one({"id": application["job_id"]}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    company_id = job.get("company_id")
    company = await db.companies.find_one({"id": company_id}, {"_id": 0, "commercial": 1, "name": 1})
    if not company or not company.get("commercial"):
        raise HTTPException(status_code=400, detail="Company has no commercial configured")

    commercial = company["commercial"]

    try:
        result = calculate_revenue(req.offered_ctc, commercial)
    except RevenueCalculationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check slab shift from forecast
    slab_shift = None
    forecast_slab = application.get("forecast_slab")
    if forecast_slab and result["slab_applied"] and forecast_slab != result["slab_applied"]:
        slab_shift = {
            "previous_slab": forecast_slab,
            "new_slab": result["slab_applied"],
            "previous_percentage": application.get("forecast_percentage"),
            "new_percentage": result["percentage_used"],
        }
        logger.warning(
            f"[RevenueEngine] SLAB SHIFT for app {app_id}: "
            f"{forecast_slab} -> {result['slab_applied']}"
        )

    now = datetime.now(timezone.utc).isoformat()
    commercial_snapshot = copy.deepcopy(commercial)

    if existing_rev:
        # Update existing revenue record (re-offer scenario)
        await db.revenue.update_one(
            {"application_id": app_id},
            {"$set": {
                "offered_ctc": req.offered_ctc,
                "commercial_snapshot": commercial_snapshot,
                "slab_applied": result["slab_applied"],
                "percentage_used": result["percentage_used"],
                "final_revenue": result["revenue_amount"],
                "revenue_status": "offered",
                "offer_date": req.offer_date,
                "updated_at": now,
                "slab_shift_log": slab_shift,
            }}
        )
        revenue_id = existing_rev["id"]
    else:
        # Create new revenue record
        revenue_id = str(uuid.uuid4())
        rev_doc = {
            "id": revenue_id,
            "application_id": app_id,
            "candidate_id": application.get("candidate_id"),
            "candidate_name": application.get("candidate_name"),
            "recruiter_id": application.get("source_recruiter_id"),
            "job_id": application["job_id"],
            "job_title": job.get("title"),
            "company_id": company_id,
            "company_name": company.get("name"),
            "expected_ctc_at_offer": application.get("expected_ctc") or application.get("expected_salary"),
            "offered_ctc": req.offered_ctc,
            "commercial_snapshot": commercial_snapshot,
            "slab_applied": result["slab_applied"],
            "percentage_used": result["percentage_used"],
            "final_revenue": result["revenue_amount"],
            "revenue_status": "offered",
            "offer_date": req.offer_date,
            "join_date": None,
            "invoice_date": None,
            "slab_shift_log": slab_shift,
            "created_at": now,
            "created_by": current_user["id"],
        }
        await db.revenue.insert_one(rev_doc)

    # Update application stage and offered_ctc
    await db.applications.update_one(
        {"id": app_id},
        {"$set": {
            "stage": "offered",
            "offered_ctc": req.offered_ctc,
            "offer_date": req.offer_date,
            "updated_at": now,
        }}
    )

    response = {
        "revenue_id": revenue_id,
        "application_id": app_id,
        "offered_ctc": req.offered_ctc,
        "revenue_status": "offered",
        **result,
    }
    if slab_shift:
        response["slab_shift"] = slab_shift

    return response


# ── PART 3b: Hired Stage (Offer Accepted) ──

@revenue_router.post("/revenue/hired/{app_id}")
async def process_hired_stage(
    app_id: str,
    req: HiredStageInput,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Process candidate moving to 'hired' stage (offer accepted).
    Requires Date of Joining (DOJ). Updates revenue record with forecast date.
    """
    if not req.date_of_joining:
        raise HTTPException(status_code=400, detail="Date of Joining (DOJ) is required")

    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if not application.get("offered_ctc"):
        raise HTTPException(status_code=400, detail="Cannot move to hired: offered_ctc must be set via offered stage first")

    existing_rev = await db.revenue.find_one({"application_id": app_id}, {"_id": 0})
    if existing_rev and existing_rev.get("revenue_status") == "joined":
        raise HTTPException(status_code=400, detail="Revenue record is locked after joined stage")

    now = datetime.now(timezone.utc).isoformat()

    # Update revenue record with hired status and forecast date
    if existing_rev:
        await db.revenue.update_one(
            {"application_id": app_id},
            {"$set": {
                "revenue_status": "hired",
                "date_of_joining": req.date_of_joining,
                "revenue_probability": 85,
                "updated_at": now,
            }}
        )

    # Update application
    await db.applications.update_one(
        {"id": app_id},
        {"$set": {
            "stage": "hired",
            "join_date": req.date_of_joining,
            "updated_at": now,
        }}
    )

    # Log event
    from services.pipeline_events import log_pipeline_event
    await log_pipeline_event(
        candidate_id=application.get("candidate_id", ""),
        mandate_id=application.get("job_id", ""),
        application_id=app_id,
        previous_stage=application.get("stage", "offered"),
        new_stage="hired",
        source="revenue",
        user_id=current_user.get("id", ""),
        user_name=current_user.get("name", current_user.get("email", "")),
        metadata={"date_of_joining": req.date_of_joining},
    )

    return {
        "application_id": app_id,
        "stage": "hired",
        "date_of_joining": req.date_of_joining,
        "revenue_probability": 85,
        "final_revenue": existing_rev.get("final_revenue") if existing_rev else None,
    }


# ── PART 4: Joined Stage ──

@revenue_router.post("/revenue/joined/{app_id}")
async def process_joined_stage(
    app_id: str,
    req: JoinStageInput,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Process candidate moving to 'joined' stage.
    Locks revenue record. No further edits allowed.
    """
    if not req.join_date:
        raise HTTPException(status_code=400, detail="join_date is required")

    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if not application.get("offered_ctc"):
        raise HTTPException(status_code=400, detail="Cannot move to joined: offered_ctc is not set")

    rev = await db.revenue.find_one({"application_id": app_id}, {"_id": 0})
    if not rev:
        raise HTTPException(status_code=400, detail="No revenue record found. Process offered stage first.")

    if rev.get("revenue_status") == "joined":
        raise HTTPException(status_code=400, detail="Revenue record is already locked at joined stage")

    now = datetime.now(timezone.utc).isoformat()

    await db.revenue.update_one(
        {"application_id": app_id},
        {"$set": {
            "revenue_status": "joined",
            "join_date": req.join_date,
            "locked_at": now,
            "locked_by": current_user["id"],
        }}
    )

    await db.applications.update_one(
        {"id": app_id},
        {"$set": {
            "stage": "joined",
            "join_date": req.join_date,
            "updated_at": now,
        }}
    )

    return {
        "application_id": app_id,
        "revenue_status": "joined",
        "join_date": req.join_date,
        "final_revenue": rev["final_revenue"],
        "locked": True,
    }


# ── PART 5: Removed — aggregate/by-company, aggregate/by-job, aggregate/by-recruiter,
#           and records endpoints. 0 traffic in 90d (only consumed by the deleted
#           RevenueDashboardPage). Pipeline offered/hired/joined write path below
#           is still used by AdminPipelinePage.


# ── Get single revenue by application ──

@revenue_router.get("/revenue/by-application/{app_id}")
async def get_revenue_by_application(
    app_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get revenue record for a specific application."""
    if not _is_revenue_visible(current_user):
        return {"revenue": None, "message": "Revenue data not available for your role"}

    rev = await db.revenue.find_one({"application_id": app_id}, {"_id": 0})
    return {"revenue": rev}
