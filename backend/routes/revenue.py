"""
Revenue Routes — Forecast, offered/joined stage hooks, aggregation, role-based visibility.
Financial-critical. No silent fallbacks.
"""
import uuid
import logging
import copy
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
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


# ── PART 5: Aggregation ──

@revenue_router.get("/revenue/aggregate/by-company")
async def aggregate_revenue_by_company(
    from_date: str = Query(...),
    to_date: str = Query(...),
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Aggregate revenue by company for joined/invoiced records within date range."""
    pipeline = [
        {"$match": {
            "revenue_status": {"$in": ["joined", "invoiced"]},
            "join_date": {"$gte": from_date, "$lte": to_date},
        }},
        {"$group": {
            "_id": "$company_id",
            "company_name": {"$first": "$company_name"},
            "total_revenue": {"$sum": "$final_revenue"},
            "count": {"$sum": 1},
            "avg_ctc": {"$avg": "$offered_ctc"},
        }},
        {"$sort": {"total_revenue": -1}},
    ]
    results = await db.revenue.aggregate(pipeline).to_list(1000)
    for r in results:
        r["company_id"] = r.pop("_id")
        r["total_revenue"] = round(r["total_revenue"])
        r["avg_ctc"] = round(r.get("avg_ctc") or 0)
    return {"from_date": from_date, "to_date": to_date, "data": results}


@revenue_router.get("/revenue/aggregate/by-job")
async def aggregate_revenue_by_job(
    from_date: str = Query(...),
    to_date: str = Query(...),
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Aggregate revenue by job/mandate for joined/invoiced records."""
    pipeline = [
        {"$match": {
            "revenue_status": {"$in": ["joined", "invoiced"]},
            "join_date": {"$gte": from_date, "$lte": to_date},
        }},
        {"$group": {
            "_id": "$job_id",
            "job_title": {"$first": "$job_title"},
            "company_name": {"$first": "$company_name"},
            "total_revenue": {"$sum": "$final_revenue"},
            "count": {"$sum": 1},
            "avg_ctc": {"$avg": "$offered_ctc"},
        }},
        {"$sort": {"total_revenue": -1}},
    ]
    results = await db.revenue.aggregate(pipeline).to_list(1000)
    for r in results:
        r["job_id"] = r.pop("_id")
        r["total_revenue"] = round(r["total_revenue"])
        r["avg_ctc"] = round(r.get("avg_ctc") or 0)
    return {"from_date": from_date, "to_date": to_date, "data": results}


@revenue_router.get("/revenue/aggregate/by-recruiter")
async def aggregate_revenue_by_recruiter(
    from_date: str = Query(...),
    to_date: str = Query(...),
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Aggregate revenue by recruiter for joined/invoiced records."""
    pipeline = [
        {"$match": {
            "revenue_status": {"$in": ["joined", "invoiced"]},
            "join_date": {"$gte": from_date, "$lte": to_date},
        }},
        {"$group": {
            "_id": "$recruiter_id",
            "total_revenue": {"$sum": "$final_revenue"},
            "count": {"$sum": 1},
            "avg_ctc": {"$avg": "$offered_ctc"},
        }},
        {"$sort": {"total_revenue": -1}},
    ]
    results = await db.revenue.aggregate(pipeline).to_list(1000)

    # Enrich with recruiter names
    recruiter_ids = [r["_id"] for r in results if r["_id"]]
    if recruiter_ids:
        recruiters = await db.users.find(
            {"id": {"$in": recruiter_ids}}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(len(recruiter_ids))
        name_map = {r["id"]: r["name"] for r in recruiters}
    else:
        name_map = {}

    for r in results:
        r["recruiter_id"] = r.pop("_id")
        r["recruiter_name"] = name_map.get(r["recruiter_id"], "Unknown")
        r["total_revenue"] = round(r["total_revenue"])
        r["avg_ctc"] = round(r.get("avg_ctc") or 0)

    return {"from_date": from_date, "to_date": to_date, "data": results}


# ── PART 6: Revenue Records (role-filtered) ──

@revenue_router.get("/revenue/records")
async def get_revenue_records(
    company_id: Optional[str] = None,
    job_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get revenue records. Recruiter role gets empty response."""
    if not _is_revenue_visible(current_user):
        return {"records": [], "message": "Revenue data not available for your role"}

    query = {}
    if company_id:
        query["company_id"] = company_id
    if job_id:
        query["job_id"] = job_id
    if status:
        query["revenue_status"] = status

    # Employer: restrict to assigned companies
    if current_user["role"] == "employer":
        assigned = await db.companies.find(
            {"assigned_employer_id": current_user["id"]},
            {"_id": 0, "id": 1}
        ).to_list(1000)
        query["company_id"] = {"$in": [c["id"] for c in assigned]}

    records = await db.revenue.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"records": records}


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
