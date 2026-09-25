"""Versioned identity decisions for extension search cards.

POST /api/extension/check-existing returns one result per input, maximum 50.
The backend owns canonicalization, candidate retrieval, ranking and decisions.
URLs are navigation-only, including URL-derived identifiers. No trusted
provider verifier is enabled, so this adapter returns review suggestions,
never `exists=true`. Scores are evidence points, not probabilities.

The existing EXTENSION_CHECK_EXISTING_ALLOWLIST controls rollout. Disabled
checks are explicit (`service_status=disabled`), never false database negatives.
Earlier pure scoring helpers remain for historical regression/benchmark tests;
the HTTP handler does not call the legacy matcher or its name-bucket cache.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
from typing import List, Optional, Literal, Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config import db
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
class ExperienceContextIn(BaseModel):
    """Bounded, non-contact slice of a prior employment entry."""
    company: Optional[str] = Field(default=None, max_length=500)
    company_name: Optional[str] = Field(default=None, max_length=500)
    employer: Optional[str] = Field(default=None, max_length=500)
    designation: Optional[str] = Field(default=None, max_length=500)
    title: Optional[str] = Field(default=None, max_length=500)
    role: Optional[str] = Field(default=None, max_length=500)
    location: Optional[str] = Field(default=None, max_length=300)
    city: Optional[str] = Field(default=None, max_length=300)


class EducationContextIn(BaseModel):
    """Only labelled education components; free text stays in education."""
    degree: Optional[str] = Field(default=None, max_length=300)
    institution: Optional[str] = Field(default=None, max_length=500)
    graduation_year: Optional[int] = Field(default=None, ge=1900, le=2100)


class CandidateIn(BaseModel):
    name: str = Field(default="", max_length=300)
    headline: Optional[str] = Field(default=None, max_length=2000)
    location: Optional[str] = Field(default=None, max_length=300)
    source: Optional[Literal["naukri", "linkedin"]] = None
    source_id_kind: Optional[Literal["data-target-id", "profile-url", "unverified"]] = None
    profile_url: Optional[str] = Field(default=None, max_length=2048)
    profileUrl: Optional[str] = Field(default=None, max_length=2048)
    # Source identifier hint with explicit provenance. Capturing an ID does
    # not verify its stability; raw pid/sid values cannot confirm identity.
    naukri_id: Optional[str] = Field(default=None, max_length=256)
    # Corroborating signals (any subset — extension sends what's visible
    # on the source card). Ordinary fields support review suggestions only.
    current_employer: Optional[str] = Field(default=None, max_length=500)
    designation: Optional[str] = Field(default=None, max_length=500)
    experience_years: Optional[float] = Field(default=None, ge=0, le=80, allow_inf_nan=False)
    annual_ctc: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    skills: Optional[List[Annotated[str, Field(max_length=200)]]] = Field(default=None, max_length=100)
    education: Optional[str] = Field(default=None, max_length=2000)
    notice_period: Optional[str] = Field(default=None, max_length=300)
    # Optional longitudinal context.  Search cards usually omit these, but a
    # richer source adapter may provide bounded prior-employment and credential
    # values.  They are corroboration only and never identity proofs.
    experience: Optional[List[ExperienceContextIn]] = Field(default=None, max_length=30)
    education_details: Optional[List[EducationContextIn]] = Field(default=None, max_length=10)
    certifications: Optional[List[Annotated[str, Field(max_length=200)]]] = Field(default=None, max_length=50)
    projects: Optional[List[Annotated[str, Field(max_length=200)]]] = Field(default=None, max_length=50)
    languages: Optional[List[Annotated[str, Field(max_length=100)]]] = Field(default=None, max_length=30)


class CheckExistingRequest(BaseModel):
    candidates: List[CandidateIn] = Field(default_factory=list, max_length=50)
    # Optional — the current Naukri/LinkedIn URL the extension is scanning.
    # Used only for the audit log (helps admin reproduce the search).
    page_url: Optional[str] = Field(default=None, max_length=2048)


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
    decision: str = "unavailable"
    matcher_version: str = "identity-resolution-1"
    score_kind: str = "evidence_points"
    top_match: Optional[dict] = None
    second_match: Optional[dict] = None
    ranked_matches: List[dict] = Field(default_factory=list)
    margin: Optional[float] = None
    reason_codes: List[str] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    retrieval_complete: bool = False
    retrieval_paths: List[str] = Field(default_factory=list)
    retrieval_stats: Optional[dict] = None
    context_fields_observed: List[str] = Field(default_factory=list)
    corpus_frequencies_available: bool = False
    frequency_adjustments: List[dict] = Field(default_factory=list)
    candidate_id: Optional[str] = None
    captured_at: Optional[str] = None
    match_confidence: Optional[str] = None  # "high" | "medium"
    matched_signals: Optional[List[str]] = None  # debug: which signals fired
    match_score: Optional[float] = None  # Uncalibrated evidence points, NOT a probability.
    # Server-built deep-link so the extension never has to guess the
    # frontend URL from a (possibly proxied) backend API host.
    profile_url: Optional[str] = None
    # Echoed DB fields so the extension can cross-check before badging
    matched_candidate: Optional[MatchedCandidate] = None


class CheckExistingResponse(BaseModel):
    results: List[CheckResult]
    matcher_version: str = "identity-resolution-1"
    service_status: str = "ready"
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
        score += _SIGNAL_WEIGHTS["employer"]
        signals.append("employer")
    elif _headline_mentions_employer(c.headline, doc.get("current_employer")):
        # Weaker — headline cross-reference when employer field wasn't parsed
        score += _SIGNAL_WEIGHTS["headline_employer"]
        signals.append("headline_employer")

    if _designation_matches(c.designation, doc.get("designation")):
        score += _SIGNAL_WEIGHTS["designation"]
        signals.append("designation")

    if _ctc_matches(c.annual_ctc, doc.get("annual_ctc") or doc.get("current_ctc")):
        score += _SIGNAL_WEIGHTS["ctc"]
        signals.append("ctc")

    if _experience_matches(c.experience_years, doc.get("experience_years")
                            or doc.get("total_experience")):
        score += _SIGNAL_WEIGHTS["experience"]
        signals.append("experience")

    if _skills_overlap(c.skills, doc.get("skills")):
        score += _SIGNAL_WEIGHTS["skills"]
        signals.append("skills")

    if _education_matches(c.education, doc.get("education")):
        score += _SIGNAL_WEIGHTS["education"]
        signals.append("education")

    if _location_matches(c.location, doc.get("location")):
        score += _SIGNAL_WEIGHTS["location"]
        signals.append("location")

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
        score += _V2_SIGNAL_WEIGHTS["employer"]
        signals.append("employer")
    elif _headline_mentions_employer(c.headline, doc.get("current_employer")):
        score += _V2_SIGNAL_WEIGHTS["headline_employer"]
        signals.append("headline_employer")

    # Direct designation
    if _designation_matches(c.designation, doc.get("designation")):
        score += _V2_SIGNAL_WEIGHTS["designation"]
        signals.append("designation")
    # NEW: headline-extracted designation (e.g. "ML Engineer at TCS - Pune")
    elif _headline_contains(c.headline, doc.get("designation"), min_len=4):
        score += _V2_SIGNAL_WEIGHTS["headline_designation"]
        signals.append("headline_designation")

    if _ctc_matches(c.annual_ctc, doc.get("annual_ctc") or doc.get("current_ctc")):
        score += _V2_SIGNAL_WEIGHTS["ctc"]
        signals.append("ctc")

    if _experience_matches(c.experience_years,
                           doc.get("experience_years") or doc.get("total_experience")):
        score += _V2_SIGNAL_WEIGHTS["experience"]
        signals.append("experience")

    if _skills_overlap(c.skills, doc.get("skills")):
        score += _V2_SIGNAL_WEIGHTS["skills"]
        signals.append("skills")

    if _education_matches(c.education, doc.get("education")):
        score += _V2_SIGNAL_WEIGHTS["education"]
        signals.append("education")

    # Direct location
    if _location_matches(c.location, doc.get("location")):
        score += _V2_SIGNAL_WEIGHTS["location"]
        signals.append("location")
    # NEW: DB location keyword in card headline ("...- Pune")
    elif _headline_contains(c.headline, doc.get("location"), min_len=3):
        score += _V2_SIGNAL_WEIGHTS["headline_location"]
        signals.append("headline_location")

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


# ──────────────────────────────────────────────────────────────────────
# Badge Phase C — Medium-band BGE re-verification (2026-06-15)
# ──────────────────────────────────────────────────────────────────────
# For V2 matches in the score band [0.85, 1.20) — "medium confidence" —
# embed the Naukri-card text and the DB candidate text with the local
# BGE model and reject the match if cosine similarity < threshold T.
#
# Why
# ----
# The medium band is where false-positive badge redirects originate.
# When name+ctc+experience all coincide (e.g. two "Amit Kumar" finance
# folks both 8 yrs ~ 20 LPA) V2 still badges, then opens the wrong
# profile. A second-pass *semantic* compare of "what the card says about
# this person" vs "what the DB says about this person" catches those.
#
# Cost
# ----
# - HIGH-band (≥1.20) matches: NO additional cost (skip the gate).
# - MEDIUM-band matches: 2 embeddings each. We BATCH them across all
#   medium candidates in the request so the BGE forward pass amortises.
# - Disabled entirely via env BADGE_PHASE_C_ENABLED=false or threshold
#   tuned via BADGE_PHASE_C_THRESHOLD (default 0.60).

def _phase_c_enabled() -> bool:
    raw = (os.environ.get("BADGE_PHASE_C_ENABLED") or "true").strip().lower()
    return raw not in ("false", "0", "no", "off")


def _phase_c_threshold() -> float:
    try:
        return float(os.environ.get("BADGE_PHASE_C_THRESHOLD", "0.60"))
    except ValueError:
        return 0.60


def _build_phase_c_text_pair(c: "CandidateIn", doc: dict) -> tuple[str, str]:
    """Compose the comparison strings for the card and DB document.
    Mirrors the sentence-level summary an LTR feature extractor would
    use: NAME, DESIGNATION, EMPLOYER, LOCATION, HEADLINE.
    """
    card_parts = [
        c.name or "",
        getattr(c, "designation", "") or "",
        getattr(c, "current_employer", "") or "",
        getattr(c, "location", "") or "",
        getattr(c, "headline", "") or "",
    ]
    doc_parts = [
        doc.get("name") or "",
        doc.get("designation") or "",
        doc.get("current_employer") or "",
        doc.get("location") or "",
        doc.get("headline") or "",
    ]
    return (
        " | ".join(p.strip() for p in card_parts if p and p.strip())[:1024],
        " | ".join(p.strip() for p in doc_parts if p and p.strip())[:1024],
    )


async def _phase_c_verify_medium_band(
    medium_pairs: list[tuple[int, "CandidateIn", dict]],
    threshold: float,
) -> dict[int, dict]:
    """Embed all medium-band card/doc text pairs in ONE BGE batch and
    return `{idx: {cosine: float, decision: 'keep'|'reject'}}` per pair.

    On any error we return an empty dict — callers default to keeping
    the match (fail-open). Phase C only ADDS precision; it never reduces
    the recall of the V2 logic that already passed.
    """
    if not medium_pairs:
        return {}

    try:
        from services.talent_graph_service import embed_texts_batch
    except Exception as e:
        logger.info(f"[PhaseC] embed import failed → fail-open: {e}")
        return {}

    texts: list[str] = []
    for _idx, c, doc in medium_pairs:
        a, b = _build_phase_c_text_pair(c, doc)
        texts.extend([a, b])

    import asyncio as _asyncio
    try:
        vecs = await _asyncio.to_thread(embed_texts_batch, texts)
    except Exception as e:
        logger.info(f"[PhaseC] embed batch failed → fail-open: {e}")
        return {}

    if not vecs or len(vecs) != len(texts):
        logger.info("[PhaseC] embed batch shape mismatch → fail-open")
        return {}

    out: dict[int, dict] = {}
    for i, (idx, _c, _doc) in enumerate(medium_pairs):
        va = vecs[2 * i]
        vb = vecs[2 * i + 1]
        if va is None or vb is None:
            continue  # leave the match alone (fail-open)
        # BGE outputs are L2-normalised so dot product == cosine
        cos = sum(x * y for x, y in zip(va, vb))
        out[idx] = {
            "cosine": round(float(cos), 4),
            "decision": "reject" if cos < threshold else "keep",
        }
    return out



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
    """Resolve search cards with one explicit decision per input (maximum 50).

    The existing rollout allowlist remains authoritative. Disabling a lookup is
    reported as unavailable rather than a negative identity decision. New clients
    batch requests; oversize legacy requests receive a validation error, never a
    silently shortened response. No legacy score can generate a green badge.
    """
    import time
    from services.identity_lookup import lookup_profiles, unavailable_result

    if not _is_user_allowed(user):
        return CheckExistingResponse(
            service_status="disabled",
            results=[CheckResult(index=i, **unavailable_result("feature_disabled"))
                     for i in range(len(payload.candidates))],
        )
    t0 = time.monotonic()
    base = (os.environ.get("SITE_URL") or "https://ventureshrd.com").rstrip("/")
    raw = await lookup_profiles(db, [c.model_dump() for c in payload.candidates], base)
    results = [CheckResult(**row) for row in raw]
    unavailable = [r for r in results if r.decision == "unavailable"]
    status = "unavailable" if results and len(unavailable) == len(results) else "ready"
    # Preserve the existing admin badge-view counters without putting a slow
    # analytics write on the identity decision's critical path.  Counter
    # failures are deliberately non-fatal and never alter the response.
    try:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).date().isoformat()
        shown = sum(1 for result in results if result.exists)

        async def record_view_stats():
            await db.badge_view_stats.update_one(
                {"day": today},
                {"$inc": {"scanned_count": len(results), "shown_count": shown, "scan_calls": 1},
                 "$set": {"last_seen_at": datetime.now(timezone.utc).isoformat()},
                 "$setOnInsert": {"day": today, "created_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
            await db.badge_view_stats_user.update_one(
                {"day": today, "user_email": (user.get("email") or "").lower()},
                {"$inc": {"scanned_count": len(results), "shown_count": shown},
                 "$setOnInsert": {"day": today, "user_email": (user.get("email") or "").lower(),
                                  "user_id": user.get("id")}},
                upsert=True,
            )

        await asyncio.wait_for(record_view_stats(), timeout=0.5)
    except Exception:
        logger.debug("Badge view counter unavailable", exc_info=True)
    audit_id = None
    # Retain the existing review workflow with versioned evidence. The logging
    # operation is bounded and cannot turn a successful lookup into a failure.
    if results:
        try:
            sample = min(1.0, max(0.0, float(os.environ.get("EXTENSION_CHECK_AUDIT_SAMPLE", "1"))))
        except ValueError:
            sample = 1.0
        if random.random() < sample:
            try:
                from routes.badge_audit import write_audit_doc

                def audit_context(result):
                    context = ((result.top_match or {}).get("context")
                               if isinstance(result.top_match, dict) else {}) or {}
                    return {
                        "name": (result.top_match or {}).get("name") if result.top_match else None,
                        "current_employer": context.get("employer"),
                        "designation": context.get("designation"),
                        "location": context.get("location"),
                        "skills": context.get("skills", []),
                        "education": context.get("education", []),
                        "experience_years": context.get("experience_years"),
                    }

                audit_id = await asyncio.wait_for(write_audit_doc(
                    user=user, used_v2=False, candidates_in=payload.candidates,
                    results_out=results,
                    docs_by_idx={r.index: audit_context(r)
                                 for r in results if r.top_match},
                    conflicts_by_idx={r.index: ",".join(r.conflicts) or None for r in results},
                    page_url=payload.page_url,
                    took_ms=int((time.monotonic() - t0) * 1000),
                ), timeout=2)
            except Exception:
                logger.warning("Identity decision audit unavailable")
    return CheckExistingResponse(results=results, service_status=status, audit_id=audit_id)
