"""
Team Lead — grant / revoke acting-employer access to a recruiter.

A "Team Lead" is a recruiter promoted by their employer (or an admin) so they can
run day-to-day operations on the employer's behalf: view team, assign mandates,
create/edit jobs — with confidential financial data masked.

Endpoints:
  POST /api/team-lead/grant   {recruiter_id, employer_id}   [admin | that employer]
  POST /api/team-lead/revoke  {recruiter_id}                [admin | that employer]
  GET  /api/team-lead/scope                                 [team lead]
  GET  /api/team-lead/team-leads/{employer_id}              [admin | that employer]
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import db
from utils import get_current_user, require_role

team_lead_router = APIRouter(prefix="/api/team-lead", tags=["Team Lead"])


class GrantRequest(BaseModel):
    recruiter_id: str
    employer_id: Optional[str] = None  # optional — defaults to current employer


class RevokeRequest(BaseModel):
    recruiter_id: str


async def _assert_can_manage(current_user: dict, employer_id: str):
    """Only the employer of the team OR an admin can grant/revoke."""
    if current_user["role"] == "admin":
        return
    if current_user["role"] == "employer" and current_user["id"] == employer_id:
        return
    raise HTTPException(status_code=403, detail="Only the employer or an admin can manage Team Leads")


async def _assert_recruiter_in_team(recruiter_id: str, employer_id: str):
    """The recruiter must be in the employer's active team."""
    team = await db.teams.find_one(
        {"employer_id": employer_id, "status": "active"}, {"_id": 0}
    )
    if not team:
        raise HTTPException(status_code=400, detail="Employer has no active team")
    if recruiter_id not in team.get("recruiter_ids", []):
        raise HTTPException(status_code=400, detail="Recruiter is not in this employer's team")


@team_lead_router.post("/grant")
async def grant_team_lead(req: GrantRequest, current_user: dict = Depends(get_current_user)):
    """Grant Team Lead access to a recruiter under an employer."""
    # Default employer_id to current user if they're an employer
    employer_id = req.employer_id or (current_user["id"] if current_user["role"] == "employer" else None)
    if not employer_id:
        raise HTTPException(status_code=400, detail="employer_id is required")

    await _assert_can_manage(current_user, employer_id)

    recruiter = await db.users.find_one({"id": req.recruiter_id, "role": "recruiter", "is_active": True})
    if not recruiter:
        raise HTTPException(status_code=404, detail="Recruiter not found")

    await _assert_recruiter_in_team(req.recruiter_id, employer_id)

    employer = await db.users.find_one({"id": employer_id, "role": "employer"}, {"_id": 0, "name": 1})
    now = datetime.now(timezone.utc).isoformat()

    await db.users.update_one(
        {"id": req.recruiter_id},
        {"$set": {
            "is_team_lead": True,
            "team_lead_employer_id": employer_id,
            "team_lead_granted_at": now,
            "team_lead_granted_by": current_user["id"],
        }},
    )

    # Invalidate cached snapshot so the recruiter's next request sees the new flag.
    from utils.auth import invalidate_user_cache
    invalidate_user_cache(req.recruiter_id)

    return {
        "success": True,
        "message": f"{recruiter.get('name', 'Recruiter')} is now a Team Lead for {employer.get('name', 'the employer') if employer else 'the employer'}",
        "recruiter_id": req.recruiter_id,
        "employer_id": employer_id,
        "granted_at": now,
    }


@team_lead_router.post("/revoke")
async def revoke_team_lead(req: RevokeRequest, current_user: dict = Depends(get_current_user)):
    """Revoke Team Lead access. Callable by admin or the employer who granted it."""
    recruiter = await db.users.find_one({"id": req.recruiter_id})
    if not recruiter:
        raise HTTPException(status_code=404, detail="Recruiter not found")
    if not recruiter.get("is_team_lead"):
        return {"success": True, "message": "Recruiter is not a Team Lead", "recruiter_id": req.recruiter_id}

    employer_id = recruiter.get("team_lead_employer_id")
    if employer_id:
        await _assert_can_manage(current_user, employer_id)
    elif current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can revoke — employer scope missing")

    await db.users.update_one(
        {"id": req.recruiter_id},
        {"$set": {
            "is_team_lead": False,
            "team_lead_employer_id": None,
            "team_lead_revoked_at": datetime.now(timezone.utc).isoformat(),
            "team_lead_revoked_by": current_user["id"],
        }},
    )

    from utils.auth import invalidate_user_cache
    invalidate_user_cache(req.recruiter_id)

    return {
        "success": True,
        "message": f"{recruiter.get('name', 'Recruiter')} is no longer a Team Lead",
        "recruiter_id": req.recruiter_id,
    }


@team_lead_router.get("/scope")
async def get_scope(current_user: dict = Depends(get_current_user)):
    """Return the Team Lead's employer scope (used by frontend to show 'Acting as XYZ')."""
    if not current_user.get("is_team_lead"):
        return {"is_team_lead": False, "employer_id": None, "employer_name": None}

    employer_id = current_user.get("team_lead_employer_id")
    employer = await db.users.find_one({"id": employer_id}, {"_id": 0, "name": 1}) if employer_id else None
    return {
        "is_team_lead": True,
        "employer_id": employer_id,
        "employer_name": employer.get("name") if employer else None,
    }


@team_lead_router.get("/list/{employer_id}")
async def list_team_leads(employer_id: str, current_user: dict = Depends(get_current_user)):
    """List all Team Leads under a specific employer."""
    await _assert_can_manage(current_user, employer_id)
    leads = await db.users.find(
        {"role": "recruiter", "is_team_lead": True, "team_lead_employer_id": employer_id, "is_active": True},
        {"_id": 0, "password": 0},
    ).to_list(200)
    return {"success": True, "team_leads": leads, "count": len(leads)}
