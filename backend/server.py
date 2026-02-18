from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, status, Form, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import hashlib
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import aiofiles
import fitz  # PyMuPDF for PDF text extraction

# Import configuration from config.py
from config import (
    ROOT_DIR,
    db,
    db_name,
    client,
    r2_client,
    R2_ENABLED,
    R2_BUCKET_NAME,
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    UPLOAD_DIR,
    PARENT_UPLOAD_DIR
)

# Import models from models/
from models import (
    # Auth models
    UserBase, UserCreate, UserLogin, UserResponse, UserUpdate,
    AdminUserCreate, AdminPasswordReset, PasswordReset, TokenResponse,
    # Job models
    JobBase, JobCreate, JobResponse, JobUpdate, JobStateTransition,
    CareerPageStatusUpdate, JDParseRequest, JDParseResponse, MandateAssignment,
    # Candidate models
    CandidateProfile, CandidateProfileUpdate,
    # Application models
    ApplicationBase, ApplicationCreate, ApplicationResponse,
    ApplicationUpdate, ApplicationDetailUpdate, AuditLogEntry, NoteCreate,
    # Company models
    CompanyBase, CompanyCreate, CompanyResponse, CompanyUpdate,
    # Team models
    TeamCreate, TeamUpdate, TeamResponse,
    # Referral models
    ReferralCreate, ReferralResponse, ReferralStatusUpdate,
    # Message models
    MessageBase, MessageCreate, MessageResponse,
    # Candidate Bank models
    CandidateBankRecord, CandidateBankUpdate, CandidateBankAuditLogEntry,
    BatchUploadCandidate, BatchSaveRequest,
    # Matching models
    MatchRequest, MatchResult, JobMatchForCandidate,
    # Alert models
    JobAlertPreferences, JobAlertCreate, WhatsAppOptIn, NotificationLogEntry,
    # Commercial models
    CommercialCreate, CommercialUpdate, CommercialResponse,
    RevenueEntry, RevenueUpdate
)

# Import utilities from utils/
from utils import (
    # Auth utilities
    hash_password, verify_password, create_access_token,
    get_current_user, require_role, security,
    # Governance utilities
    validate_mandatory_candidate_fields, create_profile_audit_entry,
    update_candidate_freshness, add_application_to_history,
    update_application_in_history
)

# Import R2 storage services
from services import (
    upload_to_r2,
    get_r2_signed_url,
    get_file_from_r2,
    generate_r2_key
)

# Import route modules
from routes import auth_router, public_router, files_router, admin_router, jobs_router, candidates_router, applications_router, settings_router, background_jobs_router, teams_router, referrals_router, commercials_router, analytics_router, revenue_router, employer_router
from routes.bulk_import import bulk_import_router
from routes.bug_reports import bug_reports_router
from routes.system_errors import system_errors_router, log_system_error
from routes.extension import extension_router
from routes.profile import profile_router
from routes.cv_upload import cv_upload_router
from routes.ai_search import ai_search_router
from routes.contact import router as contact_router
from routes.blog import router as blog_router
from routes.seo import router as seo_router
from routes.pillar_pages import router as pillar_pages_router
from routes.blog_digest import router as blog_digest_router
from routes.seo_dashboard import router as seo_dashboard_router

# Import boto3 for type hints (r2_client operations)
import boto3
from botocore.config import Config


# Create the main app
app = FastAPI(title="VHC Talent OS API")

# Include auth routes (extracted to routes/auth.py)
app.include_router(auth_router)

# Include public routes (extracted to routes/public.py)
app.include_router(public_router)

# Include file serving routes (extracted to routes/files.py)
app.include_router(files_router)

# Include admin routes (extracted to routes/admin.py)
app.include_router(admin_router)

# Include jobs routes (extracted to routes/jobs.py)
app.include_router(jobs_router)

# Include candidate bank routes (extracted to routes/candidates.py)
app.include_router(candidates_router)

# Include applications & AI matching routes (extracted to routes/applications.py)
app.include_router(applications_router)

# Include settings & alerts routes (extracted to routes/settings.py)
app.include_router(settings_router)

# Include background jobs & embeddings routes
app.include_router(background_jobs_router)

# Include bulk import routes (Admin only - for controlled data seeding)
app.include_router(bulk_import_router)

# Include extracted business-logic routes
app.include_router(teams_router)
app.include_router(referrals_router)
app.include_router(commercials_router)
app.include_router(bug_reports_router)
app.include_router(system_errors_router)
app.include_router(profile_router)
app.include_router(cv_upload_router)
app.include_router(ai_search_router)
app.include_router(extension_router)
app.include_router(analytics_router)
app.include_router(contact_router)
app.include_router(blog_router)
app.include_router(seo_router)
app.include_router(pillar_pages_router)
app.include_router(blog_digest_router)
app.include_router(seo_dashboard_router)
app.include_router(revenue_router)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Note: Auth routes extracted to routes/auth.py and included via app.include_router()

# Note: USER MANAGEMENT (ADMIN) routes have been extracted to routes/admin.py
# Endpoints: /api/users, /api/users/{user_id}, /api/admin/users, /api/admin/pipeline, etc.

# Note: JOB ROUTES have been extracted to routes/jobs.py
# Endpoints: /api/jobs, /api/jobs/{job_id}, /api/jobs/{job_id}/transition,
#            /api/jobs/{job_id}/career-page-status, /api/jobs/{job_id}/shareable-link,
#            /api/career-page/jobs, /api/jobs/parse-jd, /api/jobs/{job_id}/assign-recruiters, etc.


# Note: APPLICATION & AI MATCHING routes have been extracted to routes/applications.py
# Endpoints: /api/applications, /api/applications/{app_id}, /api/applications/{app_id}/resume,
#            /api/applications/{app_id}/notes, /api/applications/{app_id}/details,
#            /api/applications/{app_id}/edit-history, /api/jobs/{job_id}/applicants,
#            /api/candidates, /api/candidates/{candidate_id},
#            /api/ai/parse-resume, /api/ai/parse-jd,
#            /api/matching/find-candidates, /api/matching/jobs-for-candidate


# Note: SETTINGS & ALERTS routes have been extracted to routes/settings.py

# Note: Teams, Referrals, Commercials, Revenue routes have been extracted to:
#   routes/teams.py, routes/referrals.py, routes/commercials.py

# Create a router for remaining employer/admin endpoints not yet extracted
api_router = APIRouter(prefix="/api")


@api_router.get("/employers/{employer_id}/companies")
async def get_employer_companies(
    employer_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Get companies assigned to a specific employer (Admin only).
    Used for auto-populating company selection when creating a team.
    """
    # Verify employer exists
    employer = await db.users.find_one({"id": employer_id, "role": "employer"}, {"_id": 0})
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")
    
    # Get companies assigned to this employer (include None status for backwards compatibility)
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


@api_router.get("/employer/my-team")
async def get_employer_team_with_metrics(current_user: dict = Depends(require_role(["employer"]))):
    """
    Get employer's team with detailed performance metrics.
    Shows: team members, mandates assigned, pipelines, revenue per stage, closed revenue.
    
    Internal endpoint for Employer portal "My Team" panel.
    """
    # Get employer's team
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
    
    # Get team member details
    recruiter_ids = team.get("recruiter_ids", [])
    recruiters = await db.users.find(
        {"id": {"$in": recruiter_ids}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "is_active": 1, "created_at": 1}
    ).to_list(100)
    
    # Get jobs/mandates under employer's companies
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
    
    # Get all applications for these jobs
    applications = await db.applications.find(
        {"job_id": {"$in": job_ids}},
        {"_id": 0}
    ).to_list(10000)
    
    # Get commercials from company documents for revenue calculation
    companies_with_commercial = await db.companies.find(
        {"id": {"$in": company_ids}},
        {"_id": 0, "id": 1, "commercial": 1}
    ).to_list(100)
    commercial_by_company = {c["id"]: c.get("commercial", {}) for c in companies_with_commercial}
    
    # Calculate per-member metrics
    members_with_metrics = []
    
    for recruiter in recruiters:
        # Jobs assigned to this recruiter
        recruiter_jobs = [j for j in employer_jobs if 
                         j.get("posted_by") == recruiter["id"] or 
                         recruiter["id"] in j.get("assigned_recruiters", [])]
        recruiter_job_ids = [j["id"] for j in recruiter_jobs]
        
        # Applications for recruiter's jobs
        recruiter_apps = [a for a in applications if a["job_id"] in recruiter_job_ids]
        
        # Pipeline stages count
        stages = {
            "applied": 0, "shortlisted": 0, "interview": 0,
            "offered": 0, "hired": 0, "rejected": 0
        }
        for app in recruiter_apps:
            stage = app.get("stage", "applied")
            if stage in stages:
                stages[stage] += 1
        
        # Revenue calculation
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
                    
                    if app.get("stage") == "hired":
                        revenue_closed += revenue
                    elif app.get("stage") in ["offered", "interview", "shortlisted"]:
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
    
    # Calculate team totals
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


@api_router.get("/employer/companies")
async def get_employer_companies_with_details(current_user: dict = Depends(require_role(["employer"]))):
    """
    Get employer's assigned companies with commercial details, mandates, and pipelines.
    
    Internal endpoint for Employer portal "Companies" panel.
    Returns companies assigned by Admin with:
    - Commercial details (read-only)
    - Active mandates
    - Pipeline data grouped by mandate
    """
    # Get employer's team to find assigned companies
    team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
    
    if not team:
        return {"companies": []}
    
    company_ids = team.get("company_ids", [])
    
    if not company_ids:
        return {"companies": []}
    
    # Get companies
    companies = await db.companies.find(
        {"id": {"$in": company_ids}},
        {"_id": 0}
    ).to_list(100)
    
    # Commercials are now embedded in company documents
    commercial_by_company = {c["id"]: c.get("commercial", {}) for c in companies}
    
    # Get jobs for each company
    all_jobs = await db.jobs.find(
        {"company_id": {"$in": company_ids}},
        {"_id": 0}
    ).to_list(1000)
    
    # Get applications for pipeline data
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
        
        # Group pipeline by mandate
        mandates_with_pipeline = []
        for job in company_jobs:
            job_apps = [a for a in company_apps if a["job_id"] == job["id"]]
            
            stages = {"applied": 0, "shortlisted": 0, "interview": 0, "offered": 0, "hired": 0, "rejected": 0}
            revenue_by_stage = {"applied": 0, "shortlisted": 0, "interview": 0, "offered": 0, "hired": 0}
            
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
                "total_revenue_pipeline": round(sum(v for k, v in revenue_by_stage.items() if k != "hired"), 2),
                "total_revenue_closed": round(revenue_by_stage.get("hired", 0), 2)
            })
        
        # Calculate company totals
        total_pipeline = sum(m["pipeline_count"] for m in mandates_with_pipeline)
        total_revenue_closed = sum(m["total_revenue_closed"] for m in mandates_with_pipeline)
        
        enriched_companies.append({
            "id": company_id,
            "name": company["name"],
            "industry": company.get("industry"),
            "location": company.get("location"),
            "logo_url": company.get("logo_url"),
            # Commercial details (read-only for employer)
            "commercial": commercial or {},
            # Mandates
            "mandates": mandates_with_pipeline,
            "active_mandates_count": len([m for m in mandates_with_pipeline if m["status"] == "active"]),
            # Summary
            "total_pipeline": total_pipeline,
            "total_revenue_closed": round(total_revenue_closed, 2)
        })
    
    return {"companies": enriched_companies}


@api_router.get("/employer/pipeline")
async def get_employer_pipeline(
    recruiter_id: Optional[str] = None,
    job_id: Optional[str] = None,
    current_user: dict = Depends(require_role(["employer"]))
):
    """
    Employer pipeline view with stage control.
    Shows all applications for jobs under employer's teams/companies.
    
    Features:
    - Combined pipeline across all assigned companies
    - Filter by recruiter or specific job
    - Full application details for stage transitions
    
    Role-based access: Employer can only see their assigned companies/teams.
    """
    # Get employer's team
    team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
    
    if not team:
        return {
            "pipeline": {stage: [] for stage in ["applied", "shortlisted", "interview", "offered", "hired", "rejected", "on_hold"]},
            "stage_counts": {stage: 0 for stage in ["applied", "shortlisted", "interview", "offered", "hired", "rejected", "on_hold"]},
            "total_applications": 0,
            "filters": {"recruiters": [], "jobs": []}
        }
    
    company_ids = team.get("company_ids", [])
    recruiter_ids = team.get("recruiter_ids", [])
    
    # Build job filter - jobs under employer's companies or team
    job_filter = {
        "$or": [
            {"team_id": team["id"]},
            {"company_id": {"$in": company_ids}} if company_ids else {"_id": None},
            {"posted_by": {"$in": recruiter_ids + [current_user["id"]]}}
        ]
    }
    
    # Apply job_id filter if specified
    if job_id:
        job_filter = {"id": job_id, **job_filter}
    
    # Get all jobs matching filter
    jobs = await db.jobs.find(job_filter, {"_id": 0}).to_list(1000)
    job_ids = [j["id"] for j in jobs]
    jobs_map = {j["id"]: j for j in jobs}
    
    # Apply recruiter filter to jobs if specified
    if recruiter_id:
        recruiter_job_ids = [
            j["id"] for j in jobs 
            if j.get("posted_by") == recruiter_id or recruiter_id in j.get("assigned_recruiters", [])
        ]
        job_ids = [jid for jid in job_ids if jid in recruiter_job_ids]
    
    # Get all applications for these jobs
    if job_ids:
        applications = await db.applications.find(
            {"job_id": {"$in": job_ids}},
            {"_id": 0}
        ).to_list(10000)
    else:
        applications = []
    
    # Define pipeline stages
    all_stages = ["applied", "shortlisted", "interview", "offered", "joined", "hired", "rejected", "on_hold"]
    
    # Group applications by stage
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
            "stage": stage
        })
    
    # Calculate stage counts
    stage_counts = {stage: len(apps) for stage, apps in pipeline_data.items()}
    
    # Get recruiter details for filter dropdown
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


# Note: Teams CRUD (get/update/delete by ID) extracted to routes/teams.py
# Note: Referrals CRUD extracted to routes/referrals.py


# ============== PHASE-A: COMPANY-EMPLOYER ASSIGNMENT ==============

@api_router.put("/companies/{company_id}/assign-employer")
async def assign_employer_to_company(
    company_id: str,
    employer_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Assign an employer to manage a company (Admin only).
    """
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


@api_router.put("/companies/{company_id}", response_model=CompanyResponse)
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
    
    # Access control for employers
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


# ============== PHASE-A: ADMIN HIERARCHY OVERVIEW ==============

@api_router.get("/admin/hierarchy")
async def get_admin_hierarchy(current_user: dict = Depends(require_role(["admin"]))):
    """
    Get complete hierarchy overview for Admin.
    Shows: Employers -> Teams -> Recruiters -> Companies
    """
    # Get all employers
    employers = await db.users.find({"role": "employer", "is_active": True}, {"_id": 0, "password": 0}).to_list(1000)
    
    hierarchy = []
    
    for employer in employers:
        employer_data = {
            "employer_id": employer["id"],
            "employer_name": employer["name"],
            "employer_email": employer["email"],
            "teams": []
        }
        
        # Get teams for this employer
        teams = await db.teams.find({"employer_id": employer["id"], "status": "active"}, {"_id": 0}).to_list(100)
        
        for team in teams:
            # Get active jobs count
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
            
            # Get recruiters in this team
            for recruiter_id in team.get("recruiter_ids", []):
                recruiter = await db.users.find_one({"id": recruiter_id}, {"_id": 0, "password": 0})
                if recruiter:
                    team_data["recruiters"].append({
                        "id": recruiter["id"],
                        "name": recruiter["name"],
                        "email": recruiter["email"]
                    })
            
            # Get companies in this team
            for company_id in team.get("company_ids", []):
                company = await db.companies.find_one({"id": company_id}, {"_id": 0})
                if company:
                    team_data["companies"].append({
                        "id": company["id"],
                        "name": company["name"],
                        "industry": company.get("industry")
                    })
            
            employer_data["teams"].append(team_data)
        
        hierarchy.append(employer_data)
    
    # Get unassigned recruiters
    unassigned_recruiters = await db.users.find(
        {"role": "recruiter", "is_active": True, "team_id": {"$exists": False}},
        {"_id": 0, "password": 0}
    ).to_list(1000)
    
    # Get unassigned companies
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



# Note: Commercials + Revenue CRUD extracted to routes/commercials.py


# ============== ADMIN ANALYTICS DASHBOARD ==============

@api_router.get("/analytics/admin")
async def get_admin_analytics(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    employer_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    company_id: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Admin analytics dashboard - Power BI style.
    Full visibility into all business metrics.
    
    OPTIMIZED: Uses MongoDB aggregation pipelines instead of loading all data into memory.
    """
    import time
    start_time = time.time()
    
    # Build date match stage for aggregations
    date_match = {}
    if date_from:
        date_match["$gte"] = date_from
    if date_to:
        date_match["$lte"] = date_to
    
    # ========== JOBS AGGREGATION ==========
    jobs_match = {"status": {"$in": ["active", "on_hold", "closed"]}}
    if company_id:
        jobs_match["company_id"] = company_id
    
    # Get job counts and create lookup map efficiently
    jobs_pipeline = [
        {"$match": jobs_match},
        {"$project": {"_id": 0, "id": 1, "status": 1, "company_id": 1, "assigned_recruiter_ids": 1}}
    ]
    jobs = await db.jobs.aggregate(jobs_pipeline).to_list(10000)
    active_jobs_count = sum(1 for j in jobs if j.get("status") == "active")
    
    # ========== APPLICATIONS AGGREGATION (Stage Distribution) ==========
    apps_match = {}
    if date_match:
        apps_match["created_at"] = date_match
    
    # Use aggregation for stage counts instead of loading all applications
    stage_pipeline = [
        {"$match": apps_match} if apps_match else {"$match": {}},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
    ]
    stage_results = await db.applications.aggregate(stage_pipeline).to_list(20)
    stage_counts = {r["_id"] or "applied": r["count"] for r in stage_results}
    
    offered_count = stage_counts.get("offered", 0)
    hired_count = stage_counts.get("hired", 0)
    offer_to_join_ratio = (hired_count / offered_count * 100) if offered_count > 0 else 0
    
    # ========== AVG TIME TO CLOSE (Hired applications only) ==========
    hired_pipeline = [
        {"$match": {"stage": "hired", "created_at": {"$exists": True}}},
        {"$project": {"_id": 0, "created_at": 1, "updated_at": 1}},
        {"$limit": 1000}  # Limit for performance
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
    
    # ========== USER COUNTS (Efficient count_documents) ==========
    active_employers = await db.users.count_documents({"role": "employer", "is_active": True})
    active_recruiters = await db.users.count_documents({"role": "recruiter", "is_active": True})
    
    # ========== REVENUE AGGREGATION ==========
    revenue_match = {}
    if date_match:
        revenue_match["created_at"] = date_match
    if company_id:
        revenue_match["company_id"] = company_id
    
    # Revenue KPIs aggregation
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
    
    # Revenue by company aggregation (eliminates N+1 queries)
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
    
    # Revenue funnel by stage
    revenue_funnel_pipeline = [
        {"$match": revenue_match} if revenue_match else {"$match": {}},
        {"$group": {
            "_id": "$stage",
            "total": {"$sum": "$final_revenue"}
        }}
    ]
    funnel_results = await db.revenue.aggregate(revenue_funnel_pipeline).to_list(10)
    revenue_funnel = {r["_id"]: r["total"] for r in funnel_results if r["_id"]}
    
    # ========== RECRUITER PERFORMANCE AGGREGATION ==========
    # Get all recruiter IDs from jobs first
    recruiter_ids = set()
    for job in jobs:
        for rec_id in job.get("assigned_recruiter_ids", []):
            recruiter_ids.add(rec_id)
    
    # Batch fetch all recruiter names at once (eliminates N+1)
    recruiter_names = {}
    if recruiter_ids:
        recruiters = await db.users.find(
            {"id": {"$in": list(recruiter_ids)}},
            {"_id": 0, "id": 1, "name": 1}
        ).to_list(len(recruiter_ids))
        recruiter_names = {r["id"]: r.get("name", "Unknown") for r in recruiters}
    
    # Build recruiter stats from applications aggregation
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
    
    # Build recruiter performance from job assignments
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
    
    # Add revenue to recruiter stats via aggregation
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
    logging.info(f"[ADMIN ANALYTICS] Completed in {elapsed:.2f}s")
    
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


# ============== EMPLOYER ANALYTICS DASHBOARD ==============

@api_router.get("/analytics/employer")
async def get_employer_analytics(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Employer analytics dashboard.
    Scoped to assigned companies and teams only.
    
    OPTIMIZED: Uses MongoDB aggregation pipelines and batch lookups to eliminate N+1 queries.
    """
    import time
    start_time = time.time()
    
    # Get companies assigned to this employer (or all for admin)
    company_query = {"assigned_employer_id": current_user["id"]} if current_user["role"] == "employer" else {}
    assigned_companies = await db.companies.find(company_query, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
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
    
    # ========== JOBS: Get minimal fields needed ==========
    jobs = await db.jobs.find(
        {"company_id": {"$in": company_ids}},
        {"_id": 0, "id": 1, "status": 1, "company_id": 1, "team_id": 1, "assigned_recruiter_ids": 1}
    ).to_list(10000)
    
    active_jobs_count = sum(1 for j in jobs if j.get("status") == "active")
    job_ids = [j["id"] for j in jobs]
    
    # ========== APPLICATIONS: Aggregation for counts ==========
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
    
    # ========== REVENUE: Aggregation for KPIs ==========
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
    
    # Revenue by company aggregation
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
    
    # Revenue by job for recruiter calculations
    revenue_by_job_pipeline = [
        {"$match": {"job_id": {"$in": job_ids}}},
        {"$group": {
            "_id": "$job_id",
            "total_revenue": {"$sum": "$final_revenue"}
        }}
    ]
    revenue_by_job = await db.revenue.aggregate(revenue_by_job_pipeline).to_list(10000)
    job_revenue_map = {r["_id"]: r["total_revenue"] for r in revenue_by_job}
    
    # ========== COMMERCIALS: Average fee percentage (from company.commercial) ==========
    pct_fees = []
    for co in assigned_companies:
        comm = co.get("commercial", {})
        if comm and comm.get("type") == "percentage" and comm.get("percentage_value"):
            pct_fees.append(comm["percentage_value"])
    avg_fee = sum(pct_fees) / len(pct_fees) if pct_fees else 0
    
    # ========== BUILD COMPANY REVENUE (No N+1 - using pre-fetched data) ==========
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
    
    # ========== TEAMS PERFORMANCE ==========
    team_query = {"employer_id": current_user["id"]} if current_user["role"] == "employer" else {}
    teams = await db.teams.find(team_query, {"_id": 0, "id": 1, "name": 1}).to_list(100)
    
    team_performance = []
    for team in teams:
        team_jobs = [j for j in jobs if j.get("team_id") == team["id"]]
        team_job_ids = {j["id"] for j in team_jobs}
        
        # Sum from pre-aggregated data
        team_apps = sum(app_stats_map.get(jid, {}).get("total", 0) for jid in team_job_ids)
        team_hired = sum(app_stats_map.get(jid, {}).get("hired", 0) for jid in team_job_ids)
        
        # For revenue split, we need to re-query by team but this is bounded
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
    
    # ========== RECRUITER CONTRIBUTION (Batch lookup - no N+1) ==========
    recruiter_ids = set()
    for job in jobs:
        for rec_id in job.get("assigned_recruiter_ids", []):
            recruiter_ids.add(rec_id)
    
    # Batch fetch all recruiter names at once
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
        
        # Sum from pre-aggregated data
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
    logging.info(f"[EMPLOYER ANALYTICS] Completed in {elapsed:.2f}s")
    
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

@api_router.get("/companies/{company_id}/pipeline")
async def get_company_pipeline(
    company_id: str,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Get company profile with pipeline view.
    Shows mandates, revenue breakdown, and detailed pipeline.
    
    OPTIMIZED: Uses batch lookups and aggregations to eliminate N+1 queries.
    """
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Employer access control
    if current_user["role"] == "employer":
        if company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all jobs for this company (minimal fields)
    jobs = await db.jobs.find(
        {"company_id": company_id},
        {"_id": 0, "id": 1, "title": 1, "job_level": 1, "status": 1, "assigned_recruiter_ids": 1}
    ).to_list(10000)
    
    total_mandates = len(jobs)
    active_mandates = sum(1 for j in jobs if j.get("status") == "active")
    closed_mandates = sum(1 for j in jobs if j.get("status") == "closed")
    job_ids = [j["id"] for j in jobs]
    
    # Get revenue
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
    
    # Get commercial from company document
    company_doc = await db.companies.find_one({"id": company_id}, {"_id": 0, "commercial": 1})
    company_commercial = company_doc.get("commercial", {}) if company_doc else {}
    avg_commercial_pct = 0
    if company_commercial.get("type") == "percentage" and company_commercial.get("percentage_value"):
        avg_commercial_pct = company_commercial["percentage_value"]
    
    # OPTIMIZATION: Batch fetch all recruiter names at once (eliminates N+1)
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
    
    # OPTIMIZATION: Batch get application stage counts via aggregation (eliminates N+1)
    apps_pipeline = [
        {"$match": {"job_id": {"$in": job_ids}}},
        {"$group": {
            "_id": {"job_id": "$job_id", "stage": "$stage"},
            "count": {"$sum": 1}
        }}
    ]
    app_stats = await db.applications.aggregate(apps_pipeline).to_list(10000)
    
    # Build stage counts by job
    stage_counts_by_job = {}
    for stat in app_stats:
        jid = stat["_id"]["job_id"]
        stage = stat["_id"]["stage"] or "applied"
        if jid not in stage_counts_by_job:
            stage_counts_by_job[jid] = {}
        stage_counts_by_job[jid][stage] = stat["count"]
    
    # Build pipeline table (no N+1 queries - all data pre-fetched)
    pipeline = []
    for job in jobs:
        job_rev = revenue_by_job.get(job["id"], {"expected": 0, "closed": 0})
        
        # Get recruiter names from pre-fetched map
        recruiters = [recruiter_names.get(rec_id, "Unknown") for rec_id in job.get("assigned_recruiter_ids", [])]
        
        pipeline.append({
            "job_id": job["id"],
            "job_title": job.get("title"),
            "job_level": job.get("job_level"),
            "status": job.get("status"),
            "recruiters": recruiters,
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


# Note: JD PARSING routes have been extracted to routes/jobs.py
# Endpoints: /api/jobs/extract-jd-text, /api/jobs/parse-jd

# Note: MANDATE ASSIGNMENT routes have been extracted to routes/jobs.py
# Endpoints: /api/employer/team-recruiters, /api/jobs/{job_id}/assign-recruiters, etc.

# Note: FILE SERVING routes have been extracted to routes/files.py
# Endpoints: /api/uploads/{filename}

# ============== SEED ADMIN ==============

@app.on_event("startup")
async def validate_mongodb_connection():
    """
    Validates MongoDB connectivity on startup. Non-blocking: logs warning if unavailable.
    Motor will auto-reconnect on subsequent requests.
    """
    for attempt in range(3):
        try:
            await client.admin.command("ping")
            # Log connection target for deployment verification (WARNING level for visibility)
            mongo_host = os.environ.get('MONGO_URL', '')[:60]
            is_atlas = 'mongodb+srv' in mongo_host or 'mongodb.net' in mongo_host
            logging.warning(f"MongoDB connected: {'ATLAS' if is_atlas else 'LOCAL'} | DB: {db_name} | Host: {mongo_host}...")
            if not is_atlas:
                logging.warning("CRITICAL: Connected to LOCAL MongoDB, NOT Atlas! Check MONGO_URL in .env")
            return
        except Exception as e:
            logging.warning(f"MongoDB connection attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                await asyncio.sleep(5)
    logging.warning("MongoDB not available at startup. Motor will auto-reconnect on first request.")


@app.on_event("startup")
async def start_blog_scheduler():
    """Start the APScheduler background jobs for blog auto-publishing."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from services.blog_scheduler import auto_publish_blog, get_schedule_config

        scheduler = AsyncIOScheduler()

        async def run_employer_publish():
            config = await get_schedule_config()
            if config.get("employer", {}).get("enabled"):
                await auto_publish_blog("employer")

        async def run_candidate_publish():
            config = await get_schedule_config()
            if config.get("candidate", {}).get("enabled"):
                await auto_publish_blog("candidate")

        # Employer: Mon, Wed, Fri at 03:30 UTC (9:00 AM IST)
        scheduler.add_job(run_employer_publish, 'cron', day_of_week='mon,wed,fri', hour=3, minute=30, id='employer_blog')
        # Candidate: Tue, Thu at 04:30 UTC (10:00 AM IST)
        scheduler.add_job(run_candidate_publish, 'cron', day_of_week='tue,thu', hour=4, minute=30, id='candidate_blog')

        scheduler.start()
        app.state.blog_scheduler = scheduler
        logging.info("[BlogScheduler] Auto-publish scheduler started (Employer: Mon/Wed/Fri 9AM IST, Candidate: Tue/Thu 10AM IST)")
    except Exception as e:
        logging.warning(f"[BlogScheduler] Failed to start scheduler: {e}")

@app.on_event("startup")
async def validate_r2_connection():
    """
    Validates Cloudflare R2 connectivity on application startup.
    Non-blocking: Falls back to local storage if R2 is not available.
    """
    if R2_ENABLED:
        try:
            # List buckets to verify connectivity
            r2_client.list_buckets()
            logging.info("Cloudflare R2 successfully connected and operational")
            logging.info(f"R2 Bucket: {R2_BUCKET_NAME}")
        except Exception as e:
            logging.warning(f"Cloudflare R2 connectivity check failed: {e}")
            logging.warning("R2 may still work - some operations may succeed despite list_buckets failure")
    else:
        logging.info("Cloudflare R2 not configured - using local storage")

@app.on_event("startup")
async def seed_admin():
    """
    Seeds admin user from environment variables on first run.
    """
    admin_email = os.environ.get('ADMIN_EMAIL')
    admin_password = os.environ.get('ADMIN_PASSWORD')
    
    if not admin_email or not admin_password:
        logging.warning("ADMIN_EMAIL or ADMIN_PASSWORD not set - skipping admin seeding")
        return
    
    try:
        existing_admin = await db.users.find_one({"email": admin_email})
        if not existing_admin:
            admin_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            
            admin_doc = {
                "id": admin_id,
                "email": admin_email,
                "name": "System Admin",
                "role": "admin",
                "password": hash_password(admin_password),
                "phone": None,
                "company_id": None,
                "is_active": True,
                "requires_password_reset": False,
                "created_at": now
            }
            
            await db.users.insert_one(admin_doc)
            logging.info(f"Admin user seeded: {admin_email}")
        
        test_result = await db.users.delete_many({"email": {"$regex": "@test\\.com$"}})
        if test_result.deleted_count > 0:
            logging.info(f"Cleaned up {test_result.deleted_count} test users")
    except Exception as e:
        logging.warning(f"Admin seeding skipped (DB not available): {e}")

@app.on_event("startup")
async def ensure_pillar_pages_index():
    """Create unique index on pillar_pages.slug."""
    try:
        await db.pillar_pages.create_index("slug", unique=True)
        logging.info("pillar_pages.slug unique index ensured")
    except Exception as e:
        logging.warning(f"pillar_pages index creation skipped: {e}")

@app.on_event("startup")
async def ensure_blog_digests_index():
    """Create indexes on blog_digests and seo collections."""
    try:
        await db.blog_digests.create_index("week_key", unique=True)
        await db.blog_digests.create_index([("generated_at", -1)])
        await db.seo_snapshots.create_index([("snapshot_date", -1)])
        await db.seo_alerts.create_index("status")
        await db.seo_alerts.create_index("severity")
        logging.info("blog_digests + seo indexes ensured")
    except Exception as e:
        logging.warning(f"Index creation skipped: {e}")

@app.on_event("startup")
async def start_background_scheduler():
    """Start APScheduler for background jobs."""
    from services.scheduler import start_scheduler
    try:
        start_scheduler()
    except Exception as e:
        logging.error(f"Scheduler startup failed: {e}", exc_info=True)

@app.on_event("shutdown")
async def stop_background_scheduler():
    """Gracefully stop the scheduler."""
    from services.scheduler import stop_scheduler
    stop_scheduler()

# Include the router in the main app
app.include_router(api_router)


# Auto-capture unhandled exceptions and log to system_errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback as tb
    # Skip HTTP exceptions (they're intentional)
    if isinstance(exc, HTTPException):
        raise exc

    error_msg = str(exc)
    stack = tb.format_exception(type(exc), exc, exc.__traceback__)
    stack_str = "".join(stack)

    # Extract user from token if present
    user_id = None
    user_role = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from utils import verify_token
            payload = verify_token(auth_header.split(" ")[1])
            user_id = payload.get("sub")
            user_role = payload.get("role")
        except Exception:
            pass

    try:
        await log_system_error(
            source="backend",
            error_type=type(exc).__name__,
            message=error_msg,
            stack_trace=stack_str,
            endpoint=str(request.url.path),
            method=request.method,
            status_code=500,
            user_id=user_id,
            user_role=user_role,
        )
    except Exception:
        pass

    logging.error(f"Unhandled exception on {request.method} {request.url.path}: {error_msg}")
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# CORS: combine hardcoded production origins with env overrides
_hardcoded_origins = [
    "https://ventureshrd.com",
    "https://www.ventureshrd.com",
    "https://candidate-flow-5.emergent.host",
    "https://revenue-verify-3.preview.emergentagent.com",
]
_env_origins = [o.strip() for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip()]
_all_origins = list(set(_hardcoded_origins + _env_origins))

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# SEO & Security Headers Middleware
@app.middleware("http")
async def seo_security_headers(request: Request, call_next):
    response = await call_next(request)
    # HTTPS enforcement headers
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
