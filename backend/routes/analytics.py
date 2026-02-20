"""
VHC Talent OS - Analytics Routes
Admin-only analytics dashboard API + Pipeline conversion + Revenue intelligence.
"""
import io
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from utils.auth import require_role
from services.analytics_service import get_analytics_summary
from services.pipeline_events import STAGE_REVENUE_PROBABILITY, PIPELINE_STAGES
from config import db

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


@analytics_router.get("/admin/export-pdf")
async def export_analytics_pdf(
    employer_id: Optional[str] = None,
    team_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"])),
):
    """Export analytics dashboard as PDF — admin only."""
    data = await get_analytics_summary(
        employer_id=employer_id,
        team_id=team_id,
        recruiter_id=recruiter_id,
        date_from=date_from,
        date_to=date_to,
    )

    from services.analytics_pdf import build_analytics_pdf
    buf = build_analytics_pdf(data, date_from, date_to)

    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    filename = f"VHC_Analytics_{now_str}.pdf"

    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
