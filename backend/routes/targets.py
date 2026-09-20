"""Revenue targets & achievement APIs.

Who sees what (user-confirmed 2026-09-17):
  • recruiter → `GET /api/targets/me` — percentage only, no amounts.
  • employer  → their own team(s): set member targets, see target/achieved.
  • admin     → every team + the company rollup, set team targets.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from config import db
from utils import get_current_user
from services import targets_service as ts

targets_router = APIRouter(prefix="/api/targets", tags=["Targets"])
logger = logging.getLogger(__name__)


async def _visible_teams(user: dict) -> List[dict]:
    """Teams the caller may read/manage."""
    role = user.get("role")
    if role in ("admin", "accounts"):
        return await ts.live_teams(db)
    if role == "employer":
        return await ts.teams_for_employer(db, user["id"])
    return []


async def _require_manager(user: dict = Depends(get_current_user)) -> dict:
    """Rupee-level target data is Admin + Employer only.

    Team-lead recruiters are deliberately excluded: the rule is that a
    recruiter only ever sees a percentage (`GET /api/targets/me`).
    """
    if user.get("role") in ("admin", "accounts", "employer"):
        return user
    raise HTTPException(status_code=403, detail="Revenue targets are managed by Admin, Accounts and Employer logins.")


class TargetUpsert(BaseModel):
    scope: str            # "user" | "team"
    scope_id: str
    year: Optional[int] = None
    target_amount: Optional[float] = None
    opening_achieved: Optional[float] = None


@targets_router.get("/me")
async def my_target(year: Optional[int] = None, user: dict = Depends(get_current_user)):
    """Recruiter dashboard box — percentage only, by design."""
    return await ts.my_achievement_pct(db, user["id"], year or ts.current_year())


@targets_router.put("")
async def upsert_target(payload: TargetUpsert, user: dict = Depends(_require_manager)):
    year = payload.year or ts.current_year()
    if payload.scope not in ("user", "team"):
        raise HTTPException(status_code=400, detail="scope must be 'user' or 'team'")

    if user.get("role") == "accounts":
        raise HTTPException(status_code=403, detail="Accounts has read-only access to targets.")

    if payload.scope == "team" and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only Admin can set a team-level target.")

    if payload.scope == "user" and user.get("role") != "admin":
        teams = await _visible_teams(user)
        allowed = {uid for t in teams for uid in ts.team_member_ids(t)}
        if payload.scope_id not in allowed:
            raise HTTPException(status_code=403, detail="That user is not in your team.")

    doc = await ts.upsert_target(
        db, payload.scope, payload.scope_id, year,
        payload.target_amount, payload.opening_achieved, user,
    )
    return doc


@targets_router.get("/team-summary")
async def team_summary(
    team_id: Optional[str] = None,
    year: Optional[int] = None,
    user: dict = Depends(_require_manager),
):
    """Employer / team-lead view: each member's target vs achieved + team total."""
    year = year or ts.current_year()
    teams = await _visible_teams(user)
    if team_id:
        teams = [t for t in teams if t["id"] == team_id]
        if not teams:
            raise HTTPException(status_code=404, detail="Team not found for this user")
    if not teams:
        return {"year": year, "teams": [], "total_target": 0, "total_achieved": 0, "achievement_pct": 0}

    rows = [await ts.team_summary(db, t, year) for t in teams]
    total_target = round(sum(r["target_amount"] for r in rows), 2)
    total_achieved = round(sum(r["achieved"] for r in rows), 2)
    return {
        "year": year,
        "teams": rows,
        "total_target": total_target,
        "total_achieved": total_achieved,
        "achievement_pct": ts.pct(total_achieved, total_target),
        "total_joinings": sum(r["joinings"] for r in rows),
    }


@targets_router.get("/company-summary")
async def company_summary(year: Optional[int] = None, user: dict = Depends(get_current_user)):
    """Admin + Accounts view: all teams cumulated into the company number."""
    if user.get("role") not in ("admin", "accounts"):
        raise HTTPException(status_code=403, detail="Admin and Accounts only")
    return await ts.company_summary(db, year or ts.current_year())


@targets_router.get("/years")
async def target_years(user: dict = Depends(_require_manager)):
    years = await db[ts.TARGETS].distinct("year")
    cy = ts.current_year()
    return {"years": sorted({*years, cy, cy - 1}, reverse=True), "current_year": cy}
