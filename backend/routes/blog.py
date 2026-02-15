"""
Blog Engine API Routes
- Admin: CRUD, generate, publish, schedule, analytics
- Public: list published, read by slug, RSS feed, tracking
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from xml.sax.saxutils import escape as xml_escape
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from config import db
from utils import get_current_user, require_role
from services.blog_generator import generate_employer_blog, generate_candidate_blog
from services.blog_scheduler import (
    get_schedule_config, save_schedule_config,
    auto_publish_blog, get_schedule_log, get_draft_queue_counts,
)
from services.blog_analytics import (
    track_event, get_blog_stats, get_views_over_time,
    get_top_blogs, get_clicks_by_blog,
)

router = APIRouter(tags=["blog"])
logger = logging.getLogger(__name__)


# ── Pydantic Models ──

class BlogGenerateRequest(BaseModel):
    blog_type: str = Field(..., pattern="^(employer|candidate)$")
    topic: str = Field(..., min_length=5)
    industry: str = Field(..., min_length=2)
    keywords: str = Field(default="")
    # Employer-specific
    region: Optional[str] = Field(default="india", pattern="^(india|global)$")
    # Candidate-specific
    category: Optional[str] = Field(default="career-growth")


class BlogUpdateRequest(BaseModel):
    title: Optional[str] = None
    meta_description: Optional[str] = None
    slug: Optional[str] = None
    content: Optional[str] = None
    keywords: Optional[list] = None
    internal_links: Optional[list] = None
    cta_type: Optional[str] = None
    region: Optional[str] = None
    category: Optional[str] = None
    industry: Optional[str] = None


BLOG_PROJECTION = {"_id": 0}
BLOG_LIST_PROJECTION = {
    "_id": 0, "id": 1, "title": 1, "slug": 1, "meta_description": 1,
    "blog_type": 1, "region": 1, "category": 1, "industry": 1,
    "status": 1, "keywords": 1, "cta_type": 1, "word_count_estimate": 1,
    "created_at": 1, "published_at": 1, "generated_by": 1,
}


# ── Admin Endpoints ──

@router.post("/api/blog/generate")
async def generate_blog(req: BlogGenerateRequest, current_user: dict = Depends(require_role(["admin"]))):
    """One-click blog generation. Saves as draft."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        if req.blog_type == "employer":
            result = await generate_employer_blog(req.topic, req.industry, req.region, req.keywords)
        else:
            result = await generate_candidate_blog(req.topic, req.category, req.industry, req.keywords)
    except Exception as e:
        logger.error(f"[Blog Generate] LLM error: {e}")
        raise HTTPException(status_code=500, detail=f"Content generation failed: {str(e)}")

    blog_doc = {
        "id": str(uuid.uuid4()),
        "title": result.get("title", ""),
        "slug": result.get("slug", ""),
        "meta_description": result.get("meta_description", ""),
        "content": result.get("content", ""),
        "blog_type": req.blog_type,
        "region": req.region if req.blog_type == "employer" else None,
        "category": req.category if req.blog_type == "candidate" else None,
        "industry": req.industry,
        "keywords": result.get("keywords", []),
        "internal_links": result.get("internal_links", []),
        "cta_type": result.get("cta_type", ""),
        "word_count_estimate": result.get("word_count_estimate", 0),
        "status": "draft",
        "generated_by": current_user.get("name", current_user.get("email", "")),
        "generation_log": {
            "topic_source": req.topic,
            "target_keywords": req.keywords,
            "region": req.region,
            "blog_type": req.blog_type,
            "industry": req.industry,
            "category": req.category,
            "model_used": "gpt-4o-mini",
            "generated_at": now,
        },
        "created_at": now,
        "updated_at": now,
        "published_at": None,
    }
    await db.blog_posts.insert_one(blog_doc)
    # Remove _id before returning
    blog_doc.pop("_id", None)
    logger.info(f"[Blog] Generated {req.blog_type} blog: {blog_doc['title']}")
    return blog_doc


@router.get("/api/blog/admin/list")
async def admin_list_blogs(
    blog_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin: list all blogs with filters."""
    query = {}
    if blog_type:
        query["blog_type"] = blog_type
    if status:
        query["status"] = status
    blogs = await db.blog_posts.find(query, BLOG_LIST_PROJECTION).sort("created_at", -1).to_list(500)
    return {"blogs": blogs, "total": len(blogs)}


@router.get("/api/blog/admin/{blog_id}")
async def admin_get_blog(blog_id: str, current_user: dict = Depends(require_role(["admin"]))):
    """Admin: get full blog by ID."""
    blog = await db.blog_posts.find_one({"id": blog_id}, BLOG_PROJECTION)
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    return blog


@router.put("/api/blog/admin/{blog_id}")
async def admin_update_blog(blog_id: str, req: BlogUpdateRequest, current_user: dict = Depends(require_role(["admin"]))):
    """Admin: edit blog content/metadata."""
    update = {k: v for k, v in req.dict().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.blog_posts.update_one({"id": blog_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Blog not found")
    return {"message": "Blog updated"}


@router.put("/api/blog/admin/{blog_id}/publish")
async def admin_publish_blog(blog_id: str, current_user: dict = Depends(require_role(["admin"]))):
    """Admin: publish a draft blog."""
    now = datetime.now(timezone.utc).isoformat()
    result = await db.blog_posts.update_one(
        {"id": blog_id},
        {"$set": {"status": "published", "published_at": now, "updated_at": now}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Blog not found")
    return {"message": "Blog published"}


@router.put("/api/blog/admin/{blog_id}/unpublish")
async def admin_unpublish_blog(blog_id: str, current_user: dict = Depends(require_role(["admin"]))):
    """Admin: unpublish back to draft."""
    result = await db.blog_posts.update_one(
        {"id": blog_id},
        {"$set": {"status": "draft", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Blog not found")
    return {"message": "Blog unpublished"}


@router.delete("/api/blog/admin/{blog_id}")
async def admin_delete_blog(blog_id: str, current_user: dict = Depends(require_role(["admin"]))):
    """Admin: delete a blog post."""
    result = await db.blog_posts.delete_one({"id": blog_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Blog not found")
    return {"message": "Blog deleted"}


# ── Public Endpoints (No Auth) ──

@router.get("/api/blog/employer")
async def public_employer_blogs(page: int = Query(1, ge=1), limit: int = Query(12, ge=1, le=50)):
    """Public: list published employer blogs."""
    skip = (page - 1) * limit
    query = {"blog_type": "employer", "status": "published"}
    total = await db.blog_posts.count_documents(query)
    blogs = await db.blog_posts.find(
        query,
        {"_id": 0, "id": 1, "title": 1, "slug": 1, "meta_description": 1,
         "region": 1, "industry": 1, "keywords": 1, "published_at": 1, "word_count_estimate": 1}
    ).sort("published_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"blogs": blogs, "total": total, "page": page, "pages": (total + limit - 1) // limit}


@router.get("/api/blog/employer/{slug}")
async def public_employer_blog_by_slug(slug: str):
    """Public: get single employer blog by slug."""
    blog = await db.blog_posts.find_one(
        {"blog_type": "employer", "status": "published", "slug": slug}, BLOG_PROJECTION
    )
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    return blog


@router.get("/api/blog/candidate")
async def public_candidate_blogs(page: int = Query(1, ge=1), limit: int = Query(12, ge=1, le=50), category: Optional[str] = None):
    """Public: list published candidate blogs."""
    skip = (page - 1) * limit
    query = {"blog_type": "candidate", "status": "published"}
    if category:
        query["category"] = category
    total = await db.blog_posts.count_documents(query)
    blogs = await db.blog_posts.find(
        query,
        {"_id": 0, "id": 1, "title": 1, "slug": 1, "meta_description": 1,
         "category": 1, "industry": 1, "keywords": 1, "published_at": 1, "word_count_estimate": 1}
    ).sort("published_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"blogs": blogs, "total": total, "page": page, "pages": (total + limit - 1) // limit}


@router.get("/api/blog/candidate/{slug}")
async def public_candidate_blog_by_slug(slug: str):
    """Public: get single candidate blog by slug."""
    blog = await db.blog_posts.find_one(
        {"blog_type": "candidate", "status": "published", "slug": slug}, BLOG_PROJECTION
    )
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    return blog
