"""Joining List APIs (employer + admin).

When a recruiter moves a candidate to `joined`, the row appears here so the
team leader can fill in the joining CTC and the revenue generated, then
click "Raise Invoice" — which drops a pre-filled draft bill into the
Bills tab for Accounts/Admin and books the revenue against that
recruiter's target (services/targets_service.py).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import db
from utils import get_current_user
from services.joinings_service import unified_joinings
from services import targets_service as ts

joinings_router = APIRouter(prefix="/api/joinings", tags=["Joinings"])
logger = logging.getLogger(__name__)


async def _scope(user: dict) -> tuple:
    """(recruiter_ids, team_ids) the caller may see. (None, None) = everything.

    Admin and Accounts see every number; an account manager sees only the
    teams they run; recruiters never see rupee values at all.
    """
    role = user.get("role")
    if role in ("admin", "accounts"):
        return None, None
    if role != "employer":
        # Recruiters (team leads included) only ever see percentages, so the
        # rupee-level joining list stays with Admin/Accounts/Employer logins.
        raise HTTPException(status_code=403, detail="The Joining List is available to Admin, Accounts and Employer logins.")
    teams = await ts.teams_for_employer(db, user["id"])
    return list({uid for t in teams for uid in ts.team_member_ids(t)}), [t["id"] for t in teams]


async def _team_of(recruiter_id: str) -> dict:
    """The ONE team a recruiter's revenue belongs to.

    Picking "any matching team" would put a recruiter who sits on two
    teams into whichever came back first, and their revenue would then be
    counted in both team totals. `canonical_team_members` resolves the
    owner the same way the roll-ups do.
    """
    teams = await db.teams.find(
        {**ts.TEAM_LIVE, "$or": [{"recruiter_ids": recruiter_id}, {"team_lead_id": recruiter_id}]},
        {"_id": 0},
    ).to_list(20)
    if not teams:
        return {}
    if len(teams) == 1:
        return teams[0]
    all_teams = await ts.live_teams(db)
    canonical = ts.canonical_team_members(all_teams)
    for t in all_teams:
        if recruiter_id in canonical.get(t["id"], []):
            return t
    return teams[0]


@joinings_router.get("")
async def list_joinings(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    company_id: Optional[str] = None,
    position_q: Optional[str] = None,
    location_q: Optional[str] = None,
    payment_status: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    employee_id: Optional[str] = None,
    team_id: Optional[str] = None,
    limit: int = 500,
    user: dict = Depends(get_current_user),
):
    """Every joining — branch tracker + platform pipeline, merged."""
    recruiter_ids, team_ids = await _scope(user)
    if team_id:
        team = await db.teams.find_one({"id": team_id}, {"_id": 0})
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        members = ts.team_member_ids(team)
        # An employer can only narrow inside their own scope, never widen it.
        recruiter_ids = (
            members if recruiter_ids is None
            else [uid for uid in members if uid in recruiter_ids]
        ) or ["__none__"]
        team_ids = (
            [team_id] if team_ids is None
            else [t for t in team_ids if t == team_id]
        ) or ["__none__"]
    if employee_id:
        if recruiter_ids is not None and employee_id not in recruiter_ids:
            raise HTTPException(status_code=403, detail="That recruiter is not in your team.")
        recruiter_ids = [employee_id]
        team_ids = None
    return await unified_joinings(
        db,
        date_from=date_from, date_to=date_to, company_id=company_id,
        position_q=position_q, location_q=location_q, payment_status=payment_status,
        source=source, q=q, recruiter_ids=recruiter_ids, team_ids=team_ids, limit=limit,
    )


class JoiningUpdate(BaseModel):
    joined_ctc: Optional[float] = None
    revenue: Optional[float] = None
    commercial_rate_pct: Optional[float] = None


async def _load_scoped_application(application_id: str, user: dict) -> dict:
    app = await db.applications.find_one({"id": application_id}, {"_id": 0})
    if not app:
        raise HTTPException(status_code=404, detail="Joining not found")
    recruiter_ids, _ = await _scope(user)
    if recruiter_ids is not None and app.get("created_by") not in recruiter_ids:
        raise HTTPException(status_code=403, detail="That joining belongs to another team.")
    return app


async def _freeze_join_date(app: dict) -> str:
    """Persist the derived joining date the first time a joining is touched.

    Without this, the fallback chain ends at `updated_at` — so saving the
    CTC or raising an invoice would silently move the DOJ to today.
    """
    from services.joinings_service import derive_join_date
    join_date = derive_join_date(app)
    if not app.get("join_date") and join_date:
        await db.applications.update_one({"id": app["id"]}, {"$set": {"join_date": join_date}})
    return join_date


async def _block_if_in_tracker(app: dict) -> None:
    """Refuse to book money on a hire the branch tracker already bills."""
    from services import branch_revenue as br
    row = await br.tracker_row_for_candidate(db, app.get("candidate_name") or "")
    if row:
        looks_like = "" if row.get("match") == "exact" else " (spelled slightly differently)"
        raise HTTPException(
            status_code=409,
            detail=(
                f"{row.get('candidate_name')} is already in the {row.get('branch')} revenue tracker"
                f"{looks_like} — {row.get('payment_status')}, ₹{row.get('revenue'):,.0f}"
                f"{', invoice ' + row['invoice_no'] if row.get('invoice_no') else ''}. "
                "Booking revenue here as well would count it twice — update the tracker instead, "
                "or mark them as different people in Performance Records → Review."
            ),
        )


@joinings_router.patch("/{application_id}")
async def update_joining(application_id: str, payload: JoiningUpdate, user: dict = Depends(get_current_user)):
    """Fill the blanks: joining CTC and the revenue generated. The revenue
    row carries recruiter + join date so target rollups stay cheap."""
    app = await _load_scoped_application(application_id, user)
    if payload.revenue is not None or payload.commercial_rate_pct is not None:
        await _block_if_in_tracker(app)
    now = datetime.now(timezone.utc).isoformat()
    join_date = await _freeze_join_date(app)

    if payload.joined_ctc is not None:
        await db.applications.update_one(
            {"id": application_id},
            {"$set": {"joined_ctc": float(payload.joined_ctc), "updated_at": now}},
        )

    if payload.revenue is not None or payload.commercial_rate_pct is not None:
        team = await _team_of(app.get("created_by") or "")
        set_doc: dict = {"updated_at": now, "recruiter_id": app.get("created_by") or "",
                         "team_id": team.get("id") or "", "join_date": join_date}
        if payload.revenue is not None:
            set_doc["final_revenue"] = float(payload.revenue)
            set_doc["revenue_status"] = "booked"
        if payload.commercial_rate_pct is not None:
            set_doc["commercial_rate_pct"] = float(payload.commercial_rate_pct)
        await db.revenue.update_one(
            {"application_id": application_id},
            {"$set": set_doc,
             "$setOnInsert": {"application_id": application_id, "created_at": now,
                              "created_by": user.get("id")}},
            upsert=True,
        )
    return {"message": "Saved", "application_id": application_id}


class RaiseInvoiceRequest(BaseModel):
    joined_ctc: float
    commercial_rate_pct: float
    sender_variant: Optional[str] = None
    designation: Optional[str] = None
    notes: Optional[str] = None


@joinings_router.post("/{application_id}/raise-invoice")
async def raise_invoice(application_id: str, payload: RaiseInvoiceRequest, user: dict = Depends(get_current_user)):
    """Create a pre-filled DRAFT bill for Accounts/Admin from a joining.

    CTC and commercial rate are entered by the team leader (user choice
    2026-09-17) — nothing is guessed. The resulting line amount is booked
    as that recruiter's revenue for the year.
    """
    app = await _load_scoped_application(application_id, user)
    await _block_if_in_tracker(app)
    existing = await db.revenue.find_one({"application_id": application_id}, {"_id": 0, "bill_id": 1, "bill_number": 1})
    if existing and existing.get("bill_id"):
        raise HTTPException(status_code=409, detail=f"Invoice {existing.get('bill_number')} was already raised for this joining.")

    job = await db.jobs.find_one({"id": app.get("job_id")}, {"_id": 0, "company_id": 1, "title": 1}) or {}
    if not job.get("company_id"):
        raise HTTPException(status_code=400, detail="This joining has no client company on its mandate — cannot raise an invoice.")

    from routes.bills import build_draft_bill
    from models.bill import BillCreate, BillLineItem

    join_date = await _freeze_join_date(app)
    line = BillLineItem(
        candidate_name=app.get("candidate_name") or "",
        designation=payload.designation or app.get("job_title") or job.get("title") or "",
        joining_date=join_date,
        annual_ctc=float(payload.joined_ctc),
        commercial_rate_pct=float(payload.commercial_rate_pct),
    )
    bill = await build_draft_bill(
        BillCreate(
            client_company_id=job["company_id"],
            sender_variant=payload.sender_variant,
            line_items=[line],
            notes=payload.notes,
        ),
        user,
    )
    await db.bills.insert_one(dict(bill))
    bill.pop("_id", None)

    line_amount = float(bill["line_items"][0]["line_amount"])
    team = await _team_of(app.get("created_by") or "")
    now = datetime.now(timezone.utc).isoformat()
    await db.applications.update_one(
        {"id": application_id},
        {"$set": {"joined_ctc": float(payload.joined_ctc), "updated_at": now}},
    )
    await db.revenue.update_one(
        {"application_id": application_id},
        {"$set": {
            "final_revenue": line_amount,
            "commercial_rate_pct": float(payload.commercial_rate_pct),
            "revenue_status": "invoiced",
            "recruiter_id": app.get("created_by") or "",
            "team_id": team.get("id") or "",
            "join_date": join_date,
            "bill_id": bill["id"],
            "bill_number": bill["bill_number"],
            "updated_at": now,
        },
         "$setOnInsert": {"application_id": application_id, "created_at": now, "created_by": user.get("id")}},
        upsert=True,
    )
    return {
        "message": "Invoice draft created",
        "bill_id": bill["id"],
        "bill_number": bill["bill_number"],
        "revenue_booked": line_amount,
    }
