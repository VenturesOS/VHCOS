"""
LTR Telemetry — Phase 56.5 / XGBoost LTR Phase 1 (Jun 2026)

Per `/app/memory/XGBOOST_LTR_SCOPING.md`, the LTR project needs labeled
search slates BEFORE any model can be trained. This module is the data
accumulator — it captures search impressions + action events so a future
training pipeline has the ≥5k positive triplets it needs.

Schema
------
`search_sessions` collection — one doc per search query / pipeline view:
  {
    "id": uuid,
    "user_id", "user_email", "user_role",
    "ts": datetime,
    "expires_at": datetime,       # TTL field — 180 days
    "source": "talent_graph_search" | "rerank" | "pipeline_view" | ...,
    "query": str,                 # free-form text (semantic search) or job_id
    "query_meta": {...},          # filters/role/etc — optional context
    "slate": [                    # full ranked list shown to the user
      { "rank": 0, "candidate_id": "abc", "score": 0.91,
        "features": {...} },     # optional — for offline replay
      ...
    ],
    "actions": [                  # appended later as user interacts
      { "candidate_id": "abc",
        "action": "click_profile" | "shortlist" | "contact" | "reject"
                 | "add_to_pipeline" | "download_resume",
        "rank": 0,                # rank at time of action
        "ts": datetime },
      ...
    ],
  }

Two public helpers
------------------
  log_slate(...)   → write a new session doc, returns its id
  log_action(...)  → append an action to an existing session

Both are fire-and-forget where possible (caller wraps in
`asyncio.create_task(...)`).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from config import db

logger = logging.getLogger(__name__)


# Sentinel TTL — 180 days. Long enough to accumulate ≥5k labeled triplets
# even at low traffic; short enough that storage stays bounded. Set on
# the `expires_at` field; the TTL index is added in services/lifecycle.py.
_TTL_DAYS = 180


def _expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=_TTL_DAYS)


async def log_slate(
    *,
    user: Optional[dict],
    source: str,
    query: Optional[str],
    slate: List[Dict[str, Any]],
    query_meta: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Persist a search slate. Returns the session id (uuid) that the
    caller should round-trip back to the frontend so future user actions
    (click, shortlist, contact) can reference it via `log_action`.

    Returns None on failure — never raises (telemetry must not break the
    actual search path).
    """
    if not slate:
        return None
    try:
        sid = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        # Compact + truncate slate — only fields needed for future training.
        compact_slate: List[Dict[str, Any]] = []
        for i, row in enumerate(slate[:200]):  # hard cap
            compact_slate.append({
                "rank": i,
                "candidate_id": row.get("candidate_id") or row.get("id"),
                "score": row.get("score") or row.get("similarity") or row.get("relevance"),
                # Optional: features dict if caller wants to replay offline
                "features": row.get("features"),
            })
        await db.search_sessions.insert_one({
            "id": sid,
            "user_id": (user or {}).get("id"),
            "user_email": ((user or {}).get("email") or "").lower(),
            "user_role": (user or {}).get("role"),
            "ts": now,
            "expires_at": _expiry(),
            "source": source,
            "query": (query or "")[:500],
            "query_meta": query_meta or {},
            "slate": compact_slate,
            "actions": [],
        })
        return sid
    except Exception as e:
        logger.warning(f"[LTR-Telemetry] log_slate failed ({source}): {e}")
        return None


async def log_action(
    *,
    session_id: str,
    candidate_id: str,
    action: str,
    rank: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> bool:
    """Append a user action to an existing session. Returns True on
    successful append, False otherwise. Never raises."""
    if not session_id or not candidate_id or not action:
        return False
    try:
        evt: Dict[str, Any] = {
            "candidate_id": candidate_id,
            "action": action,
            "ts": datetime.now(timezone.utc),
        }
        if rank is not None:
            evt["rank"] = rank
        if extra:
            evt["extra"] = extra
        res = await db.search_sessions.update_one(
            {"id": session_id},
            {"$push": {"actions": evt}},
        )
        return res.modified_count > 0
    except Exception as e:
        logger.warning(f"[LTR-Telemetry] log_action failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# auto_log_action  —  Server-side LTR capture (no frontend wiring needed)
#
# Why this exists:
#   The frontend only round-trips `ltr_session_id` from the SemanticSearchPanel,
#   so the only action ever logged was `click_profile`. Real high-signal
#   actions (shortlist, contact, reject, hire) happen in the recruiter's
#   pipeline / applicants pages, none of which know about the session id.
#
#   Instead of wiring 8+ frontend files, we attach actions server-side:
#   when a candidate's stage advances, look up the most recent search_session
#   by this user (within the last hour) — if it exists, that's the search
#   that led to this action. If the candidate is in that session's slate,
#   record the rank too (which is what makes it a labeled training triplet).
#
# Pure side-effect, fire-and-forget, never blocks or raises.
# ─────────────────────────────────────────────────────────────────────────────

# Look back 1h — long enough to capture multi-step recruiter workflows
# (search → open profile → discuss → return → shortlist), short enough
# that we don't falsely attribute a Wednesday shortlist to last Monday's
# search.
_AUTO_LOG_LOOKBACK_HOURS = 1


async def auto_log_action(
    *,
    user: Optional[dict],
    candidate_id: str,
    action: str,
    extra: Optional[Dict[str, Any]] = None,
) -> bool:
    """Attach an action to the user's most recent recent search_session
    automatically — no session_id required at the call site.

    Returns True if a session was found and the action was appended,
    False otherwise (silently — telemetry must never break the real flow).
    """
    if not user or not user.get("id") or not candidate_id or not action:
        return False
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=_AUTO_LOG_LOOKBACK_HOURS)
        # Find the most recent session by this user in the lookback window
        sess = await db.search_sessions.find_one(
            {"user_id": user["id"], "ts": {"$gte": cutoff}},
            sort=[("ts", -1)],
            projection={"_id": 0, "id": 1, "slate.candidate_id": 1, "slate.rank": 1},
        )
        if not sess:
            return False
        # If the candidate appears in this session's slate, record its rank —
        # that's what turns the action into a labeled training triplet.
        rank: Optional[int] = None
        for row in (sess.get("slate") or []):
            if row.get("candidate_id") == candidate_id:
                rank = row.get("rank")
                break
        return await log_action(
            session_id=sess["id"],
            candidate_id=candidate_id,
            action=action,
            rank=rank,
            extra=extra,
        )
    except Exception as e:
        logger.warning(f"[LTR-Telemetry] auto_log_action failed: {e}")
        return False


# Mapping from pipeline stage transitions → LTR action labels.
# Used by routes/applications.py when a candidate's stage changes.
# Stages not in this map are skipped (no LTR signal).
STAGE_TO_LTR_ACTION: Dict[str, str] = {
    "shortlisted": "shortlist",
    "submitted_to_client": "contact",
    "interview": "contact",
    "offered": "hire",        # offer == strong positive signal
    "hired": "hire",
    "joined": "hire",
    "rejected": "reject",
    "employer_rejected": "reject",
    "dropped": "reject",
}
