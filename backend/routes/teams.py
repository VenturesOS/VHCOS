"""
VHC Talent OS - Team Management Routes
Handles team creation, management, and hierarchy operations.
Refactored from server.py for better code organization.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from config import db
from utils import get_current_user, require_role

# Create router
teams_router = APIRouter(prefix="/api", tags=["Teams"])

logger = logging.getLogger(__name__)


# ============== PYDANTIC MODELS ==============

class TeamCreate(BaseModel):
    name: str
    employer_id: str
    recruiter_ids: List[str] = []
    company_ids: List[str] = []


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    recruiter_ids: Optional[List[str]] = None
    company_ids: Optional[List[str]] = None


class TeamResponse(BaseModel):
    id: str
    name: str
    employer_id: str
    employer_name: Optional[str] = None
    recruiter_ids: List[str] = []
    recruiter_names: List[str] = []
    company_ids: List[str] = []
    company_names: List[str] = []
    status: str = "active"
    active_jobs_count: int = 0
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        extra = "ignore"


# ============== TEAM CRUD ==============

@teams_router.post("/teams", response_model=TeamResponse)
async def create_team(team_data: TeamCreate, current_user: dict = Depends(require_role(["admin"]))):
    """
    Create a new Team (Admin only).
    
    A Team links:
    - One Employer (team owner/manager)
    - Multiple Recruiters (team members)
    - Multiple Companies (client companies the team manages)
    
    AUTO-ATTACH: Companies already assigned to the employer are automatically included.
    """
    # Validate employer exists and has correct role
    employer = await db.users.find_one({"id": team_data.employer_id, "role": "employer"}, {"_id": 0})
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")
    
    # Validate all recruiters exist and have correct role
    recruiter_names = []
    for recruiter_id in team_data.recruiter_ids:
        recruiter = await db.users.find_one({"id": recruiter_id, "role": "recruiter"}, {"_id": 0})
        if not recruiter:
            raise HTTPException(status_code=400, detail=f"Recruiter {recruiter_id} not found")
        recruiter_names.append(recruiter.get("name", "Unknown"))
    
    # AUTO-ATTACH: Get companies already assigned to this employer
    employer_companies = await db.companies.find(
        {
            "assigned_employer_id": team_data.employer_id,
            "$or": [{"status": "active"}, {"status": None}, {"status": {"$exists": False}}]
        },
        {"_id": 0, "id": 1, "name": 1}
    ).to_list(100)
    
    # Merge: employer's existing companies + any explicitly provided company_ids
    auto_company_ids = [c["id"] for c in employer_companies]
    merged_company_ids = list(set(auto_company_ids + team_data.company_ids))
    
    # Validate and get names for all companies
    company_names = []
    for company_id in merged_company_ids:
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})
        if not company:
            raise HTTPException(status_code=400, detail=f"Company {company_id} not found")
        company_names.append(company.get("name", "Unknown"))
    
    team_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    team_doc = {
        "id": team_id,
        "name": team_data.name,
        "employer_id": team_data.employer_id,
        "employer_name": employer.get("name"),
        "recruiter_ids": team_data.recruiter_ids,
        "recruiter_names": recruiter_names,
        "company_ids": merged_company_ids,
        "company_names": company_names,
        "status": "active",
        "active_jobs_count": 0,
        "created_at": now,
        "updated_at": now,
        "created_by": current_user["id"],
        "audit_log": [{
            "action": "created",
            "by_id": current_user["id"],
            "by_name": current_user["name"],
            "by_role": current_user["role"],
            "timestamp": now
        }]
    }
    
    await db.teams.insert_one(team_doc)
    
    # Update recruiters with team assignment
    for recruiter_id in team_data.recruiter_ids:
        await db.users.update_one(
            {"id": recruiter_id},
            {"$set": {"team_id": team_id, "updated_at": now}}
        )
    
    # Update companies with employer assignment and team_id
    for company_id in merged_company_ids:
        await db.companies.update_one(
            {"id": company_id},
            {"$set": {"assigned_employer_id": team_data.employer_id, "team_id": team_id, "updated_at": now}}
        )
    
    logger.info(f"Team '{team_data.name}' created by {current_user['name']} with {len(merged_company_ids)} companies")
    
    return TeamResponse(**team_doc)


@teams_router.get("/teams", response_model=List[TeamResponse])
async def get_teams(current_user: dict = Depends(require_role(["admin", "employer"]))):
    """
    Get all teams.
    - Admin: sees all teams
    - Employer: sees only their teams
    """
    query = {}
    if current_user["role"] == "employer":
        query["employer_id"] = current_user["id"]
    
    teams = await db.teams.find(query, {"_id": 0}).to_list(100)
    return [TeamResponse(**t) for t in teams]


@teams_router.get("/teams/{team_id}", response_model=TeamResponse)
async def get_team(team_id: str, current_user: dict = Depends(require_role(["admin", "employer"]))):
    """Get a specific team by ID"""
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Employer can only view their own team
    if current_user["role"] == "employer" and team["employer_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return TeamResponse(**team)


@teams_router.put("/teams/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: str,
    update_data: TeamUpdate,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Update a team (Admin only)"""
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    now = datetime.now(timezone.utc).isoformat()
    update_dict = {"updated_at": now}
    
    if update_data.name:
        update_dict["name"] = update_data.name
    
    if update_data.recruiter_ids is not None:
        # Validate recruiters
        recruiter_names = []
        for recruiter_id in update_data.recruiter_ids:
            recruiter = await db.users.find_one({"id": recruiter_id, "role": "recruiter"}, {"_id": 0})
            if not recruiter:
                raise HTTPException(status_code=400, detail=f"Recruiter {recruiter_id} not found")
            recruiter_names.append(recruiter.get("name", "Unknown"))
        
        # Remove old recruiters from team
        for old_recruiter_id in team.get("recruiter_ids", []):
            if old_recruiter_id not in update_data.recruiter_ids:
                await db.users.update_one(
                    {"id": old_recruiter_id},
                    {"$unset": {"team_id": ""}}
                )
        
        # Add new recruiters to team
        for recruiter_id in update_data.recruiter_ids:
            await db.users.update_one(
                {"id": recruiter_id},
                {"$set": {"team_id": team_id, "updated_at": now}}
            )
        
        update_dict["recruiter_ids"] = update_data.recruiter_ids
        update_dict["recruiter_names"] = recruiter_names
    
    if update_data.company_ids is not None:
        # Validate companies
        company_names = []
        for company_id in update_data.company_ids:
            company = await db.companies.find_one({"id": company_id}, {"_id": 0})
            if not company:
                raise HTTPException(status_code=400, detail=f"Company {company_id} not found")
            company_names.append(company.get("name", "Unknown"))
        
        # Update company assignments
        for company_id in update_data.company_ids:
            await db.companies.update_one(
                {"id": company_id},
                {"$set": {"assigned_employer_id": team["employer_id"], "team_id": team_id, "updated_at": now}}
            )
        
        update_dict["company_ids"] = update_data.company_ids
        update_dict["company_names"] = company_names
    
    # Add audit log
    audit_entry = {
        "action": "updated",
        "by_id": current_user["id"],
        "by_name": current_user["name"],
        "by_role": current_user["role"],
        "timestamp": now,
        "changes": list(update_dict.keys())
    }
    
    await db.teams.update_one(
        {"id": team_id},
        {
            "$set": update_dict,
            "$push": {"audit_log": audit_entry}
        }
    )
    
    updated_team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    return TeamResponse(**updated_team)


@teams_router.delete("/teams/{team_id}")
async def delete_team(team_id: str, current_user: dict = Depends(require_role(["admin"]))):
    """Soft delete a team (Admin only)"""
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Remove team assignment from recruiters
    for recruiter_id in team.get("recruiter_ids", []):
        await db.users.update_one(
            {"id": recruiter_id},
            {"$unset": {"team_id": ""}}
        )
    
    # Soft delete
    await db.teams.update_one(
        {"id": team_id},
        {
            "$set": {"status": "deleted", "deleted_at": now, "deleted_by": current_user["id"]},
            "$push": {"audit_log": {
                "action": "deleted",
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "by_role": current_user["role"],
                "timestamp": now
            }}
        }
    )
    
    return {"message": "Team deleted", "team_id": team_id}


# ============== TEAM MEMBER MANAGEMENT ==============

@teams_router.post("/teams/{team_id}/recruiters/{recruiter_id}")
async def add_recruiter_to_team(
    team_id: str,
    recruiter_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Add a recruiter to a team"""
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    recruiter = await db.users.find_one({"id": recruiter_id, "role": "recruiter"}, {"_id": 0})
    if not recruiter:
        raise HTTPException(status_code=404, detail="Recruiter not found")
    
    if recruiter_id in team.get("recruiter_ids", []):
        raise HTTPException(status_code=400, detail="Recruiter already in team")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.teams.update_one(
        {"id": team_id},
        {
            "$push": {
                "recruiter_ids": recruiter_id,
                "recruiter_names": recruiter.get("name", "Unknown")
            },
            "$set": {"updated_at": now}
        }
    )
    
    await db.users.update_one(
        {"id": recruiter_id},
        {"$set": {"team_id": team_id, "updated_at": now}}
    )
    
    return {"message": f"Recruiter added to team", "recruiter_id": recruiter_id}


@teams_router.delete("/teams/{team_id}/recruiters/{recruiter_id}")
async def remove_recruiter_from_team(
    team_id: str,
    recruiter_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Remove a recruiter from a team"""
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    if recruiter_id not in team.get("recruiter_ids", []):
        raise HTTPException(status_code=400, detail="Recruiter not in team")
    
    recruiter = await db.users.find_one({"id": recruiter_id}, {"_id": 0})
    recruiter_name = recruiter.get("name", "Unknown") if recruiter else "Unknown"
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.teams.update_one(
        {"id": team_id},
        {
            "$pull": {
                "recruiter_ids": recruiter_id,
                "recruiter_names": recruiter_name
            },
            "$set": {"updated_at": now}
        }
    )
    
    await db.users.update_one(
        {"id": recruiter_id},
        {"$unset": {"team_id": ""}}
    )
    
    return {"message": f"Recruiter removed from team", "recruiter_id": recruiter_id}


# ============== TEAM COMPANIES ==============

@teams_router.post("/teams/{team_id}/companies/{company_id}")
async def add_company_to_team(
    team_id: str,
    company_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Add a company to a team"""
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    if company_id in team.get("company_ids", []):
        raise HTTPException(status_code=400, detail="Company already in team")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.teams.update_one(
        {"id": team_id},
        {
            "$push": {
                "company_ids": company_id,
                "company_names": company.get("name", "Unknown")
            },
            "$set": {"updated_at": now}
        }
    )
    
    await db.companies.update_one(
        {"id": company_id},
        {"$set": {"assigned_employer_id": team["employer_id"], "team_id": team_id, "updated_at": now}}
    )
    
    return {"message": f"Company added to team", "company_id": company_id}


@teams_router.delete("/teams/{team_id}/companies/{company_id}")
async def remove_company_from_team(
    team_id: str,
    company_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Remove a company from a team"""
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    if company_id not in team.get("company_ids", []):
        raise HTTPException(status_code=400, detail="Company not in team")
    
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    company_name = company.get("name", "Unknown") if company else "Unknown"
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.teams.update_one(
        {"id": team_id},
        {
            "$pull": {
                "company_ids": company_id,
                "company_names": company_name
            },
            "$set": {"updated_at": now}
        }
    )
    
    await db.companies.update_one(
        {"id": company_id},
        {"$unset": {"team_id": ""}}
    )
    
    return {"message": f"Company removed from team", "company_id": company_id}


# ============== TEAM STATISTICS ==============

@teams_router.get("/teams/{team_id}/stats")
async def get_team_stats(
    team_id: str,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Get statistics for a team"""
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Employer can only view their own team
    if current_user["role"] == "employer" and team["employer_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Count jobs
    jobs_query = {
        "$or": [
            {"company_id": {"$in": team.get("company_ids", [])}},
            {"posted_by": {"$in": team.get("recruiter_ids", [])}}
        ]
    }
    total_jobs = await db.jobs.count_documents(jobs_query)
    active_jobs = await db.jobs.count_documents({**jobs_query, "status": "active"})
    
    # Count applications
    job_ids = await db.jobs.find(jobs_query, {"id": 1, "_id": 0}).to_list(1000)
    job_id_list = [j["id"] for j in job_ids]
    total_applications = await db.applications.count_documents({"job_id": {"$in": job_id_list}})
    
    # Stage distribution
    stages = ["applied", "shortlisted", "interview", "offered", "hired", "rejected"]
    stage_counts = {}
    for stage in stages:
        stage_counts[stage] = await db.applications.count_documents({
            "job_id": {"$in": job_id_list},
            "stage": stage
        })
    
    return {
        "team_id": team_id,
        "team_name": team.get("name"),
        "recruiter_count": len(team.get("recruiter_ids", [])),
        "company_count": len(team.get("company_ids", [])),
        "total_jobs": total_jobs,
        "active_jobs": active_jobs,
        "total_applications": total_applications,
        "stage_distribution": stage_counts
    }
