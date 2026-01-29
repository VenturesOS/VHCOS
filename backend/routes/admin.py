"""
VHC Talent OS - Admin Routes
Handles user management and admin-only operations.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends

# Import configuration
from config import db

# Import models
from models import (
    UserResponse, UserUpdate, AdminUserCreate, AdminPasswordReset
)

# Import utilities
from utils import hash_password, require_role


# Create router for admin endpoints
admin_router = APIRouter(prefix="/api", tags=["Admin"])


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
    allowed_roles = ["employer", "recruiter", "candidate"]
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
    job_id: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Admin collective pipeline view across all employers and recruiters.
    Read-only aggregated view for management oversight.
    """
    # Build filter
    match_filter = {}
    
    if job_id:
        match_filter["job_id"] = job_id
    
    # Get all applications
    applications = await db.applications.find(match_filter, {"_id": 0}).to_list(10000)
    
    # Get job details for filtering and display
    job_ids = list(set(app["job_id"] for app in applications))
    jobs = await db.jobs.find({"id": {"$in": job_ids}}, {"_id": 0}).to_list(1000)
    jobs_map = {j["id"]: j for j in jobs}
    
    # Apply employer filter if specified
    if employer_id:
        employer_job_ids = [j["id"] for j in jobs if j.get("company_id") == employer_id or j.get("created_by") == employer_id]
        applications = [app for app in applications if app["job_id"] in employer_job_ids]
    
    # Apply recruiter filter if specified
    if recruiter_id:
        recruiter_job_ids = [j["id"] for j in jobs if j.get("created_by") == recruiter_id or j.get("assigned_recruiter") == recruiter_id]
        applications = [app for app in applications if app["job_id"] in recruiter_job_ids]
    
    # Define all pipeline stages
    all_stages = ["applied", "shortlisted", "interview", "offered", "hired", "rejected", "on_hold", "over_budget", "not_qualified"]
    
    # Group applications by stage
    pipeline_data = {stage: [] for stage in all_stages}
    
    for app in applications:
        stage = app.get("stage", "applied")
        if stage not in pipeline_data:
            stage = "applied"
        
        job = jobs_map.get(app["job_id"], {})
        
        pipeline_data[stage].append({
            "id": app["id"],
            "candidate_name": app.get("candidate_name", "Unknown"),
            "candidate_email": app.get("candidate_email"),
            "job_title": app.get("job_title") or job.get("title", "Unknown"),
            "job_id": app["job_id"],
            "company_name": job.get("company_name", ""),
            "match_score": app.get("match_score", 0),
            "applied_at": app.get("created_at"),
            "current_salary": app.get("current_salary"),
            "notice_period": app.get("notice_period"),
            "resume_url": app.get("resume_url")
        })
    
    # Calculate stage counts
    stage_counts = {stage: len(apps) for stage, apps in pipeline_data.items()}
    
    # Get filter options
    employers = await db.users.find({"role": "employer"}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(1000)
    recruiters = await db.users.find({"role": "recruiter"}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(1000)
    
    return {
        "pipeline": pipeline_data,
        "stage_counts": stage_counts,
        "total_applications": len(applications),
        "filters": {
            "employers": employers,
            "recruiters": recruiters,
            "jobs": [{"id": j["id"], "title": j.get("title", "Untitled")} for j in jobs]
        }
    }
