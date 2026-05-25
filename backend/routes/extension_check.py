"""Extension — "Already in database" check endpoint (Phase 55.9 / Feb 2026).

Powers the v5.4.1 Chrome extension's green-badge feature on Naukri/LinkedIn
search results: shows recruiters which candidates they (or anyone) have
already captured, preventing wasted profile-view credits.

Endpoint: POST /api/extension/check-existing

Request:
    {
      "candidates": [
        {"name": "...", "headline": "...", "location": "..."},
        ...
      ]
    }

Response (index in each result MATCHES the input array index):
    {
      "results": [
        {"index": 0, "exists": true, "candidate_id": "...",
         "captured_at": "ISO", "match_confidence": "high|medium"},
        {"index": 1, "exists": false},
        ...
      ]
    }

Behavior:
  * Searches `candidate_bank` by case-insensitive first-token prefix
    (uses existing name_1 index), then post-filters with `_names_are_similar`
    — the same fuzzy logic that powers auto-merge dedupe.
  * Confidence:
      - `high`   = name matches AND (headline mentions current_employer
                    OR designation OR location matches)
      - `medium` = name matches alone

Allowlist:
  Controlled by env `EXTENSION_CHECK_EXISTING_ALLOWLIST` (comma-separated
  emails, or `*` for everyone). Default: empty → only the allowlisted users
  get real results; everyone else gets `exists:false` for every input
  (the extension falls back to its local cache, which is zero-risk).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config import db
from services.extension_service import _names_are_similar
from utils.auth import get_current_user


def _strict_name_match(name_a: str, name_b: str) -> bool:
    """
    STRICT name match — for the "Already in Database" badge specifically.

    Different from `_names_are_similar` (which is the dedup matcher — loose
    by design for recall). Here we need PRECISION: don't badge every
    "Manish" or "Akash" as already-saved when only ONE of them is captured.

    Rule (multi-token names — the common case):
      Require BOTH first AND last meaningful (≥3 char) tokens to match.
      Middle tokens are ignored entirely.

      Examples:
        "Akash Chavan"          ↔ "Akash Dhanraj Chavan"  ✓  (first+last match)
        "Manish Kumar Sehgal"   ↔ "Manish Sehgal"         ✓  (first+last match)
        "Manish Kumar Sehgal"   ↔ "Manish Kumar"          ✗  ("kumar" != "sehgal")
        "Manish Singh"          ↔ "Manish Kumar Singh"    ✓  (first+last match)
        "Akash Patil"           ↔ "Akash Chavan"          ✗  (different last name)
        "Rajesh Nayak"          ↔ "Rajesh More"           ✗

    Rule (single-token names — uncommon):
      Single-token name matches only single-token name with identical token,
      or a multi-token name where that token equals the first OR last token.

    Rule (typos / transliteration):
      Very high fuzzy ratio (≥ 0.92) — handles "Rajut" vs "Rajat" etc.
    """
    if not name_a or not name_b:
        return False
    import re as _re
    from difflib import SequenceMatcher as _SM

    def _clean(s: str) -> str:
        s = _re.sub(r"\b(mr|mrs|ms|dr|prof|shri|smt)\.?\b", " ", s.lower())
        s = _re.sub(r"[^a-z0-9\s]", " ", s)
        return _re.sub(r"\s+", " ", s).strip()

    a, b = _clean(name_a), _clean(name_b)
    if not a or not b:
        return False
    if a == b:
        return True

    # Significant tokens (≥3 chars, drops noise like "K" or "M")
    sig_a = [w for w in a.split() if len(w) >= 3]
    sig_b = [w for w in b.split() if len(w) >= 3]
    if not sig_a or not sig_b:
        # Fall back to all-token list for very short names
        sig_a = [w for w in a.split() if len(w) > 1]
        sig_b = [w for w in b.split() if len(w) > 1]
        if not sig_a or not sig_b:
            return False

    # MULTI-token both sides: require first AND last to match
    if len(sig_a) >= 2 and len(sig_b) >= 2:
        if sig_a[0] == sig_b[0] and sig_a[-1] == sig_b[-1]:
            return True
        # Fuzzy as a last resort (catches "Rajut Gupta" vs "Rajat Gupta")
        return _SM(None, a, b).ratio() >= 0.92

    # SINGLE-token on one or both sides
    if len(sig_a) == 1 and len(sig_b) == 1:
        return sig_a[0] == sig_b[0]
    # Single vs multi: the single token must equal the first OR last of the multi
    single, multi = (sig_a, sig_b) if len(sig_a) == 1 else (sig_b, sig_a)
    return single[0] == multi[0] or single[0] == multi[-1]

logger = logging.getLogger(__name__)

ext_check_router = APIRouter(prefix="/api/extension", tags=["Browser Extension"])


# ── Allowlist gating ─────────────────────────────────────────────────
def _is_user_allowed(user: dict) -> bool:
    raw = (os.environ.get("EXTENSION_CHECK_EXISTING_ALLOWLIST") or "").strip()
    if not raw:
        return False
    if raw == "*":
        return True
    allowlist = {e.strip().lower() for e in raw.split(",") if e.strip()}
    return (user.get("email") or "").strip().lower() in allowlist


# ── Schemas ──────────────────────────────────────────────────────────
class CandidateIn(BaseModel):
    name: str
    headline: Optional[str] = None
    location: Optional[str] = None


class CheckExistingRequest(BaseModel):
    candidates: List[CandidateIn] = Field(default_factory=list)


class CheckResult(BaseModel):
    index: int
    exists: bool
    candidate_id: Optional[str] = None
    captured_at: Optional[str] = None
    match_confidence: Optional[str] = None  # "high" | "medium"


class CheckExistingResponse(BaseModel):
    results: List[CheckResult]


# ── Helpers ──────────────────────────────────────────────────────────
def _first_significant_token(name: str) -> str:
    """Lowercased first non-trivial token. Honorifics stripped."""
    if not name:
        return ""
    cleaned = re.sub(r"\b(mr|mrs|ms|dr|prof|shri|smt)\.?\b", " ", name.lower())
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    tokens = [t for t in cleaned.split() if len(t) > 1]
    return tokens[0] if tokens else ""


def _headline_or_loc_hits(
    headline: Optional[str],
    in_location: Optional[str],
    bank_doc: dict,
) -> bool:
    """Cross-check candidate metadata vs DB record to bump confidence to high."""
    if not headline and not in_location:
        return False
    hay = " ".join([
        (headline or "").lower(),
        (in_location or "").lower(),
    ])
    for k in ("current_employer", "designation", "location", "headline"):
        v = (bank_doc.get(k) or "")
        if not v:
            continue
        v_low = v.lower().strip()
        if len(v_low) < 3:
            continue
        # Either side mentions the other → win
        if v_low in hay:
            return True
        # Or any 4+-char token from DB shows up in the input
        for tok in re.findall(r"[a-z]{4,}", v_low):
            if tok in hay:
                return True
    return False


async def _match_one(idx: int, c: CandidateIn) -> CheckResult:
    """Find best matching candidate_bank doc for one input candidate."""
    first_tok = _first_significant_token(c.name)
    if not first_tok or len(first_tok) < 2:
        return CheckResult(index=idx, exists=False)

    # Extract other significant tokens from the input name — we'll use them
    # to narrow the Mongo query so we don't scan past 40 unrelated "AKASH"
    # docs before reaching "Akash Dhanraj Chavan".
    import re as _re
    cleaned = _re.sub(r"\b(mr|mrs|ms|dr|prof|shri|smt)\.?\b", " ", c.name.lower())
    cleaned = _re.sub(r"[^a-z0-9\s]", " ", cleaned)
    all_tokens = [t for t in cleaned.split() if len(t) >= 3]
    other_tokens = [t for t in all_tokens if t != first_tok]

    # Build the query:
    #   - Always anchor on the first token
    #   - If we have other ≥3-char tokens (likely a last name), require ANY of
    #     them to appear in the DB name. This drops the candidate pool from
    #     thousands of "AKASH" → handful of "Akash ... <lastname>".
    prefix_pattern = _re.compile(rf"^{_re.escape(first_tok)}", _re.IGNORECASE)
    query: dict = {"name": prefix_pattern}
    if other_tokens:
        query["$and"] = [
            {"name": prefix_pattern},
            {"$or": [
                {"name": _re.compile(rf"\b{_re.escape(t)}", _re.IGNORECASE)}
                for t in other_tokens[:4]  # cap at 4 to keep regex cheap
            ]},
        ]
        # When using $and, the top-level "name" key is redundant
        query.pop("name", None)

    cursor = db.candidate_bank.find(
        query,
        {
            "_id": 0, "id": 1, "name": 1,
            "current_employer": 1, "designation": 1,
            "location": 1, "headline": 1,
            "created_at": 1, "captured_at": 1,
        },
    ).limit(40)

    best: Optional[dict] = None
    best_high = False

    async for doc in cursor:
        if not _strict_name_match(c.name, doc.get("name") or ""):
            continue
        high = _headline_or_loc_hits(c.headline, c.location, doc)
        if best is None or (high and not best_high):
            best = doc
            best_high = high
            if best_high:
                break  # high-confidence early exit

    if not best:
        return CheckResult(index=idx, exists=False)

    captured_at = (
        best.get("captured_at")
        or best.get("created_at")
        or None
    )
    return CheckResult(
        index=idx,
        exists=True,
        candidate_id=best.get("id"),
        captured_at=captured_at,
        match_confidence="high" if best_high else "medium",
    )


# ── Route ────────────────────────────────────────────────────────────
@ext_check_router.post("/check-existing", response_model=CheckExistingResponse)
async def check_existing(
    payload: CheckExistingRequest,
    user: dict = Depends(get_current_user),
):
    """Bulk check which candidates from a Naukri/LinkedIn search are already in our bank."""
    candidates = payload.candidates or []
    if not candidates:
        return CheckExistingResponse(results=[])

    # Gate: testing phase — only allowlisted users (default `admin@vhc.in`) see real matches
    if not _is_user_allowed(user):
        logger.info(
            "[CheckExisting] user=%s not in allowlist — returning all-false (extension falls back to local cache)",
            user.get("email"),
        )
        return CheckExistingResponse(
            results=[CheckResult(index=i, exists=False) for i in range(len(candidates))]
        )

    # Cap batch size to keep DB load predictable
    MAX_BATCH = 50
    candidates = candidates[:MAX_BATCH]

    results = await asyncio.gather(
        *(_match_one(i, c) for i, c in enumerate(candidates))
    )
    n_exists = sum(1 for r in results if r.exists)
    logger.info(
        "[CheckExisting] user=%s batch=%d hits=%d",
        user.get("email"), len(candidates), n_exists,
    )
    return CheckExistingResponse(results=list(results))
