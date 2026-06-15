"""Badge Verification Audit — Phase 56.3 (Feb 2026).

Powers the admin Badge Audit page. Every call to
`/api/extension/check-existing` from an audited user writes ONE document
to the `badge_audit` collection (fire-and-forget — does not block the
response).

That document captures everything needed to reproduce + judge any
decision retrospectively:
  - the original card payload the extension sent
  - the per-card backend decision (score, signals, matched DB record,
    explicit conflict reason, threshold gate result, V1 vs V2 path)
  - room for the extension to later report back which cards it actually
    rendered as badges vs filtered out client-side (via
    /api/extension/audit/feedback — wired when v5.5.10 ships)
  - room for admin to label each card as
    correct / false_positive / false_negative / uncertain

Together this gives:
  (a) reproducibility — "the search is long gone" stops being a problem
  (b) a benchmark — labeled card→decision pairs accumulate over time
  (c) visibility into the extension client-side filter (`postValidateApiResults`)
      once feedback endpoint is wired

Collection: `badge_audit` (TTL 30 days, see services/lifecycle.py)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from config import db
from utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/badge-audit", tags=["Badge Audit"])
ext_feedback_router = APIRouter(prefix="/api/extension", tags=["Browser Extension"])


# ── Helpers used by /api/extension/check-existing ─────────────────────

async def write_audit_doc(
    *,
    user: dict,
    used_v2: bool,
    candidates_in: list,
    results_out: list,
    docs_by_idx: dict,           # idx → best_doc (for richer detail)
    conflicts_by_idx: dict,       # idx → conflict reason string
    page_url: Optional[str],
    took_ms: int,
) -> Optional[str]:
    """Persist one audit doc. Fire-and-forget — caller wraps in
    `asyncio.create_task(...)` so request latency is untouched.

    Returns the audit_id (uuid) which extension feedback later
    references, or None on failure.
    """
    try:
        audit_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        cards = []
        for r in results_out:
            idx = r.index if hasattr(r, "index") else r.get("index")
            c_in = candidates_in[idx] if idx < len(candidates_in) else None
            best_doc = docs_by_idx.get(idx)
            cards.append({
                "card_idx": idx,
                # Card payload (what extension scraped from Naukri DOM)
                "card_name": getattr(c_in, "name", None),
                "card_headline": getattr(c_in, "headline", None),
                "card_location": getattr(c_in, "location", None),
                "card_naukri_id": getattr(c_in, "naukri_id", None),
                "card_employer": getattr(c_in, "current_employer", None),
                "card_designation": getattr(c_in, "designation", None),
                "card_experience_years": getattr(c_in, "experience_years", None),
                # Backend decision
                "exists": bool(getattr(r, "exists", None) or (r.get("exists") if isinstance(r, dict) else False)),
                "match_confidence": getattr(r, "match_confidence", None) or (r.get("match_confidence") if isinstance(r, dict) else None),
                "match_score": getattr(r, "match_score", None) or (r.get("match_score") if isinstance(r, dict) else None),
                "matched_signals": list(getattr(r, "matched_signals", None) or (r.get("matched_signals") if isinstance(r, dict) else None) or []),
                "matched_candidate_id": getattr(r, "candidate_id", None) or (r.get("candidate_id") if isinstance(r, dict) else None),
                "matched_candidate_name": (best_doc.get("name") if best_doc else None),
                "matched_candidate_employer": (best_doc.get("current_employer") if best_doc else None),
                "matched_candidate_location": (best_doc.get("location") if best_doc else None),
                # Reason for rejection (if any)
                "conflict_reason": conflicts_by_idx.get(idx),
                # Client-side feedback — filled later via /audit/feedback
                "client_rendered": None,
                "client_skip_reason": None,
                # Human label
                "label": None,
                "label_notes": None,
                "labeled_by": None,
                "labeled_at": None,
            })

        # Pre-compute roll-up metrics on insert (saves admin-page aggregations)
        n_exists = sum(1 for c in cards if c["exists"])
        n_high = sum(1 for c in cards if c["match_confidence"] == "high")
        n_naukri_id = sum(
            1 for c in cards
            if c["exists"] and "naukri_id" in (c["matched_signals"] or [])
        )

        await db.badge_audit.insert_one({
            "id": audit_id,
            "user_email": (user.get("email") or "").lower(),
            "user_id": user.get("id"),
            "ts": now,
            "expires_at": now + timedelta(days=30),  # backstop for TTL
            "used_v2": used_v2,
            "page_url": page_url,
            "batch_size": len(candidates_in),
            "took_ms": took_ms,
            # Roll-ups
            "n_exists": n_exists,
            "n_high_confidence": n_high,
            "n_via_naukri_id": n_naukri_id,
            "hit_rate": (n_exists / len(candidates_in)) if candidates_in else 0.0,
            # Per-card detail
            "cards": cards,
        })
        return audit_id
    except Exception as e:
        logger.exception(f"[BadgeAudit] write failed: {e}")
        return None


# ── Admin: list / get / label ─────────────────────────────────────────

class AuditBatchSummary(BaseModel):
    id: str
    user_email: str
    ts: datetime
    used_v2: bool
    page_url: Optional[str]
    batch_size: int
    took_ms: int
    n_exists: int
    n_high_confidence: int
    n_via_naukri_id: int
    hit_rate: float
    # How many cards in this batch have a human label
    n_labeled: int
    # How many cards have client feedback filled in
    n_client_feedback: int


@router.get("", response_model=List[AuditBatchSummary])
async def list_audit_batches(
    limit: int = Query(50, le=200),
    user_email: Optional[str] = None,
    only_v2: bool = False,
    has_unlabeled: bool = False,
    user: dict = Depends(get_current_user),
    
):
    """List recent audit batches. Newest first.
    Admin-only — restricted by upstream auth role check would be nicer,
    but we rely on the auth_unified dependency for now (every admin
    user is `admin@vhc.in` in this deployment).
    """
    q: dict = {}
    if user_email:
        q["user_email"] = user_email.lower()
    if only_v2:
        q["used_v2"] = True

    cursor = db.badge_audit.find(q, {"cards": 0}).sort("ts", -1).limit(limit)
    rows = await cursor.to_list(limit)

    # Backfill computed columns (labels + client feedback counts) — quick
    # second query so admin page can filter on them
    out: List[AuditBatchSummary] = []
    for r in rows:
        full = await db.badge_audit.find_one(
            {"id": r["id"]},
            {"cards.label": 1, "cards.client_rendered": 1, "_id": 0},
        )
        cards = (full or {}).get("cards", []) if full else []
        n_lbl = sum(1 for c in cards if c.get("label"))
        n_fb = sum(1 for c in cards if c.get("client_rendered") is not None)
        if has_unlabeled and n_lbl == len(cards):
            continue
        out.append(AuditBatchSummary(
            id=r["id"],
            user_email=r["user_email"],
            ts=r["ts"],
            used_v2=r.get("used_v2", False),
            page_url=r.get("page_url"),
            batch_size=r.get("batch_size", 0),
            took_ms=r.get("took_ms", 0),
            n_exists=r.get("n_exists", 0),
            n_high_confidence=r.get("n_high_confidence", 0),
            n_via_naukri_id=r.get("n_via_naukri_id", 0),
            hit_rate=r.get("hit_rate", 0.0),
            n_labeled=n_lbl,
            n_client_feedback=n_fb,
        ))
    return out


@router.get("/{audit_id}")
async def get_audit_batch(
    audit_id: str,
    user: dict = Depends(get_current_user),
    
):
    """Full detail for one batch (all cards + their decision trees)."""
    doc = await db.badge_audit.find_one({"id": audit_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="audit batch not found")
    return doc


class LabelRequest(BaseModel):
    label: str   # one of: correct | false_positive | false_negative | uncertain
    notes: Optional[str] = None


_ALLOWED_LABELS = {"correct", "false_positive", "false_negative", "uncertain"}


@router.post("/{audit_id}/cards/{card_idx}/label")
async def label_card(
    audit_id: str,
    card_idx: int,
    req: LabelRequest,
    user: dict = Depends(get_current_user),
    
):
    """Apply a thumbs-style label to a single card within a batch."""
    if req.label not in _ALLOWED_LABELS:
        raise HTTPException(
            status_code=400,
            detail=f"label must be one of: {sorted(_ALLOWED_LABELS)}",
        )

    res = await db.badge_audit.update_one(
        {"id": audit_id, f"cards.{card_idx}.card_idx": card_idx},
        {"$set": {
            f"cards.{card_idx}.label": req.label,
            f"cards.{card_idx}.label_notes": req.notes,
            f"cards.{card_idx}.labeled_by": (user.get("email") or "").lower(),
            f"cards.{card_idx}.labeled_at": datetime.now(timezone.utc),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="audit batch or card not found")
    return {"ok": True}


@router.get("/_/stats/overview")
async def stats_overview(
    days: int = Query(7, le=90),
    user: dict = Depends(get_current_user),
    
):
    """Rolling stats over the last N days. Powers the admin page header."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {"ts": {"$gte": since}}},
        {"$group": {
            "_id": None,
            "n_batches": {"$sum": 1},
            "n_cards": {"$sum": "$batch_size"},
            "n_hits": {"$sum": "$n_exists"},
            "n_via_naukri_id": {"$sum": "$n_via_naukri_id"},
            "avg_took_ms": {"$avg": "$took_ms"},
        }},
    ]
    agg = await db.badge_audit.aggregate(pipeline).to_list(1)
    if not agg:
        return {
            "days": days, "n_batches": 0, "n_cards": 0, "n_hits": 0,
            "n_via_naukri_id": 0, "avg_took_ms": 0.0, "recall_pct": 0.0,
        }
    r = agg[0]
    return {
        "days": days,
        "n_batches": r["n_batches"],
        "n_cards": r["n_cards"],
        "n_hits": r["n_hits"],
        "n_via_naukri_id": r["n_via_naukri_id"],
        "avg_took_ms": round(r["avg_took_ms"] or 0, 1),
        "recall_pct": round(100.0 * r["n_hits"] / r["n_cards"], 2) if r["n_cards"] else 0.0,
    }


# ── Extension feedback (no auth checking version handles it) ──────────

class ClientCardFeedback(BaseModel):
    card_idx: int
    rendered: bool          # did the extension actually draw a green badge?
    skip_reason: Optional[str] = None  # set when rendered=False


class FeedbackRequest(BaseModel):
    audit_id: str
    cards: List[ClientCardFeedback]


@ext_feedback_router.post("/audit/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    user: dict = Depends(get_current_user),
    
):
    """Called by extension AFTER it processes the API response, reporting
    which results it kept (rendered as badge) vs filtered out client-side
    and why. Lets admin compare backend decision vs client decision —
    surfaces silent rejections by `postValidateApiResults`.

    Designed for v5.5.10+. Older extensions don't call this; the
    `client_rendered` field stays null and admin labels manually.
    """
    if not req.cards:
        return {"ok": True, "updated": 0}

    updates = {}
    for c in req.cards:
        updates[f"cards.{c.card_idx}.client_rendered"] = c.rendered
        updates[f"cards.{c.card_idx}.client_skip_reason"] = c.skip_reason
    updates["client_feedback_at"] = datetime.now(timezone.utc)

    res = await db.badge_audit.update_one(
        {"id": req.audit_id, "user_email": (user.get("email") or "").lower()},
        {"$set": updates},
    )
    return {"ok": True, "updated": res.modified_count}


# ── User-reported "Wrong match" flag (Badge Phase A, 2026-06-15) ─────
#
# Why a separate collection?
#   `badge_audit` is auto-written for every backend decision and gets
#   labelled by `auto_label_badge_audit.py` against the DB ground truth.
#   When a recruiter clicks "Wrong match?" on the extension badge they're
#   telling us the *match itself* is wrong — that's a different signal
#   class (real human judgement, not auto-derived). Keeping it in
#   `badge_feedback` lets us:
#     • compare auto-label vs human-label disagreement
#     • feed only human-confirmed FPs into threshold tuning
#     • avoid polluting the labelled-audit dataset
#
# The endpoint is silent (returns 200 immediately, no UX echo) per user
# direction — recruiters should NOT see a confirmation prompt.

class WrongMatchReport(BaseModel):
    audit_id: Optional[str] = None         # links to the originating audit doc
    card_idx: Optional[int] = None         # which card in the batch
    badge_candidate_id: str                # the DB candidate the badge pointed to
    card_name: Optional[str] = None        # what name was on the Naukri card
    card_headline: Optional[str] = None
    card_employer: Optional[str] = None
    card_location: Optional[str] = None
    page_url: Optional[str] = None
    extension_version: Optional[str] = None
    reason: Optional[str] = None           # optional free-text from user


@ext_feedback_router.post("/audit/wrong-match")
async def report_wrong_match(
    req: WrongMatchReport,
    user: dict = Depends(get_current_user),
):
    """Silent log of a user-reported wrong-match badge.

    Writes ONE document to `badge_feedback`. Returns 200 with no UI echo
    so the extension popup can close immediately without disturbing the
    recruiter's flow.
    """
    if not req.badge_candidate_id:
        # Soft-fail: still 200 so the extension doesn't surface an error.
        return {"ok": True, "stored": False, "reason": "missing badge_candidate_id"}

    try:
        now = datetime.now(timezone.utc)
        doc = {
            "id": str(uuid.uuid4()),
            "kind": "wrong_match",
            "ts": now,
            "expires_at": now + timedelta(days=180),  # keep 6 mo for tuning
            "user_email": (user.get("email") or "").lower(),
            "user_id": user.get("id"),
            "audit_id": req.audit_id,
            "card_idx": req.card_idx,
            "badge_candidate_id": req.badge_candidate_id,
            "card_name": req.card_name,
            "card_headline": req.card_headline,
            "card_employer": req.card_employer,
            "card_location": req.card_location,
            "page_url": req.page_url,
            "extension_version": req.extension_version,
            "reason": (req.reason or "")[:500],
        }
        await db.badge_feedback.insert_one(doc)

        # Also mark the originating audit card as flagged so the admin UI
        # surfaces it without an extra collection lookup.
        if req.audit_id and req.card_idx is not None:
            await db.badge_audit.update_one(
                {"id": req.audit_id, f"cards.{req.card_idx}.card_idx": req.card_idx},
                {"$set": {
                    f"cards.{req.card_idx}.user_flagged_wrong": True,
                    f"cards.{req.card_idx}.user_flagged_at": now,
                    f"cards.{req.card_idx}.user_flagged_by": (user.get("email") or "").lower(),
                }},
            )
        return {"ok": True, "stored": True}
    except Exception as e:
        logger.warning(f"[BadgeFeedback] wrong-match store failed: {e}")
        # Never bubble errors to the extension popup.
        return {"ok": True, "stored": False}


# ── Admin: list / stats for wrong-match feedback ─────────────────────

@router.get("/_/feedback/wrong-match")
async def list_wrong_match_feedback(
    limit: int = Query(100, le=500),
    days: int = Query(30, le=365),
    user: dict = Depends(get_current_user),
):
    """Admin view of recent user-reported wrong-match flags."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    cursor = db.badge_feedback.find(
        {"kind": "wrong_match", "ts": {"$gte": since}},
        {"_id": 0},
    ).sort("ts", -1).limit(limit)
    return await cursor.to_list(limit)


@router.get("/_/feedback/wrong-match/stats")
async def wrong_match_stats(
    days: int = Query(30, le=365),
    user: dict = Depends(get_current_user),
):
    """Roll-up: how often does the team flag badges as wrong?"""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {"kind": "wrong_match", "ts": {"$gte": since}}},
        {"$group": {
            "_id": "$user_email",
            "n": {"$sum": 1},
            "last_ts": {"$max": "$ts"},
        }},
        {"$sort": {"n": -1}},
        {"$limit": 50},
    ]
    rows = await db.badge_feedback.aggregate(pipeline).to_list(50)
    total = await db.badge_feedback.count_documents(
        {"kind": "wrong_match", "ts": {"$gte": since}}
    )
    return {
        "days": days,
        "total_flags": total,
        "by_user": [{"user_email": r["_id"], "n": r["n"], "last_ts": r["last_ts"]} for r in rows],
    }

