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
    query: str = Field(..., min_length=2)
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


def _apply_structured_filters(
    cands: List[Dict[str, Any]],
    filters: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Apply LLM-extracted structured filters as a post-retrieval intersection.

    Soft-match philosophy: we drop a candidate only when a filter EXPLICITLY
    contradicts them. Missing fields on the candidate are kept — the hybrid
    retriever already used the semantic signal to surface them.
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

    out: List[Dict[str, Any]] = []
    for c in cands:
        e = _exp(c)
        # Experience — only filter when candidate HAS the field
        if e is not None:
            if min_e is not None and e < float(min_e):
                continue
            if max_e is not None and e > float(max_e):
                continue

        # Skills — at least one match required when filter is set
        if skills:
            blob = _skills_blob(c)
            if not any(s in blob for s in skills):
                # Soft escape: also check designation/headline for the skill
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

        # Location
        if location_inc:
            loc = _location(c)
            if loc and not any(l in loc for l in location_inc):
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

    q = req.query.strip()
    if len(q) < 2:
        raise HTTPException(status_code=400, detail="query too short")

    # ── Step 1: LLM filter extraction ────────────────────────────────
    # Reused from the existing ai-search flow so admins see one consistent
    # filter schema across the UI. Failure here is non-fatal — we still
    # run the retrieval legs with an empty filter set.
    filters: Dict[str, Any] = req.filters or {}
    if not filters:
        try:
            extraction = await extract_filters(q)
            filters = extraction.get("filters") or {}
        except Exception as e:
            logger.info(f"[TalentSearch] filter extraction skipped: {e}")
            filters = {}

    routing_key = f"{current_user.get('id', 'anon')}|{q.lower()}"
    debug: Dict[str, Any] = {}

    # ── Step 2: HYBRID leg ───────────────────────────────────────────
    t0 = time.time()
    hybrid: List[Dict[str, Any]] = []
    try:
        # Pull a wider pool so structured-filter intersection still leaves
        # us with `limit` results in most cases.
        pool = await find_candidates_by_text(
            db, q,
            limit=min(req.limit * 3, 200),
            min_score=0.35,
            routing_key=routing_key,
        )
        normalised = [_normalise_hybrid(r) for r in pool]
        filtered = _apply_structured_filters(normalised, filters)
        # If structured filters cull too aggressively, fall back to the
        # unfiltered semantic pool so the user still sees ranked results.
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
