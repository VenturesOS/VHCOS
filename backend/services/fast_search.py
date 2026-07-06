"""
fast_search.py — index-backed candidate quick search for VHC Talent OS
======================================================================

Replaces the hot path in routes/candidates.py where each search word
becomes 12 unanchored case-insensitive $regex conditions (multiplied by
synonym expansion). That shape forces a COLLSCAN over the entire
candidate_bank on every keystroke — and the endpoint then runs the same
filter a second time for count_documents().

This service assumes ensure_search_indexes_v2.py has been applied:
  • weighted text index  `candidate_search_text`
  • mirror fields        name_lower / email_lower / phone_normalized

Feature flag FAST_SEARCH=1 with automatic fallback: if the text index
is missing or the query errors, we return None and the caller falls
through to the legacy path. Zero-risk rollout.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

FAST_SEARCH_ENABLED = os.environ.get("FAST_SEARCH", "0") == "1"

# Fields returned to list views. Excludes raw_profile_text and other
# heavyweight blobs — trimming the payload matters as much as the scan.
LIST_PROJECTION = {
    "_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1,
    "headline": 1, "current_designation": 1, "designation": 1,
    "current_employer": 1, "current_company": 1,
    "current_location": 1, "location": 1,
    "key_skills": 1, "skills": 1,
    "total_experience_years": 1, "experience_years": 1,
    "notice_period": 1, "notice_period_days": 1,
    "current_salary": 1, "expected_salary": 1,
    "source": 1, "smart_tags": 1, "created_at": 1, "updated_at": 1,
    "enriched_seniority": 1, "enriched_function": 1, "enriched_location": 1,
}

_DIGITS = re.compile(r"\D+")


def normalize_phone(raw: str) -> str:
    """Match the backfill rule in ensure_search_indexes_v2.py."""
    digits = _DIGITS.sub("", raw or "")
    return digits[-10:] if len(digits) >= 10 else digits


def build_text_condition(q: str) -> Optional[Dict[str, Any]]:
    """
    Free-text → $text condition.

    Multi-word queries are quoted per word ("sap" "mm" "pune") which
    makes $text behave as AND — matching the recall the old
    per-word $and-of-$or regex gave, but index-backed and ranked.
    """
    words = [w for w in (q or "").split() if w.strip()]
    if not words:
        return None
    return {"$text": {"$search": " ".join(f'"{w}"' for w in words)}}


def exact_lookup_conditions(
    phone: Optional[str] = None,
    email: Optional[str] = None,
    name_prefix: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Index-backed replacements for the old case-insensitive regexes."""
    conds: List[Dict[str, Any]] = []
    if phone:
        digits = normalize_phone(phone)
        if digits:
            conds.append({"phone_normalized": digits})
    if email:
        conds.append({"email_lower": email.strip().lower()})
    if name_prefix:
        conds.append({"name_lower": {"$regex": f"^{re.escape(name_prefix.strip().lower())}"}})
    return conds


async def quick_search(
    db,
    *,
    search: Optional[str] = None,
    extra_conditions: Optional[List[Dict[str, Any]]] = None,
    page: int = 1,
    limit: int = 25,
    sort_recency_first: bool = False,
) -> Optional[Tuple[List[Dict[str, Any]], int]]:
    """
    Returns (candidates, total) or None → caller uses legacy path.

    extra_conditions: the fielded-filter conditions the existing endpoint
    already builds (location, company, skills, experience, source…).
    They are AND-ed with the text condition unchanged.
    """
    if not FAST_SEARCH_ENABLED:
        return None

    conditions: List[Dict[str, Any]] = list(extra_conditions or [])
    text_cond = build_text_condition(search) if search else None
    if text_cond:
        conditions.append(text_cond)

    match: Dict[str, Any] = {"$and": conditions} if conditions else {}

    pipeline: List[Dict[str, Any]] = [{"$match": match}]

    if text_cond:
        pipeline.append({"$addFields": {"_score": {"$meta": "textScore"}}})
        sort_stage = (
            {"created_at": -1} if sort_recency_first
            else {"_score": {"$meta": "textScore"}, "created_at": -1}
        )
    else:
        sort_stage = {"created_at": -1}

    skip = max(page - 1, 0) * limit
    pipeline.append({
        "$facet": {
            "data": [
                {"$sort": sort_stage},
                {"$skip": skip},
                {"$limit": limit},
                {"$project": LIST_PROJECTION},
            ],
            "total": [{"$count": "n"}],
        }
    })

    try:
        agg = await db.candidate_bank.aggregate(pipeline).to_list(1)
    except Exception as e:
        logger.warning("fast_search fell back to legacy path: %s", e)
        return None

    if not agg:
        return [], 0
    data = agg[0].get("data", [])
    total = (agg[0].get("total") or [{}])
    total_n = total[0].get("n", 0) if total else 0
    return data, total_n
