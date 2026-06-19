"""
Talent Search v2 — Hybrid (semantic + lexical) candidate retrieval.

Powers the new Advanced Search + Find Candidates "AI" experience.

Why a new endpoint?
-------------------
The previous `/api/candidate-bank/` (regex-only) and `/api/ai-search`
(LLM filters → regex query) both ignored the 139k BGE embeddings sitting
in `candidate_embeddings`. That's why the team described results as
"vague" — there was no semantic retrieval ever in the loop.

What this endpoint does
-----------------------
For one query it returns TWO candidate lists side-by-side so the team
can A/B-compare the new ranking against the old one before cutover:

  1. **hybrid**  — vector retrieval over `candidate_embeddings` →
                   cross-encoder rerank → LTR (A/B-gated) → post-filter
                   by structured filters extracted from the NL query.
                   Top-up with keyword fallback when embedding pool is
                   sparse so users never see an empty list.

  2. **lexical** — the old regex path: `extract_filters(query)` →
                   `build_mongo_query(filters)` → `candidate_bank.find`
                   sorted by recency. This is what the team sees today
                   on Find Candidates / Advanced Search.

The frontend renders these two columns next to each other. Once the
team is happy with the hybrid quality, we'll flip the UI default and
the lexical leg becomes opt-in for debugging.

Endpoint
--------
POST /api/talent/search
  body: { query: str, limit: int = 50, compare_lexical: bool = true,
          filters?: dict }
  returns:
    {
      query, filters, took_ms: {hybrid, lexical},
      hybrid: [candidates...],
      lexical: [candidates...],   # omitted when compare_lexical=false
    }
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from config import db
from utils.auth import get_current_user
from services.ai_search import (
    extract_filters,
    build_mongo_query,
    apply_stability_filters,
)
from services.talent_graph_service import find_candidates_by_text
from services.profile_enricher import enrich_candidate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/talent", tags=["Talent Search"])


# ──────────────────────────────────────────────────────────────────────
# Lazy enrichment hook — Search Phase 2 (2026-06-15)
# ──────────────────────────────────────────────────────────────────────
# When a hybrid search surfaces a candidate that's still missing one of
# the enriched fields (industry / seniority / function / canonical
# location / notice_period_days), we queue an `enrich_candidate` task
# via FastAPI's `BackgroundTasks`. A simple token-bucket caps the rate
# at 100/min so we never overload the RunPod sidecar or the DB during
# spiky traffic.
#
# Bucket state lives at module scope (per-process). For multi-worker
# deployments each worker gets its own 100/min cap — acceptable since
# the bucket is intentionally conservative.

import asyncio as _a
import time as _t

_ENRICH_BUCKET_MAX = 100  # tokens per minute
_ENRICH_BUCKET = {
    "tokens": _ENRICH_BUCKET_MAX,
    "last_refill": _t.time(),
    "lock": _a.Lock(),
    "seen_ids": set(),  # de-dupe within this worker's lifetime
}


async def _take_token() -> bool:
    """Return True if the rate-limit allows another enrichment task."""
    async with _ENRICH_BUCKET["lock"]:
        now = _t.time()
        elapsed = now - _ENRICH_BUCKET["last_refill"]
        if elapsed >= 1.0:
            # Refill proportional to elapsed time (cap at max)
            refill = int(elapsed * (_ENRICH_BUCKET_MAX / 60.0))
            if refill > 0:
                _ENRICH_BUCKET["tokens"] = min(
                    _ENRICH_BUCKET_MAX, _ENRICH_BUCKET["tokens"] + refill
                )
                _ENRICH_BUCKET["last_refill"] = now
        if _ENRICH_BUCKET["tokens"] > 0:
            _ENRICH_BUCKET["tokens"] -= 1
            return True
    return False


def _needs_enrichment(c: Dict[str, Any]) -> bool:
    """Cheap O(1) check — true iff at least one canonical field is missing."""
    if not c.get("industry") and not c.get("current_industry"):
        return True
    if not c.get("enriched_seniority"):
        return True
    if not c.get("enriched_function"):
        return True
    if not c.get("enriched_location"):
        return True
    return False


async def _enrich_one(candidate_id: str) -> None:
    """Background task — load the full candidate doc and apply enrichment."""
    try:
        doc = await db.candidate_bank.find_one(
            {"id": candidate_id},
            {
                "_id": 0, "id": 1, "current_employer": 1, "current_company": 1,
                "industry": 1, "current_industry": 1,
                "current_designation": 1, "designation": 1, "headline": 1,
                "key_skills": 1, "skills": 1,
                "current_location": 1, "location": 1,
                "summary": 1, "profile_summary": 1, "notice_period_days": 1,
                "enriched_seniority": 1, "enriched_function": 1,
                "enriched_location": 1,
            },
        )
        if not doc:
            return
        updates = await enrich_candidate(doc, db, allow_llm=True)
        if updates:
            await db.candidate_bank.update_one(
                {"id": candidate_id}, {"$set": updates}
            )
            logger.info(
                f"[LazyEnrich] {candidate_id} ← {sorted(k for k in updates if not k.startswith('enrich'))}"
            )
    except Exception as e:
        logger.info(f"[LazyEnrich] candidate {candidate_id} failed: {e}")


# ── Projection shared across both legs so the UI renders the same card ─
_CANDIDATE_PROJECTION = {
    "_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1,
    "headline": 1, "designation": 1, "current_designation": 1,
    "current_employer": 1, "current_company": 1, "industry": 1,
    "experience_years": 1, "total_experience_years": 1,
    "location": 1, "current_location": 1,
    "skills": 1, "key_skills": 1, "it_skills": 1, "smart_tags": 1,
    "summary": 1, "profile_summary": 1,
    "highest_qualification": 1, "highest_degree": 1,
    "education": 1, "notice_period": 1, "notice_period_days": 1,
    "current_salary": 1, "expected_salary": 1,
    "preferred_locations": 1, "preferred_industry": 1,
    "source": 1, "created_at": 1, "updated_at": 1, "created_by": 1,
    "photo_url": 1, "resume_url": 1, "cv_attached": 1,
}


class TalentSearchRequest(BaseModel):
    query: Optional[str] = Field(None, min_length=2)
    job_id: Optional[str] = None  # When set, build query from the mandate's JD + skills
    limit: int = Field(50, ge=1, le=200)
    compare_lexical: bool = True
    filters: Optional[Dict[str, Any]] = None  # client may pre-extract / override


class TalentSearchResponse(BaseModel):
    query: str
    filters: Dict[str, Any]
    took_ms: Dict[str, int]
    hybrid: List[Dict[str, Any]]
    lexical: Optional[List[Dict[str, Any]]] = None
    debug: Optional[Dict[str, Any]] = None
    job: Optional[Dict[str, Any]] = None  # echoed when job_id was provided


def _build_query_from_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Compose a hybrid-search input from a mandate document.

    Returns ``{"query": str, "filters": dict}`` so the caller can seed both
    legs of the search. The query string is a compact 3-line digest that
    reads well to the BGE encoder (no JSON blobs, no boilerplate); the
    filters carry the deterministic fields (skills / location / exp range)
    that the LLM extraction would otherwise have to re-derive from prose.
    """
    title = (job.get("title") or "").strip()
    company = (job.get("company_name") or "").strip()
    location = (job.get("location") or "").strip()

    # Skills can live on `required_skills`, `skills`, or buried in `description`.
    skills_raw = (
        job.get("required_skills")
        or job.get("skills")
        or []
    )
    if isinstance(skills_raw, str):
        # Comma / semicolon separated string fallback
        skills_raw = [s.strip() for s in skills_raw.replace(";", ",").split(",") if s.strip()]
    skills: List[str] = []
    for s in (skills_raw or []):
        if isinstance(s, dict):
            name = s.get("name") or s.get("skill") or ""
        else:
            name = str(s)
        name = name.strip()
        if name and name not in skills:
            skills.append(name)

    # Experience range — handles common JD field names
    min_e = (
        job.get("min_experience")
        or job.get("min_experience_years")
        or job.get("experience_min")
    )
    max_e = (
        job.get("max_experience")
        or job.get("max_experience_years")
        or job.get("experience_max")
    )
    try: min_e = float(min_e) if min_e not in (None, "") else None
    except (TypeError, ValueError): min_e = None
    try: max_e = float(max_e) if max_e not in (None, "") else None
    except (TypeError, ValueError): max_e = None

    # Salary range — mandates store as `salary_min` / `salary_max` (raw INR
    # rupees per `backend/models/job.py`). Map to the filter schema's
    # `ctc_min` / `ctc_max` so the post-retrieval intersection can enforce
    # the bracket. _apply_structured_filters handles both raw-rupees and
    # lakhs internally and gives ±20% leniency so mandates with a tight
    # band don't cull legitimate candidates.
    sal_min = job.get("salary_min") or job.get("min_salary") or job.get("ctc_min")
    sal_max = job.get("salary_max") or job.get("max_salary") or job.get("ctc_max")
    try: sal_min = float(sal_min) if sal_min not in (None, "") else None
    except (TypeError, ValueError): sal_min = None
    try: sal_max = float(sal_max) if sal_max not in (None, "") else None
    except (TypeError, ValueError): sal_max = None

    # JD snippet — first ~600 chars is enough for the encoder to pick up
    # the role flavour without overwhelming the cosine signal.
    jd_snippet = (job.get("description") or job.get("jd_text") or "")
    jd_snippet = " ".join(jd_snippet.split())[:600]  # collapse whitespace

    # Compose the natural-language query
    query_parts: List[str] = []
    if title: query_parts.append(title)
    if skills: query_parts.append("with " + ", ".join(skills[:8]))
    if location: query_parts.append("in " + location)
    if min_e or max_e:
        if min_e and max_e: query_parts.append(f"{int(min_e)}-{int(max_e)} years")
        elif min_e: query_parts.append(f"{int(min_e)}+ years")
        elif max_e: query_parts.append(f"upto {int(max_e)} years")
    query = " ".join(query_parts).strip()
    # Tag the JD snippet on the end so the encoder picks up nuance the
    # title alone misses (e.g. "manage offshore PMO" → strategist vs IC).
    if jd_snippet:
        query = f"{query}. {jd_snippet}" if query else jd_snippet

    filters: Dict[str, Any] = {}
    if skills: filters["skills"] = skills[:12]
    if location: filters["location_include"] = [location]
    if min_e is not None: filters["min_experience"] = min_e
    if max_e is not None: filters["max_experience"] = max_e
    if sal_min is not None: filters["ctc_min"] = sal_min
    if sal_max is not None: filters["ctc_max"] = sal_max
    return {"query": query[:1500], "filters": filters}


# ──────────────────────────────────────────────────────────────────────
# Post-filter helpers — apply LLM-extracted structured filters AFTER the
# hybrid retrieval so the semantic recall isn't choked at the database
# level. Mirrors the old `build_mongo_query` semantics but operates on
# in-memory dicts.
# ──────────────────────────────────────────────────────────────────────

def _exp(c: Dict[str, Any]) -> Optional[float]:
    return c.get("total_experience_years") or c.get("experience_years")


def _designation(c: Dict[str, Any]) -> str:
    return (
        c.get("current_designation")
        or c.get("designation")
        or c.get("headline")
        or ""
    ).lower()


def _industry(c: Dict[str, Any]) -> str:
    return " ".join(filter(None, [
        c.get("industry") or "",
        c.get("current_industry") or "",
        c.get("preferred_industry") or "",
        " ".join(c.get("smart_tags") or [])[:300],
    ])).lower()


def _location(c: Dict[str, Any]) -> str:
    return (c.get("current_location") or c.get("location") or "").lower()


def _skills_blob(c: Dict[str, Any]) -> str:
    parts: List[str] = []
    for f in ("key_skills", "skills"):
        v = c.get(f)
        if isinstance(v, list):
            parts.extend(str(x) for x in v if x)
        elif isinstance(v, str):
            parts.append(v)
    it = c.get("it_skills") or []
    if isinstance(it, list):
        for s in it:
            if isinstance(s, dict) and s.get("name"):
                parts.append(str(s["name"]))
    return " ".join(parts).lower()


def _ctc_of(c: Dict[str, Any]) -> Optional[float]:
    """Return the candidate's current CTC in raw rupees, or None.
    Naukri / our extension store as integer rupees (e.g. 1,500,000).
    -1 sentinel means 'not specified'."""
    for k in ("current_salary", "annual_ctc", "ctc", "current_ctc", "salary"):
        v = c.get(k)
        if v is None: continue
        try:
            f = float(v)
            if f > 0: return f
        except (TypeError, ValueError):
            continue
    return None


def _expected_ctc_of(c: Dict[str, Any]) -> Optional[float]:
    v = c.get("expected_salary") or c.get("expected_ctc")
    try:
        f = float(v) if v is not None else None
        if f and f > 0: return f
    except (TypeError, ValueError):
        pass
    return None


# Indian city aliases — a mandate that says "Bangalore" must match
# candidates stored as "Bengaluru" (and vice-versa). Kept tiny on purpose;
# extend only when a real mandate surfaces a mismatch.
_CITY_ALIASES: Dict[str, List[str]] = {
    "bangalore": ["bengaluru"], "bengaluru": ["bangalore"],
    "bombay": ["mumbai"],       "mumbai": ["bombay"],
    "calcutta": ["kolkata"],    "kolkata": ["calcutta"],
    "madras": ["chennai"],      "chennai": ["madras"],
    "gurgaon": ["gurugram"],    "gurugram": ["gurgaon"],
    "trivandrum": ["thiruvananthapuram"], "thiruvananthapuram": ["trivandrum"],
    "pondicherry": ["puducherry"], "puducherry": ["pondicherry"],
}


def _expand_location_terms(loc: str) -> List[str]:
    """Return [loc] + known aliases, all lowercased.  Empty input → []."""
    if not loc:
        return []
    base = loc.strip().lower()
    return [base] + _CITY_ALIASES.get(base, [])


# ── Skill / title synonyms ────────────────────────────────────────────
# A token from the JD or the candidate matches if it appears in the
# OTHER side OR any of its synonyms. Bidirectional; kept small + curated
# (about 80 pairs) so we ship signal without false positives. Add a pair
# here when a real mandate surfaces a confusion.
_SKILL_SYNONYMS: Dict[str, List[str]] = {
    # Industries
    "fmcg": ["cpg", "consumer goods"],
    "cpg": ["fmcg"],
    "fintech": ["bfsi", "banking", "financial services"],
    "bfsi": ["fintech", "banking", "financial"],
    "edtech": ["education technology", "elearning"],
    "saas": ["software as a service", "cloud software"],
    "healthcare": ["health tech", "healthtech", "pharma", "medical"],
    "automotive": ["auto", "automobile"],
    "automobile": ["automotive", "auto"],
    "ecommerce": ["e-commerce", "online retail", "marketplace"],
    # Tech stack
    "k8s": ["kubernetes"],
    "kubernetes": ["k8s"],
    "ml": ["machine learning", "ai"],
    "ai": ["ml", "machine learning", "artificial intelligence"],
    "dl": ["deep learning"],
    "nlp": ["natural language processing"],
    "cv": ["computer vision"],
    "js": ["javascript"],
    "ts": ["typescript"],
    "py": ["python"],
    "react": ["reactjs", "react.js"],
    "node": ["nodejs", "node.js"],
    "postgres": ["postgresql"],
    "postgresql": ["postgres"],
    "mongo": ["mongodb"],
    "elastic": ["elasticsearch"],
    "gcp": ["google cloud"],
    "aws": ["amazon web services"],
    "ci/cd": ["cicd", "continuous integration"],
    # Roles
    "tech lead": ["engineering manager", "team lead", "lead engineer"],
    "engineering manager": ["tech lead", "em"],
    "product manager": ["pm", "product owner"],
    "data scientist": ["ds", "ml engineer"],
    "ml engineer": ["machine learning engineer", "data scientist"],
    "devops": ["sre", "site reliability"],
    "sre": ["devops", "site reliability"],
    "frontend": ["front end", "front-end", "ui developer"],
    "backend": ["back end", "back-end", "server side"],
    "fullstack": ["full stack", "full-stack"],
    "qa": ["quality assurance", "tester"],
    # Functions
    "hr": ["human resources", "people"],
    "ca": ["chartered accountant"],
    "mba": ["master of business administration"],
    "cfa": ["chartered financial analyst"],
    # Domain
    "ht/lt": ["ht", "lt", "high tension", "low tension"],
    "etp": ["effluent treatment"],
    "stp": ["sewage treatment"],
    "autocad": ["auto cad", "cad"],
    "solidworks": ["solid works"],
    "sap mm": ["mm module", "materials management"],
    "p2p": ["procure to pay", "procure-to-pay"],
    "o2c": ["order to cash"],
}
# Build reverse map once at module load — every key maps to itself + its synonyms.
_SYNONYM_EXPAND: Dict[str, set] = {}
for _k, _vs in _SKILL_SYNONYMS.items():
    _SYNONYM_EXPAND.setdefault(_k, set()).add(_k)
    for _v in _vs:
        _SYNONYM_EXPAND[_k].add(_v)
        _SYNONYM_EXPAND.setdefault(_v, set()).add(_v)
        _SYNONYM_EXPAND[_v].add(_k)
        _SYNONYM_EXPAND[_v].update(_vs)


def _expand_with_synonyms(tokens: List[str]) -> List[str]:
    """Return [tokens] + all known synonyms, deduped, lowercased."""
    out: set = set()
    for t in tokens:
        t = (t or "").lower().strip()
        if not t:
            continue
        out.add(t)
        out.update(_SYNONYM_EXPAND.get(t, ()))
    return list(out)


# ── Seniority parsing ─────────────────────────────────────────────────
# Maps designation/title tokens to a 0..3 seniority level. Used to gate
# mandate-driven matches so a "Senior Manager" JD doesn't surface "Junior
# Manager" candidates. Order matters — longest match first.
_SENIORITY_PATTERNS: List[tuple] = [
    (("chief", "cxo", "ceo", "cto", "cfo", "coo", "cmo", "cpo", "vp ", "vice president", "president"), 3),
    (("head ", "head of", "director", "principal", "staff "), 3),
    (("senior", "sr.", "sr ", "lead ", " lead", "specialist"), 2),
    (("associate", "assistant", "junior", "jr.", "jr ", "trainee", "intern", "fresher"), 0),
    (("manager", "engineer", "executive", "analyst", "officer", "developer"), 1),  # mid default
]


def _parse_seniority(text: Optional[str]) -> Optional[int]:
    """Return 0..3 (junior/mid/senior/exec) or None when unknown."""
    if not text:
        return None
    t = " " + text.lower() + " "
    for needles, level in _SENIORITY_PATTERNS:
        if any(n in t for n in needles):
            return level
    return None


# ── Education / certification requirements ────────────────────────────
# Mapped from common JD phrasings to a canonical token recruiters use.
_EDU_PATTERNS: Dict[str, List[str]] = {
    "ca":   ["chartered accountant", "ca qualified", " ca "],
    "cfa":  ["chartered financial analyst", "cfa "],
    "mba":  ["mba", "master of business"],
    "btech": ["b.tech", "b tech", "btech", "bachelor of technology"],
    "mtech": ["m.tech", "m tech", "mtech", "master of technology"],
    "phd":  ["phd", "ph.d", "doctorate"],
    "be":   ["b.e.", "b.e ", "bachelor of engineering"],
    "iit":  ["iit ", "iitian", "indian institute of technology"],
    "iim":  ["iim ", "indian institute of management"],
    "nit":  ["nit ", "national institute of technology"],
}


def _extract_education_requirements(job: Dict[str, Any]) -> List[str]:
    """Scan title + first 1.2k chars of description for explicit education /
    certification asks. Returns a list of canonical tokens (e.g., ['ca', 'mba']).
    Empty list = no education requirement detected; filter is skipped.
    """
    blob = " ".join([
        str(job.get("title") or ""),
        str(job.get("description") or job.get("jd") or "")[:1200],
    ]).lower()
    found: set = set()
    for canonical, patterns in _EDU_PATTERNS.items():
        if any(p in blob for p in patterns):
            found.add(canonical)
    return sorted(found)


def _candidate_matches_education(c: Dict[str, Any], req_edu: List[str]) -> bool:
    """True when the candidate's education / qualification fields contain at
    least ONE of the required education tokens (treat as OR, not AND, so a
    'CA OR MBA' JD doesn't drop CAs)."""
    if not req_edu:
        return True
    blob = " ".join([
        str(c.get("highest_qualification") or ""),
        str(c.get("education") or ""),
        str(c.get("qualifications") or ""),
        str(c.get("summary") or "")[:300],
    ]).lower()
    edu_arr = c.get("education")
    if isinstance(edu_arr, list):
        for e in edu_arr:
            if isinstance(e, dict):
                blob += " " + " ".join(
                    str(e.get(k) or "") for k in ("degree", "specialization", "institute", "school")
                ).lower()
    for canonical in req_edu:
        for p in _EDU_PATTERNS.get(canonical, [canonical]):
            if p.strip() in blob:
                return True
    return False


# ── Boolean operators in free-text query ──────────────────────────────
def _parse_boolean_query(query: str) -> tuple:
    """Split a query like `react developer NOT java AWS OR azure` into
    (positive_terms, negative_terms). Operators are case-insensitive.
    Returns the cleaned query (operators stripped) + the term lists.
    """
    if not query:
        return ("", [], [])
    import re as _re
    # Only treat the WORDS "NOT" / "EXCLUDE" as negative-clause separators.
    # We intentionally do NOT use "-" as a negation operator — JDs are full
    # of bullet points ("- Ensure reliable…") and hyphenated terms
    # ("end-to-end", "C-suite") that would all be mis-parsed.
    parts = _re.split(r"\b(?:NOT|EXCLUDE)\b", query, flags=_re.IGNORECASE, maxsplit=1)
    pos_clause = parts[0].strip()
    neg_clause = parts[1].strip() if len(parts) > 1 else ""
    # OR is implicit in our retrieval; just strip the literal token.
    pos_clause = _re.sub(r"\bOR\b", " ", pos_clause, flags=_re.IGNORECASE)
    cleaned = pos_clause.strip()
    pos_terms = [
        t.lower() for t in _re.findall(r"[A-Za-z][A-Za-z0-9\+\.#]{2,}", pos_clause)
    ]
    neg_terms = [
        t.lower() for t in _re.findall(r"[A-Za-z][A-Za-z0-9\+\.#]{2,}", neg_clause)
    ]
    return (cleaned, pos_terms, neg_terms)


def _candidate_blob_for_neg_match(c: Dict[str, Any]) -> str:
    return " ".join([
        str(c.get("current_designation") or ""),
        str(c.get("headline") or ""),
        " ".join(s if isinstance(s, str) else (s.get("name") or "") for s in (c.get("skills") or [])),
        " ".join(c.get("smart_tags") or []),
        str(c.get("summary") or "")[:500],
    ]).lower()


def _candidate_has_neg_term(c: Dict[str, Any], neg_terms: List[str]) -> bool:
    """Word-boundary match for negative terms.  Critical: a NOT-java filter
    must NOT cull JavaScript candidates.  We treat each negative term as a
    whole-word regex; tokens with `.` or `+` (e.g. ".NET", "C++") are escaped.
    """
    if not neg_terms:
        return False
    import re as _re_neg
    blob = _candidate_blob_for_neg_match(c)
    for nt in neg_terms:
        nt = (nt or "").lower().strip()
        if not nt:
            continue
        # Special-character tokens (C++, .NET, F#, c#) won't get a `\b`
        # boundary because `+`/`.`/`#` aren't word chars — fall back to
        # a simple substring match for those. Pure alphanumeric tokens
        # use word-boundary so "java" doesn't match "javascript".
        if any(ch in nt for ch in (".", "+", "#")):
            if nt in blob:
                return True
        else:
            pat = r"\b" + _re_neg.escape(nt) + r"\b"
            if _re_neg.search(pat, blob):
                return True
    return False


# Stopwords / generic tokens we DROP when building a job's role signature.
# These are too common to be discriminative — every mandate has "manager"
# or "experience" so requiring them as a "role match" is meaningless.
_ROLE_STOPWORDS: set = {
    "and", "the", "for", "from", "with", "into", "etc", "etc.", "well",
    "year", "years", "exp", "experience", "experienced", "experienced.",
    "senior", "junior", "lead", "team", "role", "candidate", "candidates",
    "must", "should", "able", "ability", "responsible", "responsibility",
    "responsibilities", "good", "strong", "excellent", "preferred", "preference",
    "knowledge", "understanding", "working", "work", "job", "company",
    "industry", "experience.", "based", "located", "location", "salary",
    "ctc", "compensation", "skills", "skill", "required", "requirement",
    "requirements", "qualification", "qualifications", "education", "degree",
    "graduate", "graduation", "post", "post-graduate", "btech", "mtech", "bsc",
    "msc", "diploma", "engineering", "engineer", "engineers", "minimum",
    "maximum", "min", "max", "around", "least", "more", "less", "than",
    "open", "close", "office", "field", "site", "remote", "hybrid", "onsite",
    "looking", "candidate.", "key", "responsibilities:", "description:",
    "title", "designation", "department", "department:", "to", "of", "in",
    "on", "at", "by", "as", "or", "an", "a", "is", "be", "any", "all",
    "this", "that", "these", "those", "will", "have", "has", "had", "are",
    "was", "were", "can", "could", "may", "might", "shall", "would",
    "do", "does", "done", "make", "made", "give", "given", "take", "taken",
    "manager", "managers", "executive", "officer", "lead.", "head", "associate",
    "assistant", "deputy", "vice", "president", "vp", "director", "chief",
    "founder", "co-founder", "co", "founder.", "internship", "intern",
    "fresher", "trainee", "apprentice",
}


def _extract_role_signature(job: Dict[str, Any]) -> List[str]:
    """Build the 'role token' fingerprint for a mandate.

    Pulls strong role indicators from the job's TITLE (heaviest), explicit
    `skills` / `key_skills` arrays, and the first ~800 chars of the
    `description`. Filters out generic stopwords ("manager", "experience",
    "engineer" — too common to discriminate).

    Returns a deduplicated list of lowercase tokens, capped at ~20.
    The mandate-driven path uses this to score candidate role-relevance
    so we don't surface "Area Sales Manager" for a "Utility Project
    Engineer" mandate just because they share a city.
    """
    import re as _re
    parts: List[str] = []
    title = (job.get("title") or "").strip()
    if title:
        parts.append(title)
        parts.append(title)   # weight title 2× by duplicating
    # Explicit skill arrays (rarely populated but heavily weighted when present)
    for fld in ("skills", "key_skills", "must_have_skills", "good_to_have_skills"):
        v = job.get(fld)
        if isinstance(v, list):
            parts.extend(str(s) for s in v if s)
            parts.extend(str(s) for s in v if s)   # 2× weight
        elif isinstance(v, str) and v.strip():
            parts.append(v)
    # JD body — first 800 chars catches the responsibility/skill bullets
    desc = (job.get("description") or job.get("jd") or "")[:800]
    if desc:
        parts.append(desc)

    blob = " ".join(parts).lower()
    # Tokenise: keep multi-char alphanumerics + ./+/# (so HT/LT, AutoCAD,
    # C++, .NET, ETL survive). Treat "HT/LT" as two tokens.
    raw = _re.findall(r"[a-z][a-z0-9\+\.#]{2,}", blob)
    seen: Dict[str, int] = {}
    for t in raw:
        if t in _ROLE_STOPWORDS:
            continue
        if len(t) < 3:
            continue
        seen[t] = seen.get(t, 0) + 1
    # Prefer tokens that appeared multiple times (title duplicated, repeated
    # in JD) — those are the strongest role signals.
    ranked = sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))
    primary = [tok for tok, _ in ranked[:24]]
    # Expand each token with known synonyms so "fintech" matches "BFSI",
    # "k8s" matches "kubernetes", "tech lead" matches "engineering manager", etc.
    return _expand_with_synonyms(primary)


def _role_relevance(
    candidate: Dict[str, Any], role_tokens: List[str]
) -> tuple:
    """Score how strongly a candidate matches the mandate's role signature.

    Returns (score: float in 0..1, matched_tokens: list[str]).
    Designation + skills array carry full weight; summary half-weight.
    """
    if not role_tokens:
        return (1.0, [])
    des = (candidate.get("current_designation") or "").lower()
    head = (candidate.get("headline") or "").lower()
    skills_blob = " ".join(
        s if isinstance(s, str) else (s.get("name") or "")
        for s in (candidate.get("skills") or [])
    ).lower()
    smart = " ".join(candidate.get("smart_tags") or []).lower()
    strong_blob = " ".join([des, head, skills_blob, smart])
    summary_blob = (candidate.get("summary") or "").lower()[:800]

    hits_strong = [t for t in role_tokens if t in strong_blob]
    hits_summary = [
        t for t in role_tokens
        if t not in strong_blob and t in summary_blob
    ]
    # Strong field hit = 1.0, summary-only hit = 0.5
    raw = len(hits_strong) + 0.5 * len(hits_summary)
    score = min(1.0, raw / max(len(role_tokens), 1))
    return (round(score, 4), hits_strong[:6])


def _apply_structured_filters(
    cands: List[Dict[str, Any]],
    filters: Dict[str, Any],
    *,
    strict: bool = False,
) -> List[Dict[str, Any]]:
    """Apply LLM-extracted structured filters as a post-retrieval intersection.

    Two modes
    ---------
    * **strict=False** (free-text query path) — softer matching, missing
      candidate fields don't cause a drop. Designed so AI-parsed filters
      from a vague NL query don't accidentally cull legitimate results.

    * **strict=True** (mandate-driven path, ``job_id`` provided) — the
      mandate is the source of truth: a candidate WITHOUT the
      location/experience/CTC field is rejected when those filters are
      set. Recruiters explicitly picked the mandate — surfacing a
      Delhi candidate for a Chennai mandate is worse than showing fewer
      results.
    """
    if not filters:
        return cands

    min_e = filters.get("min_experience")
    max_e = filters.get("max_experience")
    skills = [s.lower() for s in (filters.get("skills") or []) if s]
    industry_inc = [i.lower() for i in (filters.get("industry_include") or []) if i]
    industry_exc = [i.lower() for i in (filters.get("industry_exclude") or []) if i]
    location_inc = [
        term
        for raw in (filters.get("location_include") or [])
        if raw
        for term in _expand_location_terms(raw)
    ]
    company_inc = [c.lower() for c in (filters.get("company_include") or []) if c]
    company_exc = [c.lower() for c in (filters.get("company_exclude") or []) if c]
    designation_inc = [d.lower() for d in (filters.get("designation_include") or []) if d]
    ctc_min = filters.get("ctc_min")
    ctc_max = filters.get("ctc_max")
    # ±1 year leniency on the experience band — mandates are noisy.
    exp_tol = float(filters.get("experience_tolerance", 1.0))

    out: List[Dict[str, Any]] = []
    for c in cands:
        e = _exp(c)
        # Experience — strict mode rejects when missing, soft mode keeps it
        if min_e is not None or max_e is not None:
            if e is None:
                if strict: continue  # missing exp → drop in strict mode
            else:
                if min_e is not None and e < float(min_e) - exp_tol: continue
                if max_e is not None and e > float(max_e) + exp_tol: continue

        # Location — strict mode drops candidates without a location AND
        # candidates outside the include set. Naukri candidates almost
        # always have a location so the false-drop rate is low.
        if location_inc:
            loc = _location(c)
            if not loc:
                if strict: continue
            else:
                if not any(l in loc for l in location_inc):
                    continue

        # Skills — at least one match required when filter is set.
        # Falls back to designation/headline for things like "Python"
        # appearing in the title but not in the skill array.
        if skills:
            blob = _skills_blob(c)
            if not any(s in blob for s in skills):
                des = _designation(c)
                if not any(s in des for s in skills):
                    continue

        # Industry
        if industry_inc:
            ind = _industry(c)
            if ind and not any(i in ind for i in industry_inc):
                continue
        if industry_exc:
            ind = _industry(c)
            if ind and any(i in ind for i in industry_exc):
                continue

        # Company include/exclude
        emp = (c.get("current_employer") or c.get("current_company") or "").lower()
        if company_inc and emp and not any(co in emp for co in company_inc):
            continue
        if company_exc and emp and any(co in emp for co in company_exc):
            continue

        # Designation
        if designation_inc:
            des = _designation(c)
            if des and not any(d in des for d in designation_inc):
                continue

        # CTC — supports both raw rupees (1_500_000) and lakhs (15.0).
        # We coerce both sides to "rupees" using a 1L threshold heuristic
        # because mandates and candidates store the field inconsistently.
        if ctc_min is not None or ctc_max is not None:
            cur = _ctc_of(c)
            exp_ctc = _expected_ctc_of(c)
            ctc = cur or exp_ctc
            if ctc is None:
                # CTC is SOFT even in strict mode — salary data is missing
                # for ~85% of Indian candidate records and is the most
                # negotiable field. Keep the candidate; let recruiters
                # qualify the band on a call. (Location + experience
                # remain HARD because the data is dense and recruiters
                # treat them as firm constraints.)
                pass
            else:
                # Normalise: any value < 1000 is lakhs, multiply by 1e5
                if ctc < 1000: ctc = ctc * 1e5
                lo = float(ctc_min) if ctc_min is not None else None
                hi = float(ctc_max) if ctc_max is not None else None
                if lo is not None and lo < 1000: lo = lo * 1e5
                if hi is not None and hi < 1000: hi = hi * 1e5
                if lo is not None and ctc < lo * 0.80: continue  # 20% leniency
                if hi is not None and ctc > hi * 1.20: continue

        out.append(c)
    return out


# ──────────────────────────────────────────────────────────────────────
# Result normalisation — both legs return the same shape so the UI can
# render them with one component.
# ──────────────────────────────────────────────────────────────────────

def _explain_match(
    c: Dict[str, Any],
    query: str,
    filters: Optional[Dict[str, Any]] = None,
    *,
    leg: str = "hybrid",
) -> List[Dict[str, str]]:
    """Build a short list of `{label, kind}` reasons explaining why a candidate
    surfaced. Rendered as chips on the A/B Talent Search UI so recruiters can
    quickly trust (or flag) every hit. Pure function — no DB access.

    `kind` is one of: "semantic", "filter", "keyword", "model" (the UI maps
    it to a chip colour). `label` is a short human string (<35 chars).
    """
    reasons: List[Dict[str, str]] = []
    filters = filters or {}

    # 1. Model / retrieval mode — tells the recruiter HOW the hit was found
    mtype = c.get("match_type")
    if leg == "hybrid":
        if mtype == "ltr_xgboost":
            reasons.append({"label": "AI ranker (LTR)", "kind": "model"})
        elif mtype == "cross_encoder":
            reasons.append({"label": "Cross-encoder reranked", "kind": "model"})
        elif mtype == "keyword":
            reasons.append({"label": "Keyword top-up", "kind": "keyword"})
        else:
            reasons.append({"label": "Semantic match", "kind": "semantic"})

    # 1b. Role-relevance — pre-computed by the mandate-driven path. The
    # chip says WHICH role tokens actually matched (designation/skills),
    # which is the recruiter-facing answer to "why did you surface this
    # person for a Utility Project Engineer mandate?".
    rhits = c.get("role_hits")
    if rhits:
        head = ", ".join(rhits[:3])
        extra = f" +{len(rhits)-3}" if len(rhits) > 3 else ""
        reasons.append({"label": f"Role: {head}{extra}", "kind": "filter"})

    # 1c. Prior recruiter signal — if this candidate was shortlisted from
    # an earlier search for the SAME mandate, surface that. Recruiters
    # trust their own past judgment more than the model's score.
    if c.get("prior_shortlist"):
        reasons.append({"label": "✓ You shortlisted before", "kind": "model"})

    # 2. Score band — semantic confidence
    score = c.get("score")
    if isinstance(score, (int, float)) and leg == "hybrid":
        if score >= 0.70:
            reasons.append({"label": f"Strong semantic ({score:.2f})", "kind": "semantic"})
        elif score >= 0.50:
            reasons.append({"label": f"Good semantic ({score:.2f})", "kind": "semantic"})

    # 3. Filter matches — strict signals the recruiter (or mandate) requested
    locs = [
        term
        for raw in (filters.get("location_include") or [])
        if raw
        for term in _expand_location_terms(raw)
    ]
    if locs:
        cand_loc = (c.get("current_location") or "").lower()
        if cand_loc and any(l in cand_loc for l in locs):
            reasons.append({
                "label": f"Location: {c.get('current_location')}",
                "kind": "filter",
            })

    min_e = filters.get("min_experience")
    max_e = filters.get("max_experience")
    if (min_e is not None or max_e is not None) and c.get("experience_years") is not None:
        try:
            e = float(c["experience_years"])
            lo = float(min_e) if min_e is not None else None
            hi = float(max_e) if max_e is not None else None
            if (lo is None or e >= lo - 1) and (hi is None or e <= hi + 1):
                if lo is not None and hi is not None:
                    reasons.append({"label": f"Exp {int(e)}y in {int(lo)}-{int(hi)}y", "kind": "filter"})
                elif lo is not None:
                    reasons.append({"label": f"Exp {int(e)}y ≥ {int(lo)}y", "kind": "filter"})
                elif hi is not None:
                    reasons.append({"label": f"Exp {int(e)}y ≤ {int(hi)}y", "kind": "filter"})
        except (TypeError, ValueError):
            pass

    ctc_min = filters.get("ctc_min")
    ctc_max = filters.get("ctc_max")
    if ctc_min is not None or ctc_max is not None:
        ctc = _ctc_of(c) or _expected_ctc_of(c)
        if ctc is not None:
            ctc_norm = ctc * 1e5 if ctc < 1000 else ctc
            lo = float(ctc_min) if ctc_min is not None else None
            hi = float(ctc_max) if ctc_max is not None else None
            if lo is not None and lo < 1000: lo *= 1e5
            if hi is not None and hi < 1000: hi *= 1e5
            in_lo = lo is None or ctc_norm >= lo * 0.80
            in_hi = hi is None or ctc_norm <= hi * 1.20
            if in_lo and in_hi:
                reasons.append({"label": f"CTC ₹{ctc_norm/1e5:.1f}L in band", "kind": "filter"})

    # 4. Skill / keyword overlap — discrete tokens that matched
    skills_filter = [s.lower() for s in (filters.get("skills") or []) if s]
    cand_skills_blob = _skills_blob(c) + " " + _designation(c)
    if skills_filter:
        hit = [s for s in skills_filter if s in cand_skills_blob]
        if hit:
            head = ", ".join(s.title() for s in hit[:3])
            extra = f" +{len(hit)-3}" if len(hit) > 3 else ""
            reasons.append({"label": f"Skills: {head}{extra}", "kind": "keyword"})

    # 5. Free-text query token hits — same logic as _query_keywords but inlined
    #    so this remains a pure function (no module-level imports of services).
    if query and not skills_filter:
        import re as _re
        toks = [
            t.lower() for t in _re.findall(r"[A-Za-z][A-Za-z\+\-\.]{2,}", query.lower())
            if t.lower() not in {
                "and", "the", "with", "who", "for", "from", "into", "year", "years",
                "exp", "experience", "experienced", "senior", "junior", "lead",
                "candidate", "candidates", "must", "should", "looking",
            }
        ][:8]
        haystack = " ".join([
            cand_skills_blob,
            (c.get("current_employer") or ""),
            (c.get("headline") or ""),
            (c.get("summary") or ""),
        ]).lower()
        hits = [t for t in toks if t in haystack]
        if hits:
            head = ", ".join(t for t in hits[:3])
            extra = f" +{len(hits)-3}" if len(hits) > 3 else ""
            reasons.append({"label": f"Query terms: {head}{extra}", "kind": "keyword"})

    return reasons[:6]   # cap so the chip row stays readable


def _normalise_hybrid(r: Dict[str, Any]) -> Dict[str, Any]:
    """Map a `find_candidates_by_text` result to the unified shape."""
    return {
        "id": r.get("candidate_id") or r.get("id"),
        "name": r.get("candidate_name") or r.get("name"),
        "current_designation": (
            r.get("current_designation") or r.get("designation")
        ),
        "current_employer": (
            r.get("current_employer") or r.get("current_company")
        ),
        "current_location": (
            r.get("current_location") or r.get("location")
        ),
        "experience_years": (
            r.get("experience_years") or r.get("total_experience_years")
        ),
        "skills": r.get("skills") or r.get("key_skills") or [],
        "headline": r.get("headline"),
        "summary": (r.get("summary") or r.get("profile_summary") or "")[:400],
        "industry": r.get("industry") or r.get("current_industry"),
        "smart_tags": r.get("smart_tags") or [],
        "score": round(float(r.get("score") or 0.0), 4),
        "match_type": r.get("match_type") or "vector",
        "match_reasons": r.get("match_reasons") or [],
        "source": "hybrid",
    }


def _normalise_lexical(c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": c.get("id"),
        "name": c.get("name"),
        "current_designation": (
            c.get("current_designation") or c.get("designation")
        ),
        "current_employer": (
            c.get("current_employer") or c.get("current_company")
        ),
        "current_location": (
            c.get("current_location") or c.get("location")
        ),
        "experience_years": (
            c.get("total_experience_years") or c.get("experience_years")
        ),
        "skills": c.get("key_skills") or c.get("skills") or [],
        "headline": c.get("headline"),
        "summary": (c.get("summary") or c.get("profile_summary") or "")[:400],
        "industry": c.get("industry"),
        "smart_tags": c.get("smart_tags") or [],
        "score": None,
        "match_type": "lexical_regex",
        "match_reasons": c.get("match_reasons") or [],
        "source": "lexical",
    }


# ──────────────────────────────────────────────────────────────────────
# Endpoint
# ──────────────────────────────────────────────────────────────────────

@router.post("/search", response_model=TalentSearchResponse)
async def talent_search(
    req: TalentSearchRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Hybrid (semantic + lexical) candidate search with A/B comparison."""
    role = current_user.get("role")
    if role not in ("admin", "employer", "recruiter", "account_manager"):
        raise HTTPException(status_code=403, detail="Not authorised")

    # ── Step 0: Resolve query from job_id when provided ──────────────
    # Lets recruiters pick a running mandate from the UI instead of
    # composing the natural-language query themselves. We synthesise a
    # rich query string from (title + skills + first ~600 chars of JD)
    # and seed structured filters from the mandate (location, min/max
    # experience, skills). The LLM extraction step still runs to layer
    # on whatever extra signal the JD body carries — but that's a free
    # win on top of the deterministic seed.
    job_meta: Optional[Dict[str, Any]] = None
    if req.job_id:
        try:
            job = await db.jobs.find_one({"id": req.job_id}, {"_id": 0})
        except Exception as e:
            logger.warning(f"[TalentSearch] job fetch failed: {e}")
            job = None
        if not job:
            raise HTTPException(status_code=404, detail=f"Mandate {req.job_id} not found")
        synthesised = _build_query_from_job(job)
        if not req.query:
            req.query = synthesised["query"]
        # Seed filters BEFORE the LLM extraction step looks at them.
        # User-supplied filters still override (req.filters wins).
        seed_filters = synthesised["filters"]
        if req.filters:
            seed_filters.update({k: v for k, v in req.filters.items() if v not in (None, [], "")})
        req.filters = seed_filters
        job_meta = {
            "id": job.get("id"),
            "title": job.get("title"),
            "company_name": job.get("company_name"),
        }
        # Role signature for relevance ranking — captures the title +
        # JD-body tokens that genuinely discriminate this role from
        # other Indore/Bangalore/4-10y candidates. Cached on `req` so
        # the hybrid leg can read it without re-extracting.
        role_tokens = _extract_role_signature(job)
        # Seniority of the mandate's title — used to gate the role-relevance
        # step so a "Senior Manager" JD doesn't surface "Junior Manager".
        jd_seniority = _parse_seniority(job.get("title"))
        # Explicit education / certification asks (CA, MBA, B.Tech, IIT, …)
        edu_required = _extract_education_requirements(job)
        # Per-mandate learned weights from recruiter feedback. {} until
        # at least 10 feedback rows accumulate; then tokens that correlate
        # with shortlists are boosted, wrong_role-correlated ones penalised.
        from routes.talent_feedback import (
            shortlisted_candidate_ids,
            mandate_token_weights,
        )
        prior_shortlist_ids = set(await shortlisted_candidate_ids(db, req.job_id))
        token_weights = await mandate_token_weights(db, req.job_id)
    else:
        role_tokens = []
        jd_seniority = None
        edu_required = []
        prior_shortlist_ids = set()
        token_weights = {}

    if not req.query or len(req.query.strip()) < 2:
        raise HTTPException(status_code=400, detail="query or job_id required")

    q = req.query.strip()
    if len(q) < 2:
        raise HTTPException(status_code=400, detail="query too short")

    # Boolean operator parsing — "react developer NOT java" splits into
    # positive query (used for retrieval) and negative terms (used to cull
    # candidates whose blob contains them). Operators stripped from the
    # query so they don't pollute the embedding.
    cleaned_q, _pos_terms, neg_terms = _parse_boolean_query(q)
    if cleaned_q and cleaned_q != q:
        q = cleaned_q

    debug: Dict[str, Any] = {}

    # ── Step 1: LLM filter extraction ────────────────────────────────
    # Reused from the existing ai-search flow so admins see one consistent
    # filter schema across the UI. Failure here is non-fatal — we still
    # run the retrieval legs with an empty filter set.
    #
    # Hard timeout (5 s) so a slow/unreachable RunPod sidecar cannot
    # stall the whole search. The 500s we saw post-deploy traced to
    # extract_filters() hanging past the gunicorn graceful-timeout.
    filters: Dict[str, Any] = req.filters or {}
    extract_ms = 0
    if not filters:
        _es = time.time()
        try:
            extraction = await asyncio.wait_for(extract_filters(q), timeout=5.0)
            filters = (extraction or {}).get("filters") or {}
        except asyncio.TimeoutError:
            logger.warning("[TalentSearch] filter extraction timed out (>5s) — falling back to empty filters")
            filters = {}
            debug["extract_filters_timeout"] = True
        except Exception as e:  # noqa: BLE001 — never want this to 500 the request
            logger.warning(f"[TalentSearch] filter extraction failed: {type(e).__name__}: {e}")
            filters = {}
            debug["extract_filters_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        extract_ms = int((time.time() - _es) * 1000)
        debug["extract_filters_ms"] = extract_ms

    routing_key = f"{current_user.get('id', 'anon')}|{q.lower()}"

    # ── Step 2: HYBRID leg ───────────────────────────────────────────
    t0 = time.time()
    hybrid: List[Dict[str, Any]] = []
    hybrid_breakdown: Dict[str, Any] = {}
    try:
        # Pull a wider pool so structured-filter intersection still leaves
        # us with `limit` results in most cases.
        # Location hint: when the filter (mandate or manual) requests a city,
        # pass it to `find_candidates_by_text` so the service seeds the pool
        # with location-correct candidates before reranking. This fixes the
        # tight-band recall gap (e.g. Bangalore 19-25L returning 0).
        loc_hint = None
        loc_inc = filters.get("location_include") if isinstance(filters, dict) else None
        if loc_inc and isinstance(loc_inc, list) and loc_inc:
            loc_hint = str(loc_inc[0]) if loc_inc[0] else None
        pool = await find_candidates_by_text(
            db, q,
            limit=min(req.limit * 3, 200),
            min_score=0.35,
            routing_key=routing_key,
            timing=hybrid_breakdown,
            location_hint=loc_hint,
        )
        normalised = [_normalise_hybrid(r) for r in pool]
        # Mandate-driven path (job_id provided) — the recruiter explicitly
        # picked a mandate, so location / experience / CTC are HARD bounds.
        # Strict mode also drops candidates whose filter field is missing
        # (no location → reject for a Chennai mandate; no CTC → reject when
        # a salary band is set). Free-text queries keep the softer semantics
        # so vague NL searches don't get over-culled.
        strict_filter = req.job_id is not None
        filtered = _apply_structured_filters(normalised, filters, strict=strict_filter)

        # ── Seniority gate (mandate-driven only) ────────────────────
        # A "Senior Manager" JD shouldn't surface "Junior Manager"
        # candidates even if they pass the exp/location bands. Treat as
        # soft drop (level gap > 1) — keep candidates whose seniority is
        # unknown so we don't over-cull from sparse data.
        if strict_filter and jd_seniority is not None:
            before = len(filtered)
            kept = []
            for c in filtered:
                cand_lvl = _parse_seniority(
                    c.get("current_designation") or c.get("headline")
                )
                if cand_lvl is None or abs(cand_lvl - jd_seniority) <= 1:
                    kept.append(c)
            debug["seniority_gate"] = {
                "jd_level": jd_seniority,
                "before": before,
                "after":  len(kept),
            }
            filtered = kept

        # ── Education / certification gate ───────────────────────────
        if strict_filter and edu_required:
            before = len(filtered)
            filtered = [c for c in filtered if _candidate_matches_education(c, edu_required)]
            debug["education_gate"] = {
                "required": edu_required,
                "before": before,
                "after":  len(filtered),
            }

        # ── Boolean NOT operator (free-text path) ────────────────────
        # Free-text "react developer NOT java" — strip candidates whose
        # blob contains a negative term. We parsed neg_terms above.
        if neg_terms:
            before = len(filtered)
            filtered = [c for c in filtered if not _candidate_has_neg_term(c, neg_terms)]
            debug["boolean_not"] = {
                "negative_terms": neg_terms,
                "before": before,
                "after":  len(filtered),
            }

        if strict_filter and role_tokens:
            # Role-relevance step — keep only candidates whose designation /
            # skills genuinely overlap the mandate's role signature. Without
            # this, "Area Sales Manager" surfaces for a "Utility Project
            # Engineer" mandate just because they share a city + match the
            # exp band. Threshold is intentionally low (≥2 strong-field hits
            # OR ≥0.10 coverage) so we don't over-cull when title tokens
            # are unusually unique.
            scored = []
            for c in filtered:
                rscore, rhits = _role_relevance(c, role_tokens)
                # Apply per-mandate learned weights (from recruiter feedback).
                if token_weights:
                    w_sum = sum(token_weights.get(t, 1.0) for t in rhits) / max(len(rhits), 1)
                    rscore = min(1.0, round(rscore * w_sum, 4))
                c["role_relevance"] = rscore
                c["role_hits"] = rhits
                # Strong-field hits are the discriminative ones (designation /
                # skills). Require ≥2 strong hits OR ≥10% coverage.
                if len(rhits) >= 2 or rscore >= 0.10:
                    scored.append(c)
                elif c.get("id") in prior_shortlist_ids:
                    # Recruiter already shortlisted this person for THIS
                    # mandate before — always keep, even if role-relevance
                    # is low this time around (their data may have changed
                    # or our extractor missed a token).
                    scored.append(c)
            # Re-rank: 60% role-relevance + 40% original retrieval score.
            # +0.50 boost for previously-shortlisted candidates so they
            # pin to the top of subsequent searches.
            for c in scored:
                base = float(c.get("score") or 0.0)
                bonus = 0.50 if c.get("id") in prior_shortlist_ids else 0.0
                # Normalise base into 0..1 (vector scores are already there).
                c["_combined_score"] = round(
                    0.60 * c["role_relevance"] + 0.40 * base + bonus, 4
                )
                if bonus:
                    c["prior_shortlist"] = True
            scored.sort(key=lambda x: x["_combined_score"], reverse=True)
            debug["role_relevance"] = {
                "tokens_extracted": role_tokens[:12],
                "before_role_filter": len(filtered),
                "after_role_filter":  len(scored),
                "prior_shortlist_count": sum(1 for c in scored if c.get("prior_shortlist")),
                "token_weights_active": bool(token_weights),
            }
            filtered = scored

        # ── Stability (job-hopping / tenure) — port from lexical path ──
        # `apply_stability_filters` reads min_avg_tenure_years / max_switches
        # from filters and drops candidates with too many short stints.
        # Soft penalty (already applied via score adjustment in the helper).
        try:
            from services.ai_search import apply_stability_filters as _stab
            before = len(filtered)
            filtered = _stab(filtered, filters or {})
            if before != len(filtered):
                debug["stability_filter"] = {"before": before, "after": len(filtered)}
        except Exception as _se:
            debug["stability_filter_error"] = f"{type(_se).__name__}: {str(_se)[:120]}"
        if strict_filter:
            # Never silently bypass mandate filters — a small but correct
            # result list is strictly better than a long list of mis-matches.
            # Surface the low-recall signal in debug for the UI/analytics.
            if len(filtered) < min(5, req.limit):
                debug["hybrid_low_recall"] = {
                    "after_strict_filter": len(filtered),
                    "original_pool": len(normalised),
                    "filters_applied": sorted(k for k, v in (filters or {}).items() if v not in (None, [], "")),
                }
        else:
            # If structured filters cull too aggressively on a free-text
            # query, fall back to the unfiltered semantic pool so the user
            # still sees ranked results. BUT — never undo an explicit
            # NOT clause from the user (they asked to exclude these).
            if len(filtered) < min(5, req.limit):
                debug["hybrid_filter_relaxed"] = {
                    "after_filter": len(filtered),
                    "original_pool": len(normalised),
                }
                relaxed = normalised
                if neg_terms:
                    relaxed = [c for c in relaxed if not _candidate_has_neg_term(c, neg_terms)]
                filtered = relaxed
        hybrid = filtered[: req.limit]
        # Attach human-readable reasons to each hybrid card (UI chips).
        for c in hybrid:
            c["match_reasons"] = _explain_match(c, q, filters, leg="hybrid")
    except Exception as e:
        logger.exception(f"[TalentSearch] hybrid leg failed: {e}")
        debug["hybrid_error"] = str(e)
    took_hybrid = int((time.time() - t0) * 1000)
    if hybrid_breakdown:
        debug["hybrid_breakdown"] = hybrid_breakdown

    # ── Step 3: LEXICAL leg (A/B) ────────────────────────────────────
    lexical: Optional[List[Dict[str, Any]]] = None
    took_lex = 0
    if req.compare_lexical:
        t0 = time.time()
        try:
            mongo_q = build_mongo_query(filters) if filters else {}
            cursor = db.candidate_bank.find(
                mongo_q, _CANDIDATE_PROJECTION
            ).sort("created_at", -1).limit(req.limit)
            rows = await cursor.to_list(req.limit)
            # Apply stability filters (same as ai-search) for parity
            try:
                rows = apply_stability_filters(rows, filters or {})
            except Exception:
                pass
            lexical = [_normalise_lexical(c) for c in rows]
            for c in lexical:
                c["match_reasons"] = _explain_match(c, q, filters, leg="lexical")
        except Exception as e:
            logger.exception(f"[TalentSearch] lexical leg failed: {e}")
            debug["lexical_error"] = str(e)
            lexical = []
        took_lex = int((time.time() - t0) * 1000)

    # ── Step 4: Lazy enrichment hook ─────────────────────────────────
    # Walk the hybrid leg (the surface the team will actually use) and
    # queue enrichment for any candidate missing canonical fields. The
    # token bucket below caps spend at 100 enrichments / min / worker
    # so a noisy search never overloads RunPod.
    try:
        queued = 0
        for c in hybrid:
            cid = c.get("id")
            if not cid or cid in _ENRICH_BUCKET["seen_ids"]:
                continue
            if not _needs_enrichment(c):
                continue
            if not await _take_token():
                break  # rate-limit hit — leave the rest for later searches
            _ENRICH_BUCKET["seen_ids"].add(cid)
            background_tasks.add_task(_enrich_one, cid)
            queued += 1
        if queued:
            debug["lazy_enrich_queued"] = queued
    except Exception as e:
        logger.debug(f"[TalentSearch] lazy enrich hook failed: {e}")

    return TalentSearchResponse(
        query=q,
        filters=filters,
        took_ms={"hybrid": took_hybrid, "lexical": took_lex},
        hybrid=hybrid,
        lexical=lexical,
        debug=debug or None,
        job=job_meta,
    )


@router.post("/warmup")
async def warmup(current_user: dict = Depends(get_current_user)):
    """Force-load the BGE embedding model AND prime the cluster-vector
    cache so the first user-facing search after a worker restart is hot.

    Runs:
      1. `embed_text("warmup")` — pulls the BGE model into RAM (~5 s cold)
      2. `find_candidates_by_text("warmup")` — fetches the top-3 clusters
         + unclustered bucket into the in-process matrix cache so the
         first real query doesn't pay the per-cluster Mongo round-trip
         (saves ~4-5 s on cold-cache searches over the 139k embedding set).

    Idempotent — caches are TTL'd so subsequent calls do almost nothing.
    """
    if current_user.get("role") not in ("admin", "employer", "recruiter", "account_manager"):
        raise HTTPException(status_code=403, detail="Not authorised")
    import asyncio as _a
    t0 = time.time()
    step_ms: Dict[str, int] = {}
    try:
        from services.talent_graph_service import embed_text, prime_all_clusters
        # Step 1: embedding model
        s = time.time()
        vec = await _a.to_thread(embed_text, "warmup ping")
        step_ms["embed"] = int((time.time() - s) * 1000)
        # Step 2: prime ALL cluster blocks (one-shot)
        s = time.time()
        try:
            primed = await prime_all_clusters(db)
            step_ms["cluster_cache"] = int((time.time() - s) * 1000)
            step_ms["blocks_loaded"] = primed.get("blocks_loaded", 0)
        except Exception as e:
            logger.info(f"[TalentSearch] warmup cluster prime failed: {e}")
            step_ms["cluster_cache"] = int((time.time() - s) * 1000)
        ok = bool(vec)
    except Exception as e:
        logger.warning(f"[TalentSearch] warmup failed: {e}")
        ok = False
    return {
        "ok": ok,
        "took_ms": int((time.time() - t0) * 1000),
        "step_ms": step_ms,
        "model_ready": ok,
    }
