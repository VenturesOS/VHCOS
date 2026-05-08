"""
VHC Talent OS - Account Manager Routes
Handles account manager assignments and their employer-like access.
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from config import db
from utils.auth import get_current_user, require_role

from routes.notifications import create_notification

account_manager_router = APIRouter(prefix="/api/account-manager", tags=["Account Manager"])

SENSITIVE_COMPANY_FIELDS = ["commercial_terms", "billing_details", "revenue_share", "contract_value", "invoice_history"]


def _strip_sensitive_fields(company):
    """Remove financial fields from company data for non-admin access."""
    for field in SENSITIVE_COMPANY_FIELDS:
        company.pop(field, None)
    return company


async def _validate_companies(company_ids):
    """Validate company IDs exist, return list of {id, name} dicts."""
    if not company_ids:
        return []
    companies = await db.companies.find(
        {"id": {"$in": company_ids}}, {"_id": 0, "id": 1, "name": 1}
    ).to_list(len(company_ids))
    found_ids = {c["id"] for c in companies}
    missing = [cid for cid in company_ids if cid not in found_ids]
    if missing:
        raise HTTPException(status_code=400, detail=f"Company {missing[0]} not found")
    return [{"id": c["id"], "name": c.get("name", "")} for c in companies]


async def _enforce_employer_ownership(user, company_ids):
    """Ensure employer only assigns companies they manage."""
    team = await db.teams.find_one(
        {"employer_id": user["id"], "status": "active"}, {"_id": 0}
    )
    if not team:
        return
    allowed_ids = set(team.get("company_ids", []))
    for cid in company_ids:
        if cid not in allowed_ids:
            raise HTTPException(status_code=403, detail=f"You don't manage company {cid}")


async def _merge_assignments(recruiter, valid_companies):
    """Merge new company assignments with existing ones, handling legacy format."""
    existing = recruiter.get("assigned_companies", [])

    # Convert legacy string format to dict format
    if existing and isinstance(existing[0], str):
        old_ids = list(existing)
        comps = await db.companies.find(
            {"id": {"$in": old_ids}}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(len(old_ids))
        comp_map = {c["id"]: c.get("name", "") for c in comps}
        existing = [{"id": eid, "name": comp_map.get(eid, "")} for eid in old_ids]

    existing_ids = {c["id"] for c in existing} if existing and isinstance(existing[0], dict) else set()
    for vc in valid_companies:
        if vc["id"] not in existing_ids:
            existing.append(vc)
            existing_ids.add(vc["id"])

    return existing if existing else valid_companies


async def _get_company_ids_for_user(user):
    """Get all company IDs accessible to an account manager (direct + team)."""
    assigned = user.get("assigned_companies", [])
    direct_ids = [e.get("id") if isinstance(e, dict) else e for e in assigned]

    team_ids = []
    user_team_id = user.get("team_id")
    if user_team_id:
        team = await db.teams.find_one({"id": user_team_id, "status": "active"}, {"_id": 0})
        if team:
            team_ids = team.get("company_ids", [])

    member_teams = await db.teams.find(
        {"recruiter_ids": user["id"], "status": "active"}, {"_id": 0, "company_ids": 1}
    ).to_list(10)
    for mt in member_teams:
        team_ids.extend(mt.get("company_ids", []))

    return list(set(direct_ids + team_ids))


@account_manager_router.post("/assign")
async def assign_account_manager(
    payload: dict,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Admin or Employer assigns companies to a recruiter as Account Manager."""
    recruiter_id = payload.get("recruiter_id")
    company_ids = payload.get("company_ids", [])

    if not recruiter_id:
        raise HTTPException(status_code=400, detail="recruiter_id is required")

    recruiter = await db.users.find_one({"id": recruiter_id, "role": "recruiter"}, {"_id": 0})
    if not recruiter:
        raise HTTPException(status_code=404, detail="Recruiter not found")

    valid_companies = await _validate_companies(company_ids)

    if current_user["role"] == "employer":
        await _enforce_employer_ownership(current_user, company_ids)

    final_companies = await _merge_assignments(recruiter, valid_companies)

    await db.users.update_one(
        {"id": recruiter_id},
        {"$set": {
            "is_account_manager": True,
            "assigned_companies": final_companies,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )

    company_names = [c["name"] for c in valid_companies]
    try:
        await create_notification(
            user_id=recruiter_id,
            notification_type="am_company_assigned",
            title="Account Manager Assignment",
            message=f"You've been assigned as Account Manager for: {', '.join(company_names)}",
            link="/recruiter/account-manager",
            metadata={"company_ids": company_ids},
        )
    except Exception:
        pass

    return {
        "success": True,
        "recruiter_id": recruiter_id,
        "recruiter_name": recruiter.get("name"),
        "assigned_companies": final_companies,
        "message": f"Assigned {len(company_ids)} companies to {recruiter.get('name')}"
    }


@account_manager_router.post("/remove-company")
async def remove_company_from_account_manager(
    payload: dict,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Remove a company assignment from an account manager."""
    recruiter_id = payload.get("recruiter_id")
    company_id = payload.get("company_id")

    if not recruiter_id or not company_id:
        raise HTTPException(status_code=400, detail="recruiter_id and company_id required")

    recruiter = await db.users.find_one({"id": recruiter_id}, {"_id": 0})
    if not recruiter:
        raise HTTPException(status_code=404, detail="Recruiter not found")

    assigned = recruiter.get("assigned_companies", [])
    updated = [c for c in assigned if (c.get("id") if isinstance(c, dict) else c) != company_id]

    is_still_am = len(updated) > 0

    await db.users.update_one(
        {"id": recruiter_id},
        {"$set": {
            "assigned_companies": updated,
            "is_account_manager": is_still_am,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )

    return {"success": True, "remaining_companies": len(updated), "is_account_manager": is_still_am}


@account_manager_router.get("/my-companies")
async def get_my_companies(current_user: dict = Depends(get_current_user)):
    """Get companies assigned to the current account manager or employer."""
    is_am = current_user.get("is_account_manager")
    is_employer = current_user.get("role") == "employer"

    if not is_am and not is_employer:
        raise HTTPException(status_code=403, detail="Not an account manager or employer")

    if is_employer:
        team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
        company_ids = team.get("company_ids", []) if team else []
    else:
        company_ids = await _get_company_ids_for_user(current_user)

    companies = []
    if company_ids:
        raw = await db.companies.find({"id": {"$in": company_ids}}, {"_id": 0}).to_list(200)
        seen = set()
        for company in raw:
            if company["id"] not in seen:
                seen.add(company["id"])
                companies.append(_strip_sensitive_fields(company))

    return {"companies": companies, "total": len(companies)}


@account_manager_router.get("/company/{company_id}/jobs")
async def get_company_jobs(company_id: str, current_user: dict = Depends(get_current_user)):
    """Get jobs for a specific company (account manager or employer access)."""
    if current_user.get("role") == "employer":
        # Verify employer has this company in their team
        team = await db.teams.find_one({"employer_id": current_user["id"], "company_ids": company_id}, {"_id": 0})
        if not team:
            raise HTTPException(status_code=403, detail="You don't have access to this company")
    else:
        _verify_am_company_access(current_user, company_id)

    jobs = await db.jobs.find(
        {"company_id": company_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(500)

    # Mask commercial fields
    for job in jobs:
        job.pop("commercial_terms", None)
        job.pop("billing_rate", None)
        job.pop("revenue_info", None)

    return {"jobs": jobs, "total": len(jobs)}


@account_manager_router.get("/company/{company_id}/pipeline")
async def get_company_pipeline(company_id: str, current_user: dict = Depends(get_current_user)):
    """Get pipeline/applications for a company's jobs (account manager or employer access)."""
    if current_user.get("role") == "employer":
        team = await db.teams.find_one({"employer_id": current_user["id"], "company_ids": company_id}, {"_id": 0})
        if not team:
            raise HTTPException(status_code=403, detail="You don't have access to this company")
    else:
        _verify_am_company_access(current_user, company_id)

    # Get all job IDs for this company
    jobs = await db.jobs.find({"company_id": company_id}, {"_id": 0, "id": 1, "title": 1}).to_list(500)
    job_ids = [j["id"] for j in jobs]
    job_map = {j["id"]: j.get("title", "") for j in jobs}

    if not job_ids:
        return {"applications": [], "total": 0, "stage_summary": {}}

    applications = await db.applications.find(
        {"job_id": {"$in": job_ids}},
        {"_id": 0}
    ).sort("applied_at", -1).to_list(1000)

    # Add job title and mask commercials
    stage_summary = {}
    for app in applications:
        app["job_title"] = job_map.get(app.get("job_id"), "")
        app.pop("commercial_info", None)
        app.pop("billing_details", None)
        stage = app.get("stage", "applied")
        stage_summary[stage] = stage_summary.get(stage, 0) + 1

    return {"applications": applications, "total": len(applications), "stage_summary": stage_summary}


@account_manager_router.get("/company/{company_id}/analytics")
async def get_company_analytics(company_id: str, current_user: dict = Depends(get_current_user)):
    """Get analytics for a company (account manager or employer access)."""
    if current_user.get("role") == "employer":
        team = await db.teams.find_one({"employer_id": current_user["id"], "company_ids": company_id}, {"_id": 0})
        if not team:
            raise HTTPException(status_code=403, detail="You don't have access to this company")
    else:
        _verify_am_company_access(current_user, company_id)

    jobs = await db.jobs.find({"company_id": company_id}, {"_id": 0}).to_list(500)
    job_ids = [j["id"] for j in jobs]

    total_jobs = len(jobs)
    active_jobs = sum(1 for j in jobs if j.get("status") == "active")
    closed_jobs = sum(1 for j in jobs if j.get("status") == "closed")

    # Application stats
    applications = await db.applications.find(
        {"job_id": {"$in": job_ids}},
        {"_id": 0, "stage": 1}
    ).to_list(5000)

    stage_stats = {}
    for app in applications:
        stage = app.get("stage", "applied")
        stage_stats[stage] = stage_stats.get(stage, 0) + 1

    return {
        "total_jobs": total_jobs,
        "active_jobs": active_jobs,
        "closed_jobs": closed_jobs,
        "total_applications": len(applications),
        "stage_stats": stage_stats,
        # No revenue or team performance data
    }


@account_manager_router.get("/recruiters")
async def get_available_recruiters(current_user: dict = Depends(get_current_user)):
    """Get list of recruiters an account manager or employer can assign candidates to."""
    is_am = current_user.get("is_account_manager")
    is_employer = current_user.get("role") == "employer"

    if not is_am and not is_employer:
        raise HTTPException(status_code=403, detail="Not an account manager or employer")

    if is_employer:
        team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
    else:
        team = await db.teams.find_one({"recruiter_ids": current_user["id"], "status": "active"}, {"_id": 0})

    if not team:
        return {"recruiters": []}

    recruiter_ids = team.get("recruiter_ids", [])
    recruiters = await db.users.find(
        {"id": {"$in": recruiter_ids}, "role": "recruiter", "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1}
    ).to_list(100)

    return {"recruiters": recruiters}


@account_manager_router.post("/assign-candidate")
async def assign_candidate_to_recruiter(
    payload: dict,
    current_user: dict = Depends(get_current_user)
):
    """Account manager or employer assigns a candidate (application) to a junior recruiter."""
    is_am = current_user.get("is_account_manager")
    is_employer = current_user.get("role") == "employer"

    if not is_am and not is_employer:
        raise HTTPException(status_code=403, detail="Not an account manager or employer")

    application_id = payload.get("application_id")
    recruiter_id = payload.get("recruiter_id")

    if not application_id or not recruiter_id:
        raise HTTPException(status_code=400, detail="application_id and recruiter_id required")

    application = await db.applications.find_one({"id": application_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    recruiter = await db.users.find_one(
        {"id": recruiter_id, "role": "recruiter", "is_active": True},
        {"_id": 0, "id": 1, "name": 1}
    )
    if not recruiter:
        raise HTTPException(status_code=404, detail="Recruiter not found")

    now = datetime.now(timezone.utc).isoformat()
    await db.applications.update_one(
        {"id": application_id},
        {"$set": {
            "assigned_recruiter_id": recruiter_id,
            "assigned_recruiter_name": recruiter["name"],
            "assigned_by": current_user["id"],
            "assigned_by_name": current_user["name"],
            "assigned_at": now,
            "updated_at": now
        }}
    )

    # Notify the junior recruiter about candidate assignment
    try:
        await create_notification(
            user_id=recruiter_id,
            notification_type="candidate_assigned",
            title="Candidate Assigned to You",
            message=f"{current_user['name']} assigned {application.get('candidate_name', 'a candidate')} to you for {application.get('job_title', 'a job')}",
            link="/recruiter/pipeline",
            metadata={"application_id": application_id},
        )
    except Exception:
        pass

    return {
        "success": True,
        "message": f"Assigned to {recruiter['name']}",
        "assigned_recruiter": recruiter
    }

    # Notify the junior recruiter about candidate assignment
    try:
        await create_notification(
            user_id=recruiter_id,
            notification_type="candidate_assigned",
            title="Candidate Assigned to You",
            message=f"{current_user['name']} assigned {application.get('candidate_name', 'a candidate')} to you for {application.get('job_title', 'a job')}",
            link="/recruiter/pipeline",
            metadata={"application_id": application_id},
        )
    except Exception:
        pass


@account_manager_router.get("/dashboard-stats")
async def get_am_dashboard_stats(current_user: dict = Depends(get_current_user)):
    """Get dashboard stats for account manager or employer across all assigned companies."""
    is_am = current_user.get("is_account_manager")
    is_employer = current_user.get("role") == "employer"

    if not is_am and not is_employer:
        raise HTTPException(status_code=403, detail="Not an account manager or employer")

    if is_employer:
        team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
        company_ids = team.get("company_ids", []) if team else []
    else:
        # Merge direct + team companies
        assigned = current_user.get("assigned_companies", [])
        direct_ids = [c.get("id") if isinstance(c, dict) else c for c in assigned]

        team_ids = []
        user_team_id = current_user.get("team_id")
        if user_team_id:
            team = await db.teams.find_one({"id": user_team_id, "status": "active"}, {"_id": 0})
            if team:
                team_ids = team.get("company_ids", [])
        member_teams = await db.teams.find(
            {"recruiter_ids": current_user["id"], "status": "active"},
            {"_id": 0, "company_ids": 1}
        ).to_list(10)
        for mt in member_teams:
            team_ids.extend(mt.get("company_ids", []))
        company_ids = list(set(direct_ids + team_ids))

    if not company_ids:
        return {"total_companies": 0, "total_jobs": 0, "active_jobs": 0, "total_applications": 0, "stage_stats": {}}

    jobs = await db.jobs.find(
        {"company_id": {"$in": company_ids}},
        {"_id": 0, "id": 1, "status": 1}
    ).to_list(1000)

    job_ids = [j["id"] for j in jobs]
    total_jobs = len(jobs)
    active_jobs = sum(1 for j in jobs if j.get("status") == "active")

    applications = await db.applications.find(
        {"job_id": {"$in": job_ids}},
        {"_id": 0, "stage": 1}
    ).to_list(5000)

    stage_stats = {}
    for app in applications:
        stage = app.get("stage", "applied")
        stage_stats[stage] = stage_stats.get(stage, 0) + 1

    return {
        "total_companies": len(company_ids),
        "total_jobs": total_jobs,
        "active_jobs": active_jobs,
        "total_applications": len(applications),
        "stage_stats": stage_stats,
    }


def _verify_am_company_access(current_user: dict, company_id: str):
    """Verify account manager or employer has access to the given company."""
    if current_user.get("role") == "admin":
        return  # Admin always has access

    if current_user.get("role") == "employer":
        return  # Employer access is verified at the route level via team check

    if not current_user.get("is_account_manager"):
        raise HTTPException(status_code=403, detail="Not an account manager")

    assigned = current_user.get("assigned_companies", [])
    assigned_ids = {c.get("id") if isinstance(c, dict) else c for c in assigned}

    if company_id not in assigned_ids:
        raise HTTPException(status_code=403, detail="You don't have access to this company")
