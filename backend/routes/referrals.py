"""
VHC Talent OS - Referral Management Routes
Handles candidate referrals and their lifecycle.
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
referrals_router = APIRouter(prefix="/api", tags=["Referrals"])

logger = logging.getLogger(__name__)


# ============== PYDANTIC MODELS ==============

class ReferralCreate(BaseModel):
    job_id: str
    candidate_name: str
    candidate_email: str
    candidate_phone: Optional[str] = None
    resume_url: Optional[str] = None
    note: Optional[str] = None


class ReferralStatusUpdate(BaseModel):
    new_status: str
    reason: Optional[str] = None


class ReferralResponse(BaseModel):
    id: str
    job_id: str
    job_title: Optional[str] = None
    referrer_id: str
    referrer_name: Optional[str] = None
    candidate_name: str
    candidate_email: str
    candidate_phone: Optional[str] = None
    resume_url: Optional[str] = None
    note: Optional[str] = None
    status: str = "submitted"
    linked_candidate_id: Optional[str] = None
    linked_application_id: Optional[str] = None
    status_history: List[dict] = []
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        extra = "ignore"


# ============== REFERRAL CRUD ==============

@referrals_router.post("/referrals", response_model=ReferralResponse)
async def create_referral(
    referral_data: ReferralCreate,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Create a new candidate referral.
    
    Referral Lifecycle:
    1. submitted - Initial submission
    2. validated - Referral details verified
    3. linked - Linked to candidate bank record
    4. in_process - Candidate is being processed for the job
    5. outcome_reached - Hiring decision made
    6. closed - Referral process complete
    """
    # Validate job exists and is active
    job = await db.jobs.find_one({"id": referral_data.job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") != "active":
        raise HTTPException(status_code=400, detail="Can only refer candidates to active jobs")
    
    # Check for duplicate referral (same email + job)
    existing = await db.referrals.find_one({
        "job_id": referral_data.job_id,
        "candidate_email": referral_data.candidate_email.lower()
    })
    if existing:
        raise HTTPException(status_code=400, detail="This candidate has already been referred for this job")
    
    referral_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    referral_doc = {
        "id": referral_id,
        "job_id": referral_data.job_id,
        "job_title": job.get("title"),
        "referrer_id": current_user["id"],
        "referrer_name": current_user["name"],
        "candidate_name": referral_data.candidate_name,
        "candidate_email": referral_data.candidate_email.lower(),
        "candidate_phone": referral_data.candidate_phone,
        "resume_url": referral_data.resume_url,
        "note": referral_data.note,
        "status": "submitted",
        "linked_candidate_id": None,
        "linked_application_id": None,
        "status_history": [{
            "status": "submitted",
            "changed_by": current_user["id"],
            "changed_by_name": current_user["name"],
            "changed_by_role": current_user["role"],
            "timestamp": now,
            "reason": "Referral submitted"
        }],
        "created_at": now,
        "updated_at": now
    }
    
    await db.referrals.insert_one(referral_doc)
    
    logger.info(f"Referral {referral_id} created by {current_user['name']} for job {referral_data.job_id}")
    
    return ReferralResponse(**referral_doc)


@referrals_router.get("/referrals", response_model=List[ReferralResponse])
async def get_referrals(
    job_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Get referrals based on user role.
    - Admin: sees all referrals
    - Employer: sees referrals for their team's jobs
    - Recruiter: sees their own referrals
    """
    query = {}
    
    if current_user["role"] == "recruiter":
        query["referrer_id"] = current_user["id"]
    elif current_user["role"] == "employer":
        # Get jobs from employer's team
        team = await db.teams.find_one({"employer_id": current_user["id"]}, {"_id": 0})
        if team:
            team_jobs = await db.jobs.find({"team_id": team["id"]}, {"id": 1, "_id": 0}).to_list(1000)
            job_ids = [j["id"] for j in team_jobs]
            query["job_id"] = {"$in": job_ids}
        else:
            return []
    
    if job_id:
        query["job_id"] = job_id
    if status:
        query["status"] = status
    
    referrals = await db.referrals.find(query, {"_id": 0}).to_list(1000)
    return [ReferralResponse(**r) for r in referrals]


@referrals_router.get("/referrals/{referral_id}", response_model=ReferralResponse)
async def get_referral(
    referral_id: str,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Get a specific referral by ID."""
    referral = await db.referrals.find_one({"id": referral_id}, {"_id": 0})
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")
    
    # Access control for non-admin users
    if current_user["role"] == "recruiter":
        if referral["referrer_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user["role"] == "employer":
        job = await db.jobs.find_one({"id": referral["job_id"]}, {"_id": 0})
        if job:
            team = await db.teams.find_one({"employer_id": current_user["id"]}, {"_id": 0})
            if not team or job.get("team_id") != team["id"]:
                raise HTTPException(status_code=403, detail="Access denied")
        else:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return ReferralResponse(**referral)


@referrals_router.post("/referrals/{referral_id}/transition", response_model=ReferralResponse)
async def transition_referral_status(
    referral_id: str,
    transition: ReferralStatusUpdate,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Transition referral status with audit logging.
    
    Valid transitions:
    - submitted -> validated, closed
    - validated -> linked, closed
    - linked -> in_process, closed
    - in_process -> outcome_reached, closed
    - outcome_reached -> closed
    - closed -> (no transitions, final state)
    """
    referral = await db.referrals.find_one({"id": referral_id}, {"_id": 0})
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")
    
    current_status = referral.get("status", "submitted")
    new_status = transition.new_status
    
    # Define valid transitions
    valid_transitions = {
        "submitted": ["validated", "closed"],
        "validated": ["linked", "closed"],
        "linked": ["in_process", "closed"],
        "in_process": ["outcome_reached", "closed"],
        "outcome_reached": ["closed"],
        "closed": []
    }
    
    if new_status not in valid_transitions.get(current_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition from {current_status} to {new_status}"
        )
    
    now = datetime.now(timezone.utc).isoformat()
    
    audit_entry = {
        "from_status": current_status,
        "to_status": new_status,
        "changed_by": current_user["id"],
        "changed_by_name": current_user["name"],
        "changed_by_role": current_user["role"],
        "timestamp": now,
        "reason": transition.reason or f"Status changed from {current_status} to {new_status}"
    }
    
    await db.referrals.update_one(
        {"id": referral_id},
        {
            "$set": {"status": new_status, "updated_at": now},
            "$push": {"status_history": audit_entry}
        }
    )
    
    logger.info(f"Referral {referral_id} transitioned from {current_status} to {new_status} by {current_user['name']}")
    
    updated_referral = await db.referrals.find_one({"id": referral_id}, {"_id": 0})
    return ReferralResponse(**updated_referral)


@referrals_router.post("/referrals/{referral_id}/link-candidate")
async def link_referral_to_candidate(
    referral_id: str,
    candidate_id: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Link a referral to an existing candidate bank record, or create a new candidate.
    
    If candidate_id is provided: links to existing candidate
    If not provided: creates new candidate from referral data
    """
    referral = await db.referrals.find_one({"id": referral_id}, {"_id": 0})
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")
    
    if referral.get("status") not in ["submitted", "validated"]:
        raise HTTPException(status_code=400, detail="Can only link referrals in submitted or validated status")
    
    now = datetime.now(timezone.utc).isoformat()
    
    if candidate_id:
        candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
    else:
        candidate_id = str(uuid.uuid4())
        candidate_doc = {
            "id": candidate_id,
            "email": referral["candidate_email"],
            "name": referral["candidate_name"],
            "phone": referral.get("candidate_phone"),
            "phone_normalized": referral.get("candidate_phone"),
            "skills": [],
            "experience_years": 0,
            "experience": [],
            "education": [],
            "resume_url": referral.get("resume_url"),
            "source": "referral",
            "source_referral_id": referral_id,
            "visibility": {
                f"{current_user['role']}_ids": [current_user["id"]]
            },
            "created_at": now,
            "updated_at": now,
            "created_by": current_user["id"]
        }
        await db.candidate_bank.insert_one(candidate_doc)
    
    await db.referrals.update_one(
        {"id": referral_id},
        {
            "$set": {
                "status": "linked",
                "linked_candidate_id": candidate_id,
                "updated_at": now
            },
            "$push": {"status_history": {
                "from_status": referral["status"],
                "to_status": "linked",
                "changed_by": current_user["id"],
                "changed_by_name": current_user["name"],
                "changed_by_role": current_user["role"],
                "timestamp": now,
                "reason": f"Linked to candidate {candidate_id}"
            }}
        }
    )
    
    return {
        "message": "Referral linked to candidate successfully",
        "referral_id": referral_id,
        "candidate_id": candidate_id
    }


# ============== REFERRAL STATISTICS ==============

@referrals_router.get("/referrals/stats/by-job/{job_id}")
async def get_referral_stats_by_job(
    job_id: str,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Get referral statistics for a specific job"""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    pipeline = [
        {"$match": {"job_id": job_id}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1}
        }}
    ]
    
    results = await db.referrals.aggregate(pipeline).to_list(20)
    
    stats = {r["_id"]: r["count"] for r in results}
    total = sum(stats.values())
    
    return {
        "job_id": job_id,
        "job_title": job.get("title"),
        "total_referrals": total,
        "by_status": stats
    }


@referrals_router.get("/referrals/stats/by-referrer")
async def get_referral_stats_by_referrer(
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get referral statistics grouped by referrer (Admin only)"""
    pipeline = [
        {"$group": {
            "_id": {"referrer_id": "$referrer_id", "referrer_name": "$referrer_name"},
            "total": {"$sum": 1},
            "linked": {"$sum": {"$cond": [{"$eq": ["$status", "linked"]}, 1, 0]}},
            "hired": {"$sum": {"$cond": [{"$eq": ["$status", "outcome_reached"]}, 1, 0]}}
        }},
        {"$sort": {"total": -1}},
        {"$limit": 50}
    ]
    
    results = await db.referrals.aggregate(pipeline).to_list(50)
    
    return [
        {
            "referrer_id": r["_id"]["referrer_id"],
            "referrer_name": r["_id"]["referrer_name"],
            "total_referrals": r["total"],
            "linked_count": r["linked"],
            "hired_count": r["hired"],
            "conversion_rate": round(r["hired"] / r["total"] * 100, 1) if r["total"] > 0 else 0
        }
        for r in results
    ]
