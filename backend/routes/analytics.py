"""
VHC Talent OS - Analytics Routes
Admin-only analytics dashboard API + Pipeline conversion + Revenue intelligence.
"""
import io
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from utils.auth import require_role
from services.analytics_service import get_analytics_summary
from services.pipeline_events import STAGE_REVENUE_PROBABILITY, PIPELINE_STAGES
from config import db

analytics_router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@analytics_router.get("/admin")
async def admin_analytics(
    employer_id: Optional[str] = None,
    team_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"])),
):
    """Advanced analytics dashboard data — admin only."""
    return await get_analytics_summary(
        employer_id=employer_id,
        team_id=team_id,
        recruiter_id=recruiter_id,
        date_from=date_from,
        date_to=date_to,
    )


@analytics_router.get("/admin/export-pdf")
async def export_analytics_pdf(
    employer_id: Optional[str] = None,
    team_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"])),
):
    """Export analytics dashboard as PDF — admin only."""
    data = await get_analytics_summary(
        employer_id=employer_id,
        team_id=team_id,
        recruiter_id=recruiter_id,
        date_from=date_from,
        date_to=date_to,
    )

    from services.analytics_pdf import build_analytics_pdf
    buf = build_analytics_pdf(data, date_from, date_to)

    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    filename = f"VHC_Analytics_{now_str}.pdf"

    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Pipeline Conversion Rates ──

@analytics_router.get("/pipeline-conversion")
async def get_pipeline_conversion(
    mandate_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(require_role(["admin", "employer"])),
):
    """Conversion rates between pipeline stages."""
    query = {}
    if mandate_id:
        query["job_id"] = mandate_id
    if recruiter_id:
        query["assigned_recruiter_id"] = recruiter_id
    if from_date:
        query["created_at"] = {"$gte": from_date}
    if to_date:
        query.setdefault("created_at", {})["$lte"] = to_date

    agg = [{"$match": query}, {"$group": {"_id": "$stage", "count": {"$sum": 1}}}]
    results = await db.applications.aggregate(agg).to_list(50)
    counts = {r["_id"]: r["count"] for r in results}
    total = sum(counts.values())

    # Cumulative: all apps that reached a stage or beyond
    shortlisted = sum(counts.get(s, 0) for s in PIPELINE_STAGES[1:])
    submitted = sum(counts.get(s, 0) for s in PIPELINE_STAGES[2:])
    interviewed = sum(counts.get(s, 0) for s in PIPELINE_STAGES[3:])
    offered = sum(counts.get(s, 0) for s in PIPELINE_STAGES[4:])
    hired = sum(counts.get(s, 0) for s in PIPELINE_STAGES[5:])
    joined = counts.get("joined", 0)

    def rate(num, den):
        return round((num / den) * 100, 1) if den > 0 else 0

    return {
        "stage_counts": counts,
        "total_applications": total,
        "conversions": {
            "applied_to_shortlisted": {"count": shortlisted, "rate": rate(shortlisted, total)},
            "shortlisted_to_submitted": {"count": submitted, "rate": rate(submitted, shortlisted)},
            "submitted_to_interview": {"count": interviewed, "rate": rate(interviewed, submitted)},
            "interview_to_offered": {"count": offered, "rate": rate(offered, interviewed)},
            "offered_to_hired": {"count": hired, "rate": rate(hired, offered)},
            "hired_to_joined": {"count": joined, "rate": rate(joined, hired)},
        },
    }


# ── Revenue Forecast ──

@analytics_router.get("/revenue-forecast")
async def get_revenue_forecast(
    mandate_id: Optional[str] = None,
    employer_id: Optional[str] = None,
    user=Depends(require_role(["admin", "employer"])),
):
    """Revenue forecast vs realized across pipeline stages."""
    query = {"offered_ctc": {"$exists": True, "$ne": None}}
    if mandate_id:
        query["job_id"] = mandate_id

    apps = await db.applications.find(query, {
        "_id": 0, "id": 1, "stage": 1, "candidate_name": 1, "job_id": 1,
        "offered_ctc": 1, "forecast_revenue": 1, "join_date": 1,
    }).to_list(10000)

    if employer_id:
        employer_jobs = await db.jobs.find({"posted_by": employer_id}, {"_id": 0, "id": 1}).to_list(10000)
        job_ids = {j["id"] for j in employer_jobs}
        apps = [a for a in apps if a.get("job_id") in job_ids]

    forecast_pipeline = 0
    realized_revenue = 0
    by_stage = {}

    for app in apps:
        stage = app.get("stage", "applied")
        prob = STAGE_REVENUE_PROBABILITY.get(stage, 0)
        rev = app.get("forecast_revenue", 0) or 0
        weighted = rev * (prob / 100)
        forecast_pipeline += weighted
        if stage == "joined":
            realized_revenue += rev
        by_stage.setdefault(stage, {"count": 0, "total_revenue": 0, "weighted_revenue": 0, "probability": prob})
        by_stage[stage]["count"] += 1
        by_stage[stage]["total_revenue"] += rev
        by_stage[stage]["weighted_revenue"] += weighted

    return {
        "total_forecast_pipeline": round(forecast_pipeline, 2),
        "total_realized_revenue": round(realized_revenue, 2),
        "total_candidates_with_offer": len(apps),
        "by_stage": by_stage,
        "probability_map": STAGE_REVENUE_PROBABILITY,
    }


# ── Recruiter Performance ──

@analytics_router.get("/recruiter-performance")
async def get_recruiter_performance(
    user=Depends(require_role(["admin"])),
):
    """Recruiter-level: submissions, conversions, revenue contribution."""
    agg = [
        {"$group": {
            "_id": "$assigned_recruiter_id",
            "total": {"$sum": 1},
            "submitted": {"$sum": {"$cond": [{"$in": ["$stage", ["submitted_to_client", "interview", "offered", "hired", "joined"]]}, 1, 0]}},
            "offered": {"$sum": {"$cond": [{"$in": ["$stage", ["offered", "hired", "joined"]]}, 1, 0]}},
            "joined": {"$sum": {"$cond": [{"$eq": ["$stage", "joined"]}, 1, 0]}},
            "rejected": {"$sum": {"$cond": [{"$eq": ["$stage", "rejected"]}, 1, 0]}},
            "total_revenue": {"$sum": {"$ifNull": ["$forecast_revenue", 0]}},
        }},
    ]
    results = await db.applications.aggregate(agg).to_list(500)

    recruiter_ids = [r["_id"] for r in results if r["_id"]]
    recruiters = {}
    if recruiter_ids:
        users = await db.users.find({"id": {"$in": recruiter_ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(500)
        recruiters = {u["id"]: u.get("name", u.get("email", "")) for u in users}

    perf = []
    for r in results:
        rid = r["_id"]
        if not rid:
            continue
        perf.append({
            "recruiter_id": rid,
            "recruiter_name": recruiters.get(rid, "Unknown"),
            "total_candidates": r["total"],
            "submitted": r["submitted"],
            "offered": r["offered"],
            "joined": r["joined"],
            "rejected": r["rejected"],
            "total_revenue": round(r["total_revenue"], 2),
            "conversion_rate": round((r["joined"] / r["total"]) * 100, 1) if r["total"] > 0 else 0,
        })
    perf.sort(key=lambda x: x["total_revenue"], reverse=True)
    return {"recruiters": perf}


# ── Mandate Performance ──

@analytics_router.get("/mandate-performance")
async def get_mandate_performance(
    employer_id: Optional[str] = None,
    user=Depends(require_role(["admin", "employer"])),
):
    """Mandate-level metrics: applications, conversion, revenue."""
    agg = [
        {"$group": {
            "_id": "$job_id",
            "total": {"$sum": 1},
            "submitted": {"$sum": {"$cond": [{"$in": ["$stage", ["submitted_to_client", "interview", "offered", "hired", "joined"]]}, 1, 0]}},
            "offered": {"$sum": {"$cond": [{"$in": ["$stage", ["offered", "hired", "joined"]]}, 1, 0]}},
            "joined": {"$sum": {"$cond": [{"$eq": ["$stage", "joined"]}, 1, 0]}},
            "total_revenue": {"$sum": {"$ifNull": ["$forecast_revenue", 0]}},
        }},
    ]
    results = await db.applications.aggregate(agg).to_list(500)

    job_ids = [r["_id"] for r in results if r["_id"]]
    jobs = {}
    if job_ids:
        job_docs = await db.jobs.find({"id": {"$in": job_ids}}, {"_id": 0, "id": 1, "title": 1, "company_name": 1, "posted_by": 1}).to_list(500)
        jobs = {j["id"]: j for j in job_docs}

    mandates = []
    for r in results:
        jid = r["_id"]
        if not jid:
            continue
        job = jobs.get(jid, {})
        if employer_id and job.get("posted_by") != employer_id:
            continue
        mandates.append({
            "mandate_id": jid,
            "mandate_name": job.get("title", "Unknown"),
            "company": job.get("company_name", ""),
            "total_candidates": r["total"],
            "submitted": r["submitted"],
            "offered": r["offered"],
            "joined": r["joined"],
            "total_revenue": round(r["total_revenue"], 2),
            "submission_rate": round((r["submitted"] / r["total"]) * 100, 1) if r["total"] > 0 else 0,
        })
    mandates.sort(key=lambda x: x["total_revenue"], reverse=True)
    return {"mandates": mandates}

