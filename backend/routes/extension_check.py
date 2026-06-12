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
import random
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


# ── Per-name bucket TTL cache ────────────────────────────────────────
# Buckets of candidate_bank docs keyed by the card-name's token signature
# (see `_bucket_query_for`). The extension re-scans the same search page
# several times (scroll / poll), so a short TTL cache turns repeat scans
# into pure-CPU work.
#
# Cache shape: { name_signature: (expires_at_epoch, [docs...]) }
# Bounded by _BUCKET_CACHE_MAX (LRU-ish via popitem on overflow).
_BUCKET_CACHE_TTL_S = 300        # 5 minutes
_BUCKET_CACHE_MAX = 512
_bucket_cache: dict[str, tuple[float, list[dict]]] = {}


def _cache_get(tok: str) -> Optional[list[dict]]:
    import time as _t
    entry = _bucket_cache.get(tok)
    if not entry:
        return None
    expires, docs = entry
    if _t.time() > expires:
        _bucket_cache.pop(tok, None)
        return None
    return docs


def _cache_put(tok: str, docs: list[dict]) -> None:
    import time as _t
    if len(_bucket_cache) >= _BUCKET_CACHE_MAX:
        # Evict the oldest entry (Python 3.7+ dicts preserve insertion order)
        try:
            _bucket_cache.pop(next(iter(_bucket_cache)))
        except StopIteration:
            pass
    _bucket_cache[tok] = (_t.time() + _BUCKET_CACHE_TTL_S, docs)


def _bucket_query_for(name: Optional[str]) -> tuple[str, Optional[dict], int]:
    """Build the per-card Mongo query for the fuzzy badge scan.

    Returns ``(cache_key, query, limit)``. ``query`` is None when the
    name has no usable token.

    Phase 57 (Jun 2026): replaces the old batched-$or-with-shared-800-cap
    approach that starved alphabetically-later names of their buckets
    (e.g. "akash"+"amit" docs exhausted the cap so "ramesh" got an empty
    — and then cached — bucket → no badge despite the profile being in DB).

    Query shape:
      * Multi-token card name ("Ramesh Kannan"):
          (name_lower ^ramesh AND (\bkannan OR name_lower is single-token))
          OR (name_lower ^kannan AND \bramesh)        ← reversed order
        Both branches are bounded by the `name_lower_idx` prefix B-tree.
        The "single-token DB name" clause keeps "Yash" (DB) matchable
        from card "Yash Vardhan" (the single-vs-multi name rule).
      * Single-token card name ("Yash"): plain prefix scan with a higher
        limit so "yash vardhan", "yash sharma", … are all in scope.
    """
    if not name:
        return "", None, 0
    cleaned = re.sub(r"\b(mr|mrs|ms|dr|prof|shri|smt)\.?\b", " ", name.lower())
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    tokens = [t for t in cleaned.split() if len(t) > 1]
    if not tokens:
        return "", None, 0
    first = tokens[0]
    others = [t for t in tokens[1:] if len(t) >= 3][:4]
    if not others:
        # Single usable token — prefix scan, generous bound (covers the
        # vast majority of first-name buckets in a ~130k-doc bank).
        return first, {"name_lower": {"$regex": f"^{re.escape(first)}"}}, 600

    other_words = [{"name_lower": {"$regex": rf"\b{re.escape(t)}"}} for t in others]
    branch_fwd = {
        "$and": [
            {"name_lower": {"$regex": f"^{re.escape(first)}"}},
            {"$or": other_words + [{"name_lower": {"$regex": r"^\S+$"}}]},
        ]
    }
    last = others[-1]
    branch_rev = {
        "$and": [
            {"name_lower": {"$regex": f"^{re.escape(last)}"}},
            {"name_lower": {"$regex": rf"\b{re.escape(first)}"}},
        ]
    }
    key = first + "|" + ",".join(sorted(others))
    return key, {"$or": [branch_fwd, branch_rev]}, 200


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
    # Stable Naukri Resdex candidate ID (from card `data-target-id` /
    # checkbox value — NOT the rotating URL `pid` query param). When
    # present, the badge endpoint resolves the card via a single indexed
    # `$in` lookup, skipping the fuzzy name-prefix scan entirely.
    naukri_id: Optional[str] = None
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
    # Optional — the current Naukri/LinkedIn URL the extension is scanning.
    # Used only for the audit log (helps admin reproduce the search).
    page_url: Optional[str] = None


class MatchedCandidate(BaseModel):
    """Subset of the matched DB candidate's fields — returned so the extension can do a final cross-check before badging."""
    name: Optional[str] = None
    current_employer: Optional[str] = None
    designation: Optional[str] = None
    location: Optional[str] = None
    experience_years: Optional[float] = None
    annual_ctc: Optional[float] = None
    education: Optional[str] = None
    naukri_profile_id: Optional[str] = None


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
    # Echoed DB fields so the extension can cross-check before badging
    matched_candidate: Optional[MatchedCandidate] = None


class CheckExistingResponse(BaseModel):
    results: List[CheckResult]
    # ID into `badge_audit` for this batch — extension v5.5.10+ uses this
    # in /api/extension/audit/feedback to report which results it actually
    # rendered. Null when no audit was written (audit is opt-in).
    audit_id: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────
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

# Strong signals that, together with name, are sufficient to declare a
# match. At least ONE strong signal must fire — name + designation +
# location alone is too weak (designation/location are very common
# co-occurrences for shared first+last name candidates).
_STRONG_SIGNALS = {"employer", "headline_employer", "ctc", "skills"}


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


# ──────────────────────────────────────────────────────────────────────
# V2 SCORING (Phase 56.2, Feb 2026) — dark-launched to admin only via
# EXTENSION_CHECK_V2_USERS env var. Same response shape, smarter recall.
#
# Why V2:
#   The original (V1) requires score ≥ 1.0 AND at least one "strong"
#   signal. On a Naukri search results page, most cards only expose
#   name + headline + location → V1 scores them at 0.75 → no badge.
#   Recall ends up at ~10-15% (1-2 out of 15 known-in-DB candidates).
#
# What V2 changes (backend-only, no extension update needed):
#   1. Loose name match — handles "Yash" ↔ "Yash Vardhan" (V1 strict
#      requires both first+last token match).
#   2. Smarter headline parsing — extracts designation/location/employer
#      from the card's headline string (e.g. "ML Engineer at TCS - Pune").
#   3. Rebalanced weights — location bumped 0.25 → 0.30 (it's at 99.7%
#      DB coverage, deserves more weight than V1's "weak" rating).
#   4. Threshold lowered 1.0 → 0.85 BUT a "≥1 corroborator beyond name"
#      gate is enforced, so name alone never badges.
#   5. Explicit-conflict rejection — even when score passes, reject if
#      card.employer clearly contradicts DB employer (e.g. card says
#      "Infosys" but DB says "TCS"), or experience diff > 5 years.
#   6. Stable Naukri ID match = always HIGH, ignores everything else.
#
# Expected recall lift: ~15% → ~85-100% with negligible precision loss.
# ──────────────────────────────────────────────────────────────────────

_V2_SIGNAL_WEIGHTS = {
    "name": 0.5,
    "employer": 0.6,
    "designation": 0.4,
    "ctc": 0.5,
    "experience": 0.4,
    "skills": 0.5,
    "education": 0.4,
    "location": 0.30,                  # was 0.25
    "headline_employer": 0.4,
    "headline_designation": 0.30,      # NEW — DB designation appears in card headline
    "headline_location": 0.15,         # NEW — DB location appears in card headline
}
_V2_BADGE_THRESHOLD = 0.85
_V2_HIGH_THRESHOLD = 1.20
# Corroborators considered identity-STRONG (Phase 57.2). Weak-grade name
# matches need at least one of these; experience/education/ctc/skills are
# too coincidence-prone to confirm a partial name on their own (live FP:
# card "Amit Saraswat" badged bank candidate "amit" via one shared generic
# skill — benchmark precision hits 1.000 with skills excluded).
_V2_STRONG_CORROBS = {
    "employer", "headline_employer",
    "designation", "headline_designation",
    "location", "headline_location",
}


def _loose_name_match_v2(name_a: str, name_b: str) -> int:
    """V2 name matcher — returns a GRADE instead of a bool (Phase 57.2):

        0 = no match    1 = weak match    2 = strong match

    Weak matches (grade 1) only badge with a STRONG corroborator — see the
    route's gating. Tuned against the 2,372-card audit benchmark
    (precision was 76.3%; all 71 wrong-person badges were leaks below):

      * MIDDLE-TOKEN VETO: "Mohd MONIS Siddiqui" ≠ "Mohd MOAZZAM Siddiqui"
        (first+last matched, but the real given names contradict)
      * INITIALS VETO: "Amit Saraswat" ≠ "Amit Kr" / "ASHOK M R" ≠
        "Ashok Subramani" — a 1-2 char token must match SOME other-side
        token's initial, else different person
      * FUZZY TIGHTENED: whole-string 0.80 → 0.84 AND last tokens ≥ 0.80
        ("Ramesh Kannan" ≠ "RAMESH KALIYAN", "Akash G. Bangalwar" ≠
        "Akash Gangwar"; "Rajut Gupta" ↔ "Rajat Gupta" still passes)
    """
    if not name_a or not name_b:
        return 0
    import re as _re
    from difflib import SequenceMatcher as _SM

    def _clean(s: str) -> str:
        s = _re.sub(r"\b(mr|mrs|ms|dr|prof|shri|smt)\.?\b", " ", s.lower())
        s = _re.sub(r"[^a-z0-9\s]", " ", s)
        return _re.sub(r"\s+", " ", s).strip()

    a_clean, b_clean = _clean(name_a), _clean(name_b)
    if not a_clean or not b_clean:
        return 0
    if a_clean == b_clean:
        return 2

    # De-spaced form (covers "A J I T H" → "ajith")
    def _despace_if_letter_split(s: str) -> str:
        toks = s.split()
        if len(toks) >= 3 and sum(1 for t in toks if len(t) == 1) / len(toks) >= 0.5:
            return "".join(toks)
        return s
    a_desp, b_desp = _despace_if_letter_split(a_clean), _despace_if_letter_split(b_clean)
    if a_desp == b_desp:
        return 2

    all_a, all_b = a_clean.split(), b_clean.split()

    # INITIALS-CONTRADICTION VETO (both directions): every 1-2 char token
    # must be the initial of some token on the other side.
    for toks, others in ((all_a, all_b), (all_b, all_a)):
        for t in toks:
            if len(t) <= 2 and others and not any(u[0] == t[0] for u in others):
                return 0

    # Significant tokens (≥3 chars)
    sig_a = [w for w in all_a if len(w) >= 3]
    sig_b = [w for w in all_b if len(w) >= 3]
    if not sig_a:
        sig_a = [w for w in all_a if len(w) > 1] or ([a_desp] if a_desp else [])
    if not sig_b:
        sig_b = [w for w in all_b if len(w) > 1] or ([b_desp] if b_desp else [])
    if not sig_a or not sig_b:
        return 0

    def _tok_ratio(x: str, y: str) -> float:
        return 1.0 if x == y else _SM(None, x, y).ratio()

    # Both multi-token
    if len(sig_a) >= 2 and len(sig_b) >= 2:
        short, long_ = sorted((sig_a, sig_b), key=len)
        worst = min(max(_tok_ratio(t, u) for u in long_) for t in short)
        if sig_a[0] == sig_b[0] and sig_a[-1] == sig_b[-1]:
            # first+last agree — but contradicting middle tokens mean a
            # DIFFERENT given name, not a variant of the same one
            return 0 if worst < 0.60 else 2
        if worst >= 0.84:
            return 2  # all tokens have counterparts (reorder / minor typos)
        if (
            _SM(None, a_clean, b_clean).ratio() >= 0.84
            and _tok_ratio(sig_a[-1], sig_b[-1]) >= 0.80
        ):
            return 1  # typo tolerance, surname must broadly agree
        return 0

    # Both single-token
    if len(sig_a) == 1 and len(sig_b) == 1:
        if sig_a[0] == sig_b[0]:
            return 2
        return 1 if _SM(None, sig_a[0], sig_b[0]).ratio() >= 0.88 else 0

    # Single vs multi ("Yash" ↔ "Yash Vardhan") — inherently weak evidence
    single, multi = (sig_a, sig_b) if len(sig_a) == 1 else (sig_b, sig_a)
    if single[0] == multi[0] or single[0] == multi[-1]:
        return 1
    return 1 if _SM(None, a_clean, b_clean).ratio() >= 0.84 else 0


def _headline_contains(headline: Optional[str], needle: Optional[str], min_len: int = 4) -> bool:
    """Check if a normalised needle (e.g. DB designation/location) appears
    in the card's headline string. Used for the V2 headline_* signals."""
    if not headline or not needle:
        return False
    h = _norm_str(headline)
    n = _norm_str(needle)
    if not h or not n or len(n) < min_len:
        return False
    # Whole-word presence to avoid spurious substring matches
    return bool(re.search(rf"\b{re.escape(n)}\b", h))


def _has_explicit_conflict_v2(c: CandidateIn, doc: dict) -> Optional[str]:
    """Return a string reason if card+DB explicitly contradict, else None.
    Only checks fields where BOTH sides have a meaningful value — absence
    is never a conflict (DB might just be incomplete)."""
    # Employer conflict
    ce, de = _norm_str(c.current_employer), _norm_str(doc.get("current_employer"))
    if ce and de and len(ce) > 2 and len(de) > 2:
        # Strip corp suffixes for comparison
        for sfx in (" pvt ltd", " private limited", " ltd", " limited", " inc",
                    " corp", " corporation", " llp", " india"):
            ce = ce.replace(sfx, "").strip()
            de = de.replace(sfx, "").strip()
        if ce != de and ce not in de and de not in ce:
            return f"employer conflict ({c.current_employer!r} vs {doc.get('current_employer')!r})"
    # Experience > 5 years apart (allow some noise — Naukri rounding)
    if c.experience_years is not None and doc.get("experience_years") is not None:
        try:
            if abs(float(c.experience_years) - float(doc["experience_years"])) > 5.0:
                return f"experience conflict ({c.experience_years}y vs {doc['experience_years']}y)"
        except (TypeError, ValueError):
            pass
    return None


def _score_match_v2(c: CandidateIn, doc: dict) -> tuple[float, List[str]]:
    """V2 scoring — includes V1 signals + headline cross-checks + rebalanced
    location weight. Score range 0 - ~2.0."""
    signals: List[str] = ["name"]
    score = _V2_SIGNAL_WEIGHTS["name"]

    # Direct employer (best) or headline-extracted (fallback)
    if _employer_matches(c.current_employer, doc.get("current_employer")):
        score += _V2_SIGNAL_WEIGHTS["employer"]; signals.append("employer")
    elif _headline_mentions_employer(c.headline, doc.get("current_employer")):
        score += _V2_SIGNAL_WEIGHTS["headline_employer"]; signals.append("headline_employer")

    # Direct designation
    if _designation_matches(c.designation, doc.get("designation")):
        score += _V2_SIGNAL_WEIGHTS["designation"]; signals.append("designation")
    # NEW: headline-extracted designation (e.g. "ML Engineer at TCS - Pune")
    elif _headline_contains(c.headline, doc.get("designation"), min_len=4):
        score += _V2_SIGNAL_WEIGHTS["headline_designation"]; signals.append("headline_designation")

    if _ctc_matches(c.annual_ctc, doc.get("annual_ctc") or doc.get("current_ctc")):
        score += _V2_SIGNAL_WEIGHTS["ctc"]; signals.append("ctc")

    if _experience_matches(c.experience_years,
                           doc.get("experience_years") or doc.get("total_experience")):
        score += _V2_SIGNAL_WEIGHTS["experience"]; signals.append("experience")

    if _skills_overlap(c.skills, doc.get("skills")):
        score += _V2_SIGNAL_WEIGHTS["skills"]; signals.append("skills")

    if _education_matches(c.education, doc.get("education")):
        score += _V2_SIGNAL_WEIGHTS["education"]; signals.append("education")

    # Direct location
    if _location_matches(c.location, doc.get("location")):
        score += _V2_SIGNAL_WEIGHTS["location"]; signals.append("location")
    # NEW: DB location keyword in card headline ("...- Pune")
    elif _headline_contains(c.headline, doc.get("location"), min_len=3):
        score += _V2_SIGNAL_WEIGHTS["headline_location"]; signals.append("headline_location")

    return score, signals


def _is_v2_user(user: dict) -> bool:
    """Gate for the dark-launched V2 scoring path. Set env
    EXTENSION_CHECK_V2_USERS=admin@vhc.in,alice@vhc.in (or `*` for all).
    Default: empty → no one gets V2 (everyone uses V1)."""
    raw = (os.environ.get("EXTENSION_CHECK_V2_USERS") or "").strip()
    if not raw:
        return False
    if raw == "*":
        return True
    allowed = {e.strip().lower() for e in raw.split(",") if e.strip()}
    return (user.get("email") or "").strip().lower() in allowed



# ── Route ────────────────────────────────────────────────────────────
# PERF NOTE
# ----------
# Earlier this endpoint did 1 Mongo query per candidate. For a 25-card
# Naukri search results page that meant 25 round-trips to Atlas × ~100-
# 300ms RTT = a 2-4 second wall-clock latency, which made badges appear
# slowly or not at all.
#
# Phase 55.10 (Feb 2026) — three layered optimizations:
#   1. FAST PATH: candidates with a stable Naukri Resdex ID (scraped from
#      the card's `data-target-id`, NOT the rotating URL `pid` token)
#      resolve via ONE indexed `$in` lookup on `naukri_profile_id` /
#      `naukri_id`. Most Naukri cards hit this path.
#   2. FUZZY PATH: cards without a Naukri ID fall through to the existing
#      union'd `name_lower` prefix scan — but now backed by a 5-min TTL
#      in-memory bucket cache, so popular first-names like "Akash" or
#      "Rahul" skip Mongo entirely after the first request.
#   3. Per-batch result-building deduplicated via `_build_match_result`.
#
# Net effect on a 25-card Naukri page (all cards have Resdex IDs):
#   2.4s (1 query per card) → 250ms (1 union query) → ~30ms (fast path)
def _build_match_result(
    idx: int,
    c: CandidateIn,
    best_doc: dict,
    best_score: float,
    best_signals: List[str],
    web_base: str,
    high_threshold: float = _HIGH_THRESHOLD,
) -> CheckResult:
    """Shape a CheckResult from a matched candidate_bank doc.

    Used by both the fast (`naukri_id` $in) and fuzzy (name-prefix scan)
    paths so the response shape stays identical regardless of how the
    match was found. `high_threshold` parameter lets V1 and V2 callers
    use their own confidence-tier boundaries (V1=1.3, V2=1.20).
    """
    captured_at = best_doc.get("captured_at") or best_doc.get("created_at") or None
    confidence = "high" if best_score >= high_threshold else "medium"
    cid = best_doc.get("id")
    profile_url = f"{web_base}/candidate-bank?candidateId={cid}" if cid else None

    # Normalise education to a single string for the extension's cross-check
    raw_edu = best_doc.get("education")
    edu_str: Optional[str] = None
    if isinstance(raw_edu, str):
        edu_str = raw_edu
    elif isinstance(raw_edu, list) and raw_edu:
        parts: list[str] = []
        for e in raw_edu:
            if isinstance(e, str):
                parts.append(e)
            elif isinstance(e, dict):
                parts.append(" ".join(filter(None, [
                    str(e.get("degree", "") or ""),
                    str(e.get("institute", "") or e.get("university", "") or ""),
                ])).strip())
        edu_str = " | ".join(p for p in parts if p) or None

    matched_candidate = MatchedCandidate(
        name=best_doc.get("name"),
        current_employer=best_doc.get("current_employer"),
        designation=best_doc.get("designation"),
        location=best_doc.get("location"),
        experience_years=best_doc.get("experience_years") or best_doc.get("total_experience"),
        annual_ctc=best_doc.get("annual_ctc") or best_doc.get("current_ctc"),
        education=edu_str,
        naukri_profile_id=(
            best_doc.get("naukri_profile_id")
            or best_doc.get("naukri_id")
            or best_doc.get("profile_id")
        ),
    )
    return CheckResult(
        index=idx,
        exists=True,
        candidate_id=cid,
        captured_at=captured_at,
        match_confidence=confidence,
        match_score=round(best_score, 2),
        matched_signals=best_signals,
        profile_url=profile_url,
        matched_candidate=matched_candidate,
    )


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

    import time as _time

    t0 = _time.time()
    web_base = (os.environ.get("SITE_URL") or "https://ventureshrd.com").rstrip("/")

    # V2 dark-launch (Phase 56.2) — admin-only smarter recall path
    use_v2 = _is_v2_user(user)
    name_match_fn = _loose_name_match_v2 if use_v2 else _strict_name_match
    score_fn = _score_match_v2 if use_v2 else _score_match
    badge_thr = _V2_BADGE_THRESHOLD if use_v2 else _BADGE_THRESHOLD
    high_thr = _V2_HIGH_THRESHOLD if use_v2 else _HIGH_THRESHOLD

    # Pre-allocate results list — fast-path fills some indices, fuzzy fills the rest.
    results_by_idx: dict[int, CheckResult] = {}
    # Audit tracking — populated by both fast-path and fuzzy-path branches
    best_doc_by_idx: dict[int, Optional[dict]] = {}
    conflicts_by_idx: dict[int, Optional[str]] = {}

    # ── FAST PATH: stable Naukri Resdex ID ($in indexed lookup) ──
    # Naukri search cards expose a stable `data-target-id` Resdex ID that
    # survives the rotating URL `pid` token. The extension scrapes it
    # into `candidate.naukri_id`. When present, ONE indexed $in lookup on
    # both `naukri_profile_id` (used by the capture path) and `naukri_id`
    # (used by some legacy writes) resolves most cards on a typical page,
    # bypassing the fuzzy name-prefix scan entirely.
    # Typical impact: 25-card page goes from 300-600ms → 20-40ms.
    naukri_id_to_idx: dict[str, list[int]] = {}
    for i, c in enumerate(candidates):
        if c.naukri_id:
            naukri_id_to_idx.setdefault(c.naukri_id, []).append(i)

    if naukri_id_to_idx:
        nids = list(naukri_id_to_idx.keys())
        projection = {
            "_id": 0, "id": 1, "name": 1, "name_lower": 1,
            "current_employer": 1, "designation": 1,
            "location": 1, "headline": 1,
            "experience_years": 1, "total_experience": 1,
            "annual_ctc": 1, "current_ctc": 1,
            "skills": 1, "education": 1,
            "created_at": 1, "captured_at": 1,
            "naukri_profile_id": 1, "naukri_id": 1, "profile_id": 1,
        }
        fast_hits = await db.candidate_bank.find(
            {"$or": [
                {"naukri_profile_id": {"$in": nids}},
                {"naukri_id": {"$in": nids}},
            ]},
            projection,
        ).to_list(len(nids) * 2)

        # Map each hit back to every candidate-index that shared that nid
        for doc in fast_hits:
            doc_nid = (
                doc.get("naukri_profile_id")
                or doc.get("naukri_id")
                or doc.get("profile_id")
            )
            if not doc_nid or doc_nid not in naukri_id_to_idx:
                continue
            for idx in naukri_id_to_idx[doc_nid]:
                if idx in results_by_idx:
                    continue  # already resolved (first-write-wins)
                # Stable Naukri ID match = definitive — score it for
                # completeness but always badge as 'high' confidence.
                score, signals = score_fn(candidates[idx], doc)
                signals = (signals or []) + ["naukri_id"]
                results_by_idx[idx] = _build_match_result(
                    idx, candidates[idx], doc, max(score, high_thr),
                    signals, web_base, high_threshold=high_thr,
                )
                best_doc_by_idx[idx] = doc  # audit trail

    # ── FUZZY PATH: per-card refined name queries (parallel) ──
    # Phase 57 (Jun 2026) recall fix. The previous implementation ran ONE
    # $or query over every first-name token in the batch with a SHARED
    # 800-doc cap. On a page mixing popular first names ("akash" alone
    # has ~580 docs, "rahul" ~1,237) the cap was exhausted by the
    # alphabetically-first index ranges and later names got EMPTY buckets
    # — which were then TTL-cached for 5 minutes. Net effect: candidates
    # demonstrably in the DB never badged ("Ramesh Kannan" bug). Now every
    # unresolved card gets its OWN small indexed query (see
    # `_bucket_query_for`), all fired in parallel via asyncio.gather —
    # no shared cap, no starvation, less data on the wire.
    unresolved: list[tuple[int, CandidateIn]] = [
        (i, c) for i, c in enumerate(candidates) if i not in results_by_idx
    ]
    n_cache_hits = 0

    _FUZZY_PROJECTION = {
        "_id": 0, "id": 1, "name": 1, "name_lower": 1,
        "current_employer": 1, "designation": 1,
        "location": 1, "headline": 1,
        "experience_years": 1, "total_experience": 1,
        "annual_ctc": 1, "current_ctc": 1,
        "skills": 1, "education": 1,
        "created_at": 1, "captured_at": 1,
        "naukri_profile_id": 1, "naukri_id": 1, "profile_id": 1,
    }

    async def _fetch_bucket(c: CandidateIn) -> list[dict]:
        nonlocal n_cache_hits
        key, query, lim = _bucket_query_for(c.name)
        if query is None:
            return []
        cached = _cache_get(key)
        if cached is not None:
            n_cache_hits += 1
            return cached
        # `.hint("name_lower_idx")` forces the prefix index — without it
        # Atlas's planner occasionally picks COLLSCAN for $or queries.
        try:
            docs = await db.candidate_bank.find(
                query, _FUZZY_PROJECTION,
            ).hint("name_lower_idx").limit(lim).to_list(lim)
        except Exception:
            # Index missing (e.g. fresh deploy before create_indexes ran)
            # → fall back to unhinted query so the endpoint still works.
            docs = await db.candidate_bank.find(
                query, _FUZZY_PROJECTION,
            ).limit(lim).to_list(lim)
        _cache_put(key, docs)
        return docs

    buckets: list[list[dict]] = (
        await asyncio.gather(*[_fetch_bucket(c) for _, c in unresolved])
        if unresolved else []
    )

    # Score each unresolved candidate against its own bucket of docs
    for (idx, c), bucket in zip(unresolved, buckets):
        best_doc: Optional[dict] = None
        best_score: float = 0.0
        best_signals: List[str] = []
        best_grade: int = 0
        last_conflict: Optional[str] = None
        for doc in bucket:
            grade = name_match_fn(c.name, doc.get("name") or "")
            if not grade:
                continue
            # V2: reject docs with explicit field-level conflicts (employer
            # mismatch, experience > 5y apart) BEFORE scoring. Cheaper than
            # scoring then rejecting; also keeps the precision floor intact.
            if use_v2:
                conflict = _has_explicit_conflict_v2(c, doc)
                if conflict:
                    last_conflict = conflict  # remember last rejection reason for audit
                    continue
            score, signals = score_fn(c, doc)
            if score > best_score:
                best_score = score
                best_signals = signals
                best_doc = doc
                best_grade = int(grade)
                if score >= high_thr:
                    break

        best_doc_by_idx[idx] = best_doc
        conflicts_by_idx[idx] = last_conflict if best_doc is None else None

        # V2 guard: at least one corroborating signal beyond `name` must
        # fire. Prevents the lower threshold (0.85) from badging on name
        # alone (which never happens at 1.0 V1 threshold because
        # `name` weight is only 0.5).
        v2_has_corroborator = use_v2 and best_signals and len(best_signals) >= 2
        # Phase 57.2 precision gate: WEAK-grade name matches (single-token
        # side / fuzzy typo-tolerance) additionally need a STRONG
        # corroborator. Benchmark showed experience/education/ctc
        # coincidences alone produced wrong-person badges.
        if use_v2 and v2_has_corroborator and best_grade < 2:
            v2_has_corroborator = any(s in _V2_STRONG_CORROBS for s in best_signals)

        if best_doc is None or best_score < badge_thr or (use_v2 and not v2_has_corroborator):
            results_by_idx[idx] = CheckResult(
                index=idx,
                exists=False,
                match_score=round(best_score, 2) if best_doc else None,
                matched_signals=best_signals if best_doc else None,
            )
            continue

        results_by_idx[idx] = _build_match_result(
            idx, c, best_doc, best_score, best_signals, web_base,
            high_threshold=high_thr,
        )

    # Re-emit results in input order
    results: list[CheckResult] = [results_by_idx[i] for i in range(len(candidates))]

    took_ms = int((_time.time() - t0) * 1000)
    n_exists = sum(1 for r in results if r.exists)
    n_fast = sum(1 for r in results if r.exists and r.matched_signals and "naukri_id" in r.matched_signals)
    logger.info(
        "[CheckExisting%s] user=%s batch=%d hits=%d (fast=%d) cache_hits=%d/%d took=%dms",
        "-V2" if use_v2 else "",
        user.get("email"), len(candidates), n_exists, n_fast,
        n_cache_hits, len(unresolved),
        took_ms,
    )

    # ─── Phase 56.3 audit log (fire-and-forget) ────────────────────────
    # Same allowlist as V2. With the team-wide rollout
    # (EXTENSION_CHECK_V2_USERS=*) audit docs are ~16KB each, so
    # EXTENSION_CHECK_AUDIT_SAMPLE (0.0-1.0, default 1.0) caps storage
    # growth: 0.3 ≈ every 3rd scan audited — plenty for benchmarking.
    audit_id: Optional[str] = None
    try:
        _sample = float(os.environ.get("EXTENSION_CHECK_AUDIT_SAMPLE", "1.0") or 1.0)
    except ValueError:
        _sample = 1.0
    if use_v2 and (_sample >= 1.0 or random.random() < _sample):
        try:
            import asyncio as _asyncio
            from routes.badge_audit import write_audit_doc
            # Synchronous so we get the audit_id back into the response
            # (extension uses it to call /audit/feedback later). The
            # write itself is ~5ms — well within tolerance.
            audit_id = await write_audit_doc(
                user=user,
                used_v2=use_v2,
                candidates_in=candidates,
                results_out=results,
                docs_by_idx=best_doc_by_idx,
                conflicts_by_idx=conflicts_by_idx,
                page_url=getattr(payload, "page_url", None),
                took_ms=took_ms,
            )
        except Exception as _e:
            logger.warning(f"[CheckExisting] audit write failed: {_e}")

    return CheckExistingResponse(results=results, audit_id=audit_id)
