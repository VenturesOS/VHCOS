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
from services.blog_generator import generate_employer_blog, generate_candidate_blog, research_topics
from services.llm_service import get_model
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


class ScheduleConfigRequest(BaseModel):
    employer: Optional[dict] = None
    candidate: Optional[dict] = None


class TrackEventRequest(BaseModel):
    blog_id: str
    event_type: str = Field(..., pattern="^(view|cta_click)$")
    metadata: Optional[dict] = None


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
            "model_used": get_model(),
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


# ── RSS Feed ──

def _build_rss_item(blog: dict, base_url: str) -> str:
    path = "industrial-hiring-insights" if blog.get("blog_type") == "employer" else "career-insights"
    link = f"{base_url}/{path}/{blog.get('slug', '')}"
    pub_date = blog.get("published_at", blog.get("created_at", ""))
    return f"""<item>
  <title>{xml_escape(blog.get('title', ''))}</title>
  <link>{xml_escape(link)}</link>
  <description>{xml_escape(blog.get('meta_description', ''))}</description>
  <pubDate>{pub_date}</pubDate>
  <guid isPermaLink="true">{xml_escape(link)}</guid>
  <category>{xml_escape(blog.get('blog_type', ''))}</category>
</item>"""


@router.get("/api/blog/rss")
async def rss_feed(blog_type: Optional[str] = None):
    """Public: RSS 2.0 feed of published blog posts."""
    query = {"status": "published"}
    if blog_type in ("employer", "candidate"):
        query["blog_type"] = blog_type

    blogs = await db.blog_posts.find(
        query,
        {"_id": 0, "id": 1, "title": 1, "slug": 1, "meta_description": 1,
         "blog_type": 1, "published_at": 1, "created_at": 1}
    ).sort("published_at", -1).limit(50).to_list(50)

    base_url = "https://ventureshrd.com"
    items = "\n".join(_build_rss_item(b, base_url) for b in blogs)
    title = "VHC Talent Advisory Blog"
    if blog_type == "employer":
        title = "Industrial Hiring Insights - VHC Talent Advisory"
    elif blog_type == "candidate":
        title = "Career Insights & Advice - VHC Talent Advisory"

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{xml_escape(title)}</title>
  <link>{xml_escape(base_url)}</link>
  <description>Expert insights on industrial recruitment, career growth, and talent acquisition.</description>
  <language>en-in</language>
  <lastBuildDate>{datetime.now(timezone.utc).isoformat()}</lastBuildDate>
  <atom:link href="{xml_escape(base_url)}/api/blog/rss" rel="self" type="application/rss+xml"/>
{items}
</channel>
</rss>"""

    return Response(content=rss_xml, media_type="application/rss+xml")


# ── Analytics Tracking (Public — No Auth) ──

@router.post("/api/blog/track")
async def track_blog_event(req: TrackEventRequest):
    """Public: track blog page views and CTA clicks."""
    await track_event(req.blog_id, req.event_type, req.metadata)
    return {"ok": True}


# ── Admin: Analytics Dashboard ──

@router.get("/api/blog/analytics/stats")
async def admin_blog_stats(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin: get blog analytics summary."""
    stats = await get_blog_stats(days)
    return stats


@router.get("/api/blog/analytics/views-over-time")
async def admin_views_over_time(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin: get daily views over time."""
    data = await get_views_over_time(days)
    return {"data": data}


@router.get("/api/blog/analytics/top-blogs")
async def admin_top_blogs(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin: get top blogs by views."""
    data = await get_top_blogs(limit, days)
    return {"data": data}


@router.get("/api/blog/analytics/top-clicks")
async def admin_top_clicks(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin: get top blogs by CTA clicks."""
    data = await get_clicks_by_blog(limit, days)
    return {"data": data}


# ── Admin: Auto-Scheduling ──

@router.get("/api/blog/schedule/config")
async def admin_get_schedule(current_user: dict = Depends(require_role(["admin"]))):
    """Admin: get current scheduling configuration."""
    config = await get_schedule_config()
    queue = await get_draft_queue_counts()
    return {"config": config, "draft_queue": queue}


@router.put("/api/blog/schedule/config")
async def admin_update_schedule(req: ScheduleConfigRequest, current_user: dict = Depends(require_role(["admin"]))):
    """Admin: update scheduling configuration."""
    current = await get_schedule_config()
    if req.employer:
        current["employer"] = {**current.get("employer", {}), **req.employer}
    if req.candidate:
        current["candidate"] = {**current.get("candidate", {}), **req.candidate}
    await save_schedule_config(current)
    return {"message": "Schedule updated", "config": current}


@router.post("/api/blog/schedule/trigger")
async def admin_trigger_publish(
    blog_type: str = Query(..., pattern="^(employer|candidate)$"),
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin: manually trigger auto-publish for a blog type."""
    blog_id = await auto_publish_blog(blog_type)
    if not blog_id:
        return {"message": f"No {blog_type} drafts available to publish"}
    return {"message": f"Published one {blog_type} blog", "blog_id": blog_id}


@router.get("/api/blog/schedule/log")
async def admin_schedule_log(
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin: get auto-publish history."""
    logs = await get_schedule_log(limit)
    return {"logs": logs}


# ── AI Topic & Keyword Research ──

class TopicResearchRequest(BaseModel):
    blog_type: str = Field(..., pattern="^(employer|candidate)$")
    industry: Optional[str] = None
    region: Optional[str] = None
    count: int = Field(5, ge=1, le=10)


@router.post("/api/blog/research-topics")
async def admin_research_topics(
    req: TopicResearchRequest,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin: AI-powered topic & keyword research."""
    topics = await research_topics(req.blog_type, req.industry, req.region, req.count)
    return {"topics": topics}


# ── Blog Sitemap.xml ──

@router.get("/api/blog/sitemap.xml")
async def blog_sitemap():
    """Public: generate XML sitemap for all published blog posts."""
    blogs = await db.blog_posts.find(
        {"status": "published"},
        {"_id": 0, "slug": 1, "blog_type": 1, "published_at": 1, "updated_at": 1}
    ).sort("published_at", -1).to_list(500)

    base = "https://ventureshrd.com"
    urls = []

    # Static pages
    static_pages = [
        {"loc": "/", "priority": "1.0"},
        {"loc": "/about", "priority": "0.8"},
        {"loc": "/services", "priority": "0.8"},
        {"loc": "/industries", "priority": "0.7"},
        {"loc": "/careers", "priority": "0.7"},
        {"loc": "/contact", "priority": "0.7"},
        {"loc": "/global-hiring", "priority": "0.7"},
        {"loc": "/industrial-hiring-insights", "priority": "0.8"},
        {"loc": "/career-insights", "priority": "0.8"},
    ]
    for p in static_pages:
        urls.append(f"""  <url>
    <loc>{xml_escape(base + p['loc'])}</loc>
    <priority>{p['priority']}</priority>
    <changefreq>weekly</changefreq>
  </url>""")

    # Blog posts
    for b in blogs:
        path = "industrial-hiring-insights" if b.get("blog_type") == "employer" else "career-insights"
        lastmod = b.get("updated_at") or b.get("published_at", "")
        if lastmod:
            lastmod = lastmod[:10] if isinstance(lastmod, str) else ""
        urls.append(f"""  <url>
    <loc>{xml_escape(f"{base}/{path}/{b.get('slug', '')}")}</loc>
    <lastmod>{lastmod}</lastmod>
    <priority>0.6</priority>
    <changefreq>monthly</changefreq>
  </url>""")

    sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""

    return Response(content=sitemap_xml, media_type="application/xml")


# ── Weekly Blog Digest ──

@router.post("/api/blog/send-digest")
async def admin_send_digest(current_user: dict = Depends(require_role(["admin"]))):
    """Admin: manually trigger weekly blog digest email to candidates."""
    from datetime import timedelta
    from services.email_service import send_email

    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_blogs = await db.blog_posts.find(
        {"status": "published", "published_at": {"$gte": week_ago}},
        {"_id": 0, "title": 1, "slug": 1, "blog_type": 1, "meta_description": 1, "published_at": 1}
    ).sort("published_at", -1).to_list(20)

    if not recent_blogs:
        return {"message": "No blogs published in the last 7 days", "sent": 0}

    # Get candidate emails
    candidates = await db.users.find(
        {"role": "candidate", "email": {"$exists": True}},
        {"_id": 0, "email": 1, "name": 1}
    ).to_list(500)

    if not candidates:
        return {"message": "No candidate subscribers found", "sent": 0}

    # Build digest HTML
    base = "https://ventureshrd.com"
    blog_items = ""
    for b in recent_blogs:
        path = "industrial-hiring-insights" if b.get("blog_type") == "employer" else "career-insights"
        link = f"{base}/{path}/{b.get('slug', '')}"
        blog_items += f"""
        <tr>
          <td style="padding:16px 0;border-bottom:1px solid #E5E7EB;">
            <a href="{link}" style="color:#111827;font-size:16px;font-weight:600;text-decoration:none;">{b.get('title','')}</a>
            <p style="color:#6B7280;font-size:13px;margin:6px 0 0;">{b.get('meta_description','')}</p>
          </td>
        </tr>"""

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;padding:32px;">
      <h2 style="color:#111827;">Weekly Career Insights Digest</h2>
      <p style="color:#6B7280;">Here's what we published this week:</p>
      <table style="width:100%;border-collapse:collapse;">{blog_items}</table>
      <div style="text-align:center;margin-top:28px;">
        <a href="{base}/career-insights" style="display:inline-block;background:#7CB342;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;">Read More Articles</a>
      </div>
      <hr style="border:none;border-top:1px solid #E5E7EB;margin:32px 0 16px;">
      <p style="color:#9CA3AF;font-size:11px;text-align:center;">Ventures HRD Centre Pvt Ltd</p>
    </div>"""

    sent = 0
    for c in candidates:
        try:
            await send_email(
                recipient_email=c["email"],
                subject="Your Weekly Career Insights — Ventures HRD",
                html_content=html,
            )
            sent += 1
        except Exception as e:
            logger.warning(f"[Digest] Failed to send to {c['email']}: {e}")

    # Log the digest send
    await db.blog_digest_log.insert_one({
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "blogs_count": len(recent_blogs),
        "recipients_count": sent,
    })

    return {"message": f"Digest sent to {sent} candidates", "sent": sent, "blogs_included": len(recent_blogs)}
