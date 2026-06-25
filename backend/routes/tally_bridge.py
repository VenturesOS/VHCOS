"""Tally Bridge endpoints — Phase 55.8 (Feb 2026).

These endpoints are consumed by `tally_bridge.py` running on the
Windows PC at the Delhi office. The bridge polls VHC every N minutes,
pulls pending bills, posts them to local Tally:9000, then reports
success/failure back to VHC so we can mark them pushed.

ACL: This is a service-to-service API. Authentication is via a shared
secret in the `X-Tally-Bridge-Token` header (env `TALLY_BRIDGE_TOKEN`).
That token is generated once and pasted into the bridge's `.ini`. Do
NOT reuse user JWTs here — the bridge runs unattended.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from config import db
from services.tally_xml import build_sales_voucher_xml, build_ledger_create_xml
from utils.auth import get_current_user

logger = logging.getLogger(__name__)

tally_router = APIRouter(prefix="/api/tally", tags=["tally"])


# ── Auth ─────────────────────────────────────────────────────────────
def _require_bridge_token(
    x_tally_bridge_token: Optional[str] = Header(None, alias="X-Tally-Bridge-Token"),
) -> None:
    expected = os.environ.get("TALLY_BRIDGE_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=500,
            detail="TALLY_BRIDGE_TOKEN not configured on server",
        )
    if not x_tally_bridge_token or x_tally_bridge_token != expected:
        raise HTTPException(status_code=403, detail="Invalid bridge token")


# ── Models ───────────────────────────────────────────────────────────
class BridgeAck(BaseModel):
    """Bridge → server: reports the outcome of a single bill push."""
    bill_id: str
    success: bool
    tally_vch_id: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None
    pushed_at: Optional[str] = None  # ISO; server fills if omitted


class QueueItem(BaseModel):
    bill_id: str
    bill_number: str
    bill_date: str
    party: str
    party_gstin: Optional[str] = None
    grand_total: float
    gst_kind: str
    xml: str  # Pre-rendered Tally XML envelope


# ── Endpoints ────────────────────────────────────────────────────────
@tally_router.get("/queue", response_model=List[QueueItem])
async def queue(
    company: str = "VENTURE HRD CENTRE PVT LTD",
    limit: int = 25,
    _: None = Depends(_require_bridge_token),
):
    """Return up-to-`limit` bills awaiting Tally push.

    A bill is eligible when:
      • status in ('sent', 'paid')          — drafts/cancelled excluded
      • tally.pushed != True                 — not already done
      • client_legal_name is non-empty       — required for party ledger
    """
    q = {
        "status": {"$in": ["sent", "paid"]},
        "client_legal_name": {"$ne": ""},
        "$or": [
            {"tally.pushed": {"$ne": True}},
            {"tally": {"$exists": False}},
        ],
    }
    out: List[QueueItem] = []
    # Sort: priority_at (manual fast-track) first, then FIFO by created_at.
    # Using a compound sort means "Push to Tally now" actions surface at the
    # front of the bridge's next poll without disturbing global queue order.
    cursor = db.bills.find(q, {"_id": 0}).sort([
        ("tally.priority_at", -1),
        ("created_at", 1),
    ]).limit(int(limit))
    async for b in cursor:
        try:
            xml = build_sales_voucher_xml(b, company)
        except Exception as e:
            logger.warning("[Tally queue] skipping %s — xml build failed: %s", b.get("id"), e)
            continue
        out.append(QueueItem(
            bill_id=b["id"],
            bill_number=b.get("bill_number") or "",
            bill_date=b.get("bill_date") or "",
            party=b.get("client_legal_name") or "",
            party_gstin=b.get("client_gstin") or None,
            grand_total=float((b.get("totals") or {}).get("grand_total") or 0),
            gst_kind=(b.get("totals") or {}).get("gst_kind") or "IGST",
            xml=xml,
        ))
    return out


@tally_router.post("/ack")
async def ack(payload: BridgeAck, _: None = Depends(_require_bridge_token)):
    """Bridge reports back. We mark the bill pushed (or record the error)."""
    bill = await db.bills.find_one({"id": payload.bill_id}, {"_id": 0, "id": 1, "tally": 1})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    now_iso = payload.pushed_at or datetime.now(timezone.utc).isoformat()
    history = (bill.get("tally") or {}).get("history") or []
    history.append({
        "at": now_iso,
        "success": payload.success,
        "vch_id": payload.tally_vch_id,
        "error": payload.error,
        "raw": (payload.raw_response or "")[:1500],
    })
    tally_state = {
        "pushed": payload.success,
        "last_attempt_at": now_iso,
        "last_success_at": now_iso if payload.success else (bill.get("tally") or {}).get("last_success_at"),
        "tally_vch_id": payload.tally_vch_id or (bill.get("tally") or {}).get("tally_vch_id"),
        "last_error": None if payload.success else payload.error,
        "history": history[-20:],  # keep last 20 attempts
    }
    await db.bills.update_one(
        {"id": payload.bill_id},
        {"$set": {"tally": tally_state, "updated_at": now_iso}},
    )
    return {"ok": True, "pushed": payload.success}


@tally_router.get("/status")
async def status(_: None = Depends(_require_bridge_token)):
    """Quick health/stats endpoint so the bridge can log a heartbeat
    and the admin UI can show 'X bills queued, Y pushed today'."""
    pending = await db.bills.count_documents({
        "status": {"$in": ["sent", "paid"]},
        "client_legal_name": {"$ne": ""},
        "$or": [{"tally.pushed": {"$ne": True}}, {"tally": {"$exists": False}}],
    })
    pushed = await db.bills.count_documents({"tally.pushed": True})
    today = datetime.now(timezone.utc).date().isoformat()
    pushed_today = await db.bills.count_documents({
        "tally.last_success_at": {"$regex": f"^{today}"},
    })
    pending_ledgers = await db.finance_clients.count_documents({
        "name": {"$ne": ""},
        "$or": [{"tally.ledger_pushed": {"$ne": True}}, {"tally": {"$exists": False}}],
    })
    receipts_today = await db.tally_receipts.count_documents({
        "received_at": {"$regex": f"^{today}"},
    })
    # Record a heartbeat doc so the admin UI knows the bridge is alive
    await db.tally_bridge_heartbeat.update_one(
        {"_id": "singleton"},
        {"$set": {
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
            "pending_bills":   pending,
            "pending_ledgers": pending_ledgers,
        }},
        upsert=True,
    )
    return {
        "pending":         pending,
        "pending_ledgers": pending_ledgers,
        "pushed_total":    pushed,
        "pushed_today":    pushed_today,
        "receipts_today":  receipts_today,
        "ts":              datetime.now(timezone.utc).isoformat(),
    }


# ── Phase 55.9: Bulk client-ledger sync ──────────────────────────────


class LedgerQueueItem(BaseModel):
    """Bridge fetches this to push a party ledger to Tally before any
    bills referencing it. Bridge must process ledgers BEFORE bills in the
    same poll cycle."""
    client_id: str
    ledger_name: str
    gstin: Optional[str] = None
    state: Optional[str] = None
    xml: str


class LedgerAck(BaseModel):
    client_id: str
    success: bool
    error: Optional[str] = None
    raw_response: Optional[str] = None
    pushed_at: Optional[str] = None


@tally_router.get("/ledgers/queue", response_model=List[LedgerQueueItem])
async def ledger_queue(
    company: str = "VENTURE HRD CENTRE PVT LTD",
    limit: int = 25,
    _: None = Depends(_require_bridge_token),
):
    """Return up-to-`limit` client ledgers awaiting Tally creation.

    Eligible when:
      • `name` is non-empty (Tally needs the party display name)
      • `tally.ledger_pushed` ≠ True

    A ledger is pushed once. Subsequent invoices for the same party
    are matched by name in `build_sales_voucher_xml`.
    """
    q = {
        "name": {"$nin": ["", None]},
        "$or": [{"tally.ledger_pushed": {"$ne": True}}, {"tally": {"$exists": False}}],
    }
    out: List[LedgerQueueItem] = []
    cursor = db.finance_clients.find(q, {"_id": 0}).sort("created_at", 1).limit(int(limit))
    async for c in cursor:
        try:
            xml = build_ledger_create_xml(
                company_name=company,
                ledger_name=c.get("name") or "",
                parent_group="Sundry Debtors",
                gstin=(c.get("gst_number") or "").strip(),
                state=(c.get("state") or "").strip(),
            )
        except Exception as e:
            logger.warning("[Tally ledger queue] skip %s — xml build failed: %s", c.get("id"), e)
            continue
        out.append(LedgerQueueItem(
            client_id=c["id"],
            ledger_name=c.get("name") or "",
            gstin=(c.get("gst_number") or None),
            state=(c.get("state") or None),
            xml=xml,
        ))
    return out


@tally_router.post("/ledgers/ack")
async def ledger_ack(payload: LedgerAck, _: None = Depends(_require_bridge_token)):
    """Bridge reports back on a ledger-create. We mark the client pushed
    (success) or store the error and let the bridge retry on its next
    poll."""
    client = await db.finance_clients.find_one({"id": payload.client_id}, {"_id": 0, "id": 1, "tally": 1})
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    now_iso = payload.pushed_at or datetime.now(timezone.utc).isoformat()
    history = (client.get("tally") or {}).get("history") or []
    history.append({
        "at":      now_iso,
        "success": payload.success,
        "error":   payload.error,
        "raw":     (payload.raw_response or "")[:1500],
    })
    tally_state = {
        "ledger_pushed":   payload.success,
        "last_attempt_at": now_iso,
        "last_success_at": now_iso if payload.success else (client.get("tally") or {}).get("last_success_at"),
        "last_error":      None if payload.success else payload.error,
        "history":         history[-10:],
    }
    await db.finance_clients.update_one(
        {"id": payload.client_id},
        {"$set": {"tally": tally_state, "updated_at": now_iso}},
    )
    return {"ok": True, "pushed": payload.success}


# ── Phase 55.10: Payment receipt pull (Tally → VHC) ──────────────────


class ReceiptItem(BaseModel):
    """Single payment receipt as read from Tally by the bridge."""
    tally_voucher_id: str           # unique receipt voucher GUID/number from Tally
    party_name: str
    amount: float
    receipt_date: str               # ISO yyyy-mm-dd
    against_bill_number: Optional[str] = None   # if Tally records a bill-ref
    against_bill_id: Optional[str] = None       # VHC bill id when bridge can resolve
    instrument: Optional[str] = None            # cheque/neft/upi/cash
    instrument_no: Optional[str] = None
    narration: Optional[str] = None
    raw: Optional[str] = None


class ReceiptsPayload(BaseModel):
    receipts: List[ReceiptItem]


@tally_router.post("/receipts")
async def receipts_inbound(
    payload: ReceiptsPayload,
    _: None = Depends(_require_bridge_token),
):
    """Bridge posts a batch of payment receipts pulled from Tally.

    Reconciliation logic (best-effort):
      1. If `against_bill_id` is supplied → mark that bill as paid.
      2. Else if `against_bill_number` + `party_name` resolve to a
         single bill in VHC → mark it paid.
      3. Otherwise → store the receipt unmatched so the finance team
         can resolve from the admin UI.

    Duplicate protection: `tally_voucher_id` is unique. Subsequent posts
    of the same voucher are upserts (no double-counting).
    """
    inserted = 0
    duplicates = 0
    matched = 0
    unmatched = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for r in payload.receipts:
        existing = await db.tally_receipts.find_one(
            {"tally_voucher_id": r.tally_voucher_id},
            {"_id": 0, "id": 1},
        )
        if existing:
            duplicates += 1
            continue

        # Try to resolve a bill
        bill = None
        if r.against_bill_id:
            bill = await db.bills.find_one({"id": r.against_bill_id}, {"_id": 0, "id": 1, "totals": 1})
        if not bill and r.against_bill_number and r.party_name:
            bill = await db.bills.find_one(
                {
                    "bill_number": r.against_bill_number,
                    "client_legal_name": {"$regex": f"^{r.party_name}$", "$options": "i"},
                },
                {"_id": 0, "id": 1, "totals": 1},
            )

        receipt_doc = {
            "id":                f"rcpt-{r.tally_voucher_id}",
            "tally_voucher_id":  r.tally_voucher_id,
            "party_name":        r.party_name,
            "amount":            float(r.amount),
            "receipt_date":      r.receipt_date,
            "against_bill_number": r.against_bill_number,
            "matched_bill_id":   bill.get("id") if bill else None,
            "instrument":        r.instrument,
            "instrument_no":     r.instrument_no,
            "narration":         (r.narration or "")[:500],
            "received_at":       now_iso,
            "status":            "matched" if bill else "unmatched",
        }
        await db.tally_receipts.insert_one(receipt_doc)
        inserted += 1
        if bill:
            matched += 1
            # Mark bill paid if the receipt covers the grand total.
            grand = float((bill.get("totals") or {}).get("grand_total") or 0)
            paid_status = "paid" if r.amount >= grand * 0.99 else "part_paid"
            await db.bills.update_one(
                {"id": bill["id"]},
                {"$set": {
                    "payment_status": paid_status,
                    "last_payment_at": now_iso,
                    "tally_receipt_id": receipt_doc["id"],
                    "updated_at": now_iso,
                }},
            )
        else:
            unmatched += 1

    return {
        "received":   len(payload.receipts),
        "inserted":   inserted,
        "duplicates": duplicates,
        "matched":    matched,
        "unmatched":  unmatched,
    }


# ── Admin-facing health endpoint (JWT auth, no bridge token) ─────────


@tally_router.get("/admin/health")
async def admin_health(user: dict = Depends(get_current_user)):
    """Read-only health snapshot for the `/admin/tally-health` UI.

    Differs from `/status` in that it uses JWT auth (any logged-in admin
    can view) and includes the most recent heartbeat from the Windows
    bridge so the team can see if it's still polling.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    pending = await db.bills.count_documents({
        "status": {"$in": ["sent", "paid"]},
        "client_legal_name": {"$ne": ""},
        "$or": [{"tally.pushed": {"$ne": True}}, {"tally": {"$exists": False}}],
    })
    pushed_today = await db.bills.count_documents({"tally.last_success_at": {"$regex": f"^{today}"}})
    pending_ledgers = await db.finance_clients.count_documents({
        "name": {"$nin": ["", None]},
        "$or": [{"tally.ledger_pushed": {"$ne": True}}, {"tally": {"$exists": False}}],
    })
    receipts_today = await db.tally_receipts.count_documents({"received_at": {"$regex": f"^{today}"}})
    receipts_unmatched = await db.tally_receipts.count_documents({"status": "unmatched"})
    heartbeat = await db.tally_bridge_heartbeat.find_one({"_id": "singleton"}, {"_id": 0})
    # Last 10 push failures for quick diagnosis
    failed_cursor = db.bills.find(
        {"tally.last_error": {"$ne": None}, "tally.pushed": {"$ne": True}},
        {"_id": 0, "id": 1, "bill_number": 1, "client_legal_name": 1, "tally.last_error": 1, "tally.last_attempt_at": 1},
    ).sort("tally.last_attempt_at", -1).limit(10)
    failures = [d async for d in failed_cursor]
    return {
        "pending_bills":      pending,
        "pending_ledgers":    pending_ledgers,
        "pushed_today":       pushed_today,
        "receipts_today":     receipts_today,
        "receipts_unmatched": receipts_unmatched,
        "heartbeat":          heartbeat,
        "recent_failures":    failures,
        "ts":                 datetime.now(timezone.utc).isoformat(),
    }


@tally_router.get("/admin/receipts/unmatched")
async def admin_receipts_unmatched(
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    """List unmatched receipts so the finance team can resolve them."""
    cur = db.tally_receipts.find(
        {"status": "unmatched"},
        {"_id": 0},
    ).sort("received_at", -1).limit(int(limit))
    return [r async for r in cur]


@tally_router.post("/admin/bills/{bill_id}/push-now")
async def admin_push_bill_now(
    bill_id: str,
    user: dict = Depends(get_current_user),
):
    """Bump a bill's `created_at` so the bridge picks it up on the very
    next poll instead of waiting in FIFO. Useful for fast-tracking urgent
    invoices without losing queue order for the rest.

    Returns the new position; bridge still has to actually call /queue
    for the push to happen — typically within 30s on prod.
    """
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0, "id": 1, "bill_number": 1, "tally": 1, "status": 1})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if (bill.get("tally") or {}).get("pushed"):
        return {"ok": True, "already_pushed": True, "bill_id": bill_id}
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.bills.update_one(
        {"id": bill_id},
        {"$set": {"tally.priority_at": now_iso, "updated_at": now_iso}},
    )
    return {
        "ok": True,
        "bill_id": bill_id,
        "bill_number": bill.get("bill_number"),
        "priority_at": now_iso,
        "message": "Bumped to top of bridge queue — bridge polls every ~30s on prod.",
    }


@tally_router.get("/admin/pending-bills")
async def admin_pending_bills(
    limit: int = 10,
    user: dict = Depends(get_current_user),
):
    """List the next N bills awaiting Tally push, in queue order (priority
    first then FIFO). Powers the "Push now" mini-tile on the health page.
    """
    q = {
        "status": {"$in": ["sent", "paid"]},
        "client_legal_name": {"$ne": ""},
        "$or": [{"tally.pushed": {"$ne": True}}, {"tally": {"$exists": False}}],
    }
    cur = db.bills.find(
        q,
        {"_id": 0, "id": 1, "bill_number": 1, "client_legal_name": 1, "created_at": 1, "totals": 1, "tally": 1},
    ).sort([("tally.priority_at", -1), ("created_at", 1)]).limit(int(limit))
    return [b async for b in cur]
