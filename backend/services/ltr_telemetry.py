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
