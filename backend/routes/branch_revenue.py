"""Branch & Recruiter Revenue dashboard — reads `placement_ledger`.

Shaped exactly like the client's tracker: KPI strip, Branch Summary,
Recruiter Revenue, the placement list and the data-quality review rows.
Admin sees every branch; an employer only ever sees their own team's.
Recruiters never reach this (they see a percentage on their dashboard).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

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


class PlacementPatch(BaseModel):
    """Manual resolution of a tracker row. Every field is optional — send
    only what changed."""
    recruiter_id: Optional[str] = None
    revenue: Optional[float] = None
    payment_status: Optional[str] = None
    invoice_no: Optional[str] = None
    payment_date: Optional[str] = None
    note: Optional[str] = None
    dismiss_review: Optional[bool] = None


async def _editable_row(placement_id: str, user: dict) -> dict:
    row = await db[br.COLL].find_one({"id": placement_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Placement not found")
    team_ids = await _scope_team_ids(user)
    if team_ids is not None and row.get("team_id") not in team_ids:
        raise HTTPException(status_code=403, detail="That placement belongs to another branch.")
    return row


@branch_revenue_router.patch("/placements/{placement_id}")
async def update_placement(placement_id: str, payload: PlacementPatch,
                           user: dict = Depends(require_role(["admin", "accounts", "employer"]))):
    """Resolve a flagged row or move a payment along.

    Changing the recruiter moves the revenue to that person (and to their
    team); changing the status moves it between the collected / pending /
    written-off buckets. Every edit is logged — these are money fields.
    """
    row = await _editable_row(placement_id, user)
    changes: dict = {}
    set_doc: dict = {}

    if payload.payment_status is not None:
        if payload.payment_status not in br.BUCKET:
            raise HTTPException(status_code=400, detail=f"Unknown payment status. Use one of: {', '.join(br.BUCKET)}")
        set_doc["payment_status"] = payload.payment_status
        set_doc["payment_status_raw"] = payload.payment_status
        changes["payment_status"] = [row.get("payment_status"), payload.payment_status]
        if payload.payment_status == "Payment Received":
            # The client asked to capture when the money landed.
            set_doc["payment_date"] = (payload.payment_date or ts.ist_today().date().isoformat())[:10]
            changes["payment_date"] = [row.get("payment_date"), set_doc["payment_date"]]
    elif payload.payment_date is not None:
        set_doc["payment_date"] = payload.payment_date[:10]
        changes["payment_date"] = [row.get("payment_date"), payload.payment_date]

    if payload.revenue is not None:
        set_doc["revenue"] = round(float(payload.revenue), 2)
        changes["revenue"] = [row.get("revenue"), set_doc["revenue"]]

    if payload.invoice_no is not None:
        set_doc["invoice_no"] = payload.invoice_no.strip()
        changes["invoice_no"] = [row.get("invoice_no"), set_doc["invoice_no"]]

    if payload.recruiter_id is not None:
        if payload.recruiter_id:
            owner = await db.users.find_one(
                {"id": payload.recruiter_id, "is_active": True}, {"_id": 0, "id": 1, "name": 1, "email": 1})
            if not owner:
                raise HTTPException(status_code=400, detail="That recruiter does not exist or is inactive.")
            team = next((t for t in await ts.live_teams(db)
                         if payload.recruiter_id in ts.team_member_ids(t)), None)
            if team_ids := await _scope_team_ids(user):
                if not team or team["id"] not in team_ids:
                    raise HTTPException(status_code=403, detail="You can only assign a placement to your own team.")
            set_doc.update({
                "recruiter_id": owner["id"],
                "recruiter_name": owner.get("name") or owner.get("email"),
                "unassigned": False,
                "is_ex_employee": False,
                # Revenue follows the person, so the team follows too.
                "team_id": (team or {}).get("id") or row.get("team_id") or "",
            })
            changes["recruiter"] = [row.get("recruiter_name"), set_doc["recruiter_name"]]
        else:
            set_doc.update({"recruiter_id": "", "recruiter_name": "Ex-employee / Unassigned",
                            "unassigned": True})
            changes["recruiter"] = [row.get("recruiter_name"), "Ex-employee / Unassigned"]

    if payload.dismiss_review or changes:
        set_doc["review_resolved"] = True
        set_doc["review_resolved_at"] = datetime.now(timezone.utc).isoformat()
        set_doc["review_resolved_by"] = user.get("email") or user.get("id")
    if payload.note:
        set_doc["resolution_note"] = payload.note

    if not set_doc:
        raise HTTPException(status_code=400, detail="Nothing to change.")

    await db[br.COLL].update_one({"id": placement_id}, {
        "$set": set_doc,
        "$push": {"edits": {
            "at": datetime.now(timezone.utc).isoformat(),
            "by": user.get("email") or user.get("id"),
            "role": user.get("role"),
            "changes": changes,
            "note": payload.note or "",
        }},
    })
    return {"message": "Updated", "id": placement_id, "changes": changes,
            "row": await db[br.COLL].find_one({"id": placement_id}, {"_id": 0})}


@branch_revenue_router.get("/assignable-recruiters")
async def assignable_recruiters(user: dict = Depends(require_role(["admin", "accounts", "employer"]))):
    """People a flagged placement can be credited to — the whole roster for
    Admin/Accounts, only their own team for an account manager."""
    teams = await ts.live_teams(db) if user.get("role") in ("admin", "accounts") \
        else await ts.teams_for_employer(db, user["id"])
    ids = list({uid for t in teams for uid in ts.team_member_ids(t)})
    people = await db.users.find(
        {"id": {"$in": ids}, "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1},
    ).to_list(500)
    people.sort(key=lambda u: (u.get("name") or u.get("email") or "").lower())
    return {"items": people}


@branch_revenue_router.get("/reconcile")
async def reconcile(year: Optional[int] = None,
                    user: dict = Depends(require_role(["admin", "accounts"]))):
    """Re-derives every revenue figure from a different direction and
    compares — proof that the dashboards, targets and Joining List agree."""
    from services.revenue_reconcile import reconcile as run
    return await run(db, year or ts.current_year())


@branch_revenue_router.get("/branches")
async def branches(user: dict = Depends(require_role(["admin", "accounts", "employer"]))):
    team_ids = await _scope_team_ids(user)
    match = {} if team_ids is None else {"team_id": {"$in": team_ids or ["__none__"]}}
    names = await db[br.COLL].distinct("branch", match)
    return {"branches": sorted(n for n in names if n)}
