"""Auto-draft a bill when an application transitions to `joined` or `hired`.

Hooked from `routes/applications.py` after the stage transition is
persisted. Idempotent — if a draft bill already contains a line item with
the same `application_id`, we skip silently. Errors are swallowed: this
runs as a side-effect of stage change and must never break that path.

Public:
    maybe_auto_draft_bill(app_id, application, current_user) -> Optional[str]
        Returns the new bill_number (e.g. "VHC/26-27/9") if a draft was
        created, else None.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from config import db
from services.bill_pdf import amount_to_words

logger = logging.getLogger(__name__)

# Stages that should trigger a draft bill.
_TRIGGER_STAGES = {"hired", "joined"}

# Toggle so this can be disabled in dev / staging quickly.
_ENABLED = (os.environ.get("BILLING_AUTODRAFT_ENABLED", "true") or "").lower() in (
    "1", "true", "yes", "on",
)


# ── Sender defaults (mirrors bills.py — kept tiny to avoid circular imports) ──
def _sender() -> dict:
    return {
        "legal_name": "VENTURE HRD CENTER",
        "address": (
            "Second Floor, D-12/79-80, Rohini, Rohini Sector 8, "
            "New Delhi, North West Delhi, Delhi, 110085"
        ),
        "gstin": os.environ.get("BILLING_SENDER_GSTIN") or "07AAMPY9883D2ZT",
        "pan": os.environ.get("BILLING_SENDER_PAN") or "AAMPY9883D",
        "state_code": "07",
    }


def _fy_code(d: datetime) -> str:
    yr = d.year
    if d.month < 4:
        start, end = yr - 1, yr
    else:
        start, end = yr, yr + 1
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


def _round2(x: float) -> float:
    return round(float(x or 0) + 1e-9, 2)


async def _already_drafted(app_id: str) -> bool:
    """Return True if a non-cancelled bill already references this application."""
    cur = db.bills.find(
        {"status": {"$ne": "cancelled"}, "line_items.application_id": app_id},
        {"_id": 0, "id": 1},
    )
    async for _ in cur:
        return True
    return False


async def maybe_auto_draft_bill(
    app_id: str,
    application: dict,
    current_user: Optional[dict] = None,
) -> Optional[str]:
    """Create a draft bill for a hired/joined application, if eligible."""
    if not _ENABLED:
        return None

    stage = (application or {}).get("stage")
    if stage not in _TRIGGER_STAGES:
        return None

    # Need a CTC to bill against.
    offered_ctc = application.get("offered_ctc") or application.get("expected_ctc") or 0
    if not offered_ctc or offered_ctc <= 0:
        logger.info("[Bill auto-draft] skipping %s — no offered_ctc on application", app_id)
        return None

    # Idempotency
    if await _already_drafted(app_id):
        logger.info("[Bill auto-draft] skipping %s — draft already exists", app_id)
        return None

    # Resolve the client company from the application's job
    job_id = application.get("job_id")
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0}) if job_id else None
    if not job:
        logger.info("[Bill auto-draft] skipping %s — job not found (%s)", app_id, job_id)
        return None

    company = None
    # Try several conventional FK fields the jobs collection might use
    for fk in ("company_id", "client_company_id", "employer_company_id"):
        if job.get(fk):
            company = await db.companies.find_one({"id": job[fk]}, {"_id": 0})
            if company:
                break
    # Fallback: match by company_name (best-effort)
    if not company and job.get("company_name"):
        company = await db.companies.find_one(
            {"$or": [
                {"legal_name": job["company_name"]},
                {"name": job["company_name"]},
            ]},
            {"_id": 0},
        )

    if not company:
        logger.info("[Bill auto-draft] skipping %s — company not resolvable for job %s", app_id, job_id)
        return None

    sender = _sender()
    client_state = ((company.get("gstin") or "")[:2] or "00").zfill(2)
    gst_kind = "CGST_SGST" if client_state == sender["state_code"] else "IGST"

    # Commercial rate: per-company override → global default
    rate_pct = float(
        company.get("commercial_rate_pct")
        or os.environ.get("BILLING_DEFAULT_COMMERCIAL_PCT")
        or 8.33
    )
    line_amount = _round2(float(offered_ctc) * rate_pct / 100.0)
    tax_total = _round2(line_amount * 0.18)
    grand = _round2(line_amount + tax_total)

    now = datetime.now(timezone.utc)
    join_date = (
        application.get("join_date")
        or application.get("offer_date")
        or now.date().isoformat()
    )

    line_item = {
        "candidate_name": application.get("candidate_name") or "(candidate)",
        "designation": application.get("designation") or job.get("title") or "",
        "joining_date": join_date,
        "annual_ctc": _round2(offered_ctc),
        "commercial_rate_pct": rate_pct,
        "line_amount": line_amount,
        "hsn_sac": "998512",
        "application_id": app_id,
    }

    bill = {
        "id": str(uuid.uuid4()),
        "bill_number": await _next_bill_number(now),
        "bill_date": now.date().isoformat(),
        "due_date": None,
        "sender_legal_name": sender["legal_name"],
        "sender_address": sender["address"],
        "sender_gstin": sender["gstin"],
        "sender_pan": sender["pan"],
        "sender_state_code": sender["state_code"],
        "client_company_id": company.get("id"),
        "client_legal_name": company.get("legal_name") or company.get("name") or "",
        "client_address": company.get("billing_address") or company.get("address") or "",
        "client_gstin": company.get("gstin") or "",
        "client_state_code": client_state,
        "client_billing_email": company.get("billing_email") or company.get("primary_email") or "",
        "line_items": [line_item],
        "totals": {
            "taxable_value": line_amount,
            "gst_kind": gst_kind,
            "igst_pct": 18.0 if gst_kind == "IGST" else 0,
            "cgst_pct": 0 if gst_kind == "IGST" else 9.0,
            "sgst_pct": 0 if gst_kind == "IGST" else 9.0,
            "tax_total": tax_total,
            "grand_total": grand,
            "amount_in_words": amount_to_words(grand),
            "tax_in_words": amount_to_words(tax_total),
        },
        "status": "draft",
        "reminders_enabled": True,
        "reminder_schedule_days": [7, 14, 30],
        "reminders_sent": [],
        "mail_events": [],
        "cc_emails": [],
        "bcc_emails": [],
        "created_by": (current_user or {}).get("id", "system-autodraft"),
        "created_by_email": (current_user or {}).get("email", "system@vhc.in"),
        "created_at": now.isoformat(),
        "auto_drafted": True,
        "auto_drafted_from_application_id": app_id,
    }
    try:
        await db.bills.insert_one(bill)
        logger.info(
            "[Bill auto-draft] created %s for %s (CTC=%s rate=%.2f%% amount=%s)",
            bill["bill_number"], application.get("candidate_name"),
            offered_ctc, rate_pct, line_amount,
        )
        return bill["bill_number"]
    except Exception as e:
        logger.warning("[Bill auto-draft] insert failed for %s: %s", app_id, e)
        return None
