"""Branch & Recruiter Revenue dashboard — reads `placement_ledger`.

Shaped exactly like the client's tracker: KPI strip, Branch Summary,
Recruiter Revenue, the placement list and the data-quality review rows.
Admin sees every branch; an employer only ever sees their own team's.
Recruiters never reach this (they see a percentage on their dashboard).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from config import db
from services import branch_revenue as br
from services import targets_service as ts
from utils import require_role

branch_revenue_router = APIRouter(prefix="/api/branch-revenue", tags=["Branch Revenue"])
logger = logging.getLogger(__name__)


def _resolve_period(period_type: str, period: Optional[str]) -> tuple:
    if not period:
        now = ts.ist_today()
        period = {
            "month": now.strftime("%Y-%m"),
            "quarter": f"{now.year}-Q{(now.month - 1) // 3 + 1}",
            "year": str(now.year),
        }[period_type]
    bounds = ts.period_bounds(period_type, period)
    if not bounds:
        raise HTTPException(status_code=400, detail="Bad period. Use 2026-09, 2026-Q3 or 2026.")
    return period, bounds


async def _scope_team_ids(user: dict) -> Optional[list]:
    """None = every branch (Admin + Accounts). A list = the account
    manager's own teams."""
    if user.get("role") in ("admin", "accounts"):
        return None
    return [t["id"] for t in await ts.teams_for_employer(db, user["id"])]


@branch_revenue_router.get("/dashboard")
async def dashboard(
    period_type: str = Query("year", pattern="^(month|quarter|year)$"),
    period: Optional[str] = None,
    branch: Optional[str] = None,
    user: dict = Depends(require_role(["admin", "accounts", "employer"])),
):
    period, (start, end) = _resolve_period(period_type, period)
    team_ids = await _scope_team_ids(user)
    rows = await br.fetch_rows(db, date_from=start, date_to=end, branch=branch, team_ids=team_ids)
    out = br.summarise(rows)

    # Target context for each recruiter row (annual target, pro-rated for
    # the window being viewed) so the table reads like the sheet plus
    # achievement, and matches what the dashboards show.
    year = int(period[:4])
    rec_ids = [r["recruiter_id"] for r in out["recruiters"] if r["recruiter_id"]]
    targets = await ts.get_targets(db, "user", rec_ids, year)
    for r in out["recruiters"]:
        annual = float((targets.get(r["recruiter_id"]) or {}).get("target_amount") or 0)
        p_target = ts.period_target(annual, period_type)
        r["annual_target"] = annual
        r["period_target"] = p_target
        r["achievement_pct"] = ts.pct(r["active"], p_target)

    team_targets = await ts.get_targets(db, "team", [t for t in {r["team_id"] for r in out["recruiters"]} if t], year)
    branch_team = {}
    for r in out["recruiters"]:
        if r["team_id"]:
            branch_team.setdefault(r["branch"], r["team_id"])
    for b in out["branches"]:
        tid = branch_team.get(b["branch"])
        annual = float((team_targets.get(tid) or {}).get("target_amount") or 0)
        b["team_id"] = tid or ""
        b["annual_target"] = annual
        b["period_target"] = ts.period_target(annual, period_type)
        b["achievement_pct"] = ts.pct(b["active"], b["period_target"])

    return {
        "period_type": period_type,
        "period": period,
        "range": {"from": start, "to": end},
        "branch_filter": branch or "",
        "scoped": team_ids is not None,
        **out,
        "data_quality": br.data_quality(rows),
    }


@branch_revenue_router.get("/placements")
async def placements(
    period_type: str = Query("year", pattern="^(month|quarter|year)$"),
    period: Optional[str] = None,
    branch: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    payment_status: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_role(["admin", "accounts", "employer"])),
):
    """The tracker's row-level view (one line per placement)."""
    period, (start, end) = _resolve_period(period_type, period)
    team_ids = await _scope_team_ids(user)
    rows = await br.fetch_rows(db, date_from=start, date_to=end, branch=branch, team_ids=team_ids)
    if recruiter_id:
        rows = [r for r in rows if r.get("recruiter_id") == recruiter_id]
    if payment_status:
        rows = [r for r in rows if r.get("payment_status") == payment_status]
    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in " ".join(str(r.get(k) or "") for k in
                ("candidate_name", "organization", "designation", "recruiter_name",
                 "invoice_no", "location")).lower()]
    return {"items": rows[offset:offset + limit], "count": len(rows),
            "totals": br.totals(rows), "range": {"from": start, "to": end}}


@branch_revenue_router.get("/branches")
async def branches(user: dict = Depends(require_role(["admin", "accounts", "employer"]))):
    team_ids = await _scope_team_ids(user)
    match = {} if team_ids is None else {"team_id": {"$in": team_ids or ["__none__"]}}
    names = await db[br.COLL].distinct("branch", match)
    return {"branches": sorted(n for n in names if n)}
