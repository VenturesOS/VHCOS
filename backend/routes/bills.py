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
    BillRecord,
    BillSend,
    BillUpdate,
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
    if role == "admin":
        return current_user
    if role == "employer":
        return current_user
    if role == "recruiter" and current_user.get("is_account_manager"):
        return current_user
    raise HTTPException(status_code=403, detail="Bills are accessible to Admin, Employer or Account-Manager recruiters only.")


# ──────────────────────────────────────────────────────────────────────
# Sender variants — frozen at creation time
# ──────────────────────────────────────────────────────────────────────
_SENDER_PRESETS = {
    "VENTURE HRD CENTRE": {
        "legal_name": "VENTURE HRD CENTRE",
        "address": "Second Floor, D-12/79 & 80, Rohini Sector-8, New Delhi 110085",
        "gstin": os.environ.get("BILLING_SENDER_GSTIN") or "07AAMPY9883D2ZT",
        "pan": os.environ.get("BILLING_SENDER_PAN") or "AAMPY9883D",
        "state_code": "07",
        "logo_url": os.environ.get("BILLING_SENDER_LOGO_URL") or "",
    },
    "VENTURE HRD CENTRE PVT LTD": {
        "legal_name": "VENTURE HRD CENTRE PVT LTD",
        "address": "Second Floor, D-12/79 & 80, Rohini Sector-8, New Delhi 110085",
        "gstin": os.environ.get("BILLING_SENDER_PVT_GSTIN") or "",
        "pan": os.environ.get("BILLING_SENDER_PVT_PAN") or "",
        "state_code": "07",
        "logo_url": os.environ.get("BILLING_SENDER_PVT_LOGO_URL") or "",
    },
}


def _resolve_sender(variant: Optional[str]) -> dict:
    key = (variant or "VENTURE HRD CENTRE").upper().strip()
    return _SENDER_PRESETS.get(key, _SENDER_PRESETS["VENTURE HRD CENTRE"])


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
    await db.bills.insert_one(bill)
    bill.pop("_id", None)
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
async def mark_paid(bill_id: str, user: dict = Depends(_require_billing_role)):
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0, "status": 1})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill["status"] == "paid":
        return {"message": "Already marked paid", "id": bill_id}
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.bills.update_one(
        {"id": bill_id},
        {"$set": {"status": "paid", "paid_at": now_iso, "updated_at": now_iso}},
    )
    return {"message": "Bill marked as paid", "id": bill_id}
