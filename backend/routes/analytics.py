"""
VHC Talent OS - Analytics Routes
Admin-only analytics dashboard API.
"""
from typing import Optional
from fastapi import APIRouter, Depends
from utils.auth import require_role
from services.analytics_service import get_analytics_summary

analytics_router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@analytics_router.get("/admin")
async def admin_analytics(
    employer_id: Optional[str] = None,
    team_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"])),
):
    """Advanced analytics dashboard data — admin only."""
    return await get_analytics_summary(
        employer_id=employer_id,
        team_id=team_id,
        recruiter_id=recruiter_id,
        date_from=date_from,
        date_to=date_to,
    )
