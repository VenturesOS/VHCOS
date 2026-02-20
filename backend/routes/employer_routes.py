"""
VHC Talent OS - Employer Routes
Employer portal endpoints: My Team, Companies, Pipeline, Analytics, Company Pipeline.
Also includes admin-facing employer management: hierarchy, assign-employer, company update.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends

from config import db
from models import CompanyResponse, CompanyUpdate
from utils import get_current_user, require_role

employer_router = APIRouter(prefix="/api", tags=["Employer"])
logger = logging.getLogger(__name__)


# ============== ADMIN: EMPLOYER-COMPANY LOOKUP ==============

@employer_router.get("/employers/{employer_id}/companies")
async def get_employer_companies(
    employer_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Get companies assigned to a specific employer (Admin only).
    Used for auto-populating company selection when creating a team.
    """
    employer = await db.users.find_one({"id": employer_id, "role": "employer"}, {"_id": 0})
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")

    companies = await db.companies.find(
        {
            "assigned_employer_id": employer_id,
            "$or": [{"status": "active"}, {"status": None}, {"status": {"$exists": False}}]
        },
        {"_id": 0}
    ).to_list(100)

    return {
        "employer_id": employer_id,
        "employer_name": employer.get("name"),
        "companies": companies,
        "count": len(companies)
    }


# ============== EMPLOYER: MY TEAM ==============

@employer_router.get("/employer/my-team")
async def get_employer_team_with_metrics(current_user: dict = Depends(require_role(["employer"]))):
    """
    Get employer's team with detailed performance metrics.
    Shows: team members, mandates assigned, pipelines, revenue per stage, closed revenue.
    """
    team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})

    if not team:
        return {
            "team": None,
            "members": [],
            "summary": {
                "total_members": 0,
                "total_mandates": 0,
                "total_pipeline": 0,
                "total_revenue_pipeline": 0,
                "total_revenue_closed": 0
            }
        }

    recruiter_ids = team.get("recruiter_ids", [])
    recruiters = await db.users.find(
        {"id": {"$in": recruiter_ids}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "is_active": 1, "created_at": 1}
    ).to_list(100)

    company_ids = team.get("company_ids", [])
    employer_jobs = await db.jobs.find(
        {"$or": [
            {"team_id": team["id"]},
            {"company_id": {"$in": company_ids}},
            {"posted_by": {"$in": recruiter_ids + [current_user["id"]]}}
        ]},
        {"_id": 0}
    ).to_list(1000)

    job_ids = [j["id"] for j in employer_jobs]

    applications = await db.applications.find(
        {"job_id": {"$in": job_ids}},
        {"_id": 0}
    ).to_list(10000)

    companies_with_commercial = await db.companies.find(
        {"id": {"$in": company_ids}},
        {"_id": 0, "id": 1, "commercial": 1}
    ).to_list(100)
    commercial_by_company = {c["id"]: c.get("commercial", {}) for c in companies_with_commercial}

    members_with_metrics = []

    for recruiter in recruiters:
        recruiter_jobs = [j for j in employer_jobs if
                         j.get("posted_by") == recruiter["id"] or
                         recruiter["id"] in j.get("assigned_recruiters", [])]
        recruiter_job_ids = [j["id"] for j in recruiter_jobs]

        recruiter_apps = [a for a in applications if a["job_id"] in recruiter_job_ids]

        stages = {
            "applied": 0, "shortlisted": 0, "submitted_to_client": 0, "interview": 0,
            "offered": 0, "hired": 0, "joined": 0, "rejected": 0
        }
        for app in recruiter_apps:
            stage = app.get("stage", "applied")
            if stage in stages:
                stages[stage] += 1

        revenue_pipeline = 0
        revenue_closed = 0

        for app in recruiter_apps:
            job = next((j for j in recruiter_jobs if j["id"] == app["job_id"]), None)
            if job:
                company_id = job.get("company_id")
                commercial = commercial_by_company.get(company_id, {})
                offered_salary = app.get("offered_salary", 0) or app.get("current_salary", 0) or 0

                if commercial and offered_salary > 0:
                    from routes.commercials import calculate_revenue as _calc_rev
                    revenue = _calc_rev(offered_salary, commercial)

                    if app.get("stage") == "joined":
                        revenue_closed += revenue
                    elif app.get("stage") in ["offered", "hired", "interview", "shortlisted", "submitted_to_client"]:
                        revenue_pipeline += revenue

        members_with_metrics.append({
            "id": recruiter["id"],
            "name": recruiter["name"],
            "email": recruiter["email"],
            "is_active": recruiter.get("is_active", True),
            "joined_at": recruiter.get("created_at"),
            "mandates_assigned": len(recruiter_jobs),
            "mandates": [{"id": j["id"], "title": j["title"], "company_name": j.get("company_name")} for j in recruiter_jobs[:5]],
            "pipeline": stages,
            "total_pipeline_count": sum(stages.values()),
            "revenue_pipeline": round(revenue_pipeline, 2),
            "revenue_closed": round(revenue_closed, 2)
        })

    total_pipeline = sum(m["total_pipeline_count"] for m in members_with_metrics)
    total_revenue_pipeline = sum(m["revenue_pipeline"] for m in members_with_metrics)
    total_revenue_closed = sum(m["revenue_closed"] for m in members_with_metrics)

    return {
        "team": {
            "id": team["id"],
            "name": team["name"],
            "company_ids": company_ids,
            "company_names": team.get("company_names", [])
        },
        "members": members_with_metrics,
        "summary": {
            "total_members": len(members_with_metrics),
            "total_mandates": len(employer_jobs),
            "total_pipeline": total_pipeline,
            "total_revenue_pipeline": round(total_revenue_pipeline, 2),
            "total_revenue_closed": round(total_revenue_closed, 2)
        }
    }


# ============== EMPLOYER: COMPANIES ==============

@employer_router.get("/employer/companies")
async def get_employer_companies_with_details(current_user: dict = Depends(require_role(["employer"]))):
    """
    Get employer's assigned companies with commercial details, mandates, and pipelines.
    """
    team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})

    if not team:
        return {"companies": []}

    company_ids = team.get("company_ids", [])

    if not company_ids:
        return {"companies": []}

    companies = await db.companies.find(
        {"id": {"$in": company_ids}},
        {"_id": 0}
    ).to_list(100)

    commercial_by_company = {c["id"]: c.get("commercial", {}) for c in companies}

    all_jobs = await db.jobs.find(
        {"company_id": {"$in": company_ids}},
        {"_id": 0}
    ).to_list(1000)

    job_ids = [j["id"] for j in all_jobs]
    applications = await db.applications.find(
        {"job_id": {"$in": job_ids}},
        {"_id": 0}
    ).to_list(10000)

    enriched_companies = []

    for company in companies:
        company_id = company["id"]
        commercial = commercial_by_company.get(company_id, {})
        company_jobs = [j for j in all_jobs if j.get("company_id") == company_id]
        company_job_ids = [j["id"] for j in company_jobs]
        company_apps = [a for a in applications if a["job_id"] in company_job_ids]

        mandates_with_pipeline = []
        for job in company_jobs:
            job_apps = [a for a in company_apps if a["job_id"] == job["id"]]

            stages = {"applied": 0, "shortlisted": 0, "submitted_to_client": 0, "interview": 0, "offered": 0, "hired": 0, "joined": 0, "rejected": 0}
            revenue_by_stage = {"applied": 0, "shortlisted": 0, "submitted_to_client": 0, "interview": 0, "offered": 0, "hired": 0}

            for app in job_apps:
                stage = app.get("stage", "applied")
                if stage in stages:
                    stages[stage] += 1

                offered_salary = app.get("offered_salary", 0) or app.get("current_salary", 0) or 0
                if offered_salary > 0 and stage in revenue_by_stage:
                    from routes.commercials import calculate_revenue as _calc_rev
                    revenue_by_stage[stage] += _calc_rev(offered_salary, commercial)

            mandates_with_pipeline.append({
                "id": job["id"],
                "title": job["title"],
                "status": job.get("status", "active"),
                "location": job.get("location"),
                "posted_by": job.get("posted_by"),
                "created_at": job.get("created_at"),
                "pipeline_count": sum(stages.values()),
                "stages": stages,
                "revenue_by_stage": {k: round(v, 2) for k, v in revenue_by_stage.items()},
                "total_revenue_pipeline": round(sum(v for k, v in revenue_by_stage.items() if k != "joined"), 2),
                "total_revenue_closed": round(revenue_by_stage.get("joined", 0), 2)
            })

        total_pipeline = sum(m["pipeline_count"] for m in mandates_with_pipeline)
        total_revenue_closed = sum(m["total_revenue_closed"] for m in mandates_with_pipeline)

        enriched_companies.append({
            "id": company_id,
            "name": company["name"],
            "industry": company.get("industry"),
            "location": company.get("location"),
            "logo_url": company.get("logo_url"),
            "commercial": commercial or {},
            "mandates": mandates_with_pipeline,
            "active_mandates_count": len([m for m in mandates_with_pipeline if m["status"] == "active"]),
            "total_pipeline": total_pipeline,
            "total_revenue_closed": round(total_revenue_closed, 2)
        })

    return {"companies": enriched_companies}


# ============== EMPLOYER: PIPELINE ==============

@employer_router.get("/employer/pipeline")
async def get_employer_pipeline(
    recruiter_id: Optional[str] = None,
    job_id: Optional[str] = None,
    current_user: dict = Depends(require_role(["employer"]))
):
    """
    Employer pipeline view with stage control.
    Shows all applications for jobs under employer's teams/companies.
    """
    team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})

    if not team:
        return {
            "pipeline": {stage: [] for stage in ["applied", "shortlisted", "submitted_to_client", "interview", "offered", "hired", "joined", "rejected", "on_hold"]},
            "stage_counts": {stage: 0 for stage in ["applied", "shortlisted", "submitted_to_client", "interview", "offered", "hired", "joined", "rejected", "on_hold"]},
            "total_applications": 0,
            "filters": {"recruiters": [], "jobs": []}
        }

    company_ids = team.get("company_ids", [])
    recruiter_ids = team.get("recruiter_ids", [])

    job_filter = {
        "$or": [
            {"team_id": team["id"]},
            {"company_id": {"$in": company_ids}} if company_ids else {"_id": None},
            {"posted_by": {"$in": recruiter_ids + [current_user["id"]]}}
        ]
    }

    if job_id:
        job_filter = {"id": job_id, **job_filter}

    jobs = await db.jobs.find(job_filter, {"_id": 0}).to_list(1000)
    job_ids_list = [j["id"] for j in jobs]
    jobs_map = {j["id"]: j for j in jobs}

    if recruiter_id:
        recruiter_job_ids = [
            j["id"] for j in jobs
            if j.get("posted_by") == recruiter_id or recruiter_id in j.get("assigned_recruiters", [])
        ]
        job_ids_list = [jid for jid in job_ids_list if jid in recruiter_job_ids]

    if job_ids_list:
        applications = await db.applications.find(
            {"job_id": {"$in": job_ids_list}},
            {"_id": 0}
        ).to_list(10000)
    else:
        applications = []

    all_stages = ["applied", "shortlisted", "submitted_to_client", "interview", "offered", "hired", "joined", "rejected", "on_hold"]

    pipeline_data = {stage: [] for stage in all_stages}

    for app in applications:
        stage = app.get("stage", "applied")
        if stage not in pipeline_data:
            stage = "applied"

        job = jobs_map.get(app.get("job_id"), {})

        pipeline_data[stage].append({
            "id": app.get("id"),
            "candidate_id": app.get("candidate_id"),
            "candidate_name": app.get("candidate_name", "Unknown"),
            "candidate_email": app.get("candidate_email"),
            "candidate_phone": app.get("candidate_phone"),
            "job_id": app.get("job_id"),
            "job_title": app.get("job_title") or job.get("title", "Unknown"),
            "company_name": job.get("company_name", ""),
            "match_score": app.get("match_score", 0),
            "current_salary": app.get("current_salary"),
            "expected_salary": app.get("expected_salary"),
            "notice_period": app.get("notice_period"),
            "experience_years": app.get("experience_years"),
            "resume_url": app.get("resume_url"),
            "applied_at": app.get("created_at"),
            "updated_at": app.get("updated_at"),
            "notes": app.get("notes", []),
            "stage": stage,
            "offered_ctc": app.get("offered_ctc"),
            "offer_date": app.get("offer_date"),
            "join_date": app.get("join_date"),
        })

    stage_counts = {stage: len(apps) for stage, apps in pipeline_data.items()}

    recruiters = []
    if recruiter_ids:
        recruiter_docs = await db.users.find(
            {"id": {"$in": recruiter_ids}},
            {"_id": 0, "id": 1, "name": 1, "email": 1}
        ).to_list(100)
        recruiters = recruiter_docs

    return {
        "pipeline": pipeline_data,
        "stage_counts": stage_counts,
        "total_applications": len(applications),
        "filters": {
            "recruiters": recruiters,
            "jobs": [{"id": j["id"], "title": j.get("title", "Untitled"), "company_name": j.get("company_name")} for j in jobs]
        }
    }


# ============== ADMIN: ASSIGN EMPLOYER TO COMPANY ==============

@employer_router.put("/companies/{company_id}/assign-employer")
async def assign_employer_to_company(
    company_id: str,
    employer_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Assign an employer to manage a company (Admin only)."""
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    employer = await db.users.find_one({"id": employer_id, "role": "employer"}, {"_id": 0})
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")

    now = datetime.now(timezone.utc).isoformat()

    await db.companies.update_one(
        {"id": company_id},
        {"$set": {
            "assigned_employer_id": employer_id,
            "assigned_employer_name": employer.get("name"),
            "updated_at": now
        }}
    )

    return {
        "message": "Employer assigned to company successfully",
        "company_id": company_id,
        "employer_id": employer_id,
        "employer_name": employer.get("name")
    }


# ============== COMPANY UPDATE (Admin/Employer) ==============

@employer_router.put("/companies/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: str,
    update_data: CompanyUpdate,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Update company details.
    - Admin: can update any company
    - Employer: can only update companies assigned to them
    """
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if current_user["role"] == "employer":
        if company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="You are not assigned to this company")

    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.companies.update_one({"id": company_id}, {"$set": update_dict})

    updated_company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    return CompanyResponse(**updated_company)


# ============== ADMIN: HIERARCHY OVERVIEW ==============

@employer_router.get("/admin/hierarchy")
async def get_admin_hierarchy(current_user: dict = Depends(require_role(["admin"]))):
    """
    Get complete hierarchy overview for Admin.
    Shows: Employers -> Teams -> Recruiters -> Companies
    """
    employers = await db.users.find({"role": "employer", "is_active": True}, {"_id": 0, "password": 0}).to_list(1000)

    hierarchy = []

    for employer in employers:
        employer_data = {
            "employer_id": employer["id"],
            "employer_name": employer["name"],
            "employer_email": employer["email"],
            "teams": []
        }

        teams = await db.teams.find({"employer_id": employer["id"], "status": "active"}, {"_id": 0}).to_list(100)

        for team in teams:
            jobs_count = await db.jobs.count_documents({
                "team_id": team["id"],
                "status": {"$in": ["active", "pending_approval"]}
            })

            team_data = {
                "team_id": team["id"],
                "team_name": team["name"],
                "active_jobs_count": jobs_count,
                "recruiters": [],
                "companies": []
            }

            for recruiter_id in team.get("recruiter_ids", []):
                recruiter = await db.users.find_one({"id": recruiter_id}, {"_id": 0, "password": 0})
                if recruiter:
                    team_data["recruiters"].append({
                        "id": recruiter["id"],
                        "name": recruiter["name"],
                        "email": recruiter["email"]
                    })

            for cid in team.get("company_ids", []):
                comp = await db.companies.find_one({"id": cid}, {"_id": 0})
                if comp:
                    team_data["companies"].append({
                        "id": comp["id"],
                        "name": comp["name"],
                        "industry": comp.get("industry")
                    })

            employer_data["teams"].append(team_data)

        hierarchy.append(employer_data)

    unassigned_recruiters = await db.users.find(
        {"role": "recruiter", "is_active": True, "team_id": {"$exists": False}},
        {"_id": 0, "password": 0}
    ).to_list(1000)

    unassigned_companies = await db.companies.find(
        {"assigned_employer_id": {"$exists": False}},
        {"_id": 0}
    ).to_list(1000)

    return {
        "hierarchy": hierarchy,
        "unassigned_recruiters": [{"id": r["id"], "name": r["name"], "email": r["email"]} for r in unassigned_recruiters],
        "unassigned_companies": [{"id": c["id"], "name": c["name"]} for c in unassigned_companies],
        "summary": {
            "total_employers": len(employers),
            "total_teams": sum(len(e["teams"]) for e in hierarchy),
            "total_unassigned_recruiters": len(unassigned_recruiters),
            "total_unassigned_companies": len(unassigned_companies)
        }
    }


# ============== ADMIN ANALYTICS ==============

@employer_router.get("/analytics/admin")
async def get_admin_analytics(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    employer_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    company_id: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin analytics dashboard - Power BI style. Full visibility into all business metrics."""
    start_time = time.time()

    date_match = {}
    if date_from:
        date_match["$gte"] = date_from
    if date_to:
        date_match["$lte"] = date_to

    # JOBS
    jobs_match = {"status": {"$in": ["active", "on_hold", "closed"]}}
    if company_id:
        jobs_match["company_id"] = company_id

    jobs_pipeline = [
        {"$match": jobs_match},
        {"$project": {"_id": 0, "id": 1, "status": 1, "company_id": 1, "assigned_recruiter_ids": 1}}
    ]
    jobs = await db.jobs.aggregate(jobs_pipeline).to_list(10000)
    active_jobs_count = sum(1 for j in jobs if j.get("status") == "active")

    # APPLICATIONS (stage distribution)
    apps_match = {}
    if date_match:
        apps_match["created_at"] = date_match

    stage_pipeline = [
        {"$match": apps_match} if apps_match else {"$match": {}},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
    ]
    stage_results = await db.applications.aggregate(stage_pipeline).to_list(20)
    stage_counts = {r["_id"] or "applied": r["count"] for r in stage_results}

    offered_count = stage_counts.get("offered", 0)
    hired_count = stage_counts.get("hired", 0)
    offer_to_join_ratio = (hired_count / offered_count * 100) if offered_count > 0 else 0

    # AVG TIME TO CLOSE
    hired_pipeline = [
        {"$match": {"stage": "hired", "created_at": {"$exists": True}}},
        {"$project": {"_id": 0, "created_at": 1, "updated_at": 1}},
        {"$limit": 1000}
    ]
    hired_apps = await db.applications.aggregate(hired_pipeline).to_list(1000)

    avg_time_to_close = 0
    if hired_apps:
        total_days = 0
        valid_count = 0
        for app in hired_apps:
            try:
                created = datetime.fromisoformat(app["created_at"].replace("Z", "+00:00"))
                updated = datetime.fromisoformat(app.get("updated_at", app["created_at"]).replace("Z", "+00:00"))
                total_days += (updated - created).days
                valid_count += 1
            except (ValueError, KeyError, TypeError):
                pass
        avg_time_to_close = total_days / valid_count if valid_count > 0 else 0

    # USER COUNTS
    active_employers = await db.users.count_documents({"role": "employer", "is_active": True})
    active_recruiters = await db.users.count_documents({"role": "recruiter", "is_active": True})

    # REVENUE
    revenue_match = {}
    if date_match:
        revenue_match["created_at"] = date_match
    if company_id:
        revenue_match["company_id"] = company_id

    revenue_kpi_pipeline = [
        {"$match": revenue_match} if revenue_match else {"$match": {}},
        {"$group": {
            "_id": None,
            "pipeline_revenue": {"$sum": {"$cond": [{"$eq": ["$is_closed", False]}, "$final_revenue", 0]}},
            "closed_revenue": {"$sum": {"$cond": [{"$eq": ["$is_closed", True]}, "$final_revenue", 0]}}
        }}
    ]
    revenue_kpis = await db.revenue.aggregate(revenue_kpi_pipeline).to_list(1)
    total_pipeline_revenue = revenue_kpis[0]["pipeline_revenue"] if revenue_kpis else 0
    closed_revenue = revenue_kpis[0]["closed_revenue"] if revenue_kpis else 0

    company_revenue_pipeline = [
        {"$match": revenue_match} if revenue_match else {"$match": {}},
        {"$group": {
            "_id": "$company_id",
            "pipeline": {"$sum": {"$cond": [{"$eq": ["$is_closed", False]}, "$final_revenue", 0]}},
            "closed": {"$sum": {"$cond": [{"$eq": ["$is_closed", True]}, "$final_revenue", 0]}}
        }},
        {"$lookup": {
            "from": "companies",
            "localField": "_id",
            "foreignField": "id",
            "as": "company"
        }},
        {"$unwind": {"path": "$company", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 0,
            "name": {"$ifNull": ["$company.name", "Unknown"]},
            "pipeline": 1,
            "closed": 1
        }}
    ]
    company_revenue = await db.revenue.aggregate(company_revenue_pipeline).to_list(100)

    revenue_funnel_pipeline = [
        {"$match": revenue_match} if revenue_match else {"$match": {}},
        {"$group": {
            "_id": "$stage",
            "total": {"$sum": "$final_revenue"}
        }}
    ]
    funnel_results = await db.revenue.aggregate(revenue_funnel_pipeline).to_list(10)
    revenue_funnel = {r["_id"]: r["total"] for r in funnel_results if r["_id"]}

    # RECRUITER PERFORMANCE
    recruiter_ids = set()
    for job in jobs:
        for rec_id in job.get("assigned_recruiter_ids", []):
            recruiter_ids.add(rec_id)

    recruiter_names = {}
    if recruiter_ids:
        recruiters = await db.users.find(
            {"id": {"$in": list(recruiter_ids)}},
            {"_id": 0, "id": 1, "name": 1}
        ).to_list(len(recruiter_ids))
        recruiter_names = {r["id"]: r.get("name", "Unknown") for r in recruiters}

    recruiter_stats_pipeline = [
        {"$match": apps_match} if apps_match else {"$match": {}},
        {"$group": {
            "_id": "$job_id",
            "total": {"$sum": 1},
            "shortlisted": {"$sum": {"$cond": [{"$in": ["$stage", ["shortlisted", "interview", "offered", "hired"]]}, 1, 0]}},
            "hired": {"$sum": {"$cond": [{"$eq": ["$stage", "hired"]}, 1, 0]}}
        }}
    ]
    app_stats_by_job = await db.applications.aggregate(recruiter_stats_pipeline).to_list(10000)
    app_stats_map = {r["_id"]: r for r in app_stats_by_job}

    recruiter_stats = {}
    for job in jobs:
        job_stats = app_stats_map.get(job["id"], {"total": 0, "shortlisted": 0, "hired": 0})
        for rec_id in job.get("assigned_recruiter_ids", []):
            if rec_id not in recruiter_stats:
                recruiter_stats[rec_id] = {
                    "name": recruiter_names.get(rec_id, "Unknown"),
                    "applications": 0,
                    "shortlisted": 0,
                    "hired": 0,
                    "revenue": 0
                }
            recruiter_stats[rec_id]["applications"] += job_stats["total"]
            recruiter_stats[rec_id]["shortlisted"] += job_stats["shortlisted"]
            recruiter_stats[rec_id]["hired"] += job_stats["hired"]

    if recruiter_ids:
        revenue_by_job_pipeline = [
            {"$match": revenue_match} if revenue_match else {"$match": {}},
            {"$group": {
                "_id": "$job_id",
                "total_revenue": {"$sum": "$final_revenue"}
            }}
        ]
        revenue_by_job = await db.revenue.aggregate(revenue_by_job_pipeline).to_list(10000)
        revenue_map = {r["_id"]: r["total_revenue"] for r in revenue_by_job}

        for job in jobs:
            job_revenue = revenue_map.get(job["id"], 0)
            assigned_count = len(job.get("assigned_recruiter_ids", []))
            if assigned_count > 0:
                per_recruiter = job_revenue / assigned_count
                for rec_id in job.get("assigned_recruiter_ids", []):
                    if rec_id in recruiter_stats:
                        recruiter_stats[rec_id]["revenue"] += per_recruiter

    elapsed = time.time() - start_time
    logger.info(f"[ADMIN ANALYTICS] Completed in {elapsed:.2f}s")

    return {
        "kpis": {
            "total_active_mandates": active_jobs_count,
            "total_pipeline_revenue": round(total_pipeline_revenue, 2),
            "closed_revenue": round(closed_revenue, 2),
            "avg_time_to_close_days": round(avg_time_to_close, 1),
            "offer_to_join_ratio": round(offer_to_join_ratio, 1),
            "active_employers": active_employers,
            "active_recruiters": active_recruiters,
        },
        "stage_distribution": stage_counts,
        "revenue_funnel": revenue_funnel,
        "company_revenue": company_revenue,
        "recruiter_performance": list(recruiter_stats.values()),
    }


# ============== EMPLOYER ANALYTICS ==============

@employer_router.get("/analytics/employer")
async def get_employer_analytics(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Employer analytics dashboard. Scoped to assigned companies and teams only."""
    start_time = time.time()

    company_query = {"assigned_employer_id": current_user["id"]} if current_user["role"] == "employer" else {}
    assigned_companies = await db.companies.find(company_query, {"_id": 0, "id": 1, "name": 1, "commercial": 1}).to_list(1000)
    company_ids = [c["id"] for c in assigned_companies]

    if not company_ids:
        return {
            "kpis": {
                "active_mandates": 0,
                "pipeline_revenue": 0,
                "closed_revenue": 0,
                "offers_pending": 0,
                "avg_fee_percentage": 0,
            },
            "team_performance": [],
            "company_revenue": [],
            "recruiter_contribution": [],
        }

    jobs = await db.jobs.find(
        {"company_id": {"$in": company_ids}},
        {"_id": 0, "id": 1, "status": 1, "company_id": 1, "team_id": 1, "assigned_recruiter_ids": 1}
    ).to_list(10000)

    active_jobs_count = sum(1 for j in jobs if j.get("status") == "active")
    job_ids = [j["id"] for j in jobs]

    apps_pipeline = [
        {"$match": {"job_id": {"$in": job_ids}}},
        {"$group": {
            "_id": "$job_id",
            "total": {"$sum": 1},
            "offered": {"$sum": {"$cond": [{"$eq": ["$stage", "offered"]}, 1, 0]}},
            "hired": {"$sum": {"$cond": [{"$eq": ["$stage", "hired"]}, 1, 0]}}
        }}
    ]
    app_stats = await db.applications.aggregate(apps_pipeline).to_list(10000)
    app_stats_map = {r["_id"]: r for r in app_stats}

    offers_pending = sum(s.get("offered", 0) for s in app_stats)

    revenue_pipeline = [
        {"$match": {"company_id": {"$in": company_ids}}},
        {"$group": {
            "_id": None,
            "pipeline_revenue": {"$sum": {"$cond": [{"$eq": ["$is_closed", False]}, "$final_revenue", 0]}},
            "closed_revenue": {"$sum": {"$cond": [{"$eq": ["$is_closed", True]}, "$final_revenue", 0]}}
        }}
    ]
    revenue_kpis = await db.revenue.aggregate(revenue_pipeline).to_list(1)
    pipeline_revenue = revenue_kpis[0]["pipeline_revenue"] if revenue_kpis else 0
    closed_revenue = revenue_kpis[0]["closed_revenue"] if revenue_kpis else 0

    company_revenue_pipeline = [
        {"$match": {"company_id": {"$in": company_ids}}},
        {"$group": {
            "_id": "$company_id",
            "pipeline": {"$sum": {"$cond": [{"$eq": ["$is_closed", False]}, "$final_revenue", 0]}},
            "closed": {"$sum": {"$cond": [{"$eq": ["$is_closed", True]}, "$final_revenue", 0]}}
        }}
    ]
    revenue_by_company = await db.revenue.aggregate(company_revenue_pipeline).to_list(100)
    revenue_map = {r["_id"]: r for r in revenue_by_company}

    revenue_by_job_pipeline = [
        {"$match": {"job_id": {"$in": job_ids}}},
        {"$group": {
            "_id": "$job_id",
            "total_revenue": {"$sum": "$final_revenue"}
        }}
    ]
    revenue_by_job = await db.revenue.aggregate(revenue_by_job_pipeline).to_list(10000)
    job_revenue_map = {r["_id"]: r["total_revenue"] for r in revenue_by_job}

    pct_fees = []
    for co in assigned_companies:
        comm = co.get("commercial", {})
        if comm and comm.get("type") == "percentage" and comm.get("percentage_value"):
            pct_fees.append(comm["percentage_value"])
    avg_fee = sum(pct_fees) / len(pct_fees) if pct_fees else 0

    jobs_by_company = {}
    for j in jobs:
        cid = j.get("company_id")
        jobs_by_company[cid] = jobs_by_company.get(cid, 0) + 1

    company_revenue = []
    for company in assigned_companies:
        cid = company["id"]
        rev_data = revenue_map.get(cid, {"pipeline": 0, "closed": 0})
        company_revenue.append({
            "company_id": cid,
            "company_name": company.get("name"),
            "pipeline": rev_data.get("pipeline", 0),
            "closed": rev_data.get("closed", 0),
            "mandates": jobs_by_company.get(cid, 0),
        })

    team_query = {"employer_id": current_user["id"]} if current_user["role"] == "employer" else {}
    teams = await db.teams.find(team_query, {"_id": 0, "id": 1, "name": 1}).to_list(100)

    team_performance = []
    for team in teams:
        team_jobs = [j for j in jobs if j.get("team_id") == team["id"]]
        team_job_ids = {j["id"] for j in team_jobs}

        team_apps = sum(app_stats_map.get(jid, {}).get("total", 0) for jid in team_job_ids)
        team_hired = sum(app_stats_map.get(jid, {}).get("hired", 0) for jid in team_job_ids)

        team_rev_pipeline = [
            {"$match": {"job_id": {"$in": list(team_job_ids)}}},
            {"$group": {
                "_id": None,
                "pipeline": {"$sum": {"$cond": [{"$eq": ["$is_closed", False]}, "$final_revenue", 0]}},
                "closed": {"$sum": {"$cond": [{"$eq": ["$is_closed", True]}, "$final_revenue", 0]}}
            }}
        ]
        team_rev_result = await db.revenue.aggregate(team_rev_pipeline).to_list(1) if team_job_ids else []

        team_performance.append({
            "team_id": team["id"],
            "team_name": team.get("name"),
            "mandates": len(team_jobs),
            "applications": team_apps,
            "hired": team_hired,
            "pipeline_revenue": team_rev_result[0]["pipeline"] if team_rev_result else 0,
            "closed_revenue": team_rev_result[0]["closed"] if team_rev_result else 0,
        })

    recruiter_ids = set()
    for job in jobs:
        for rec_id in job.get("assigned_recruiter_ids", []):
            recruiter_ids.add(rec_id)

    recruiter_names = {}
    if recruiter_ids:
        recruiters = await db.users.find(
            {"id": {"$in": list(recruiter_ids)}},
            {"_id": 0, "id": 1, "name": 1}
        ).to_list(len(recruiter_ids))
        recruiter_names = {r["id"]: r.get("name", "Unknown") for r in recruiters}

    recruiter_contribution = []
    for rec_id in recruiter_ids:
        rec_jobs = [j for j in jobs if rec_id in j.get("assigned_recruiter_ids", [])]
        rec_job_ids = {j["id"] for j in rec_jobs}

        rec_apps = sum(app_stats_map.get(jid, {}).get("total", 0) for jid in rec_job_ids)
        rec_hired = sum(app_stats_map.get(jid, {}).get("hired", 0) for jid in rec_job_ids)
        rec_revenue = sum(job_revenue_map.get(jid, 0) for jid in rec_job_ids)

        recruiter_contribution.append({
            "recruiter_id": rec_id,
            "recruiter_name": recruiter_names.get(rec_id, "Unknown"),
            "mandates": len(rec_jobs),
            "applications": rec_apps,
            "hired": rec_hired,
            "revenue": rec_revenue,
        })

    elapsed = time.time() - start_time
    logger.info(f"[EMPLOYER ANALYTICS] Completed in {elapsed:.2f}s")

    return {
        "kpis": {
            "active_mandates": active_jobs_count,
            "pipeline_revenue": round(pipeline_revenue, 2),
            "closed_revenue": round(closed_revenue, 2),
            "offers_pending": offers_pending,
            "avg_fee_percentage": round(avg_fee, 2),
        },
        "team_performance": team_performance,
        "company_revenue": company_revenue,
        "recruiter_contribution": recruiter_contribution,
    }


# ============== COMPANY PIPELINE VIEW ==============

@employer_router.get("/companies/{company_id}/pipeline")
async def get_company_pipeline(
    company_id: str,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Get company profile with pipeline view. Shows mandates, revenue breakdown, and detailed pipeline."""
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if current_user["role"] == "employer":
        if company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

    jobs = await db.jobs.find(
        {"company_id": company_id},
        {"_id": 0, "id": 1, "title": 1, "job_level": 1, "status": 1, "assigned_recruiter_ids": 1}
    ).to_list(10000)

    total_mandates = len(jobs)
    active_mandates = sum(1 for j in jobs if j.get("status") == "active")
    closed_mandates = sum(1 for j in jobs if j.get("status") == "closed")
    job_ids = [j["id"] for j in jobs]

    revenues = await db.revenue.find({"company_id": company_id}, {"_id": 0}).to_list(10000)
    total_revenue = sum(r.get("final_revenue", 0) for r in revenues)
    revenue_by_job = {}
    for r in revenues:
        jid = r.get("job_id")
        if jid not in revenue_by_job:
            revenue_by_job[jid] = {"expected": 0, "closed": 0}
        if r.get("is_closed"):
            revenue_by_job[jid]["closed"] += r.get("final_revenue", 0)
        else:
            revenue_by_job[jid]["expected"] += r.get("final_revenue", 0)

    company_commercial = company.get("commercial", {})
    avg_commercial_pct = 0
    if company_commercial.get("type") == "percentage" and company_commercial.get("percentage_value"):
        avg_commercial_pct = company_commercial["percentage_value"]

    recruiter_ids = set()
    for job in jobs:
        for rec_id in job.get("assigned_recruiter_ids", []):
            recruiter_ids.add(rec_id)

    recruiter_names = {}
    if recruiter_ids:
        recruiters = await db.users.find(
            {"id": {"$in": list(recruiter_ids)}},
            {"_id": 0, "id": 1, "name": 1}
        ).to_list(len(recruiter_ids))
        recruiter_names = {r["id"]: r.get("name", "Unknown") for r in recruiters}

    apps_pipeline = [
        {"$match": {"job_id": {"$in": job_ids}}},
        {"$group": {
            "_id": {"job_id": "$job_id", "stage": "$stage"},
            "count": {"$sum": 1}
        }}
    ]
    app_stats = await db.applications.aggregate(apps_pipeline).to_list(10000)

    stage_counts_by_job = {}
    for stat in app_stats:
        jid = stat["_id"]["job_id"]
        stage = stat["_id"]["stage"] or "applied"
        if jid not in stage_counts_by_job:
            stage_counts_by_job[jid] = {}
        stage_counts_by_job[jid][stage] = stat["count"]

    pipeline = []
    for job in jobs:
        job_rev = revenue_by_job.get(job["id"], {"expected": 0, "closed": 0})

        recruiters_list = [recruiter_names.get(rec_id, "Unknown") for rec_id in job.get("assigned_recruiter_ids", [])]

        pipeline.append({
            "job_id": job["id"],
            "job_title": job.get("title"),
            "job_level": job.get("job_level"),
            "status": job.get("status"),
            "recruiters": recruiters_list,
            "stage_counts": stage_counts_by_job.get(job["id"], {}),
            "expected_revenue": round(job_rev["expected"], 2),
            "closed_revenue": round(job_rev["closed"], 2),
        })

    return {
        "company": {
            "id": company["id"],
            "name": company.get("name"),
            "industry": company.get("industry"),
        },
        "summary": {
            "total_mandates": total_mandates,
            "active_mandates": active_mandates,
            "closed_mandates": closed_mandates,
            "total_revenue": round(total_revenue, 2),
            "avg_commercial_percentage": round(avg_commercial_pct, 2),
        },
        "commercials": [company_commercial] if company_commercial else [],
        "pipeline": pipeline,
    }
