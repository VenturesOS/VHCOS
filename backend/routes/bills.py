"""Bills (Invoices) routes — Phase 55.6 (May 2026).

Provides CRUD + render-PDF + send + manual-reminder + list endpoints.

ACL: Admin, Employer, and account-manager recruiters (`is_account_manager`)
can list/view/create/edit/preview/send their own bills. Admin sees all.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse

from config import db
from models.bill import (
    BankAccountCreate,
    BankAccountUpdate,
    BillBankSnapshot,
    BillCreate,
    BillLineItem,
    BillRecord,
    BillSend,
    BillUpdate,
    ConsolidatedInvoiceRequest,
)
from services.bill_llm_body import generate_send_body, plain_to_html
from services.bill_mailer import build_cc_list, send_bill_email
from services.bill_pdf import amount_to_words, render_bill_pdf
from utils.auth import get_current_user

logger = logging.getLogger(__name__)

bills_router = APIRouter(prefix="/api", tags=["bills"])


# ──────────────────────────────────────────────────────────────────────
# ACL helper
# ──────────────────────────────────────────────────────────────────────
async def _require_billing_role(current_user: dict = Depends(get_current_user)) -> dict:
    role = (current_user or {}).get("role")
    if role in ("admin", "employer", "accounts"):
        return current_user
    if role == "recruiter" and current_user.get("is_account_manager"):
        return current_user
    raise HTTPException(status_code=403, detail="Bills are accessible to Admin, Employer, Accounts or Account-Manager recruiters only.")


# ──────────────────────────────────────────────────────────────────────
# Sender variants — frozen at creation time
# ──────────────────────────────────────────────────────────────────────
# Both entities share one registered office (user-confirmed 2026-09-17).
_SENDER_ADDRESS = (
    "Second Floor, D-12/79-80, Rohini, Rohini Sector 8, "
    "New Delhi, North West Delhi, Delhi, 110085"
)

_SENDER_PRESETS = {
    "VENTURE HRD CENTER": {
        "legal_name": "VENTURE HRD CENTER",
        "address": _SENDER_ADDRESS,
        "gstin": os.environ.get("BILLING_SENDER_GSTIN") or "07AAMPY9883D2ZT",
        "pan": os.environ.get("BILLING_SENDER_PAN") or "AAMPY9883D",
        "state_code": "07",
        "logo_url": os.environ.get("BILLING_SENDER_LOGO_URL") or "",
    },
    "VENTURES HRD PVT LTD": {
        "legal_name": "Ventures HRD Pvt Ltd",
        "address": _SENDER_ADDRESS,
        "gstin": os.environ.get("BILLING_SENDER_PVT_GSTIN") or "07AACCV6268J1ZW",
        "pan": os.environ.get("BILLING_SENDER_PVT_PAN") or "AACCV6268J",
        "state_code": "07",
        "logo_url": os.environ.get("BILLING_SENDER_PVT_LOGO_URL") or "",
    },
}

# Legacy spellings stored on older drafts still resolve.
_SENDER_ALIASES = {
    "VENTURE HRD CENTRE": "VENTURE HRD CENTER",
    "VENTURE HRD CENTRE PVT LTD": "VENTURES HRD PVT LTD",
    "VENTURE HRD CENTER PVT LTD": "VENTURES HRD PVT LTD",
    "VENTURES HRD PVT. LTD.": "VENTURES HRD PVT LTD",
}


def _resolve_sender(variant: Optional[str]) -> dict:
    key = (variant or "VENTURE HRD CENTER").upper().strip()
    key = _SENDER_ALIASES.get(key, key)
    return _SENDER_PRESETS.get(key, _SENDER_PRESETS["VENTURE HRD CENTER"])


def _state_code_from_gstin(gstin: str) -> str:
    return (gstin or "")[:2].zfill(2)


# ──────────────────────────────────────────────────────────────────────
# Bill number — auto-increment per Indian FY (Apr–Mar)
# ──────────────────────────────────────────────────────────────────────
def _fy_code(d: datetime) -> str:
    """26-27 for any date between Apr-2026 and Mar-2027."""
    yr = d.year
    if d.month < 4:
        start = yr - 1
        end = yr
    else:
        start = yr
        end = yr + 1
    return f"{str(start)[-2:]}-{str(end)[-2:]}"


async def _next_bill_number(now: datetime) -> str:
    fy = _fy_code(now)
    pipeline = [
        {"$match": {"bill_number": {"$regex": f"^VHC/{fy}/"}}},
        {"$project": {"_id": 0, "n": {"$toInt": {"$arrayElemAt": [{"$split": ["$bill_number", "/"]}, 2]}}}},
        {"$sort": {"n": -1}},
        {"$limit": 1},
    ]
    rows = await db.bills.aggregate(pipeline).to_list(1)
    last = rows[0]["n"] if rows else 0
    return f"VHC/{fy}/{last + 1}"


# ──────────────────────────────────────────────────────────────────────
# Totals helper
# ──────────────────────────────────────────────────────────────────────
def _round2(x: float) -> float:
    return round(float(x or 0) + 1e-9, 2)


def _build_totals(line_items: List[dict], gst_kind: str) -> dict:
    taxable = _round2(sum(li.get("line_amount", 0) for li in line_items))
    if gst_kind == "IGST":
        tax_total = _round2(taxable * 0.18)
    else:
        # CGST 9 + SGST 9 = 18% overall
        tax_total = _round2(taxable * 0.18)
    grand = _round2(taxable + tax_total)
    return {
        "taxable_value": taxable,
        "gst_kind": gst_kind,
        "igst_pct": 18.0 if gst_kind == "IGST" else 0,
        "cgst_pct": 0 if gst_kind == "IGST" else 9.0,
        "sgst_pct": 0 if gst_kind == "IGST" else 9.0,
        "tax_total": tax_total,
        "grand_total": grand,
        "amount_in_words": amount_to_words(grand),
        "tax_in_words": amount_to_words(tax_total),
    }


# ──────────────────────────────────────────────────────────────────────
# Bank accounts (fix.docx 2026-09-15) — admin CRUD, snapshot per-bill.
# ──────────────────────────────────────────────────────────────────────
@bills_router.get("/bills/bank-accounts")
async def list_bank_accounts(user: dict = Depends(_require_billing_role)):
    """Return every configured bank account, default first, then alphabetical."""
    rows = await db.bill_bank_accounts.find({}, {"_id": 0}).to_list(200)
    rows.sort(key=lambda r: (not r.get("is_default"), (r.get("label") or "").lower()))
    return {"items": rows}


@bills_router.post("/bills/bank-accounts")
async def create_bank_account(payload: BankAccountCreate, user: dict = Depends(_require_billing_role)):
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = now
    if doc.get("is_default"):
        # Only one default at a time.
        await db.bill_bank_accounts.update_many({}, {"$set": {"is_default": False}})
    await db.bill_bank_accounts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@bills_router.put("/bills/bank-accounts/{account_id}")
async def update_bank_account(
    account_id: str,
    payload: BankAccountUpdate,
    user: dict = Depends(_require_billing_role),
):
    upd = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not upd:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    if upd.get("is_default") is True:
        await db.bill_bank_accounts.update_many({}, {"$set": {"is_default": False}})
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.bill_bank_accounts.update_one({"id": account_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Bank account not found.")
    doc = await db.bill_bank_accounts.find_one({"id": account_id}, {"_id": 0})
    return doc


@bills_router.delete("/bills/bank-accounts/{account_id}")
async def delete_bank_account(account_id: str, user: dict = Depends(_require_billing_role)):
    res = await db.bill_bank_accounts.delete_one({"id": account_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bank account not found.")
    return {"message": "Deleted", "id": account_id}


async def _resolve_bank_snapshot(bank_account_id: Optional[str]) -> Optional[dict]:
    """Load a bank account (given id, or the default) and return the
    subset of fields we snapshot onto a bill."""
    q = {"id": bank_account_id} if bank_account_id else {"is_default": True}
    doc = await db.bill_bank_accounts.find_one(q, {"_id": 0})
    if not doc and bank_account_id:
        raise HTTPException(status_code=404, detail=f"Bank account {bank_account_id} not found.")
    if not doc and not bank_account_id:
        # No account flagged default — use the only/first saved one so the
        # payment block still prints.
        doc = await db.bill_bank_accounts.find_one({}, {"_id": 0})
    if not doc:
        return None
    return {
        "bank_account_id":  doc.get("id"),
        "bank_name":        doc.get("bank_name", ""),
        "beneficiary_name": doc.get("beneficiary_name", ""),
        "branch":           doc.get("branch", ""),
        "account_number":   doc.get("account_number", ""),
        "ifsc":             doc.get("ifsc", ""),
    }


# ──────────────────────────────────────────────────────────────────────
# CRUD
# ──────────────────────────────────────────────────────────────────────
@bills_router.post("/bills")
async def create_bill(payload: BillCreate, user: dict = Depends(_require_billing_role)):
    """Create a draft bill from line items + client company id."""
    bill = await build_draft_bill(payload, user)
    await db.bills.insert_one(dict(bill))
    bill.pop("_id", None)
    return bill


async def build_draft_bill(payload: BillCreate, user: dict) -> dict:
    """Build (but don't insert) a draft bill document.

    Shared with the employer Joining List "Raise Invoice" action so a
    joining-sourced invoice is identical to a hand-made one.
    """
    company = await db.companies.find_one({"id": payload.client_company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Client company not found")

    sender = _resolve_sender(payload.sender_variant)
    client_state = _state_code_from_gstin(company.get("gstin") or "")
    gst_kind = payload.gst_kind or ("CGST_SGST" if client_state == sender["state_code"] else "IGST")

    # Lock line amounts to the user's submitted values, BUT recompute from CTC+% if missing
    line_items = []
    for li in payload.line_items:
        amt = li.line_amount
        if amt is None or amt <= 0:
            amt = _round2(li.annual_ctc * (li.commercial_rate_pct or 0) / 100.0)
        d = li.model_dump()
        d["line_amount"] = _round2(amt)
        line_items.append(d)

    totals = _build_totals(line_items, gst_kind)
    now = datetime.now(timezone.utc)
    bank_snapshot = await _resolve_bank_snapshot(payload.bank_account_id)

    bill = {
        "id": str(uuid.uuid4()),
        "bill_number": await _next_bill_number(now),
        "bill_date": (payload.bill_date or now.date().isoformat()),
        "due_date": payload.due_date,
        "sender_legal_name": sender["legal_name"],
        "sender_address": sender["address"],
        "sender_gstin": sender["gstin"],
        "sender_pan": sender["pan"],
        "sender_state_code": sender["state_code"],
        "sender_logo_url": sender.get("logo_url") or "",
        "client_company_id": company.get("id"),
        "client_legal_name": company.get("legal_name") or company.get("name") or "",
        "client_address": company.get("billing_address") or company.get("address") or "",
        "client_gstin": company.get("gstin") or "",
        "client_state_code": client_state,
        "client_billing_email": company.get("billing_email") or company.get("primary_email") or "",
        "line_items": line_items,
        "totals": totals,
        "bank_account": bank_snapshot,
        "status": "draft",
        "reminders_enabled": True,
        "reminder_schedule_days": [7, 14, 30],
        "reminders_sent": [],
        "mail_events": [],
        "cc_emails": [],
        "bcc_emails": [],
        "created_by": user.get("id"),
        "created_by_email": user.get("email"),
        "created_at": now.isoformat(),
    }
    return bill


@bills_router.get("/bills")
async def list_bills(
    status: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(_require_billing_role),
):
    q: dict = {}
    if status:
        q["status"] = status
    # Employers see only their own company's bills; admins see all.
    if user.get("role") == "employer":
        # Find companies this employer manages
        cur = db.companies.find({"assigned_employer_id": user["id"]}, {"_id": 0, "id": 1})
        ids = [c["id"] async for c in cur]
        q["client_company_id"] = {"$in": ids} if ids else "__none__"
    rows = []
    async for r in db.bills.find(q, {"_id": 0}).sort("created_at", -1).limit(limit):
        rows.append(r)
    return {"items": rows, "count": len(rows)}


@bills_router.post("/bills/consolidated-invoice")
async def consolidated_invoice(payload: ConsolidatedInvoiceRequest,
                               user: dict = Depends(_require_billing_role)):
    """One invoice for several candidates of the same client.

    Six people joining the same client in a month used to mean six invoices
    and six payments to chase. Billed together, the client gets one document
    and marking it paid clears every candidate on it in one go.
    """
    from routes.joinings import book_joining_revenue, load_joining_for_invoice
    from services import branch_revenue as br

    lines: List[BillLineItem] = []
    joinings: List[tuple] = []      # (application, line index, rate, ctc)
    placements: List[str] = []
    company_ids: set = set()
    if payload.client_company_id:
        company_ids.add(payload.client_company_id)

    for item in payload.items:
        if item.application_id:
            app, job, join_date = await load_joining_for_invoice(item.application_id, user)
            if not item.line_amount and not (item.annual_ctc and item.commercial_rate_pct):
                raise HTTPException(
                    status_code=400,
                    detail=f"{app.get('candidate_name')}: enter the CTC and commercial rate (or a line amount).")
            company_ids.add(job["company_id"])
            lines.append(BillLineItem(
                candidate_name=app.get("candidate_name") or "",
                designation=item.designation or app.get("job_title") or job.get("title") or "",
                joining_date=join_date,
                annual_ctc=float(item.annual_ctc or 0),
                commercial_rate_pct=float(item.commercial_rate_pct or 0),
                line_amount=item.line_amount,
                application_id=item.application_id,
            ))
            joinings.append((app, len(lines) - 1, float(item.commercial_rate_pct or 0),
                             float(item.annual_ctc or 0), join_date))
        elif item.placement_id:
            row = await db[br.COLL].find_one({"id": item.placement_id, "void": {"$ne": True}}, {"_id": 0})
            if not row:
                raise HTTPException(status_code=404, detail="Placement not found")
            if row.get("invoice_no"):
                raise HTTPException(
                    status_code=409,
                    detail=f"{row.get('candidate_name')} already carries invoice {row['invoice_no']}.")
            company = await db.companies.find_one(
                {"$or": [{"name": row.get("organization")}, {"legal_name": row.get("organization")}]},
                {"_id": 0, "id": 1})
            if not company and not payload.client_company_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"No client company named '{row.get('organization')}' — add it under Companies first, "
                           "or pick the client explicitly.")
            company_ids.add((company or {}).get("id") or payload.client_company_id)
            lines.append(BillLineItem(
                candidate_name=row.get("candidate_name") or "",
                designation=item.designation or row.get("designation") or "",
                joining_date=row.get("doj") or "",
                annual_ctc=float(item.annual_ctc or row.get("offered_ctc") or 0),
                commercial_rate_pct=float(item.commercial_rate_pct or 0),
                line_amount=item.line_amount if item.line_amount is not None else float(row.get("revenue") or 0),
                placement_id=item.placement_id,
            ))
            placements.append(item.placement_id)
        else:
            raise HTTPException(status_code=400, detail="Each item needs an application_id or a placement_id.")

    company_ids.discard(None)
    if len(company_ids) != 1:
        raise HTTPException(
            status_code=400,
            detail="All candidates on one invoice must belong to the same client. "
                   "Raise separate invoices per client.")

    bill = await build_draft_bill(
        BillCreate(
            client_company_id=company_ids.pop(),
            sender_variant=payload.sender_variant,
            gst_kind=payload.gst_kind,
            bank_account_id=payload.bank_account_id,
            bill_date=payload.bill_date,
            due_date=payload.due_date,
            line_items=lines,
            notes=payload.notes,
        ),
        user,
    )
    await db.bills.insert_one(dict(bill))
    bill.pop("_id", None)

    # Book each candidate's revenue against the same invoice
    for app, idx, rate, ctc, join_date in joinings:
        await book_joining_revenue(
            app, bill, float(bill["line_items"][idx]["line_amount"]), rate, ctc, join_date, user)

    now = datetime.now(timezone.utc).isoformat()
    if placements:
        await db[br.COLL].update_many({"id": {"$in": placements}}, {
            "$set": {"invoice_no": bill["bill_number"], "bill_id": bill["id"],
                     "payment_status": "PP", "payment_status_raw": "PP", "updated_at": now},
            "$push": {"edits": {"at": now, "by": user.get("email"), "role": user.get("role"),
                                "changes": {"invoice_no": bill["bill_number"], "payment_status": "PP"},
                                "note": "Billed on a consolidated invoice"}},
        })

    return {
        "message": f"Invoice {bill['bill_number']} raised for {len(lines)} candidates",
        "bill_id": bill["id"],
        "bill_number": bill["bill_number"],
        "candidates": [li["candidate_name"] for li in bill["line_items"]],
        "total": bill["totals"]["grand_total"],
    }


@bills_router.get("/bills/worklist")
async def bills_worklist(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    state: Optional[str] = None,
    q: Optional[str] = None,
    user: dict = Depends(_require_billing_role),
):
    """Invoices & Payments: everything waiting to be raised, collected or
    already collected — tracker rows, platform joinings and bills together.

    Employers only ever see their own branch; Admin and Accounts see all.
    """
    from services import targets_service as ts
    from services.invoice_worklist import worklist

    year = ts.current_year()
    team_ids = recruiter_ids = None
    if user.get("role") not in ("admin", "accounts"):
        teams = await ts.teams_for_employer(db, user["id"])
        team_ids = [t["id"] for t in teams]
        recruiter_ids = list({uid for t in teams for uid in ts.team_member_ids(t)})

    start, end = ts.year_bounds(year)
    return await worklist(
        db,
        date_from=date_from or start, date_to=date_to or end,
        team_ids=team_ids, recruiter_ids=recruiter_ids, state=state, q=q,
    )


@bills_router.get("/bills/{bill_id}")
async def get_bill(bill_id: str, user: dict = Depends(_require_billing_role)):
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


@bills_router.put("/bills/{bill_id}")
async def update_bill(bill_id: str, payload: BillUpdate, user: dict = Depends(_require_billing_role)):
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.get("status") in ("paid", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Bill is {bill['status']} — edits are locked.")

    upd = {k: v for k, v in payload.model_dump(exclude_none=True).items()}

    # If line items changed (or gst_kind / sender_variant), recompute totals + sender fields
    if "line_items" in upd or "gst_kind" in upd or "sender_variant" in upd:
        new_items = upd.get("line_items") or bill["line_items"]
        new_items_dicts = []
        for li in new_items:
            d = li.model_dump() if hasattr(li, "model_dump") else dict(li)
            if not d.get("line_amount") or d["line_amount"] <= 0:
                d["line_amount"] = _round2(d.get("annual_ctc", 0) * (d.get("commercial_rate_pct", 0) or 0) / 100.0)
            d["line_amount"] = _round2(d["line_amount"])
            new_items_dicts.append(d)

        if "sender_variant" in upd:
            sender = _resolve_sender(upd["sender_variant"])
            upd["sender_legal_name"] = sender["legal_name"]
            upd["sender_address"] = sender["address"]
            upd["sender_gstin"] = sender["gstin"]
            upd["sender_pan"] = sender["pan"]
            upd["sender_state_code"] = sender["state_code"]
            upd["sender_logo_url"] = sender.get("logo_url") or ""
            upd.pop("sender_variant", None)

        gst_kind = upd.get("gst_kind") or bill["totals"]["gst_kind"]
        upd["line_items"] = new_items_dicts
        upd["totals"] = _build_totals(new_items_dicts, gst_kind)

    # Bank account swap
    if "bank_account_id" in upd:
        upd["bank_account"] = await _resolve_bank_snapshot(upd.pop("bank_account_id"))

    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.bills.update_one({"id": bill_id}, {"$set": upd})
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0})
    return bill


@bills_router.delete("/bills/{bill_id}")
async def cancel_bill(bill_id: str, user: dict = Depends(_require_billing_role)):
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0, "id": 1, "status": 1})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill["status"] == "paid":
        raise HTTPException(status_code=409, detail="Paid bills cannot be cancelled.")
    await db.bills.update_one(
        {"id": bill_id},
        {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"message": "Bill cancelled", "id": bill_id}


# ──────────────────────────────────────────────────────────────────────
# PDF render
# ──────────────────────────────────────────────────────────────────────
async def _load_signature_png() -> Optional[bytes]:
    key = os.environ.get("BILLING_SIGNATURE_R2_KEY")
    if not key:
        return None
    try:
        from utils.r2_client import get_r2_client  # type: ignore
        cli = get_r2_client()
        if not cli:
            return None
        obj = cli.get_object(Bucket=os.environ.get("R2_BUCKET", "vhc-talent-os-storage"), Key=key)
        return obj["Body"].read()
    except Exception as e:
        logger.warning("[Bills] Couldn't load signature PNG: %s", e)
        return None


# Simple in-process cache for remote sender logos so we don't refetch on
# every /pdf render.
_LOGO_CACHE: dict = {}


async def _load_logo_bytes(url: Optional[str]) -> Optional[bytes]:
    """Fetch the sender's logo from `sender_logo_url` (or the preset
    default). Cached in-process.

    fix.docx ("in bills add company logo next to the name"): when no
    logo URL is configured — or the remote fetch fails — fall back to the
    VHC logo bundled with the frontend so the invoice header always shows
    the company mark.
    """
    if url:
        cached = _LOGO_CACHE.get(url)
        if cached:
            return cached
        if cached is None:
            try:
                import httpx  # already a dep for LLM calls
                async with httpx.AsyncClient(timeout=8.0) as _c:
                    r = await _c.get(url)
                    r.raise_for_status()
                    _LOGO_CACHE[url] = r.content
                    return r.content
            except Exception as e:
                logger.warning("[Bills] Couldn't fetch sender logo %s: %s", url, e)
                _LOGO_CACHE[url] = b""  # cache the failure so we don't spam retries
    return _load_local_logo_bytes()


_LOCAL_LOGO_PATHS = (
    os.environ.get("BILLING_SENDER_LOGO_PATH") or "",
    "/app/frontend/public/assets/vhc_logo_invoice.png",
    "/app/frontend/build/assets/vhc_logo_invoice.png",
    "/app/frontend/public/assets/vhc_logo.png",
    "/app/frontend/build/assets/vhc_logo.png",
)


def _load_local_logo_bytes() -> Optional[bytes]:
    cached = _LOGO_CACHE.get("__local__")
    if cached is not None:
        return cached or None
    for path in _LOCAL_LOGO_PATHS:
        if path and os.path.exists(path):
            try:
                with open(path, "rb") as fh:
                    data = fh.read()
                _LOGO_CACHE["__local__"] = data
                return data
            except Exception as e:
                logger.warning("[Bills] Couldn't read local logo %s: %s", path, e)
    _LOGO_CACHE["__local__"] = b""
    return None


async def _bill_with_bank_fallback(bill: dict) -> dict:
    """Bills created before bank accounts existed carry no snapshot — fall
    back to the current default account so the payment block still prints."""
    if not bill.get("bank_account"):
        snap = await _resolve_bank_snapshot(None)
        if snap:
            bill = {**bill, "bank_account": snap}
    return bill


@bills_router.get("/bills/{bill_id}/pdf")
async def render_pdf(bill_id: str, user: dict = Depends(_require_billing_role)):
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    bill = await _bill_with_bank_fallback(bill)
    sig = await _load_signature_png()
    logo = await _load_logo_bytes(bill.get("sender_logo_url"))
    pdf = render_bill_pdf(bill, signature_png_bytes=sig, logo_png_bytes=logo)
    headers = {
        "Content-Disposition": f'inline; filename="{bill["bill_number"].replace("/", "_")}.pdf"',
        "X-VHC-Bill-Id": bill_id,
    }
    return Response(content=pdf, media_type="application/pdf", headers=headers)


# ──────────────────────────────────────────────────────────────────────
# Send
# ──────────────────────────────────────────────────────────────────────
@bills_router.post("/bills/{bill_id}/preview-mail")
async def preview_mail_body(bill_id: str, user: dict = Depends(_require_billing_role)):
    """Compose (or recompose) the LLM-generated mail body without sending."""
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    text = await generate_send_body(bill)
    return {"plain": text, "html": plain_to_html(text)}


@bills_router.post("/bills/{bill_id}/send")
async def send_bill(bill_id: str, payload: BillSend, user: dict = Depends(_require_billing_role)):
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.get("status") == "paid":
        raise HTTPException(status_code=409, detail="Bill is already marked paid.")

    # Find employer's email for the client company (if assigned)
    employer_email = None
    cid = bill.get("client_company_id")
    if cid:
        company = await db.companies.find_one({"id": cid}, {"_id": 0, "assigned_employer_id": 1})
        if company and company.get("assigned_employer_id"):
            emp = await db.users.find_one(
                {"id": company["assigned_employer_id"], "role": "employer"}, {"_id": 0, "email": 1}
            )
            if emp:
                employer_email = emp.get("email")

    cc_list = build_cc_list(employer_email, payload.extra_cc)
    if payload.test_mode:
        # Self-test: redirect to the requester only
        to_addr = user.get("email")
        cc_list = []
    else:
        # fix.docx (2026-09-15): allow the user to type a per-send To
        # address that overrides the company's stored billing_email.
        to_addr = (payload.to_email or bill.get("client_billing_email") or "").strip()
    if not to_addr:
        raise HTTPException(status_code=400, detail="No recipient email — set one on the client company or pass `to_email`.")

    # Body — payload override > stored > generate fresh
    plain = payload.mail_body_plain or bill.get("mail_body_plain")
    if not plain:
        plain = await generate_send_body(bill)
    html = payload.mail_body_html or plain_to_html(plain)
    subject = (
        payload.mail_subject
        or bill.get("mail_subject")
        or f"Invoice {bill['bill_number']} — {bill.get('sender_legal_name')}"
    )

    # Render the PDF fresh
    bill = await _bill_with_bank_fallback(bill)
    sig = await _load_signature_png()
    logo = await _load_logo_bytes(bill.get("sender_logo_url"))
    pdf = render_bill_pdf(bill, signature_png_bytes=sig, logo_png_bytes=logo)
    sha = hashlib.sha256(pdf).hexdigest()

    res = await send_bill_email(
        to_email=to_addr,
        cc_emails=cc_list,
        subject=subject,
        html_body=html,
        plain_body=plain,
        pdf_bytes=pdf,
        pdf_filename=f"{bill['bill_number'].replace('/', '_')}.pdf",
        tags=[{"name": "kind", "value": "bill_send"}, {"name": "bill_id", "value": bill_id}],
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    event = {
        "kind": "send",
        "to": to_addr,
        "cc": cc_list,
        "subject": subject,
        "success": res.get("success"),
        "message_id": res.get("id"),
        "error": res.get("error"),
        "at": now_iso,
        "by": user.get("email"),
        "test_mode": payload.test_mode,
        "pdf_sha256": sha,
    }
    upd = {
        "$push": {"mail_events": event},
        "$set": {
            "mail_subject": subject,
            "mail_body_plain": plain,
            "mail_body_html": html,
            "pdf_sha256": sha,
            "updated_at": now_iso,
            "cc_emails": cc_list,
        },
    }
    if res.get("success") and not payload.test_mode:
        upd["$set"]["status"] = "sent"
        upd["$set"]["sent_at"] = now_iso
    await db.bills.update_one({"id": bill_id}, upd)

    if not res.get("success"):
        raise HTTPException(status_code=502, detail=f"Mail send failed: {res.get('error')}")
    return {"message": "Bill emailed", "to": to_addr, "cc": cc_list, "id": res.get("id"), "test_mode": payload.test_mode}


# ──────────────────────────────────────────────────────────────────────
# Mark paid
# ──────────────────────────────────────────────────────────────────────
@bills_router.post("/bills/{bill_id}/mark-paid")
async def mark_paid(bill_id: str, paid_on: Optional[str] = None,
                    user: dict = Depends(_require_billing_role)):
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0, "status": 1})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill["status"] == "paid":
        return {"message": "Already marked paid", "id": bill_id}
    now_iso = datetime.now(timezone.utc).isoformat()
    paid_date = (paid_on or now_iso)[:10]
    await db.bills.update_one(
        {"id": bill_id},
        {"$set": {"status": "paid", "paid_at": paid_date,
                  "marked_paid_by": user.get("email"), "updated_at": now_iso}},
    )

    # One payment clears every candidate on the invoice — that is the whole
    # point of billing them together.
    full = await db.bills.find_one({"id": bill_id}, {"_id": 0, "line_items": 1, "bill_number": 1}) or {}
    lines = full.get("line_items") or []
    placement_ids = [li["placement_id"] for li in lines if li.get("placement_id")]
    application_ids = [li["application_id"] for li in lines if li.get("application_id")]
    cleared = 0
    if placement_ids:
        res = await db.placement_ledger.update_many({"id": {"$in": placement_ids}}, {
            "$set": {"payment_status": "Payment Received", "payment_status_raw": "Payment Received",
                     "payment_date": paid_date, "updated_at": now_iso},
            "$push": {"edits": {"at": now_iso, "by": user.get("email"), "role": user.get("role"),
                                "changes": {"payment_status": "Payment Received", "payment_date": paid_date},
                                "note": f"Paid on invoice {full.get('bill_number')}"}},
        })
        cleared += res.modified_count
    if application_ids:
        res = await db.revenue.update_many(
            {"application_id": {"$in": application_ids}},
            {"$set": {"revenue_status": "received", "payment_date": paid_date, "updated_at": now_iso}},
        )
        cleared += res.modified_count
    return {"message": "Bill marked as paid", "id": bill_id,
            "candidates_cleared": cleared, "line_count": len(lines)}
