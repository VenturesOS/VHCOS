"""Recruiter feedback signals on talent-search results.

Captures shortlist / "wrong role" clicks against a (mandate, candidate, query)
tuple so the hybrid search can:
  1. Boost previously-shortlisted candidates the next time the SAME mandate
     is searched (collaborative-filter style — no model retraining needed).
  2. Down-weight role tokens that correlated with wrong picks (per-mandate
     tuning, computed on demand by `mandate_token_weights`).
  3. Feed positive / negative labels into the offline LTR retraining job.

Collection schema (`talent_search_feedback`):
    {
      id, mandate_id, candidate_id, query, action,    # shortlist|wrong_role|hide
      created_at, created_by, role_hits,              # tokens active at click time
    }

Indexes: (mandate_id, action), (candidate_id, mandate_id).
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config import db
from utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/talent/feedback", tags=["Talent Feedback"])

FB_COLL = "talent_search_feedback"
_ACTIONS = ("shortlist", "wrong_role", "hide")


class FeedbackRequest(BaseModel):
    candidate_id: str = Field(..., min_length=1)
    action: Literal["shortlist", "wrong_role", "hide"]
    mandate_id: Optional[str] = None
    query: Optional[str] = None
    role_hits: Optional[List[str]] = None


@router.post("/")
async def post_feedback(
    req: FeedbackRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    doc = {
        "id": str(uuid.uuid4()),
        "mandate_id":  req.mandate_id,
        "candidate_id": req.candidate_id,
        "query":       (req.query or "")[:500],
        "action":      req.action,
        "role_hits":   (req.role_hits or [])[:12],
        "created_by":  current_user.get("id"),
        "created_at":  datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db[FB_COLL].insert_one(doc)
    except Exception as e:
        logger.exception("[TalentFeedback] insert failed")
        raise HTTPException(status_code=500, detail=f"persist failed: {e}")
    return {"ok": True, "id": doc["id"]}


# ── helpers used by the search route ──────────────────────────────────


async def shortlisted_candidate_ids(db_, mandate_id: str, limit: int = 100) -> List[str]:
    """All candidate IDs a recruiter has shortlisted (or partly-converted) for
    this mandate. Used to boost them to the top of subsequent searches."""
    if not mandate_id:
        return []
    try:
        cur = db_[FB_COLL].find(
            {"mandate_id": mandate_id, "action": "shortlist"},
            {"_id": 0, "candidate_id": 1},
        ).limit(limit)
        return [d["candidate_id"] async for d in cur if d.get("candidate_id")]
    except Exception:
        return []


async def mandate_token_weights(db_, mandate_id: str) -> Dict[str, float]:
    """Compute per-mandate role-token weights from accumulated feedback.

    For each token in the role signature, we look at how often it appeared in
    `role_hits` of shortlisted candidates vs wrong_role candidates. A token
    that consistently shows up in wrong_role gets a weight < 1.0 (down-weight),
    a token in shortlists gets > 1.0 (boost). Returns {} until at least 10
    feedback rows accumulate.
    """
    if not mandate_id:
        return {}
    try:
        rows = await db_[FB_COLL].find(
            {"mandate_id": mandate_id, "action": {"$in": ["shortlist", "wrong_role"]}},
            {"_id": 0, "action": 1, "role_hits": 1},
        ).to_list(500)
    except Exception:
        return {}
    if len(rows) < 10:
        return {}
    pos_counts: Dict[str, int] = {}
    neg_counts: Dict[str, int] = {}
    for r in rows:
        bucket = pos_counts if r.get("action") == "shortlist" else neg_counts
        for t in (r.get("role_hits") or []):
            bucket[t] = bucket.get(t, 0) + 1
    weights: Dict[str, float] = {}
    for tok in set(pos_counts) | set(neg_counts):
        p = pos_counts.get(tok, 0)
        n = neg_counts.get(tok, 0)
        # Add-one smoothing — never goes to zero, never explodes.
        weights[tok] = round((p + 1) / (n + 1), 3)
    return weights
