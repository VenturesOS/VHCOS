"""
VHC Talent OS - Background Jobs & Embeddings Routes
API endpoints for job queue management and embedding operations.
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel

from config import db
from utils import get_current_user, require_role
from services import job_queue, JobType, JobStatus, BackgroundJob, cache
from services.embeddings import embedding_service, batch_generate_embeddings

logger = logging.getLogger(__name__)

jobs_router = APIRouter(tags=["Background Jobs"])


# ============== Job Queue Endpoints ==============

class CreateJobRequest(BaseModel):
    job_type: str
    input_data: dict = {}


@jobs_router.post("/background-jobs", response_model=BackgroundJob)
async def create_background_job(
    request: CreateJobRequest,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Create and start a background job."""
    try:
        job_type = JobType(request.job_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid job type: {request.job_type}")
    
    job = await job_queue.enqueue_and_process(
        job_type=job_type,
        input_data=request.input_data,
        created_by=current_user["id"]
    )
    
    return job


@jobs_router.get("/background-jobs/{job_id}", response_model=BackgroundJob)
async def get_background_job(
    job_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get status of a background job."""
    job = await job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Only allow access to own jobs or admin
    if job.created_by != current_user["id"] and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    
    return job


@jobs_router.get("/background-jobs", response_model=List[BackgroundJob])
async def list_background_jobs(
    job_type: Optional[str] = None,
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    """List background jobs for current user."""
    jt = JobType(job_type) if job_type else None
    jobs = await job_queue.get_jobs_by_user(
        user_id=current_user["id"],
        job_type=jt,
        limit=limit
    )
    return jobs


@jobs_router.delete("/background-jobs/{job_id}")
async def cancel_background_job(
    job_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Cancel a running background job."""
    success = await job_queue.cancel_job(job_id)
    if success:
        return {"message": "Job cancelled"}
    return {"message": "Job not running or already completed"}


# ============== Embedding Endpoints ==============

class EmbeddingStatsResponse(BaseModel):
    total_candidates: int
    with_embeddings: int
    without_embeddings: int
    coverage_percent: float


@jobs_router.get("/embeddings/stats", response_model=EmbeddingStatsResponse)
async def get_embedding_stats(
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get statistics about candidate embeddings."""
    total = await db.candidate_bank.count_documents({})
    with_emb = await db.candidate_bank.count_documents({"embedding": {"$exists": True}})
    without_emb = total - with_emb
    
    return EmbeddingStatsResponse(
        total_candidates=total,
        with_embeddings=with_emb,
        without_embeddings=without_emb,
        coverage_percent=round((with_emb / total * 100) if total > 0 else 0, 2)
    )


@jobs_router.post("/embeddings/generate-batch")
async def generate_batch_embeddings(
    background_tasks: BackgroundTasks,
    limit: int = 100,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Start batch embedding generation for candidates without embeddings.
    Returns a job ID to track progress.
    """
    job = await job_queue.enqueue_and_process(
        job_type=JobType.BATCH_EMBEDDING,
        input_data={"limit": limit},
        created_by=current_user["id"]
    )
    
    return {
        "message": "Batch embedding generation started",
        "job_id": job.id,
        "status_url": f"/api/background-jobs/{job.id}"
    }


# ============== Cache Management Endpoints ==============

class CacheStatsResponse(BaseModel):
    enabled: bool
    message: str


@jobs_router.get("/cache/stats", response_model=CacheStatsResponse)
async def get_cache_stats(
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get cache status."""
    return CacheStatsResponse(
        enabled=cache.enabled,
        message="Redis cache is active" if cache.enabled else "Redis cache is disabled"
    )


@jobs_router.post("/cache/clear")
async def clear_cache(
    pattern: str = "*",
    current_user: dict = Depends(require_role(["admin"]))
):
    """Clear cache entries matching pattern."""
    if pattern == "search":
        deleted = cache.invalidate_search_cache()
    elif pattern == "match":
        deleted = cache.invalidate_match_cache()
    elif pattern == "*":
        # Clear all caches
        deleted = cache.delete_pattern("*")
    else:
        deleted = cache.delete_pattern(f"{pattern}:*")
    
    return {"message": f"Cleared {deleted} cache entries", "pattern": pattern}
