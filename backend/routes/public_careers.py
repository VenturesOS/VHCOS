"""
Public Careers API — no-auth endpoints powering the /careers page + SEO.

Endpoints:
    GET  /api/public/careers/jobs                 List of live public jobs
    GET  /api/public/careers/jobs/{job_id}        Single public job (bonus)
    GET  /api/public/careers/filters              Filter facets (function/location)

A "public" job is any `status == 'active'` role whose `career_page_status`
has not been explicitly set to `'removed'` (recruiter takedown). This gives
maximum SEO coverage — all live mandates surface on `/careers` the moment
they are created, without requiring an explicit "publish" toggle.

To hide a specific role from the public careers page, either:
    - set `status` to something other than `'active'` (e.g. `'archived'`), OR
    - set `career_page_status` to `'removed'`.

We intentionally return `public_company_alias` (a masked name) rather than the
real client company on the list endpoint — recruiters use that to hide the
end client while still showing the role publicly. If no alias is set we fall
back to the client's industry vertical so cards aren't blank.
"""
from __future__ import annotations
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config import db

router = APIRouter(prefix="/api/public/careers", tags=["public-careers"])
logger = logging.getLogger(__name__)


# ── Query ─────────────────────────────────────────────────────────────────

_PUBLIC_FILTER = {
    "status": "active",
    "career_page_status": {"$ne": "removed"},
}

# Fields returned to the /careers page card grid. Deliberately narrow — we
# don't want to leak salary bands, internal notes, or client-real-name.
_LIST_PROJECTION = {
    "_id": 0,
    "id": 1,
    "title": 1,
    "public_company_alias": 1,
    "industry": 1,
    "location": 1,
    "function": 1,
    "seniority": 1,
    "employment_type": 1,
    "experience_min": 1,
    "experience_max": 1,
    "created_at": 1,
    "updated_at": 1,
    "career_page_status": 1,
    "shareable_link_enabled": 1,
}


class PublicJobCard(BaseModel):
    id: str
    title: str
    company_display: str
    industry: Optional[str] = None
    location: Optional[str] = None
    function: Optional[str] = None
    seniority: Optional[str] = None
    employment_type: Optional[str] = None
    experience_range: Optional[str] = None
    posted_at: Optional[str] = None


def _to_card(doc: dict) -> PublicJobCard:
    exp_min = doc.get("experience_min")
    exp_max = doc.get("experience_max")
    exp_range = None
    if exp_min is not None and exp_max is not None:
        exp_range = f"{exp_min}–{exp_max} yrs"
    elif exp_min is not None:
        exp_range = f"{exp_min}+ yrs"

    company_display = (
        doc.get("public_company_alias")
        or doc.get("industry")
        or "Confidential"
    )

    posted = doc.get("updated_at") or doc.get("created_at")
    if hasattr(posted, "isoformat"):
        posted = posted.isoformat()
    if isinstance(posted, str):
        posted = posted[:10]

    return PublicJobCard(
        id=doc["id"],
        title=doc.get("title", "Open Role"),
        company_display=company_display,
        industry=doc.get("industry"),
        location=doc.get("location"),
        function=doc.get("function"),
        seniority=doc.get("seniority"),
        employment_type=doc.get("employment_type"),
        experience_range=exp_range,
        posted_at=posted,
    )


@router.get("/jobs")
async def list_public_jobs(
    q: Optional[str] = Query(None, description="Free-text search on title/function"),
    function: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    seniority: Optional[str] = Query(None),
    experience_min: Optional[int] = Query(None, ge=0, description="Include jobs whose max exp >= this"),
    experience_max: Optional[int] = Query(None, ge=0, description="Include jobs whose min exp <= this"),
    sort: str = Query("recent", pattern="^(recent|oldest|title)$"),
    limit: int = Query(24, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    """Public listing of live jobs for the careers page."""
    query = dict(_PUBLIC_FILTER)
    if q:
        query["$and"] = [{"$or": [
            {"title":    {"$regex": q, "$options": "i"}},
            {"function": {"$regex": q, "$options": "i"}},
            {"seniority":{"$regex": q, "$options": "i"}},
        ]}]
    if function:
        query["function"] = function
    if location:
        query["location"] = {"$regex": location, "$options": "i"}
    if seniority:
        query["seniority"] = seniority

    # Experience range: overlap semantics — return jobs whose [min,max] band
    # intersects the user's filter band. Nulls are treated as "any".
    exp_conditions = []
    if experience_min is not None:
        exp_conditions.append({"$or": [
            {"experience_max": {"$gte": experience_min}},
            {"experience_max": None},
            {"experience_max": {"$exists": False}},
        ]})
    if experience_max is not None:
        exp_conditions.append({"$or": [
            {"experience_min": {"$lte": experience_max}},
            {"experience_min": None},
            {"experience_min": {"$exists": False}},
        ]})
    if exp_conditions:
        query.setdefault("$and", []).extend(exp_conditions)

    sort_spec = [("updated_at", -1)]
    if sort == "oldest":
        sort_spec = [("created_at", 1)]
    elif sort == "title":
        sort_spec = [("title", 1)]

    total = await db.jobs.count_documents(query)
    cursor = db.jobs.find(query, _LIST_PROJECTION).sort(sort_spec).skip(skip).limit(limit)
    docs = await cursor.to_list(limit)
    return {
        "total": total,
        "count": len(docs),
        "skip":  skip,
        "limit": limit,
        "jobs":  [_to_card(d).model_dump() for d in docs],
    }


@router.get("/jobs/{job_id}")
async def get_public_job(job_id: str):
    """Single-job detail for the public careers page card / share URL."""
    query = dict(_PUBLIC_FILTER)
    query["id"] = job_id
    doc = await db.jobs.find_one(query, _LIST_PROJECTION)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found or not public")
    return _to_card(doc).model_dump()


@router.get("/filters")
async def public_career_filters():
    """Distinct function/location/seniority values across live jobs.

    Powers the filter sidebar without exposing sensitive metadata. Caching
    at the HTTP layer (cache-control) is left to nginx if needed.
    """
    async def _distinct(field: str) -> list:
        vals = await db.jobs.distinct(field, _PUBLIC_FILTER)
        return sorted([v for v in vals if isinstance(v, str) and v.strip()])

    return {
        "functions":   await _distinct("function"),
        "locations":   await _distinct("location"),
        "seniorities": await _distinct("seniority"),
    }
