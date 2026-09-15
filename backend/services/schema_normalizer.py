"""
VHC Talent OS — Schema Normalizer
Single source of truth for candidate field normalization.
Resolves the dual-schema divergence between:
  Canonical:  key_skills, profile_summary, work_experience, total_experience_years
  Aliases:    skills,     summary,          experience,      experience_years

Every candidate document MUST pass through normalize_candidate() before
being written to MongoDB. Reading code uses get_skills(), get_summary(),
get_experience_years() helpers which transparently resolve either schema.
"""
from __future__ import annotations

import re
import json
import hashlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public read helpers — use these everywhere instead of dict.get()
# ---------------------------------------------------------------------------

def get_skills(candidate: Dict) -> List[str]:
    """Return skills list regardless of which field name was used."""
    raw = (
        candidate.get("key_skills")
        or candidate.get("skills")
        or []
    )
    if not isinstance(raw, list):
        return []
    result = []
    for s in raw:
        if isinstance(s, str) and s.strip():
            result.append(s.strip())
        elif isinstance(s, dict) and s.get("name"):
            result.append(str(s["name"]).strip())
    return result


def get_it_skill_names(candidate: Dict) -> List[str]:
    """Return flat list of IT skill names from it_skills array."""
    names = []
    for s in (candidate.get("it_skills") or []):
        if isinstance(s, dict) and s.get("name"):
            names.append(str(s["name"]).strip())
        elif isinstance(s, str) and s.strip():
            names.append(s.strip())
    return names


def get_all_skill_tokens(candidate: Dict) -> List[str]:
    """All skill tokens: key_skills + it_skills, lowercased, deduped."""
    tokens = [s.lower() for s in get_skills(candidate)]
    tokens += [s.lower() for s in get_it_skill_names(candidate)]
    return list(dict.fromkeys(tokens))


def get_summary(candidate: Dict) -> str:
    """Return summary string regardless of which field name was used."""
    val = (
        candidate.get("profile_summary")
        or candidate.get("summary")
        or ""
    )
    return val if isinstance(val, str) else ""


def get_experience_years(candidate: Dict) -> float:
    """Return experience years regardless of which field name was used."""
    raw = (
        candidate.get("total_experience_years")
        if candidate.get("total_experience_years") is not None
        else candidate.get("experience_years")
    )
    try:
        return float(raw) if raw is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def get_experience_list(candidate: Dict) -> List[Dict]:
    """Return work experience list regardless of which field name was used."""
    raw = (
        candidate.get("work_experience")
        or candidate.get("experience")
        or []
    )
    return raw if isinstance(raw, list) else []


def get_designation(candidate: Dict) -> str:
    """Return current designation/title regardless of which field name was used."""
    return (
        candidate.get("current_designation")
        or candidate.get("designation")
        or candidate.get("headline")
        or ""
    )


def get_employer(candidate: Dict) -> str:
    """Return current employer regardless of which field name was used."""
    return (
        candidate.get("current_company")
        or candidate.get("current_employer")
        or ""
    )


def get_industry(candidate: Dict) -> str:
    """Return industry regardless of which field name was used."""
    return (
        candidate.get("current_industry")
        or candidate.get("industry")
        or ""
    )


# ---------------------------------------------------------------------------
# Canonical normalizer — call before every DB write
# ---------------------------------------------------------------------------

def normalize_candidate(parsed: Dict) -> Dict:
    """
    Normalize ANY parser output to the canonical + alias dual-write schema.

    After this function every document contains BOTH:
      canonical field  AND  alias field  (identical values)

    This means:
    - New queries using canonical names work.
    - Existing queries using alias names continue to work.
    - Scoring and embedding functions read consistent data.

    Safe to call on documents already in canonical form (idempotent).
    """
    out = dict(parsed)

    # ── name_lower (indexed for extension /check-existing perf) ─────────────
    # See routes/extension_check.py + scripts/backfill_name_lower.py
    _nm = out.get("name")
    if isinstance(_nm, str) and _nm:
        out["name_lower"] = _nm.lower()

    # ── skills ──────────────────────────────────────────────────────────────
    canonical_skills = _merge_string_lists(
        out.get("key_skills"), out.get("skills")
    )
    out["key_skills"] = canonical_skills   # canonical
    out["skills"]     = canonical_skills   # alias
    # Lowercased mirror for indexed facet aggregation (Spec 5.11 follow-up).
    # `$regex` on the raw `skills` array with case-insensitive flag cannot
    # use the multikey index; matching against a pre-lowercased mirror with
    # a case-SENSITIVE `^prefix` regex is index-backed and ~50-100× faster.
    out["skills_lc"] = [s.lower() for s in canonical_skills if isinstance(s, str)]

    # ── summary ─────────────────────────────────────────────────────────────
    canonical_summary = _pick_longer_string(
        out.get("profile_summary"), out.get("summary")
    )
    out["profile_summary"] = canonical_summary  # canonical
    out["summary"]         = canonical_summary  # alias

    # ── work experience ──────────────────────────────────────────────────────
    canonical_exp = _resolve_experience(
        out.get("work_experience"), out.get("experience")
    )
    out["work_experience"] = canonical_exp  # canonical
    out["experience"]      = canonical_exp  # alias

    # ── experience years ─────────────────────────────────────────────────────
    years = _coerce_float(
        out.get("total_experience_years") if out.get("total_experience_years") is not None
        else out.get("experience_years")
    )
    out["total_experience_years"] = years  # canonical
    out["experience_years"]       = years  # alias

    # ── type safety on optional fields ──────────────────────────────────────
    if not isinstance(out.get("it_skills"), list):
        out["it_skills"] = []
    if not isinstance(out.get("education"), list):
        out["education"] = []
    if not isinstance(out.get("certifications"), list):
        out["certifications"] = []
    if not isinstance(out.get("preferred_locations"), list):
        out["preferred_locations"] = []

    # ── phone normalization for dedup ────────────────────────────────────────
    phone_raw = out.get("phone") or ""
    digits = "".join(filter(str.isdigit, str(phone_raw)))
    out["phone_normalized"] = digits[-10:] if len(digits) >= 10 else None

    # ── email normalization ──────────────────────────────────────────────────
    email = out.get("email")
    if isinstance(email, str) and email.strip():
        out["email"] = email.strip().lower()

    # ── lowercased mirrors for indexed facet aggregation (Spec 5.11) ────────
    # current_company / location facets used to `$regex` scan the raw fields.
    # We mirror to `_lc` so the /facets endpoint can `$match` an indexed
    # case-sensitive `^prefix` regex — index-backed, 10-50× faster.
    _company_raw = out.get("current_company") or out.get("current_employer") or ""
    if isinstance(_company_raw, str) and _company_raw.strip():
        out["current_company_lc"] = _company_raw.strip().lower()
    else:
        out["current_company_lc"] = None

    _loc_raw = out.get("location") or out.get("current_location") or ""
    if isinstance(_loc_raw, str) and _loc_raw.strip():
        out["location_lc"] = _loc_raw.strip().lower()
    else:
        out["location_lc"] = None

    return out


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

def extract_json_from_llm_response(response_text: str) -> str:
    """
    Extract raw JSON string from LLM response.
    Handles markdown code fences (```json ... ```) and bare JSON.
    Raises ValueError if no JSON-like content found.
    """
    if not response_text:
        raise ValueError("Empty LLM response")

    text = response_text.strip()

    # Markdown code fence: ```json ... ```
    if "```json" in text:
        inner = text.split("```json", 1)[1]
        return inner.split("```", 1)[0].strip()

    # Generic code fence: ``` ... ```
    if "```" in text:
        inner = text.split("```", 1)[1]
        return inner.split("```", 1)[0].strip()

    # Attempt to find outermost { ... } block
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1].strip()

    return text


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _merge_string_lists(*lists) -> List[str]:
    """Merge multiple nullable lists of strings, dedup, preserve order."""
    seen = {}
    for lst in lists:
        if not isinstance(lst, list):
            continue
        for item in lst:
            if isinstance(item, str) and item.strip():
                key = item.strip().lower()
                if key not in seen:
                    seen[key] = item.strip()
            elif isinstance(item, dict) and item.get("name"):
                key = str(item["name"]).strip().lower()
                if key not in seen:
                    seen[key] = str(item["name"]).strip()
    return list(seen.values())


def _pick_longer_string(a, b) -> str:
    """Return the non-empty string; if both non-empty, return the longer one."""
    a = a if isinstance(a, str) else ""
    b = b if isinstance(b, str) else ""
    if not a:
        return b
    if not b:
        return a
    return a if len(a) >= len(b) else b


def _resolve_experience(canonical, alias) -> List[Dict]:
    """Return canonical if non-empty, else map alias to canonical format."""
    if isinstance(canonical, list) and canonical:
        return canonical
    if isinstance(alias, list) and alias:
        return _map_legacy_experience(alias)
    return []


def _map_legacy_experience(raw_exp: list) -> List[Dict]:
    """Map legacy experience array format to canonical work_experience format."""
    mapped = []
    for e in raw_exp:
        if not isinstance(e, dict):
            continue
        mapped.append({
            "designation": e.get("title") or e.get("designation"),
            "company":     e.get("company"),
            "from_date":   e.get("from_date") or e.get("start_date"),
            "to_date":     e.get("to_date")   or e.get("end_date"),
            "is_current":  bool(e.get("is_current", False)),
            "description": e.get("description") or e.get("duration") or "",
        })
    return mapped


def _coerce_float(val) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
