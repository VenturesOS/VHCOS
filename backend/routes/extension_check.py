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
    # Corroborating signals (any subset — extension sends what's visible
    # on the Naukri/LinkedIn card). The badge now REQUIRES name + at
    # least one strong signal match to fire.
    current_employer: Optional[str] = None
    designation: Optional[str] = None
    experience_years: Optional[float] = None  # e.g. 2.07 from "2y 7m"
    annual_ctc: Optional[float] = None        # in INR (₹ 4.20 Lacs → 420000)
    skills: Optional[List[str]] = None
    education: Optional[str] = None
    notice_period: Optional[str] = None


class CheckExistingRequest(BaseModel):
    candidates: List[CandidateIn] = Field(default_factory=list)


class CheckResult(BaseModel):
    index: int
    exists: bool
    candidate_id: Optional[str] = None
    captured_at: Optional[str] = None
    match_confidence: Optional[str] = None  # "high" | "medium"
    matched_signals: Optional[List[str]] = None  # debug: which signals fired
    match_score: Optional[float] = None  # 0.0–1.0
    # Server-built deep-link so the extension never has to guess the
    # frontend URL from a (possibly proxied) backend API host.
    profile_url: Optional[str] = None


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


# ── Multi-signal scoring ─────────────────────────────────────────────
# Each signal contributes a weight when it matches. Threshold to badge
# is 1.0 — name match alone (weight 0.5) is NOT enough; needs at least
# one corroborating signal worth ≥0.5.
_SIGNAL_WEIGHTS = {
    "name": 0.5,        # baseline — required, but alone is insufficient
    "employer": 0.6,    # strong: same company is a near-certain co-signal
    "designation": 0.4,
    "ctc": 0.5,         # within ±20%
    "experience": 0.4,  # within ±1 year
    "skills": 0.5,      # ≥30% overlap on listed skills
    "education": 0.4,
    "location": 0.25,   # weak (Pune has many Akashes)
    "headline_employer": 0.4,  # employer mentioned in headline (when not parsed)
}

# Threshold (out of 1.6 max) to declare a match. name (0.5) + any one
# of employer/ctc/skills (≥ 0.5) clears 1.0. Two weak signals (e.g.
# designation 0.4 + location 0.25) won't, which is the desired behavior.
_BADGE_THRESHOLD = 1.0
_HIGH_THRESHOLD = 1.3


def _norm_str(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s.lower())).strip()


def _employer_matches(in_emp: Optional[str], db_emp: Optional[str]) -> bool:
    a, b = _norm_str(in_emp), _norm_str(db_emp)
    if not a or not b:
        return False
    if a == b:
        return True
    # Strip common corp suffixes
    for suffix in (" pvt ltd", " private limited", " ltd", " limited", " inc",
                   " corp", " corporation", " llp", " india"):
        a = a.replace(suffix, "").strip()
        b = b.replace(suffix, "").strip()
    if a == b:
        return True
    # One being a substring of the other (≥4 chars)
    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
        return True
    return False


def _designation_matches(in_d: Optional[str], db_d: Optional[str]) -> bool:
    a, b = _norm_str(in_d), _norm_str(db_d)
    if not a or not b:
        return False
    if a == b:
        return True
    # Token overlap ≥ 1 non-trivial word
    ta = {w for w in a.split() if len(w) >= 4}
    tb = {w for w in b.split() if len(w) >= 4}
    return bool(ta & tb)


def _ctc_matches(in_ctc: Optional[float], db_ctc: Optional[float]) -> bool:
    """CTC within ±20% (handles imprecise Naukri rounding like 4.2 → 420000)."""
    if not in_ctc or not db_ctc:
        return False
    try:
        a, b = float(in_ctc), float(db_ctc)
    except (TypeError, ValueError):
        return False
    if a <= 0 or b <= 0:
        return False
    smaller, larger = min(a, b), max(a, b)
    return (larger - smaller) / larger <= 0.20


def _experience_matches(in_exp: Optional[float], db_exp: Optional[float]) -> bool:
    """Within ±1 year."""
    if in_exp is None or db_exp is None:
        return False
    try:
        return abs(float(in_exp) - float(db_exp)) <= 1.0
    except (TypeError, ValueError):
        return False


def _skills_overlap(in_skills: Optional[List[str]], db_skills) -> bool:
    """≥30% of the input skills appear in the DB candidate's skill set."""
    if not in_skills:
        return False
    # DB may store skills as list of strings, or list of dicts {name: ...},
    # or a single comma-separated string. Normalise all to a set.
    db_set: set[str] = set()
    if isinstance(db_skills, list):
        for s in db_skills:
            if isinstance(s, str):
                db_set.add(_norm_str(s))
            elif isinstance(s, dict):
                db_set.add(_norm_str(s.get("name") or s.get("skill") or ""))
    elif isinstance(db_skills, str):
        for s in db_skills.split(","):
            db_set.add(_norm_str(s))
    db_set.discard("")
    if not db_set:
        return False
    in_set = {_norm_str(s) for s in in_skills if s}
    in_set.discard("")
    if not in_set:
        return False
    hits = sum(1 for s in in_set if any(s in d or d in s for d in db_set))
    return hits / max(len(in_set), 1) >= 0.30


def _education_matches(in_edu: Optional[str], db_edu) -> bool:
    a = _norm_str(in_edu)
    if not a:
        return False
    # DB may be string, list of strings, or list of dicts
    db_str = ""
    if isinstance(db_edu, list):
        parts = []
        for e in db_edu:
            if isinstance(e, str):
                parts.append(e)
            elif isinstance(e, dict):
                parts.extend([
                    str(e.get("institute", "")),
                    str(e.get("university", "")),
                    str(e.get("degree", "")),
                ])
        db_str = _norm_str(" ".join(parts))
    elif isinstance(db_edu, str):
        db_str = _norm_str(db_edu)
    if not db_str:
        return False
    # Any 6+-char token from input education appearing in DB
    for tok in re.findall(r"[a-z]{6,}", a):
        if tok in db_str:
            return True
    return False


def _location_matches(in_loc: Optional[str], db_loc: Optional[str]) -> bool:
    a, b = _norm_str(in_loc), _norm_str(db_loc)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _headline_mentions_employer(headline: Optional[str], db_emp: Optional[str]) -> bool:
    h, e = _norm_str(headline), _norm_str(db_emp)
    if not h or not e or len(e) < 4:
        return False
    return e in h


def _score_match(c: CandidateIn, doc: dict) -> tuple[float, List[str]]:
    """Compute a 0–~1.6 match score + list of signals that fired."""
    signals: List[str] = ["name"]
    score = _SIGNAL_WEIGHTS["name"]

    if _employer_matches(c.current_employer, doc.get("current_employer")):
        score += _SIGNAL_WEIGHTS["employer"]; signals.append("employer")
    elif _headline_mentions_employer(c.headline, doc.get("current_employer")):
        # Weaker — headline cross-reference when employer field wasn't parsed
        score += _SIGNAL_WEIGHTS["headline_employer"]; signals.append("headline_employer")

    if _designation_matches(c.designation, doc.get("designation")):
        score += _SIGNAL_WEIGHTS["designation"]; signals.append("designation")

    if _ctc_matches(c.annual_ctc, doc.get("annual_ctc") or doc.get("current_ctc")):
        score += _SIGNAL_WEIGHTS["ctc"]; signals.append("ctc")

    if _experience_matches(c.experience_years, doc.get("experience_years")
                            or doc.get("total_experience")):
        score += _SIGNAL_WEIGHTS["experience"]; signals.append("experience")

    if _skills_overlap(c.skills, doc.get("skills")):
        score += _SIGNAL_WEIGHTS["skills"]; signals.append("skills")

    if _education_matches(c.education, doc.get("education")):
        score += _SIGNAL_WEIGHTS["education"]; signals.append("education")

    if _location_matches(c.location, doc.get("location")):
        score += _SIGNAL_WEIGHTS["location"]; signals.append("location")

    return score, signals


def _headline_or_loc_hits(
    headline: Optional[str],
    in_location: Optional[str],
    bank_doc: dict,
) -> bool:
    """Legacy helper — kept for backwards compat with any other callers."""
    if not headline and not in_location:
        return False
    hay = " ".join([
        (headline or "").lower(),
        (in_location or "").lower(),
    ])
    for k in ("current_employer", "designation", "location", "headline"):
        v = (bank_doc.get(k) or "")
        if not v or len(str(v)) < 3:
            continue
        if str(v).lower().strip() in hay:
            return True
    return False


async def _match_one(idx: int, c: CandidateIn) -> CheckResult:
    """Find best matching candidate_bank doc for one input candidate.

    Returns `exists=True` ONLY when name match + at least one strong
    corroborating signal (employer / ctc / skills / etc.) push the
    composite score above the badge threshold."""
    first_tok = _first_significant_token(c.name)
    if not first_tok or len(first_tok) < 2:
        return CheckResult(index=idx, exists=False)

    # Narrow the Mongo pool by requiring at least one non-first-name token
    # from the input to appear in the DB name. Drops candidate pool from
    # thousands of "AKASH" → handful of "Akash ... <lastname>".
    import re as _re
    cleaned = _re.sub(r"\b(mr|mrs|ms|dr|prof|shri|smt)\.?\b", " ", c.name.lower())
    cleaned = _re.sub(r"[^a-z0-9\s]", " ", cleaned)
    all_tokens = [t for t in cleaned.split() if len(t) >= 3]
    other_tokens = [t for t in all_tokens if t != first_tok]

    prefix_pattern = _re.compile(rf"^{_re.escape(first_tok)}", _re.IGNORECASE)
    query: dict = {"name": prefix_pattern}
    if other_tokens:
        query["$and"] = [
            {"name": prefix_pattern},
            {"$or": [
                {"name": _re.compile(rf"\b{_re.escape(t)}", _re.IGNORECASE)}
                for t in other_tokens[:4]
            ]},
        ]
        query.pop("name", None)

    cursor = db.candidate_bank.find(
        query,
        {
            "_id": 0, "id": 1, "name": 1,
            "current_employer": 1, "designation": 1,
            "location": 1, "headline": 1,
            "experience_years": 1, "total_experience": 1,
            "annual_ctc": 1, "current_ctc": 1,
            "skills": 1, "education": 1,
            "created_at": 1, "captured_at": 1,
        },
    ).limit(40)

    # Score every name-matching doc, pick the highest scorer
    best_doc: Optional[dict] = None
    best_score: float = 0.0
    best_signals: List[str] = []

    async for doc in cursor:
        if not _strict_name_match(c.name, doc.get("name") or ""):
            continue
        score, signals = _score_match(c, doc)
        if score > best_score:
            best_score = score
            best_signals = signals
            best_doc = doc
            if score >= _HIGH_THRESHOLD:
                break  # excellent match — stop scanning

    # Below badge threshold → no false positive. NAME-only matches are
    # treated as misses by design (too many shared first+last names).
    if best_doc is None or best_score < _BADGE_THRESHOLD:
        return CheckResult(
            index=idx,
            exists=False,
            match_score=round(best_score, 2) if best_doc else None,
            matched_signals=best_signals if best_doc else None,
        )

    captured_at = best_doc.get("captured_at") or best_doc.get("created_at") or None
    confidence = "high" if best_score >= _HIGH_THRESHOLD else "medium"
    cid = best_doc.get("id")
    # SITE_URL is the canonical frontend URL (e.g. https://ventureshrd.com).
    # Used so the extension never has to guess the web URL from a possibly
    # proxied API host (e.g. a Cloudflare Worker).
    web_base = (os.environ.get("SITE_URL") or "https://ventureshrd.com").rstrip("/")
    profile_url = f"{web_base}/candidate-bank?candidateId={cid}" if cid else None
    return CheckResult(
        index=idx,
        exists=True,
        candidate_id=cid,
        captured_at=captured_at,
        match_confidence=confidence,
        match_score=round(best_score, 2),
        matched_signals=best_signals,
        profile_url=profile_url,
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
