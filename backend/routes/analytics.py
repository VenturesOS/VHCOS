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



@analytics_router.get("/export-combined-pdf")
async def export_combined_analytics_pdf(
    employer_id: Optional[str] = None,
    team_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"])),
):
    """Export all analytics sections as a single PDF: Revenue > Pipeline > Performance > Overview."""
    import asyncio

    # Fetch all 4 datasets in parallel
    overview_task = get_analytics_summary(
        employer_id=employer_id, team_id=team_id, recruiter_id=recruiter_id,
        date_from=date_from, date_to=date_to,
    )

    query_pipe = {}
    if recruiter_id:
        query_pipe["assigned_recruiter_id"] = recruiter_id
    if date_from:
        query_pipe["created_at"] = {"$gte": date_from}
    if date_to:
        query_pipe.setdefault("created_at", {})["$lte"] = date_to

    async def get_pipeline():
        agg = [{"$match": query_pipe}, {"$group": {"_id": "$stage", "count": {"$sum": 1}}}] if query_pipe else [{"$group": {"_id": "$stage", "count": {"$sum": 1}}}]
        results = await db.applications.aggregate(agg).to_list(50)
        counts = {r["_id"]: r["count"] for r in results}
        # Funnel-cumulative counts (each stage = this + all downstream)
        sourced = sum(counts.get(s, 0) for s in ["sourced", "submitted_to_client", "shortlisted", "interview", "offered", "hired", "joined"])
        submitted = sum(counts.get(s, 0) for s in ["submitted_to_client", "shortlisted", "interview", "offered", "hired", "joined"])
        shortlisted = sum(counts.get(s, 0) for s in ["shortlisted", "interview", "offered", "hired", "joined"])
        interviewed = sum(counts.get(s, 0) for s in ["interview", "offered", "hired", "joined"])
        offered = sum(counts.get(s, 0) for s in ["offered", "hired", "joined"])
        hired = sum(counts.get(s, 0) for s in ["hired", "joined"])
        joined = counts.get("joined", 0)
        total = sum(counts.values())
        def rate(num, den):
            return round((num / den) * 100, 1) if den > 0 else 0
        return {"stage_counts": counts, "total_applications": total, "conversions": {
            # New simplified flow: Sourced → Submitted → Shortlisted → Interviewed → Offered → Hired → Joined
            "sourced_to_submitted": {"count": submitted, "rate": rate(submitted, sourced)},
            "submitted_to_shortlisted": {"count": shortlisted, "rate": rate(shortlisted, submitted)},
            "shortlisted_to_interview": {"count": interviewed, "rate": rate(interviewed, shortlisted)},
            "interview_to_offered": {"count": offered, "rate": rate(offered, interviewed)},
            "offered_to_hired": {"count": hired, "rate": rate(hired, offered)},
            "hired_to_joined": {"count": joined, "rate": rate(joined, hired)},
            # Legacy alias so old dashboards keep rendering
            "applied_to_shortlisted": {"count": shortlisted, "rate": rate(shortlisted, sourced)},
            "shortlisted_to_submitted": {"count": submitted, "rate": rate(submitted, shortlisted) if shortlisted else 0},
            "submitted_to_interview": {"count": interviewed, "rate": rate(interviewed, submitted)},
        }}

    async def get_revenue():
        rq = {"offered_ctc": {"$exists": True, "$ne": None}}
        apps = await db.applications.find(rq, {"_id": 0, "stage": 1, "forecast_revenue": 1}).to_list(10000)
        forecast_pipeline, realized_revenue = 0, 0
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
        return {"total_forecast_pipeline": round(forecast_pipeline, 2), "total_realized_revenue": round(realized_revenue, 2), "total_candidates_with_offer": len(apps), "by_stage": by_stage, "probability_map": STAGE_REVENUE_PROBABILITY}

    async def get_perf():
        rec_agg = [{"$group": {"_id": "$assigned_recruiter_id", "total": {"$sum": 1}, "submitted": {"$sum": {"$cond": [{"$in": ["$stage", ["submitted_to_client", "interview", "offered", "hired", "joined"]]}, 1, 0]}}, "offered": {"$sum": {"$cond": [{"$in": ["$stage", ["offered", "hired", "joined"]]}, 1, 0]}}, "joined": {"$sum": {"$cond": [{"$eq": ["$stage", "joined"]}, 1, 0]}}, "rejected": {"$sum": {"$cond": [{"$eq": ["$stage", "rejected"]}, 1, 0]}}, "total_revenue": {"$sum": {"$ifNull": ["$forecast_revenue", 0]}}}}]
        man_agg = [{"$group": {"_id": "$job_id", "total": {"$sum": 1}, "submitted": {"$sum": {"$cond": [{"$in": ["$stage", ["submitted_to_client", "interview", "offered", "hired", "joined"]]}, 1, 0]}}, "offered": {"$sum": {"$cond": [{"$in": ["$stage", ["offered", "hired", "joined"]]}, 1, 0]}}, "joined": {"$sum": {"$cond": [{"$eq": ["$stage", "joined"]}, 1, 0]}}, "total_revenue": {"$sum": {"$ifNull": ["$forecast_revenue", 0]}}}}]
        rec_results, man_results = await asyncio.gather(db.applications.aggregate(rec_agg).to_list(500), db.applications.aggregate(man_agg).to_list(500))
        rec_ids = [r["_id"] for r in rec_results if r["_id"]]
        job_ids = [r["_id"] for r in man_results if r["_id"]]
        users, job_docs = await asyncio.gather(db.users.find({"id": {"$in": rec_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(500) if rec_ids else asyncio.sleep(0), db.jobs.find({"id": {"$in": job_ids}}, {"_id": 0, "id": 1, "title": 1, "company_name": 1}).to_list(500) if job_ids else asyncio.sleep(0))
        umap = {u["id"]: u.get("name", "") for u in (users or [])}
        jmap = {j["id"]: j for j in (job_docs or [])}
        perf = [{"recruiter_id": r["_id"], "recruiter_name": umap.get(r["_id"], "Unknown"), "total_candidates": r["total"], "submitted": r["submitted"], "offered": r["offered"], "joined": r["joined"], "rejected": r["rejected"], "total_revenue": round(r["total_revenue"], 2), "conversion_rate": round((r["joined"] / r["total"]) * 100, 1) if r["total"] > 0 else 0} for r in rec_results if r["_id"]]
        perf.sort(key=lambda x: x["total_revenue"], reverse=True)
        mandates = [{"mandate_id": r["_id"], "mandate_name": jmap.get(r["_id"], {}).get("title", "Unknown"), "company": jmap.get(r["_id"], {}).get("company_name", ""), "total_candidates": r["total"], "submitted": r["submitted"], "offered": r["offered"], "joined": r["joined"], "total_revenue": round(r["total_revenue"], 2), "submission_rate": round((r["submitted"] / r["total"]) * 100, 1) if r["total"] > 0 else 0} for r in man_results if r["_id"]]
        mandates.sort(key=lambda x: x["total_revenue"], reverse=True)
        return {"recruiter": {"recruiters": perf}, "mandate": {"mandates": mandates}}

    overview, pipeline, revenue, performance = await asyncio.gather(overview_task, get_pipeline(), get_revenue(), get_perf())

    from services.analytics_pdf import build_combined_pdf
    buf = build_combined_pdf(overview, pipeline, revenue, performance, date_from, date_to)

    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    filename = f"VHC_Complete_Analytics_{now_str}.pdf"

    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})



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

    # Simplified funnel: Sourced → Submitted → Shortlisted → Interviewed → Offered → Hired → Joined
    # Each value = cumulative (stage count + all downstream).
    sourced = sum(counts.get(s, 0) for s in ["sourced", "submitted_to_client", "shortlisted", "interview", "offered", "hired", "joined"])
    submitted = sum(counts.get(s, 0) for s in ["submitted_to_client", "shortlisted", "interview", "offered", "hired", "joined"])
    shortlisted = sum(counts.get(s, 0) for s in ["shortlisted", "interview", "offered", "hired", "joined"])
    interviewed = sum(counts.get(s, 0) for s in ["interview", "offered", "hired", "joined"])
    offered = sum(counts.get(s, 0) for s in ["offered", "hired", "joined"])
    hired = sum(counts.get(s, 0) for s in ["hired", "joined"])
    joined = counts.get("joined", 0)

    def rate(num, den):
        return round((num / den) * 100, 1) if den > 0 else 0

    return {
        "stage_counts": counts,
        "total_applications": total,
        "conversions": {
            # New simplified flow
            "sourced_to_submitted": {"count": submitted, "rate": rate(submitted, sourced)},
            "submitted_to_shortlisted": {"count": shortlisted, "rate": rate(shortlisted, submitted)},
            "shortlisted_to_interview": {"count": interviewed, "rate": rate(interviewed, shortlisted)},
            "interview_to_offered": {"count": offered, "rate": rate(offered, interviewed)},
            "offered_to_hired": {"count": hired, "rate": rate(hired, offered)},
            "hired_to_joined": {"count": joined, "rate": rate(joined, hired)},
            # Legacy alias for older dashboards that haven't shipped yet
            "applied_to_shortlisted": {"count": shortlisted, "rate": rate(shortlisted, sourced)},
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



# ═══════════════════════════════════════
# SALARY BENCHMARKING
# ═══════════════════════════════════════

@analytics_router.get("/salary-benchmark")
async def salary_benchmark(
    skills: Optional[str] = Query(None, description="Comma-separated skills to filter by"),
    location: Optional[str] = Query(None, description="Location filter"),
    designation: Optional[str] = Query(None, description="Designation/role filter"),
    company: Optional[str] = Query(None, description="Company/employer filter"),
    industry: Optional[str] = Query(None, description="Industry filter"),
    experience_min: Optional[int] = Query(None, description="Minimum years of experience"),
    experience_max: Optional[int] = Query(None, description="Maximum years of experience"),
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"])),
):
    """
    Salary benchmarking tool — aggregates salary data from the candidate bank.
    Returns stats: avg, median, min, max, percentiles, breakdowns by location & experience.
    Pure MongoDB aggregation, zero LLM cost.
    """
    import re as _re
    import math

    # Build match filter
    match_filter = {
        "current_salary": {"$exists": True, "$gt": 0},
    }

    # Skills filter: match candidates who have ANY of the requested skills
    if skills:
        skill_list = [s.strip() for s in skills.split(",") if s.strip()]
        if skill_list:
            skill_regexes = [{"skills": {"$regex": _re.escape(s), "$options": "i"}} for s in skill_list]
            match_filter["$or"] = skill_regexes

    # Location filter (partial match)
    if location:
        match_filter["location"] = {"$regex": _re.escape(location.strip()), "$options": "i"}

    # Designation filter (partial match)
    if designation:
        match_filter["designation"] = {"$regex": _re.escape(designation.strip()), "$options": "i"}

    # Company/Employer filter (partial match)
    if company:
        match_filter["current_employer"] = {"$regex": _re.escape(company.strip()), "$options": "i"}

    # Industry filter (partial match)
    if industry:
        match_filter["industry"] = {"$regex": _re.escape(industry.strip()), "$options": "i"}

    # Experience range
    if experience_min is not None:
        match_filter.setdefault("experience_years", {})["$gte"] = experience_min
    if experience_max is not None:
        match_filter.setdefault("experience_years", {})["$lte"] = experience_max

    # Main stats aggregation
    stats_pipeline = [
        {"$match": match_filter},
        {"$group": {
            "_id": None,
            "count": {"$sum": 1},
            "avg_salary": {"$avg": "$current_salary"},
            "min_salary": {"$min": "$current_salary"},
            "max_salary": {"$max": "$current_salary"},
            "salaries": {"$push": "$current_salary"},
        }},
    ]
    stats_result = await db.candidate_bank.aggregate(stats_pipeline).to_list(1)

    if not stats_result or stats_result[0]["count"] == 0:
        return {
            "count": 0, "avg_salary": 0, "median_salary": 0,
            "min_salary": 0, "max_salary": 0,
            "p25": 0, "p75": 0,
            "by_location": [], "by_experience": [], "by_designation": [],
            "salary_ranges": [],
        }

    s = stats_result[0]
    salaries = sorted(s["salaries"])
    n = len(salaries)

    def percentile(arr, p):
        k = (len(arr) - 1) * p / 100
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return arr[int(k)]
        return arr[f] * (c - k) + arr[c] * (k - f)

    median = percentile(salaries, 50)
    p25 = percentile(salaries, 25)
    p75 = percentile(salaries, 75)

    # Breakdown by location (top 10)
    loc_pipeline = [
        {"$match": match_filter},
        {"$match": {"location": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {
            "_id": "$location",
            "count": {"$sum": 1},
            "avg_salary": {"$avg": "$current_salary"},
        }},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    by_location = await db.candidate_bank.aggregate(loc_pipeline).to_list(10)

    # Breakdown by experience range
    exp_pipeline = [
        {"$match": match_filter},
        {"$match": {"experience_years": {"$exists": True, "$gte": 0}}},
        {"$bucket": {
            "groupBy": "$experience_years",
            "boundaries": [0, 2, 5, 8, 12, 16, 20, 50],
            "default": "20+",
            "output": {
                "count": {"$sum": 1},
                "avg_salary": {"$avg": "$current_salary"},
                "min_salary": {"$min": "$current_salary"},
                "max_salary": {"$max": "$current_salary"},
            },
        }},
    ]
    by_experience = await db.candidate_bank.aggregate(exp_pipeline).to_list(20)

    exp_labels = {0: "0-2 yrs", 2: "2-5 yrs", 5: "5-8 yrs", 8: "8-12 yrs", 12: "12-16 yrs", 16: "16-20 yrs", 20: "20+ yrs"}
    for b in by_experience:
        b["label"] = exp_labels.get(b["_id"], f"{b['_id']}+ yrs")
        b["avg_salary"] = round(b["avg_salary"])

    # Breakdown by designation (top 10)
    desig_pipeline = [
        {"$match": match_filter},
        {"$match": {"designation": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {
            "_id": "$designation",
            "count": {"$sum": 1},
            "avg_salary": {"$avg": "$current_salary"},
        }},
        {"$sort": {"avg_salary": -1}},
        {"$limit": 10},
    ]
    by_designation = await db.candidate_bank.aggregate(desig_pipeline).to_list(10)

    # Salary range distribution
    range_pipeline = [
        {"$match": match_filter},
        {"$bucket": {
            "groupBy": "$current_salary",
            "boundaries": [0, 300000, 500000, 800000, 1200000, 1800000, 2500000, 4000000, 6000000, 10000000, 100000000],
            "default": "10Cr+",
            "output": {"count": {"$sum": 1}},
        }},
    ]
    salary_ranges = await db.candidate_bank.aggregate(range_pipeline).to_list(20)

    range_labels = {
        0: "0-3L", 300000: "3-5L", 500000: "5-8L", 800000: "8-12L",
        1200000: "12-18L", 1800000: "18-25L", 2500000: "25-40L",
        4000000: "40-60L", 6000000: "60L-1Cr", 10000000: "1Cr+",
    }
    for r in salary_ranges:
        r["label"] = range_labels.get(r["_id"], str(r["_id"]))

    # Top skills in the filtered set
    skills_pipeline = [
        {"$match": match_filter},
        {"$unwind": "$skills"},
        {"$group": {"_id": {"$toLower": "$skills"}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 15},
    ]
    top_skills = await db.candidate_bank.aggregate(skills_pipeline).to_list(15)

    return {
        "count": n,
        "avg_salary": round(s["avg_salary"]),
        "median_salary": round(median),
        "min_salary": s["min_salary"],
        "max_salary": s["max_salary"],
        "p25": round(p25),
        "p75": round(p75),
        "by_location": [{"location": b["_id"], "count": b["count"], "avg_salary": round(b["avg_salary"])} for b in by_location],
        "by_experience": by_experience,
        "by_designation": [{"designation": b["_id"], "count": b["count"], "avg_salary": round(b["avg_salary"])} for b in by_designation],
        "salary_ranges": salary_ranges,
        "top_skills": [{"skill": s["_id"], "count": s["count"]} for s in top_skills],
    }


@analytics_router.get("/salary-benchmark/suggestions")
async def salary_benchmark_suggestions(
    field: str = Query(..., description="Field to get suggestions for: skills, location, designation"),
    q: Optional[str] = Query(None, description="Search query"),
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"])),
):
    """Get autocomplete suggestions for salary benchmark filters."""
    import re as _re

    field_map = {
        "skills": "skills",
        "location": "location",
        "designation": "designation",
        "company": "current_employer",
        "industry": "industry",
    }
    db_field = field_map.get(field)
    if not db_field:
        return {"suggestions": []}

    match = {"current_salary": {"$gt": 0}}
    if db_field == "skills":
        pipeline = [
            {"$match": match},
            {"$unwind": "$skills"},
        ]
        if q:
            pipeline.append({"$match": {"skills": {"$regex": _re.escape(q), "$options": "i"}}})
        pipeline.extend([
            {"$group": {"_id": "$skills", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 20},
        ])
    else:
        if q:
            match[db_field] = {"$regex": _re.escape(q), "$options": "i"}
        else:
            match[db_field] = {"$exists": True, "$nin": [None, ""]}
        pipeline = [
            {"$match": match},
            {"$group": {"_id": f"${db_field}", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 20},
        ]

    results = await db.candidate_bank.aggregate(pipeline).to_list(20)
    return {"suggestions": [{"value": r["_id"], "count": r["count"]} for r in results if r["_id"]]}
