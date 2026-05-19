"""
VHC Talent OS - Admin Routes
Handles user management and admin-only operations.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Any, Dict
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

# Import Zero Trust middleware
from middleware.zero_trust import require_zero_trust

# Import environment resolver (with fallback)
try:
    from utils.environment import normalize_email, ENV_NAME, DB_NAME
except ImportError:
    def normalize_email(e): return e.strip().lower() if e else ""
    ENV_NAME = "unknown"
    DB_NAME = "vhc_talent_os"

logger = logging.getLogger(__name__)


def _archive_email(email: str) -> str:
    """Build an archived form of an email so the original becomes free for
    re-use by a brand-new account.

    Example
    -------
    >>> _archive_email("hr6@vhc.in")
    '_deact_20260518T134522_hr6@vhc.in'

    The archived form keeps the domain (so existing analytics that group
    by domain still work) and is unique per second — sufficient since
    a single email can only be deactivated once per second.
    """
    if not email or "@" not in email:
        return email or ""
    local, _, domain = email.partition("@")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"_deact_{ts}_{local}@{domain}"



# Create router for admin endpoints (Zero Trust applied at router level)
admin_router = APIRouter(
    prefix="/api",
    tags=["Admin"],
    dependencies=[Depends(require_zero_trust)],
)


def _validate_commercial(commercial):
    """Validate commercial model fields based on type."""
    if commercial.type not in ("percentage", "fixed", "level_based", "fixed_level_based"):
        raise HTTPException(status_code=400, detail="Commercial type must be percentage, fixed, level_based, or fixed_level_based")

    if commercial.type == "percentage":
        if commercial.percentage_value is None or commercial.percentage_value <= 0:
            raise HTTPException(status_code=400, detail="percentage_value is required and must be > 0")

    elif commercial.type == "fixed":
        if commercial.fixed_fee_amount is None or commercial.fixed_fee_amount <= 0:
            raise HTTPException(status_code=400, detail="fixed_fee_amount is required and must be > 0")

    elif commercial.type == "level_based":
        levels = commercial.level_config or []
        if not levels:
            raise HTTPException(status_code=400, detail="At least one level range is required for level_based type")
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

    elif commercial.type == "fixed_level_based":
        levels = commercial.fixed_fee_levels or []
        if not levels:
            raise HTTPException(status_code=400, detail="At least one fixed fee level is required for fixed_level_based type")


# ============== COMPANY MANAGEMENT (ADMIN) ==============

@admin_router.get("/companies", response_model=List[CompanyResponse])
async def get_all_companies(current_user: dict = Depends(require_role(["admin"]))):
    """
    Get all companies (Admin only).
    Returns complete list of companies with assigned employer info.
    Uses batch lookup to avoid N+1 queries.
    """
    companies = await db.companies.find({"status": {"$ne": "deleted"}}, {"_id": 0}).to_list(1000)
    
    # Batch-fetch all employer names in one query instead of N individual find_ones
    employer_ids = list({c["assigned_employer_id"] for c in companies if c.get("assigned_employer_id")})
    employer_map = {}
    if employer_ids:
        employers = await db.users.find(
            {"id": {"$in": employer_ids}},
            {"_id": 0, "id": 1, "name": 1}
        ).to_list(len(employer_ids))
        employer_map = {e["id"]: e.get("name") for e in employers}
    
    result = []
    for company in companies:
        eid = company.get("assigned_employer_id")
        if eid and eid in employer_map:
            company["assigned_employer_name"] = employer_map[eid]
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

    # Add company to ALL of the employer's teams (handles multiple teams per employer)
    team_count = await db.teams.count_documents({"employer_id": employer_id})
    teams_updated = 0
    if team_count > 0:
        result = await db.teams.update_many(
            {"employer_id": employer_id},
            {"$addToSet": {"company_ids": company_id, "company_names": company.get("name", "")}, "$set": {"updated_at": now}}
        )
        teams_updated = result.modified_count
    else:
        await db.teams.insert_one({
            "id": str(uuid.uuid4()),
            "name": f"{employer.get('name', 'Employer')} Team",
            "employer_id": employer_id,
            "company_ids": [company_id],
            "company_names": [company.get("name", "")],
            "recruiter_ids": [],
            "status": "active",
            "created_at": now,
            "updated_at": now,
        })
        teams_updated = 1

    # Remove company from any OTHER employer's team to avoid duplication
    await db.teams.update_many(
        {"employer_id": {"$ne": employer_id}, "company_ids": company_id},
        {"$pull": {"company_ids": company_id, "company_names": company.get("name", "")}, "$set": {"updated_at": now}}
    )

    return {
        "message": f"Company '{company.get('name')}' assigned to employer '{employer.get('name')}'",
        "teams_updated": teams_updated,
        "teams_found": team_count,
    }

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
    
    # Remove company from teams' company_ids and company_names
    await db.teams.update_many(
        {"company_ids": company_id},
        {"$pull": {"company_ids": company_id, "company_names": company.get("name", "")}}
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
async def get_users(
    page: int = 1,
    limit: int = 200,
    current_user: dict = Depends(require_role(["admin"]))
):
    skip = (page - 1) * max(1, min(limit, 500))
    limit = max(1, min(limit, 500))
    users = await db.users.find(
        {"deleted_at": {"$exists": False}}, {"_id": 0, "password": 0}
    ).skip(skip).limit(limit).to_list(limit)
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
    
    # Validate role if being changed
    if "role" in update_dict:
        allowed_roles = ["admin", "employer", "recruiter", "candidate"]
        if update_dict["role"] not in allowed_roles:
            raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(allowed_roles)}")
        # Prevent admin from changing their own role
        if user_id == current_user["id"]:
            raise HTTPException(status_code=400, detail="You cannot change your own role")
    
    result = await db.users.update_one({"id": user_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    return UserResponse(**user)


@admin_router.delete("/users/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(require_role(["admin"]))):
    # Soft delete - set is_active to False instead of hard delete.
    # SEC-04: bump token_version + purge refresh tokens so the user's
    # extension / browser sessions are invalidated immediately.
    # Phase 55.4 (May 2026): also archive the email so it becomes
    # available for re-use by a brand-new account.
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "email": 1})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    archived_email = _archive_email(user.get("email") or "")
    result = await db.users.update_one(
        {"id": user_id},
        {
            "$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "email": archived_email,
                "original_email": user.get("email"),
            },
            "$inc": {"token_version": 1},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await db.refresh_tokens.delete_many({"user_id": user_id})
    return {
        "message": "User deactivated successfully",
        "archived_email": archived_email,
        "original_email": user.get("email"),
    }


@admin_router.post("/admin/users", response_model=UserResponse)
async def admin_create_user(user_data: AdminUserCreate, current_user: dict = Depends(require_role(["admin"]))):
    """Admin-only endpoint to create users with any role"""
    # Validate role
    allowed_roles = ["admin", "employer", "recruiter", "candidate"]
    if user_data.role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(allowed_roles)}")
    
    # Normalize email
    email = normalize_email(user_data.email)

    # Check if email already exists
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": email,
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
    logger.info("[USER_CREATED] env=%s db=%s id=%s email=%s role=%s created_by=%s", ENV_NAME, DB_NAME, user_id, email, user_data.role, current_user["id"])
    
    # Create candidate profile if role is candidate
    if user_data.role == "candidate":
        profile_doc = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": user_data.name,
            "email": email,
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
    
    await db.users.update_one(
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
    """Admin-only endpoint to activate/deactivate a user.

    Phase 55.4 (May 2026): when DEACTIVATING, the user's email is archived
    (renamed to `_deact_<timestamp>_<original>`) so it can be re-used by a
    brand-new account. When REACTIVATING, the original email is restored
    iff it's still free; otherwise an HTTP 409 is returned so the admin
    knows to pick a different one.
    """
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Cannot deactivate own account
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    new_status = not user.get("is_active", True)
    update_set: Dict[str, Any] = {
        "is_active": new_status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    update_doc: Dict[str, Any] = {"$set": update_set}

    if not new_status:
        # DEACTIVATING — archive the current email
        archived_email = _archive_email(user.get("email") or "")
        update_set["email"] = archived_email
        update_set["original_email"] = user.get("email")
        # SEC-04: bump token_version so existing JWTs are rejected immediately
        update_doc["$inc"] = {"token_version": 1}
    else:
        # REACTIVATING — try to restore original_email if free
        orig = user.get("original_email")
        if orig:
            taken = await db.users.find_one({"email": orig, "id": {"$ne": user_id}}, {"_id": 0, "id": 1})
            if taken:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Cannot reactivate — original email '{orig}' is now used by another "
                        f"account. Edit this user's email first, then reactivate."
                    ),
                )
            update_set["email"] = orig
            update_set["original_email"] = None

    await db.users.update_one({"id": user_id}, update_doc)
    if not new_status:
        await db.refresh_tokens.delete_many({"user_id": user_id})

    return {
        "message": f"User {'activated' if new_status else 'deactivated'} successfully",
        "is_active": new_status,
    }


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

@admin_router.get("/admin/pipeline/filters")
async def get_admin_pipeline_filters(
    employer_id: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Phase 54.12 — Lightweight dropdown-data endpoint for the Collective
    Pipeline page. Returns ONLY the filter options (employers, recruiters,
    teams, jobs). The frontend calls this ONCE on mount + whenever the
    `employer_id` cascade changes. Heavy data calls then go to
    `/admin/pipeline?include_filters=false` (skips ~300ms of duplicate
    dropdown computation per filter change).

    Cached 5 minutes per (employer_id) tuple — these dropdowns rarely
    change vs pipeline data.
    """
    from services.cache import cache

    _key = f"admin:pipeline:filters:v1:emp={employer_id or 'all'}"
    _cached = cache.get(_key)
    if _cached is not None:
        return _cached

    test_accounts_filter = {
        "$nor": [
            {"name": {"$regex": "^Test ", "$options": "i"}},
            {"name": {"$regex": "^Demo ", "$options": "i"}},
            {"email": {"$regex": "^test_", "$options": "i"}},
            {"is_test_account": True},
        ]
    }
    employers = await db.users.find(
        {"role": "employer", **test_accounts_filter},
        {"_id": 0, "id": 1, "name": 1, "email": 1},
    ).to_list(1000)

    # Cascading recruiter list when employer is selected
    recruiter_query = {"role": "recruiter", **test_accounts_filter}
    if employer_id:
        employer_team_docs = await db.teams.find(
            {"employer_id": employer_id},
            {"_id": 0, "recruiter_ids": 1}
        ).to_list(100)
        scoped_recruiter_ids = set()
        for t in employer_team_docs:
            for rid in (t.get("recruiter_ids") or []):
                if rid:
                    scoped_recruiter_ids.add(rid)
        if scoped_recruiter_ids:
            recruiter_query["id"] = {"$in": list(scoped_recruiter_ids)}
        else:
            recruiter_query["id"] = {"$in": []}

    recruiters = await db.users.find(
        recruiter_query, {"_id": 0, "id": 1, "name": 1, "email": 1},
    ).to_list(1000)
    teams = await db.teams.find(
        {}, {"_id": 0, "id": 1, "name": 1, "employer_id": 1}
    ).to_list(1000)

    # Jobs scoped to employer if specified, else all
    jobs_query = {}
    if employer_id:
        # Same logic as the data endpoint: jobs belong to the employer's
        # teams. Reuse the team_ids gathered above if any.
        scoped_team_ids = [t["id"] for t in teams if t.get("employer_id") == employer_id]
        if scoped_team_ids:
            jobs_query["team_id"] = {"$in": scoped_team_ids}
        else:
            jobs_query["team_id"] = {"$in": []}
    jobs_docs = await db.jobs.find(
        jobs_query,
        {"_id": 0, "id": 1, "title": 1, "company_name": 1},
    ).to_list(10000)

    result = {
        "employers": employers,
        "recruiters": recruiters,
        "teams": teams,
        "jobs": [
            {
                "id": j["id"],
                "title": j.get("title", "Untitled"),
                "company_name": j.get("company_name", ""),
            }
            for j in jobs_docs
        ],
    }
    cache.set(_key, result, ttl=300)   # 5 min — dropdowns change slowly
    return result


@admin_router.get("/admin/pipeline")
async def get_admin_pipeline(
    employer_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    team_id: Optional[str] = None,
    job_id: Optional[str] = None,
    include_filters: bool = True,   # Phase 54.12 — skip if frontend already has them
    per_stage_limit: int = 100,     # Phase 54.16 — cap per-stage rows (kanban perf)
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Admin collective pipeline view across all employers and recruiters.

    Phase 54.16 (2026-05-11) — per-stage pagination + denormalized counts.
    `stage_counts` are now computed via a single Mongo aggregation against
    pre-filtered job_ids → accurate even when the kanban only renders the
    top `per_stage_limit` rows per stage. Cuts wire payload from ~260KB
    to ~80KB at the cost of one extra cheap aggregation query.
    Read-only aggregated view for management oversight.

    Filter Hierarchy (Phase 52 fix, 2026-05-06):
    Filters now COMBINE rather than override each other. If both employer +
    recruiter are selected, the result is the INTERSECTION (jobs in that
    employer's teams AND posted by / assigned to that recruiter).

    Filter dropdowns are also now **cascading**:
      • employer selected → recruiters dropdown lists only that employer's
        team members (not all 50+ recruiters in the org).
      • employer or recruiter selected → jobs dropdown narrows accordingly.

    Phase 54.11 — Redis cache (60s TTL) keyed by the filter tuple.
    Repeat filter combinations served in ~10ms instead of 3-4s. Cache
    is per-filter-tuple (not per-user) since pipeline data is identical
    for any admin viewer. TTL is short enough that stage drags +
    new applications surface within a minute.
    """
    from services.cache import cache

    _cache_key = (
        f"admin:pipeline:v3:"
        f"emp={employer_id or 'all'}|"
        f"rec={recruiter_id or 'all'}|"
        f"team={team_id or 'all'}|"
        f"job={job_id or 'all'}|"
        f"psl={per_stage_limit}|"
        f"filters={'1' if include_filters else '0'}"
    )
    _cached = cache.get(_cache_key)
    if _cached is not None:
        return _cached

    # ── Build the job filter — combine, not override ───────────────────────
    job_clauses = []

    if job_id:
        # Direct job filter — most specific, short-circuits other filters
        job_clauses.append({"id": job_id})

    if employer_id:
        # All teams + companies for this employer
        employer_teams = await db.teams.find(
            {"employer_id": employer_id},
            {"_id": 0, "id": 1, "company_ids": 1, "recruiter_ids": 1}
        ).to_list(100)

        emp_team_ids = [t["id"] for t in employer_teams]
        emp_company_ids = []
        for t in employer_teams:
            emp_company_ids.extend(t.get("company_ids", []) or [])

        emp_or = []
        if emp_team_ids:
            emp_or.append({"team_id": {"$in": emp_team_ids}})
        if emp_company_ids:
            emp_or.append({"company_id": {"$in": emp_company_ids}})
        emp_or.append({"posted_by": employer_id})

        job_clauses.append({"$or": emp_or})

    if team_id:
        job_clauses.append({"team_id": team_id})

    if recruiter_id:
        recruiter_teams = await db.teams.find(
            {"recruiter_ids": recruiter_id},
            {"_id": 0, "id": 1}
        ).to_list(100)
        recruiter_team_ids = [t["id"] for t in recruiter_teams]

        rec_or = [{"posted_by": recruiter_id}, {"assigned_to": recruiter_id}]
        if recruiter_team_ids:
            rec_or.append({"team_id": {"$in": recruiter_team_ids}})

        job_clauses.append({"$or": rec_or})

    job_filter = {"$and": job_clauses} if job_clauses else {}

    # Phase 54.10 — projection: only fetch fields we actually use downstream.
    # Previously this returned the full job document (~2.5 KB each × 421
    # jobs ≈ 1 MB transfer + parse on every filter change). Cuts the
    # filter-change Mongo round-trip from ~600ms to ~50ms.
    JOBS_PROJECTION = {
        "_id": 0, "id": 1, "title": 1, "company_name": 1,
        "team_id": 1, "company_id": 1, "posted_by": 1, "assigned_to": 1,
    }
    if job_filter:
        jobs = await db.jobs.find(job_filter, JOBS_PROJECTION).to_list(10000)
    else:
        jobs = await db.jobs.find({}, JOBS_PROJECTION).to_list(10000)
    
    jobs_map = {j["id"]: j for j in jobs}
    job_ids = list(jobs_map.keys())
    
    # Get applications for these jobs — Phase 54.16:
    #   (1) cheap aggregation FIRST gets accurate stage_counts across ALL apps.
    #   (2) Then we load only the most-recent `per_stage_limit` apps per stage
    #       (default 100) for kanban display. This cuts wire payload by ~70%
    #       on busy organizations while keeping the badge counts correct.
    # Applies pipeline_display_filter() to hide extension-capture clutter and
    # stale rejections (>7 days) per product spec.
    from services.pipeline_events import pipeline_display_filter

    psl = max(10, min(per_stage_limit, 500))  # clamp to sensible range
    pipeline_display = pipeline_display_filter()

    LEGACY_STAGE_MAP = {
        "applied": "sourced",
        "employer_approved": "shortlisted",
        "employer_rejected": "rejected",
    }

    stage_counts_raw: dict = {}
    total_applications = 0
    applications: list = []
    if job_ids:
        # (1) Accurate stage counts across ALL apps (no per-stage cap)
        async for row in db.applications.aggregate([
            {"$match": {"$and": [
                {"job_id": {"$in": job_ids}},
                pipeline_display,
            ]}},
            {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
        ]):
            raw = row["_id"] or "sourced"
            canon = LEGACY_STAGE_MAP.get(raw, raw)
            stage_counts_raw[canon] = stage_counts_raw.get(canon, 0) + row["count"]
            total_applications += row["count"]

        # (2) Per-stage limit: union of `psl` most-recent docs per stage.
        # Issued in parallel via asyncio.gather so wall-clock stays low.
        import asyncio as _aio

        async def _fetch_stage(stage_name: str):
            cursor = db.applications.find(
                {"$and": [
                    {"job_id": {"$in": job_ids}},
                    {"stage": stage_name},
                    pipeline_display,
                ]},
                {"_id": 0},
            ).sort("created_at", -1).limit(psl)
            return await cursor.to_list(psl)

        active_stages = list(stage_counts_raw.keys())
        fetched = await _aio.gather(*[_fetch_stage(s) for s in active_stages])
        applications = [doc for sub in fetched for doc in sub]
    
    # Define all pipeline stages — simplified flow (no approval gate)
    all_stages = ["sourced", "submitted_to_client", "shortlisted", "interview", "offered", "hired", "joined", "rejected", "on_hold"]
    
    # Batch-fetch candidate_bank profiles for enrichment
    candidate_ids = list({app.get("candidate_id") for app in applications if app.get("candidate_id")})
    candidates_map = {}
    if candidate_ids:
        cands = await db.candidate_bank.find(
            {"id": {"$in": candidate_ids}},
            # Phase 54.13 — projection trimmed: removed industry, education,
            # ug_course, headline (none are rendered in the kanban view).
            # ~10% smaller payload, plus less per-doc memory in Python.
            {"_id": 0, "id": 1, "location": 1, "current_employer": 1, "designation": 1,
             "expected_salary": 1, "current_salary": 1, "experience_years": 1,
             "notice_period": 1, "phone": 1, "name": 1, "email": 1}
        ).to_list(len(candidate_ids))
        candidates_map = {c["id"]: c for c in cands}

    # Group applications by stage
    pipeline_data = {stage: [] for stage in all_stages}
    
    for app in applications:
        stage = app.get("stage", "sourced")
        # Map legacy stages onto the new simplified pipeline
        if stage == "applied":
            stage = "sourced"
        elif stage == "employer_approved":
            stage = "shortlisted"
        elif stage == "employer_rejected":
            stage = "rejected"
        if stage not in pipeline_data:
            stage = "sourced"
        
        job = jobs_map.get(app.get("job_id"), {})
        cb = candidates_map.get(app.get("candidate_id"), {})
        
        pipeline_data[stage].append({
            "id": app.get("id"),
            "candidate_id": app.get("candidate_id"),
            "candidate_name": app.get("candidate_name") or cb.get("name", "Unknown"),
            "candidate_email": app.get("candidate_email") or cb.get("email"),
            "candidate_phone": app.get("candidate_phone") or cb.get("phone"),
            "job_title": app.get("job_title") or job.get("title", "Unknown"),
            "job_id": app.get("job_id"),
            "company_name": job.get("company_name", ""),
            "match_score": app.get("match_score", 0),
            "applied_at": app.get("created_at"),
            "current_salary": app.get("current_salary") or cb.get("current_salary"),
            "expected_salary": app.get("expected_salary") or cb.get("expected_salary"),
            "notice_period": app.get("notice_period") or cb.get("notice_period"),
            "experience_years": app.get("experience_years") or cb.get("experience_years"),
            "resume_url": app.get("resume_url"),
            "offered_ctc": app.get("offered_ctc"),
            "offer_date": app.get("offer_date"),
            "join_date": app.get("join_date"),
            "stage": stage,
            "location": app.get("location") or cb.get("location"),
            "current_employer": app.get("current_employer") or cb.get("current_employer"),
            "designation": app.get("designation") or cb.get("designation"),
            # Phase 54.13: industry, education, ug_course, headline removed
            # — not rendered in the kanban. Re-fetch via /candidates/{id}
            # if a future detail dialog needs them.
        })
    
    # Calculate stage counts — Phase 54.16: use Mongo-computed totals (cover ALL
    # apps, not just the per-stage paginated slice). Falls back to in-memory
    # count for any stage that had no rows (shouldn't happen if the agg ran).
    stage_counts = {stage: stage_counts_raw.get(stage, 0) for stage in all_stages}
    
    # Phase 54.12 — skip dropdown computation when the frontend already
    # has them (loaded once via /admin/pipeline/filters). Saves ~300ms
    # per filter click since we don't re-query employers/recruiters/teams.
    if not include_filters:
        result = {
            "pipeline": pipeline_data,
            "stage_counts": stage_counts,
            "total_applications": total_applications,
            "per_stage_limit": psl,  # Phase 54.16: client knows it's paginated
        }
        cache.set(_cache_key, result, ttl=60)
        return result

    # Get filter options. Exclude obvious test/demo accounts so the dropdown
    # stops showing non-existent / orphan entries.
    test_accounts_filter = {
        "$nor": [
            {"name": {"$regex": "^Test ", "$options": "i"}},
            {"name": {"$regex": "^Demo ", "$options": "i"}},
            {"email": {"$regex": "^test_", "$options": "i"}},
            {"is_test_account": True},
        ]
    }
    employers = await db.users.find(
        {"role": "employer", **test_accounts_filter},
        {"_id": 0, "id": 1, "name": 1, "email": 1},
    ).to_list(1000)

    # ── Cascading recruiter dropdown (Phase 52 fix, 2026-05-06) ────────────
    # When an employer is selected, narrow the recruiter list to ONLY the
    # recruiters belonging to that employer's teams. Without this, the
    # dropdown overwhelms the admin with 50+ recruiters when only 3-5 are
    # actually relevant to the chosen employer.
    recruiter_query = {"role": "recruiter", **test_accounts_filter}
    if employer_id:
        employer_team_docs = await db.teams.find(
            {"employer_id": employer_id},
            {"_id": 0, "recruiter_ids": 1}
        ).to_list(100)
        scoped_recruiter_ids = set()
        for t in employer_team_docs:
            for rid in (t.get("recruiter_ids") or []):
                if rid:
                    scoped_recruiter_ids.add(rid)
        if scoped_recruiter_ids:
            recruiter_query["id"] = {"$in": list(scoped_recruiter_ids)}
        else:
            # Employer has no teams/recruiters yet → empty dropdown
            recruiter_query["id"] = {"$in": []}

    recruiters = await db.users.find(
        recruiter_query,
        {"_id": 0, "id": 1, "name": 1, "email": 1},
    ).to_list(1000)
    teams = await db.teams.find({}, {"_id": 0, "id": 1, "name": 1, "employer_id": 1}).to_list(1000)
    
    result = {
        "pipeline": pipeline_data,
        "stage_counts": stage_counts,
        "total_applications": total_applications,
        "per_stage_limit": psl,  # Phase 54.16: client knows it's paginated
        "filters": {
            "employers": employers,
            "recruiters": recruiters,
            "teams": teams,
            # Phase 54.10: include `company_name` so the UI can render
            # "JSW Steel · Manager Sales" instead of just "Manager Sales"
            # which is ambiguous when the same job title repeats across
            # multiple companies.
            "jobs": [
                {
                    "id": j["id"],
                    "title": j.get("title", "Untitled"),
                    "company_name": j.get("company_name", ""),
                }
                for j in jobs
            ],
        }
    }
    # Phase 54.11 — populate cache for 60s. Filter changes within a minute
    # hit Redis (~10ms) instead of recomputing the full aggregation.
    cache.set(_cache_key, result, ttl=60)
    return result



# ============== DASHBOARD STATS ENDPOINTS ==============

@admin_router.get("/stats/admin")
async def get_admin_dashboard_stats(current_user: dict = Depends(require_role(["admin"]))):
    """
    Admin dashboard statistics — enhanced with at-a-glance insights.

    Phase 52 (2026-05-06): cached for 90s in Redis. Reduces ~10 Mongo
    aggregations per dashboard load to one. Cache is shared across all admin
    users; cleared on every full minute via natural TTL expiry.
    """
    from datetime import datetime, timezone, timedelta
    from services.cache import cache

    # Single cache key — same data for any admin viewer
    _cache_key = "stats:admin_dashboard:v1"
    _cached = cache.get(_cache_key)
    if _cached is not None:
        return _cached

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_start = (now - timedelta(days=7)).isoformat()

    # === Core Stats ===
    total_users = await db.users.count_documents({})
    role_pipeline = [{"$group": {"_id": "$role", "count": {"$sum": 1}}}]
    role_results = await db.users.aggregate(role_pipeline).to_list(10)
    users_by_role = {r["_id"]: r["count"] for r in role_results if r["_id"]}

    total_jobs = await db.jobs.count_documents({"status": {"$in": ["active", "pending_approval"]}})
    total_applications = await db.applications.count_documents({})
    total_companies = await db.companies.count_documents({})
    total_candidates = await db.candidate_bank.estimated_document_count()

    # === Today's Activity ===
    today_captures = await db.activity_logs.count_documents({"action": "captured", "timestamp": {"$gte": today_start}})
    today_views = await db.activity_logs.count_documents({"action": "viewed", "timestamp": {"$gte": today_start}})
    today_stage_changes = await db.activity_logs.count_documents({"action": "stage_changed", "timestamp": {"$gte": today_start}})

    # Active users today (distinct performers)
    today_active_pipeline = [
        {"$match": {"timestamp": {"$gte": today_start}}},
        {"$group": {"_id": "$performed_by"}},
        {"$count": "count"}
    ]
    today_active_res = await db.activity_logs.aggregate(today_active_pipeline).to_list(1)
    today_active_users = today_active_res[0]["count"] if today_active_res else 0

    # === Top Recruiters This Week ===
    top_recruiters_pipeline = [
        {"$match": {"timestamp": {"$gte": week_start}, "action": "captured"}},
        {"$group": {"_id": "$performed_by", "name": {"$first": "$performed_by_name"}, "captures": {"$sum": 1}}},
        {"$sort": {"captures": -1}},
        {"$limit": 5}
    ]
    top_recruiters = await db.activity_logs.aggregate(top_recruiters_pipeline).to_list(5)
    top_recruiters_list = [{"name": r["name"] or "Unknown", "captures": r["captures"]} for r in top_recruiters]

    # === Pipeline Health ===
    stage_pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    stage_results = await db.applications.aggregate(stage_pipeline).to_list(20)
    pipeline_stages = {r["_id"]: r["count"] for r in stage_results if r["_id"]}

    # Stale candidates: in sourced/shortlisted for >7 days
    stale_cutoff = (now - timedelta(days=7)).isoformat()
    stale_count = await db.applications.count_documents({
        "status": "active",
        "stage": {"$in": ["sourced", "shortlisted", "applied"]},
        "updated_at": {"$lte": stale_cutoff}
    })

    # Jobs with 0 applicants
    jobs_with_apps = await db.applications.distinct("job_id")
    all_active_jobs = await db.jobs.count_documents({"status": "active"})
    jobs_no_apps = max(0, all_active_jobs - len(set(jobs_with_apps)))

    # === Hiring Funnel (last 30 days) ===
    month_start = (now - timedelta(days=30)).isoformat()
    funnel_pipeline = [
        {"$match": {"created_at": {"$gte": month_start}}},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}}
    ]
    funnel_results = await db.applications.aggregate(funnel_pipeline).to_list(20)
    funnel = {r["_id"]: r["count"] for r in funnel_results if r["_id"]}

    # === Capture Velocity (last 7 days) ===
    velocity_pipeline = [
        {"$match": {"action": "captured", "timestamp": {"$gte": week_start}}},
        {"$addFields": {"date_str": {"$substr": ["$timestamp", 0, 10]}}},
        {"$group": {"_id": "$date_str", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    velocity_results = await db.activity_logs.aggregate(velocity_pipeline).to_list(7)
    capture_velocity = [{"date": r["_id"], "count": r["count"]} for r in velocity_results]

    # Recent applications (last 10)
    recent_apps = await db.applications.find(
        {},
        {"_id": 0, "id": 1, "candidate_name": 1, "job_title": 1, "stage": 1, "created_at": 1}
    ).sort("created_at", -1).limit(10).to_list(10)

    result = {
        "total_users": total_users,
        "total_jobs": total_jobs,
        "total_applications": total_applications,
        "total_companies": total_companies,
        "total_candidates": total_candidates,
        "users_by_role": users_by_role,
        "recent_applications": recent_apps,
        "today": {
            "captures": today_captures,
            "views": today_views,
            "stage_changes": today_stage_changes,
            "active_users": today_active_users,
        },
        "top_recruiters_week": top_recruiters_list,
        "pipeline_stages": pipeline_stages,
        "stale_candidates": stale_count,
        "jobs_no_applicants": jobs_no_apps,
        "hiring_funnel": funnel,
        "capture_velocity": capture_velocity,
    }

    # Cache for 90s — admin dashboard refreshes typically more frequent than
    # this don't add information (Mongo ETL lag itself is several seconds).
    cache.set(_cache_key, result, ttl=90)
    return result


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



# ============== DATA RESET (Clean Sweep) ==============

@admin_router.post("/admin/clean-sweep")
async def admin_clean_sweep(
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Clean sweep: Zero out pipeline, revenue, attendance analytics.
    KEEPS: users, jobs, candidate_bank.
    DELETES: applications, tracker_rows, tracker_events, pipeline_events,
             revenue, attendance, notifications, cron_job_locks.
    
    Admin-only. Use with caution.
    """
    results = {}
    now = datetime.now(timezone.utc).isoformat()
    
    # Collections to wipe
    collections_to_clear = [
        "applications",
        "tracker_rows",
        "tracker_events",
        "pipeline_events",
        "revenue",
        "attendance",
        "attendance_records",
        "leave_requests",
        "notifications",
        "cron_job_locks",
        "blog_schedule_log",
    ]
    
    for coll_name in collections_to_clear:
        try:
            coll = db[coll_name]
            count = await coll.count_documents({})
            if count > 0:
                await coll.delete_many({})
                results[coll_name] = f"Cleared {count} documents"
            else:
                results[coll_name] = "Already empty"
        except Exception as e:
            results[coll_name] = f"Error: {str(e)}"
    
    # Reset job applicant_count to 0 (keep jobs themselves)
    job_result = await db.jobs.update_many({}, {"$set": {"applicant_count": 0}})
    results["jobs_applicant_count_reset"] = f"Reset {job_result.modified_count} jobs"
    
    # Clear candidate application_history but keep candidate records
    cand_result = await db.candidate_bank.update_many(
        {},
        {"$set": {"application_history": [], "notes": []}}
    )
    results["candidate_history_cleared"] = f"Cleared history for {cand_result.modified_count} candidates"
    
    # Log the sweep
    await db.audit_log.insert_one({
        "action": "clean_sweep",
        "performed_by": current_user["id"],
        "performed_by_name": current_user["name"],
        "timestamp": now,
        "results": results,
    })
    
    logger.warning(f"[ADMIN] Clean sweep performed by {current_user['name']} at {now}")
    
    return {
        "success": True,
        "message": "Clean sweep complete. Pipeline, revenue, attendance, and notifications cleared.",
        "preserved": ["users", "jobs", "candidate_bank", "teams", "companies", "blog_posts"],
        "results": results,
    }


@admin_router.get("/api-keys/usage")
async def get_api_key_usage(current_user: dict = Depends(require_role(["admin"]))):
    """Get Anthropic API key usage stats with estimated remaining balance."""
    import os

    # Haiku 4.5 pricing (per million tokens)
    INPUT_COST_PER_M = 0.80   # $0.80 per 1M input tokens
    OUTPUT_COST_PER_M = 4.00  # $4.00 per 1M output tokens
    FREE_CREDIT = 5.00        # $5 per key

    # Check which keys are configured
    keys_configured = []
    pk = os.environ.get("ANTHROPIC_API_KEY")
    if pk:
        keys_configured.append({"index": 1, "suffix": f"...{pk[-6:]}"})
    for i in range(2, 5):
        k = os.environ.get(f"ANTHROPIC_API_KEY_{i}")
        if k:
            keys_configured.append({"index": i, "suffix": f"...{k[-6:]}"})

    # Get all-time usage per key
    pipeline = [
        {"$group": {
            "_id": "$key_index",
            "total_input": {"$sum": "$input_tokens"},
            "total_output": {"$sum": "$output_tokens"},
            "total_calls": {"$sum": "$call_count"},
            "last_used": {"$max": "$last_used"},
        }},
        {"$sort": {"_id": 1}},
    ]
    usage_data = {}
    async for doc in db.anthropic_key_usage.aggregate(pipeline):
        usage_data[doc["_id"]] = doc

    # Get today's usage per key
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_pipeline = [
        {"$match": {"date": today}},
        {"$group": {
            "_id": "$key_index",
            "today_input": {"$sum": "$input_tokens"},
            "today_output": {"$sum": "$output_tokens"},
            "today_calls": {"$sum": "$call_count"},
        }},
    ]
    today_data = {}
    async for doc in db.anthropic_key_usage.aggregate(today_pipeline):
        today_data[doc["_id"]] = doc

    # Build response
    keys = []
    total_spent = 0
    total_remaining = 0
    for kc in keys_configured:
        idx = kc["index"]
        usage = usage_data.get(idx, {})
        today_usage = today_data.get(idx, {})

        inp = usage.get("total_input", 0)
        out = usage.get("total_output", 0)
        cost = (inp / 1_000_000 * INPUT_COST_PER_M) + (out / 1_000_000 * OUTPUT_COST_PER_M)
        remaining = max(0, FREE_CREDIT - cost)

        total_spent += cost
        total_remaining += remaining

        keys.append({
            "key_index": idx,
            "key_suffix": kc["suffix"],
            "total_input_tokens": inp,
            "total_output_tokens": out,
            "total_calls": usage.get("total_calls", 0),
            "estimated_cost_usd": round(cost, 4),
            "estimated_remaining_usd": round(remaining, 4),
            "last_used": usage.get("last_used"),
            "today_calls": today_usage.get("today_calls", 0),
            "today_input_tokens": today_usage.get("today_input", 0),
            "today_output_tokens": today_usage.get("today_output", 0),
            "status": "exhausted" if remaining <= 0.01 else "low" if remaining < 1.0 else "active",
        })

    return {
        "keys": keys,
        "total_keys": len(keys_configured),
        "total_estimated_spent_usd": round(total_spent, 4),
        "total_estimated_remaining_usd": round(total_remaining, 4),
        "pricing": {
            "model": "claude-haiku-4-5",
            "input_per_1m": INPUT_COST_PER_M,
            "output_per_1m": OUTPUT_COST_PER_M,
            "free_credit_per_key": FREE_CREDIT,
        },
    }


@admin_router.get("/stats/extraction-quality")
async def get_extraction_quality_stats(current_user: dict = Depends(require_role(["admin"]))):
    """Get regex extraction quality stats for the admin ZERO-API parser."""

    tracked_fields = {
        "phone": "Phone", "email": "Email", "current_employer": "Employer",
        "designation": "Designation", "location": "Location",
        "current_salary": "Current CTC", "expected_salary": "Expected CTC",
        "notice_period": "Notice Period", "experience_years": "Experience",
        "skills": "Skills", "experience": "Work History", "education": "Education",
        "summary": "Summary", "headline": "Headline",
    }

    regex_query = {"ai_enrichment_source": {"$regex": "regex", "$options": "i"}}

    # Single aggregation to get all stats in one DB round-trip
    agg_pipeline = [
        {"$facet": {
            "regex_count": [{"$match": regex_query}, {"$count": "n"}],
            "claude_count": [
                {"$match": {"ai_enrichment_source": {"$regex": "anthropic|claude|haiku", "$options": "i"}}},
                {"$count": "n"},
            ],
            "total_enriched": [{"$match": {"ai_enriched_at": {"$exists": True}}}, {"$count": "n"}],
            "regex_field_fill": [
                {"$match": regex_query},
                {"$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    **{f"has_{k}": {"$sum": {"$cond": [
                        {"$and": [
                            {"$ne": [f"${k}", None]},
                            {"$ne": [f"${k}", ""]},
                            {"$ne": [f"${k}", []]},
                        ]}, 1, 0
                    ]}} for k in tracked_fields.keys()},
                }},
            ],
            "recent": [
                {"$match": regex_query},
                {"$sort": {"ai_enriched_at": -1}},
                {"$limit": 10},
                {"$project": {"_id": 0, "id": 1, "name": 1, "ai_enriched_at": 1, "ai_enrichment_source": 1}},
            ],
        }}
    ]

    result = await db.candidate_bank.aggregate(agg_pipeline).to_list(1)
    facets = result[0] if result else {}

    total_regex = facets.get("regex_count", [{}])[0].get("n", 0) if facets.get("regex_count") else 0
    total_claude = facets.get("claude_count", [{}])[0].get("n", 0) if facets.get("claude_count") else 0
    total_enriched = facets.get("total_enriched", [{}])[0].get("n", 0) if facets.get("total_enriched") else 0
    fill_data = facets.get("regex_field_fill", [{}])[0] if facets.get("regex_field_fill") else {}
    total = fill_data.get("total", 0)

    field_stats = []
    for db_field, label in tracked_fields.items():
        filled = fill_data.get(f"has_{db_field}", 0)
        rate = round((filled / total) * 100, 1) if total else 0
        field_stats.append({"label": label, "filled": filled, "total": total, "rate": rate})

    missed_fields = sorted([f for f in field_stats if f["rate"] < 80], key=lambda x: x["rate"])
    strong_fields = sorted([f for f in field_stats if f["rate"] >= 80], key=lambda x: -x["rate"])
    avg_rate = round(sum(f["rate"] for f in field_stats) / len(field_stats), 1) if field_stats else 0

    return {
        "total_regex_enriched": total_regex,
        "total_claude_enriched": total_claude,
        "total_enriched": total_enriched,
        "overall_quality_score": avg_rate,
        "field_stats": field_stats,
        "missed_fields": missed_fields,
        "strong_fields": strong_fields,
        "recent_regex_enriched": facets.get("recent", []),
    }


# ═══════════════════════════════════════
# HIRING FUNNEL KPI DASHBOARD
# ═══════════════════════════════════════

@admin_router.get("/hiring-funnel")
async def get_hiring_funnel(
    days: int = Query(30, description="Look-back period in days"),
    job_id: Optional[str] = Query(None),
    user=Depends(require_role(["admin"]))
):
    """Hiring funnel KPIs: pipeline velocity, time-to-hire, conversion rates per stage."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    match_filter = {"created_at": {"$gte": cutoff}}
    if job_id:
        match_filter["job_id"] = job_id

    # Stage counts
    stage_pipeline = [
        {"$match": match_filter},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
    ]
    stage_results = await db.applications.aggregate(stage_pipeline).to_list(50)
    stage_counts = {r["_id"]: r["count"] for r in stage_results}

    # Funnel order
    funnel_order = ["sourced", "applied", "shortlisted", "submitted_to_client", "interview", "offered", "hired", "joined"]
    funnel = []
    for stage in funnel_order:
        count = stage_counts.pop(stage, 0)
        funnel.append({"stage": stage, "count": count})

    # Total applications
    total = sum(s["count"] for s in funnel)

    # Conversion rates (stage-to-stage)
    conversions = []
    for i in range(len(funnel) - 1):
        from_count = funnel[i]["count"]
        to_count = funnel[i + 1]["count"]
        rate = round((to_count / from_count) * 100, 1) if from_count > 0 else 0
        conversions.append({
            "from": funnel[i]["stage"],
            "to": funnel[i + 1]["stage"],
            "rate": rate,
        })

    # Time-to-hire (avg days from applied to hired/joined)
    tth_pipeline = [
        {"$match": {**match_filter, "stage": {"$in": ["hired", "joined"]}}},
        {"$project": {
            "_id": 0,
            "created_at": 1,
            "updated_at": 1,
        }},
    ]
    hired_docs = await db.applications.aggregate(tth_pipeline).to_list(500)
    tth_days = []
    for doc in hired_docs:
        try:
            created = datetime.fromisoformat(doc["created_at"].replace("Z", "+00:00")) if isinstance(doc["created_at"], str) else doc["created_at"]
            updated = datetime.fromisoformat(doc["updated_at"].replace("Z", "+00:00")) if isinstance(doc["updated_at"], str) else doc["updated_at"]
            diff = (updated - created).days
            if 0 <= diff <= 365:
                tth_days.append(diff)
        except Exception:
            pass
    avg_time_to_hire = round(sum(tth_days) / len(tth_days), 1) if tth_days else None

    # Source effectiveness
    source_pipeline = [
        {"$match": match_filter},
        {"$group": {
            "_id": "$source",
            "total": {"$sum": 1},
            "hired": {"$sum": {"$cond": [{"$in": ["$stage", ["hired", "joined"]]}, 1, 0]}},
        }},
        {"$sort": {"total": -1}},
        {"$limit": 10},
    ]
    source_results = await db.applications.aggregate(source_pipeline).to_list(10)
    source_effectiveness = [{
        "source": r["_id"] or "unknown",
        "total": r["total"],
        "hired": r["hired"],
        "conversion_rate": round((r["hired"] / r["total"]) * 100, 1) if r["total"] > 0 else 0,
    } for r in source_results]

    # Rejection reasons
    rejection_pipeline = [
        {"$match": {**match_filter, "stage": {"$in": ["rejected", "employer_rejected", "dropped"]}}},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
    ]
    rejection_results = await db.applications.aggregate(rejection_pipeline).to_list(10)
    rejections = {r["_id"]: r["count"] for r in rejection_results}

    # Active jobs count
    active_jobs = await db.jobs.count_documents({"status": "active"})

    return {
        "period_days": days,
        "total_applications": total,
        "active_jobs": active_jobs,
        "funnel": funnel,
        "other_stages": stage_counts,
        "conversions": conversions,
        "avg_time_to_hire_days": avg_time_to_hire,
        "source_effectiveness": source_effectiveness,
        "rejections": rejections,
    }



# ═══════════════════════════════════════
# CLIENT (COMPANY) PROFILE — MANDATE HISTORY
# ═══════════════════════════════════════

@admin_router.get("/companies/{company_id}/profile")
async def get_company_profile(
    company_id: str,
    user=Depends(require_role(["admin", "recruiter", "employer"]))
):
    """Full client profile: company info + all mandates + candidates + stages + team members."""
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Get all jobs/mandates for this company
    jobs = await db.jobs.find(
        {"company_id": company_id},
        {"_id": 0, "id": 1, "title": 1, "location": 1, "status": 1, "created_at": 1, "created_by": 1, "created_by_name": 1}
    ).sort("created_at", -1).to_list(200)

    mandate_details = []
    total_candidates_sourced = 0
    total_hired = 0

    for job in jobs:
        # Get all applications for this mandate
        apps = await db.applications.find(
            {"job_id": job["id"]},
            {"_id": 0, "candidate_id": 1, "candidate_name": 1, "stage": 1,
             "created_at": 1, "updated_at": 1, "source": 1,
             "submitted_by_name": 1, "submitted_by": 1}
        ).sort("created_at", -1).to_list(500)

        # Count stages
        stage_counts = {}
        for app in apps:
            s = app.get("stage", "unknown")
            stage_counts[s] = stage_counts.get(s, 0) + 1

        total_candidates_sourced += len(apps)
        total_hired += stage_counts.get("hired", 0) + stage_counts.get("joined", 0)

        # Get unique team members who worked on this mandate
        team_members = list({a.get("submitted_by_name", "Unknown") for a in apps if a.get("submitted_by_name")})

        candidates = [{
            "candidate_id": a.get("candidate_id"),
            "candidate_name": a.get("candidate_name"),
            "stage": a.get("stage"),
            "source": a.get("source"),
            "submitted_by": a.get("submitted_by_name"),
            "created_at": a.get("created_at"),
            "updated_at": a.get("updated_at"),
        } for a in apps[:50]]  # Limit to 50 per mandate for performance

        mandate_details.append({
            "id": job["id"],
            "title": job.get("title"),
            "location": job.get("location"),
            "status": job.get("status"),
            "created_at": job.get("created_at"),
            "created_by": job.get("created_by_name"),
            "candidates_count": len(apps),
            "stage_breakdown": stage_counts,
            "team_members": team_members,
            "candidates": candidates,
        })

    return {
        "company": {
            "id": company.get("id"),
            "name": company.get("name"),
            "industry": company.get("industry"),
            "location": company.get("location"),
            "website": company.get("website"),
            "description": company.get("description"),
            "hr_contacts": company.get("hr_contacts", []),
            "commercial": company.get("commercial"),
            "status": company.get("status"),
            "created_at": company.get("created_at"),
        },
        "summary": {
            "total_mandates": len(jobs),
            "active_mandates": sum(1 for j in jobs if j.get("status") == "active"),
            "total_candidates_sourced": total_candidates_sourced,
            "total_hired": total_hired,
        },
        "mandates": mandate_details,
    }
