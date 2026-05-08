"""Admin endpoints for recruiter performance reports — manual trigger + preview."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
import io

from utils.auth import require_role
from services.reports_service import (
    aggregate_daily,
    aggregate_weekly,
    build_daily_excel,
    build_weekly_excel,
    compute_daily_window,
    compute_weekly_window,
    generate_and_send_daily_reports,
    generate_and_send_weekly_reports,
)

router = APIRouter(prefix="/api/reports", tags=["Reports"])


async def get_db():
    from config import db
    return db


@router.post("/daily/run-now")
async def run_daily_now(
    db=Depends(get_db),
    user=Depends(require_role(["admin", "employer"])),
):
    """Manually trigger the daily report pipeline right now."""
    result = await generate_and_send_daily_reports(db)
    return {"triggered": "daily", **result}


@router.post("/weekly/run-now")
async def run_weekly_now(
    db=Depends(get_db),
    user=Depends(require_role(["admin", "employer"])),
):
    """Manually trigger the weekly report pipeline right now."""
    result = await generate_and_send_weekly_reports(db)
    return {"triggered": "weekly", **result}


@router.get("/daily/preview/{team_id}")
async def preview_daily_excel(
    team_id: str,
    db=Depends(get_db),
    user=Depends(require_role(["admin", "employer"])),
):
    """Download the Excel a specific team would receive tonight (no email sent)."""
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(404, f"Team {team_id} not found")
    start_iso, end_iso, label = compute_daily_window()
    rows = await aggregate_daily(db, team.get("recruiter_ids") or [], start_iso, end_iso)
    xlsx = build_daily_excel(team.get("name") or "Team", label, rows)
    return StreamingResponse(
        io.BytesIO(xlsx),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Daily_Preview_{team_id}.xlsx"'},
    )


@router.get("/weekly/preview/{team_id}")
async def preview_weekly_excel(
    team_id: str,
    db=Depends(get_db),
    user=Depends(require_role(["admin", "employer"])),
):
    """Download the Excel a specific team would receive Monday (no email sent)."""
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(404, f"Team {team_id} not found")
    start_iso, end_iso, label = compute_weekly_window()
    per_rec = await aggregate_weekly(db, team.get("recruiter_ids") or [], start_iso, end_iso)
    xlsx = build_weekly_excel(team.get("name") or "Team", label, per_rec)
    return StreamingResponse(
        io.BytesIO(xlsx),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Weekly_Preview_{team_id}.xlsx"'},
    )


@router.get("/dispatches")
async def list_dispatches(
    limit: int = Query(50, ge=1, le=500),
    report_type: str = Query("", description="Filter by 'daily' or 'weekly' (empty = all)"),
    db=Depends(get_db),
    user=Depends(require_role(["admin", "employer"])),
):
    """Audit log — last N report emails sent."""
    q = {}
    if report_type in ("daily", "weekly"):
        q["type"] = report_type
    rows = await db.report_dispatches.find(q, {"_id": 0}).sort("sent_at", -1).limit(limit).to_list(limit)
    return {"dispatches": rows, "count": len(rows)}
