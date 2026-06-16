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
    location_inc = [l.lower() for l in (filters.get("location_include") or []) if l]
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
                if strict: continue
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

    if not req.query or len(req.query.strip()) < 2:
        raise HTTPException(status_code=400, detail="query or job_id required")

    q = req.query.strip()
    if len(q) < 2:
        raise HTTPException(status_code=400, detail="query too short")

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
        pool = await find_candidates_by_text(
            db, q,
            limit=min(req.limit * 3, 200),
            min_score=0.35,
            routing_key=routing_key,
            timing=hybrid_breakdown,
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
            # still sees ranked results.
            if len(filtered) < min(5, req.limit):
                debug["hybrid_filter_relaxed"] = {
                    "after_filter": len(filtered),
                    "original_pool": len(normalised),
                }
                filtered = normalised
        hybrid = filtered[: req.limit]
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
