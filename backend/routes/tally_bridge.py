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
from services.tally_xml import build_sales_voucher_xml

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
    cursor = db.bills.find(q, {"_id": 0}).sort("created_at", 1).limit(int(limit))
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
    return {
        "pending": pending,
        "pushed_total": pushed,
        "pushed_today": pushed_today,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
