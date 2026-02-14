"""
AI Search API Route — Phase 1
POST /api/ai-search — Natural language candidate search
"""
import time
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from config import db
from utils import require_role
from services.ai_search import extract_filters, build_mongo_query, apply_stability_filters, generate_explanations

logger = logging.getLogger(__name__)
ai_search_router = APIRouter(prefix="/api", tags=["AI Search"])

CANDIDATE_PROJECTION = {
    "_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1,
    "headline": 1, "designation": 1, "current_employer": 1, "industry": 1,
    "experience_years": 1, "experience": 1, "location": 1, "current_city": 1,
    "skills": 1, "it_skills": 1, "summary": 1,
    "highest_qualification": 1, "highest_degree": 1, "education": 1,
    "notice_period": 1, "notice_period_days": 1, "is_serving_notice": 1,
    "current_salary": 1, "expected_salary": 1,
    "preferred_locations": 1, "preferred_industry": 1,
    "source": 1, "created_by": 1, "photo_url": 1,
}


class AISearchRequest(BaseModel):
    prompt: str
    limit: int = 50
    generate_explanations: bool = True


class AISearchResponse(BaseModel):
    candidates: list
    total: int
    filters_used: dict
    log: dict


@ai_search_router.post("/ai-search")
async def ai_search(
    req: AISearchRequest,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"])),
):
    """Natural language AI-powered candidate search."""
    start = time.time()

    if not req.prompt or len(req.prompt.strip()) < 5:
        raise HTTPException(status_code=400, detail="Search prompt is too short.")

    # STEP 1: LLM extracts structured filters
    try:
        extraction = await extract_filters(req.prompt)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    filters = extraction["filters"]
    extraction_log = extraction["log"]

    # STEP 2: Build deterministic MongoDB query
    mongo_query = build_mongo_query(filters)
    logger.info(f"[AI Search] Mongo query: {mongo_query}")

    # Execute query
    candidates = await db.candidate_bank.find(
        mongo_query, CANDIDATE_PROJECTION
    ).sort("experience_years", -1).limit(min(req.limit, 200)).to_list(min(req.limit, 200))

    # Apply post-query stability filters
    candidates = apply_stability_filters(candidates, filters)

    total = len(candidates)
    logger.info(f"[AI Search] DB returned {total} candidates in {time.time() - start:.2f}s")

    # STEP 3: Generate AI explanations
    if req.generate_explanations and candidates:
        candidates = await generate_explanations(candidates, filters)

    elapsed = round(time.time() - start, 2)
    extraction_log["total_time_s"] = elapsed
    extraction_log["candidates_found"] = total

    # Store search log
    try:
        log_doc = {
            "raw_prompt": extraction_log.get("raw_prompt", ""),
            "extracted_filters": extraction_log.get("extracted_filters", {}),
            "model": extraction_log.get("model", ""),
            "token_usage": extraction_log.get("token_usage", {}),
            "extraction_time_s": extraction_log.get("extraction_time_s", 0),
            "total_time_s": elapsed,
            "candidates_found": total,
            "user_id": current_user.get("id"),
            "user_email": current_user.get("email"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.ai_search_logs.insert_one(log_doc)
        logger.info(f"[AI Search] Log saved successfully")
    except Exception as e:
        logger.warning(f"[AI Search] Failed to log search: {e}")

    return {
        "candidates": candidates,
        "total": total,
        "filters_used": filters,
        "log": {"model": extraction_log.get("model"), "time_s": elapsed, "tokens": extraction_log.get("token_usage", {})},
    }
