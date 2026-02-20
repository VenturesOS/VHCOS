"""
VHC Talent OS - Admin Routes
Handles user management and admin-only operations.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query

# Import configuration
from config import db

# Import models
from models import (
    UserResponse, UserUpdate, AdminUserCreate, AdminPasswordReset,
    CompanyCreate, CompanyResponse, CompanyUpdate
)

# Import utilities
from utils import hash_password, require_role


# Create router for admin endpoints
admin_router = APIRouter(prefix="/api", tags=["Admin"])


def _validate_commercial(commercial):
    """Validate commercial model fields based on type."""
    if commercial.type not in ("percentage", "fixed", "level_based"):
        raise HTTPException(status_code=400, detail="Commercial type must be percentage, fixed, or level_based")

    if commercial.type == "percentage":
        if commercial.percentage_value is None or commercial.percentage_value <= 0:
            raise HTTPException(status_code=400, detail="percentage_value is required and must be > 0")

    elif commercial.type == "fixed":
        if commercial.fixed_fee_amount is None or commercial.fixed_fee_amount <= 0:
            raise HTTPException(status_code=400, detail="fixed_fee_amount is required and must be > 0")

    elif commercial.type == "level_based":
        levels = commercial.level_config or []
        for i, lv in enumerate(levels):
            if lv.min_salary >= lv.max_salary:
                raise HTTPException(status_code=400, detail=f"Level {i+1}: min_salary must be less than max_salary")
            if lv.percentage <= 0:
                raise HTTPException(status_code=400, detail=f"Level {i+1}: percentage must be > 0")
        # Check for overlapping ranges
        sorted_levels = sorted(levels, key=lambda x: x.min_salary)
        for i in range(1, len(sorted_levels)):
            if sorted_levels[i].min_salary <= sorted_levels[i-1].max_salary:
                raise HTTPException(
                    status_code=400,
                    detail=f"Overlapping salary ranges: level {i} and {i+1}"
                )


# ============== COMPANY MANAGEMENT (ADMIN) ==============

@admin_router.get("/companies", response_model=List[CompanyResponse])
async def get_all_companies(current_user: dict = Depends(require_role(["admin"]))):
    """
    Get all companies (Admin only).
    Returns complete list of companies with assigned employer info.
    """
    companies = await db.companies.find({}, {"_id": 0}).to_list(1000)
    
    # Enrich with employer names
    result = []
    for company in companies:
        if company.get("assigned_employer_id"):
            employer = await db.users.find_one(
                {"id": company["assigned_employer_id"]},
                {"_id": 0, "name": 1}
            )
            if employer:
                company["assigned_employer_name"] = employer.get("name")
        result.append(CompanyResponse(**company))
    
    return result


@admin_router.get("/employers/{employer_id}/companies")
async def get_employer_companies(
    employer_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get all companies assigned to a specific employer (via direct assignment or team)."""
    # Companies directly assigned
    direct = await db.companies.find(
        {"assigned_employer_id": employer_id}, {"_id": 0}
    ).to_list(100)

    # Companies linked via teams
    teams = await db.teams.find(
        {"employer_id": employer_id}, {"_id": 0, "company_ids": 1}
    ).to_list(100)
    team_company_ids = set()
    for t in teams:
        team_company_ids.update(t.get("company_ids", []))

    # Merge: add team-linked companies not already in direct list
    direct_ids = {c["id"] for c in direct}
    for cid in team_company_ids - direct_ids:
        company = await db.companies.find_one({"id": cid}, {"_id": 0})
        if company:
            direct.append(company)

    return {"companies": [CompanyResponse(**c) for c in direct]}


@admin_router.post("/companies", response_model=CompanyResponse)
async def create_company(
    company_data: CompanyCreate,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Create a new company (Admin only).
    Commercial model is mandatory at creation.
    """
    # Validate commercial is provided
    if not company_data.commercial:
        raise HTTPException(status_code=400, detail="Commercial structure is required")

    _validate_commercial(company_data.commercial)

    company = {
        "id": str(uuid.uuid4()),
        "name": company_data.name,
        "description": company_data.description,
        "industry": company_data.industry,
        "website": company_data.website,
        "location": company_data.location,
        "hr_contacts": [c.model_dump() for c in (company_data.hr_contacts or [])],
        "commercial": company_data.commercial.model_dump(),
        "assigned_employer_id": None,
        "assigned_employer_name": None,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    await db.companies.insert_one(company)
    return CompanyResponse(**company)


@admin_router.get("/companies/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: str,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Get company details by ID.
    Admin: can access any company
    Employer: can only access assigned companies
    """
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Employer access control
    if current_user["role"] == "employer":
        # Check if employer is assigned to this company via team
        teams = await db.teams.find(
            {"employer_id": current_user["id"], "company_ids": company_id},
            {"_id": 0, "id": 1}
        ).to_list(1)
        if not teams:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Enrich with employer name
    if company.get("assigned_employer_id"):
        employer = await db.users.find_one(
            {"id": company["assigned_employer_id"]},
            {"_id": 0, "name": 1}
        )
        if employer:
            company["assigned_employer_name"] = employer.get("name")
    
    return CompanyResponse(**company)


@admin_router.put("/companies/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: str,
    company_data: CompanyCreate,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Update company details (Admin only).
    """
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if company_data.commercial:
        _validate_commercial(company_data.commercial)

    now = datetime.now(timezone.utc).isoformat()

    update_data = {
        "name": company_data.name,
        "description": company_data.description,
        "industry": company_data.industry,
        "website": company_data.website,
        "location": company_data.location,
        "hr_contacts": [c.model_dump() for c in (company_data.hr_contacts or [])],
        "updated_at": now
    }

    if company_data.commercial:
        update_data["commercial"] = company_data.commercial.model_dump()

    await db.companies.update_one(
        {"id": company_id},
        {"$set": update_data}
    )

    updated_company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    return CompanyResponse(**updated_company)


@admin_router.put("/companies/{company_id}/assign-employer")
async def assign_employer_to_company(
    company_id: str,
    employer_id: str = Query(...),
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Assign an employer to a company (Admin only).
    Sets assigned_employer_id on the company and adds company to employer's team.
    """
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    employer = await db.users.find_one({"id": employer_id, "role": "employer"}, {"_id": 0, "id": 1, "name": 1})
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")

    now = datetime.now(timezone.utc).isoformat()

    # Update company with assigned employer
    await db.companies.update_one(
        {"id": company_id},
        {"$set": {
            "assigned_employer_id": employer_id,
            "assigned_employer_name": employer.get("name"),
            "updated_at": now,
        }}
    )

    # Also ensure the company is in the employer's team
    existing_team = await db.teams.find_one({"employer_id": employer_id}, {"_id": 0})
    if existing_team:
        await db.teams.update_one(
            {"employer_id": employer_id},
            {"$addToSet": {"company_ids": company_id}, "$set": {"updated_at": now}}
        )
    else:
        await db.teams.insert_one({
            "id": str(uuid.uuid4()),
            "name": f"{employer.get('name', 'Employer')} Team",
            "employer_id": employer_id,
            "company_ids": [company_id],
            "recruiter_ids": [],
            "status": "active",
            "created_at": now,
            "updated_at": now,
        })

    # Remove company from any OTHER employer's team to avoid duplication
    await db.teams.update_many(
        {"employer_id": {"$ne": employer_id}, "company_ids": company_id},
        {"$pull": {"company_ids": company_id}, "$set": {"updated_at": now}}
    )

    return {"message": f"Company '{company.get('name')}' assigned to employer '{employer.get('name')}'"}


@admin_router.delete("/companies/{company_id}")
async def delete_company(
    company_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Delete/Deactivate a company (Admin only).
    
    Soft delete: Sets status to 'deleted' and preserves data integrity.
    
    Cascade rules:
    - Jobs linked to this company: Marked as 'archived' (not deleted)
    - Teams with this company: Company removed from team's company_ids
    - Applications: Preserved (historical data)
    """
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Soft delete - set status to 'deleted'
    await db.companies.update_one(
        {"id": company_id},
        {"$set": {
            "status": "deleted",
            "deleted_at": now,
            "deleted_by": current_user["id"]
        }}
    )
    
    # Archive jobs linked to this company
    jobs_archived = await db.jobs.update_many(
        {"company_id": company_id, "status": {"$ne": "archived"}},
        {"$set": {"status": "archived", "updated_at": now}}
    )
    
    # Remove company from teams' company_ids
    await db.teams.update_many(
        {"company_ids": company_id},
        {"$pull": {"company_ids": company_id}}
    )
    
    # Audit log
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "entity_type": "company",
        "entity_id": company_id,
        "action": "deleted",
        "changed_by": current_user["id"],
        "changed_by_name": current_user.get("name"),
        "changed_by_role": current_user["role"],
        "timestamp": now,
        "details": {
            "jobs_archived": jobs_archived.modified_count,
            "company_name": company.get("name")
        }
    })
    
    return {
        "message": "Company deleted successfully",
        "company_id": company_id,
        "jobs_archived": jobs_archived.modified_count
    }


# ============== USER MANAGEMENT (ADMIN) ==============

@admin_router.get("/users", response_model=List[UserResponse])
async def get_users(current_user: dict = Depends(require_role(["admin"]))):
    users = await db.users.find({}, {"_id": 0, "password": 0}).to_list(1000)
    return [UserResponse(**u) for u in users]


@admin_router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, current_user: dict = Depends(require_role(["admin"]))):
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**user)


@admin_router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, update_data: UserUpdate, current_user: dict = Depends(require_role(["admin"]))):
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = await db.users.update_one({"id": user_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    return UserResponse(**user)


@admin_router.delete("/users/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(require_role(["admin"]))):
    # Soft delete - set is_active to False instead of hard delete
    result = await db.users.update_one(
        {"id": user_id}, 
        {"$set": {"is_active": False, "deleted_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deactivated successfully"}


@admin_router.post("/admin/users", response_model=UserResponse)
async def admin_create_user(user_data: AdminUserCreate, current_user: dict = Depends(require_role(["admin"]))):
    """Admin-only endpoint to create users with any role"""
    # Validate role
    allowed_roles = ["admin", "employer", "recruiter", "candidate"]
    if user_data.role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(allowed_roles)}")
    
    # Check if email already exists
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": user_data.email,
        "name": user_data.name,
        "role": user_data.role,
        "password": hash_password(user_data.password),
        "phone": user_data.phone,
        "company_id": user_data.company_id,
        "is_active": True,
        "requires_password_reset": False,
        "created_at": now,
        "created_by": current_user["id"]
    }
    
    await db.users.insert_one(user_doc)
    
    # Create candidate profile if role is candidate
    if user_data.role == "candidate":
        profile_doc = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": user_data.name,
            "email": user_data.email,
            "phone": user_data.phone,
            "headline": None,
            "summary": None,
            "skills": [],
            "experience": [],
            "education": [],
            "resume_url": None,
            "created_at": now,
            "updated_at": now
        }
        await db.candidates.insert_one(profile_doc)
    
    return UserResponse(**{k: v for k, v in user_doc.items() if k != "password" and k != "_id"})


@admin_router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_user_password(user_id: str, reset_data: AdminPasswordReset, current_user: dict = Depends(require_role(["admin"]))):
    """Admin-only endpoint to reset any user's password"""
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Cannot reset admin passwords through this endpoint for security
    if user.get("role") == "admin" and user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Cannot reset another admin's password")
    
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "password": hash_password(reset_data.new_password),
            "requires_password_reset": False,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": "Password reset successfully", "user_id": user_id}


@admin_router.post("/admin/users/{user_id}/toggle-status")
async def admin_toggle_user_status(user_id: str, current_user: dict = Depends(require_role(["admin"]))):
    """Admin-only endpoint to activate/deactivate a user"""
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Cannot deactivate own account
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    
    new_status = not user.get("is_active", True)
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"is_active": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"message": f"User {'activated' if new_status else 'deactivated'} successfully", "is_active": new_status}


@admin_router.get("/admin/employers")
async def get_employers_list(current_user: dict = Depends(require_role(["admin"]))):
    """Get list of all employers for recruiter assignment"""
    employers = await db.users.find({"role": "employer"}, {"_id": 0, "password": 0}).to_list(1000)
    return employers


@admin_router.post("/admin/assign-recruiter")
async def assign_recruiter_to_employer(
    recruiter_id: str,
    employer_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Assign a recruiter to an employer"""
    recruiter = await db.users.find_one({"id": recruiter_id, "role": "recruiter"})
    if not recruiter:
        raise HTTPException(status_code=404, detail="Recruiter not found")
    
    employer = await db.users.find_one({"id": employer_id, "role": "employer"})
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")
    
    # Update recruiter with employer assignment
    await db.users.update_one(
        {"id": recruiter_id},
        {"$set": {"assigned_employer_id": employer_id, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"message": "Recruiter assigned to employer successfully"}


# ============== ADMIN PIPELINE VIEW ==============

@admin_router.get("/admin/pipeline")
async def get_admin_pipeline(
    employer_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    team_id: Optional[str] = None,
    job_id: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Admin collective pipeline view across all employers and recruiters.
    Read-only aggregated view for management oversight.
    
    Filter Hierarchy:
    - employer_id: Filter by employer (via teams → companies → jobs)
    - team_id: Filter by specific team (jobs under that team)
    - recruiter_id: Filter by recruiter (jobs they posted or are assigned to)
    - job_id: Filter by specific job
    
    FIXED: Proper relationship joins via Team → Company → Job links.
    """
    # Build the job filter based on provided parameters
    job_filter = {}
    
    if job_id:
        # Direct job filter - most specific
        job_filter["id"] = job_id
    elif team_id:
        # Filter by team - jobs with this team_id
        job_filter["team_id"] = team_id
    elif employer_id:
        # Filter by employer - get all companies/teams for this employer
        # Teams link employers to companies
        employer_teams = await db.teams.find(
            {"employer_id": employer_id},
            {"_id": 0, "id": 1, "company_ids": 1}
        ).to_list(100)
        
        team_ids = [t["id"] for t in employer_teams]
        company_ids = []
        for t in employer_teams:
            company_ids.extend(t.get("company_ids", []))
        
        # Jobs either have team_id or company_id or posted_by employer
        if team_ids or company_ids:
            job_filter["$or"] = []
            if team_ids:
                job_filter["$or"].append({"team_id": {"$in": team_ids}})
            if company_ids:
                job_filter["$or"].append({"company_id": {"$in": company_ids}})
            # Also include jobs directly posted by employer
            job_filter["$or"].append({"posted_by": employer_id})
        else:
            # Employer has no teams/companies - filter by posted_by only
            job_filter["posted_by"] = employer_id
    elif recruiter_id:
        # Filter by recruiter - jobs they posted or are assigned to
        # Check team membership for recruiter
        recruiter_teams = await db.teams.find(
            {"recruiter_ids": recruiter_id},
            {"_id": 0, "id": 1}
        ).to_list(100)
        recruiter_team_ids = [t["id"] for t in recruiter_teams]
        
        job_filter["$or"] = [
            {"posted_by": recruiter_id}
        ]
        if recruiter_team_ids:
            job_filter["$or"].append({"team_id": {"$in": recruiter_team_ids}})
    
    # Get jobs matching the filter
    if job_filter:
        jobs = await db.jobs.find(job_filter, {"_id": 0}).to_list(10000)
    else:
        jobs = await db.jobs.find({}, {"_id": 0}).to_list(10000)
    
    jobs_map = {j["id"]: j for j in jobs}
    job_ids = list(jobs_map.keys())
    
    # Get applications for these jobs
    if job_ids:
        applications = await db.applications.find(
            {"job_id": {"$in": job_ids}},
            {"_id": 0}
        ).to_list(100000)
    else:
        applications = []
    
    # Define all pipeline stages
    all_stages = ["applied", "shortlisted", "submitted_to_client", "interview", "offered", "hired", "joined", "rejected", "on_hold"]
    
    # Group applications by stage
    pipeline_data = {stage: [] for stage in all_stages}
    
    for app in applications:
        stage = app.get("stage", "applied")
        if stage not in pipeline_data:
            stage = "applied"
        
        job = jobs_map.get(app.get("job_id"), {})
        
        pipeline_data[stage].append({
            "id": app.get("id"),
            "candidate_name": app.get("candidate_name", "Unknown"),
            "candidate_email": app.get("candidate_email"),
            "job_title": app.get("job_title") or job.get("title", "Unknown"),
            "job_id": app.get("job_id"),
            "company_name": job.get("company_name", ""),
            "match_score": app.get("match_score", 0),
            "applied_at": app.get("created_at"),
            "current_salary": app.get("current_salary"),
            "notice_period": app.get("notice_period"),
            "resume_url": app.get("resume_url"),
            "offered_ctc": app.get("offered_ctc"),
            "offer_date": app.get("offer_date"),
            "join_date": app.get("join_date"),
        })
    
    # Calculate stage counts
    stage_counts = {stage: len(apps) for stage, apps in pipeline_data.items()}
    
    # Get filter options
    employers = await db.users.find({"role": "employer"}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(1000)
    recruiters = await db.users.find({"role": "recruiter"}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(1000)
    teams = await db.teams.find({}, {"_id": 0, "id": 1, "name": 1, "employer_id": 1}).to_list(1000)
    
    return {
        "pipeline": pipeline_data,
        "stage_counts": stage_counts,
        "total_applications": len(applications),
        "filters": {
            "employers": employers,
            "recruiters": recruiters,
            "teams": teams,
            "jobs": [{"id": j["id"], "title": j.get("title", "Untitled")} for j in jobs]
        }
    }



# ============== DASHBOARD STATS ENDPOINTS ==============

@admin_router.get("/stats/admin")
async def get_admin_dashboard_stats(current_user: dict = Depends(require_role(["admin"]))):
    """
    Admin dashboard statistics.
    Returns counts and recent data for the admin overview dashboard.
    
    ALWAYS returns complete schema even when data is empty.
    """
    # User counts
    total_users = await db.users.count_documents({})
    
    # Users by role aggregation
    role_pipeline = [
        {"$group": {"_id": "$role", "count": {"$sum": 1}}}
    ]
    role_results = await db.users.aggregate(role_pipeline).to_list(10)
    users_by_role = {r["_id"]: r["count"] for r in role_results if r["_id"]}
    
    # Job counts
    total_jobs = await db.jobs.count_documents({"status": {"$in": ["active", "pending_approval"]}})
    
    # Application counts
    total_applications = await db.applications.count_documents({})
    
    # Company counts
    total_companies = await db.companies.count_documents({})
    
    # Recent applications (last 10)
    recent_apps = await db.applications.find(
        {},
        {"_id": 0, "id": 1, "candidate_name": 1, "job_title": 1, "stage": 1, "created_at": 1}
    ).sort("created_at", -1).limit(10).to_list(10)
    
    return {
        "total_users": total_users,
        "total_jobs": total_jobs,
        "total_applications": total_applications,
        "total_companies": total_companies,
        "users_by_role": users_by_role,
        "recent_applications": recent_apps
    }


@admin_router.get("/stats/employer")
async def get_employer_dashboard_stats(current_user: dict = Depends(require_role(["admin", "employer"]))):
    """
    Employer dashboard statistics.
    Returns job counts and application stats for employer overview.
    
    ALWAYS returns complete schema even when data is empty.
    """
    # Get jobs for this employer
    if current_user["role"] == "employer":
        # Get jobs created by employer or for their companies/teams
        company_ids = []
        team_ids = []
        
        # Get all teams (including disabled) to find related jobs
        teams = await db.teams.find(
            {"employer_id": current_user["id"]},
            {"id": 1, "company_ids": 1, "_id": 0}
        ).to_list(100)
        
        for team in teams:
            team_ids.append(team.get("id"))
            company_ids.extend(team.get("company_ids", []))
        
        # Build flexible query - employer can see jobs they created, 
        # jobs for their companies, or jobs under their teams
        or_conditions = [
            {"created_by": current_user["id"]},
            {"posted_by": current_user["id"]}
        ]
        if company_ids:
            or_conditions.append({"company_id": {"$in": company_ids}})
        if team_ids:
            or_conditions.append({"team_id": {"$in": team_ids}})
        
        jobs_query = {"$or": or_conditions}
    else:
        # Admin sees all
        jobs_query = {}
    
    my_jobs = await db.jobs.count_documents({
        **jobs_query,
        "status": {"$in": ["active", "pending_approval"]}
    })
    
    # Get job IDs for application counts
    job_ids = await db.jobs.distinct("id", jobs_query)
    
    # Total applicants for employer's jobs
    if job_ids:
        total_applicants = await db.applications.count_documents({"job_id": {"$in": job_ids}})
        
        # Stage stats aggregation
        stage_pipeline = [
            {"$match": {"job_id": {"$in": job_ids}}},
            {"$group": {"_id": "$stage", "count": {"$sum": 1}}}
        ]
        stage_results = await db.applications.aggregate(stage_pipeline).to_list(20)
        stage_stats = {r["_id"]: r["count"] for r in stage_results if r["_id"]}
    else:
        total_applicants = 0
        stage_stats = {}
    
    return {
        "my_jobs": my_jobs,
        "total_applicants": total_applicants,
        "stage_stats": {
            "applied": stage_stats.get("applied", 0),
            "shortlisted": stage_stats.get("shortlisted", 0),
            "submitted_to_client": stage_stats.get("submitted_to_client", 0),
            "interview": stage_stats.get("interview", 0),
            "offered": stage_stats.get("offered", 0),
            "hired": stage_stats.get("hired", 0),
            "joined": stage_stats.get("joined", 0),
            "rejected": stage_stats.get("rejected", 0)
        }
    }


@admin_router.get("/stats/recruiter")
async def get_recruiter_dashboard_stats(current_user: dict = Depends(require_role(["admin", "recruiter"]))):
    """
    Recruiter dashboard statistics.
    Returns mandate counts and pipeline stats for recruiter overview.
    
    ALWAYS returns complete schema even when data is empty.
    """
    if current_user["role"] == "recruiter":
        # Get jobs assigned to this recruiter or created by them
        jobs_query = {
            "$or": [
                {"created_by": current_user["id"]},
                {"assigned_recruiters": current_user["id"]}
            ]
        }
    else:
        # Admin sees all
        jobs_query = {}
    
    # Total active mandates
    total_jobs = await db.jobs.count_documents({
        **jobs_query,
        "status": {"$in": ["active", "pending_approval"]}
    })
    
    # Get job IDs for application counts
    job_ids = await db.jobs.distinct("id", jobs_query)
    
    # Total candidates in pipeline
    if job_ids:
        total_candidates = await db.applications.count_documents({"job_id": {"$in": job_ids}})
        
        # Pipeline stats aggregation
        pipeline_agg = [
            {"$match": {"job_id": {"$in": job_ids}}},
            {"$group": {"_id": "$stage", "count": {"$sum": 1}}}
        ]
        pipeline_results = await db.applications.aggregate(pipeline_agg).to_list(20)
        pipeline_stats = {r["_id"]: r["count"] for r in pipeline_results if r["_id"]}
    else:
        total_candidates = 0
        pipeline_stats = {}
    
    return {
        "total_jobs": total_jobs,
        "total_candidates": total_candidates,
        "pipeline_stats": {
            "applied": pipeline_stats.get("applied", 0),
            "shortlisted": pipeline_stats.get("shortlisted", 0),
            "submitted_to_client": pipeline_stats.get("submitted_to_client", 0),
            "interview": pipeline_stats.get("interview", 0),
            "offered": pipeline_stats.get("offered", 0),
            "hired": pipeline_stats.get("hired", 0),
            "joined": pipeline_stats.get("joined", 0),
            "rejected": pipeline_stats.get("rejected", 0)
        }
    }


@admin_router.get("/stats/candidate")
async def get_candidate_dashboard_stats(current_user: dict = Depends(require_role(["admin", "candidate"]))):
    """
    Candidate dashboard statistics.
    Returns application stats for candidate overview.
    
    ALWAYS returns complete schema even when data is empty.
    """
    if current_user["role"] == "candidate":
        # Get candidate's applications
        apps_query = {"candidate_id": current_user["id"]}
    else:
        # Admin testing endpoint - return empty
        apps_query = {"_id": None}
    
    # Total applications
    total_applications = await db.applications.count_documents(apps_query)
    
    # Application stats by stage
    if current_user["role"] == "candidate":
        stage_pipeline = [
            {"$match": apps_query},
            {"$group": {"_id": "$stage", "count": {"$sum": 1}}}
        ]
        stage_results = await db.applications.aggregate(stage_pipeline).to_list(20)
        application_stats = {r["_id"]: r["count"] for r in stage_results if r["_id"]}
    else:
        application_stats = {}
    
    return {
        "total_applications": total_applications,
        "application_stats": {
            "applied": application_stats.get("applied", 0),
            "shortlisted": application_stats.get("shortlisted", 0),
            "interview": application_stats.get("interview", 0),
            "offered": application_stats.get("offered", 0),
            "hired": application_stats.get("hired", 0),
            "rejected": application_stats.get("rejected", 0)
        },
        "active_jobs": await db.jobs.count_documents({"status": "active"})
    }
