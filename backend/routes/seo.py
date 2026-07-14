"""
SEO Routes — Sitemap, robots.txt, SEO settings admin API
"""
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional
from xml.sax.saxutils import escape as xml_escape
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import Response, PlainTextResponse
from pydantic import BaseModel

from config import db
from utils import require_role
from services import indexnow, google_indexing

router = APIRouter(tags=["seo"])
logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("SITE_URL", "https://ventureshrd.com").rstrip("/")


# ── Comprehensive XML Sitemap ──

@router.get("/api/sitemap.xml")
async def comprehensive_sitemap():
    """Auto-generated sitemap including static pages, blogs, and job listings."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = []

    # Static pages with SEO priorities
    static_pages = [
        {"loc": "/", "priority": "1.0", "changefreq": "weekly"},
        {"loc": "/about", "priority": "0.8", "changefreq": "monthly"},
        {"loc": "/services", "priority": "0.9", "changefreq": "monthly"},
        {"loc": "/industries", "priority": "0.8", "changefreq": "monthly"},
        {"loc": "/careers", "priority": "0.8", "changefreq": "daily"},
        {"loc": "/contact", "priority": "0.7", "changefreq": "monthly"},
        {"loc": "/global-hiring", "priority": "0.8", "changefreq": "monthly"},
        {"loc": "/recruitment-expertise", "priority": "0.9", "changefreq": "monthly"},
        {"loc": "/industrial-hiring-insights", "priority": "0.9", "changefreq": "daily"},
        {"loc": "/career-insights", "priority": "0.8", "changefreq": "daily"},
        {"loc": "/industrial-recruitment", "priority": "0.9", "changefreq": "weekly"},
        {"loc": "/hr-consulting-services", "priority": "0.9", "changefreq": "weekly"},
    ]
    for p in static_pages:
        urls.append(f"""  <url>
    <loc>{xml_escape(BASE_URL + p['loc'])}</loc>
    <lastmod>{now}</lastmod>
    <changefreq>{p['changefreq']}</changefreq>
    <priority>{p['priority']}</priority>
  </url>""")

    # Published blog posts
    blogs = await db.blog_posts.find(
        {"status": "published"},
        {"_id": 0, "slug": 1, "blog_type": 1, "published_at": 1, "updated_at": 1}
    ).sort("published_at", -1).to_list(1000)

    for b in blogs:
        path = "industrial-hiring-insights" if b.get("blog_type") == "employer" else "career-insights"
        lastmod = b.get("updated_at") or b.get("published_at", now)
        if isinstance(lastmod, str):
            lastmod = lastmod[:10]
        urls.append(f"""  <url>
    <loc>{xml_escape(f"{BASE_URL}/{path}/{b.get('slug', '')}")}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>""")

    # Active job listings on the public careers page. All active jobs are
    # auto-exposed for maximum SEO coverage; only explicit takedowns
    # (`career_page_status == 'removed'`) are excluded. Archived / on_hold /
    # closed / draft roles are already skipped by the status filter.
    jobs = await db.jobs.find(
        {
            "status": "active",
            "career_page_status": {"$ne": "removed"},
        },
        {"_id": 0, "id": 1, "title": 1, "updated_at": 1, "created_at": 1}
    ).to_list(2000)

    for j in jobs:
        lastmod = j.get("updated_at") or j.get("created_at", now)
        if isinstance(lastmod, str):
            lastmod = lastmod[:10]
        elif hasattr(lastmod, "strftime"):
            lastmod = lastmod.strftime("%Y-%m-%d")
        urls.append(f"""  <url>
    <loc>{xml_escape(f"{BASE_URL}/jobs/{j.get('id', '')}")}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
  </url>""")

    sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9
        http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">
{chr(10).join(urls)}
</urlset>"""

    return Response(content=sitemap_xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


# ── robots.txt (served from backend for dynamic control) ──

@router.get("/api/robots.txt")
async def robots_txt():
    """Dynamic robots.txt with sitemap reference."""
    content = f"""User-agent: *
Allow: /
Allow: /about
Allow: /services
Allow: /industries
Allow: /careers
Allow: /contact
Allow: /global-hiring
Allow: /industrial-hiring-insights
Allow: /career-insights
Allow: /industrial-recruitment
Allow: /hr-consulting-services

Disallow: /admin
Disallow: /employer
Disallow: /recruiter
Disallow: /candidate
Disallow: /login
Disallow: /register
Disallow: /api/

Sitemap: {BASE_URL}/sitemap.xml
"""
    return PlainTextResponse(content=content, headers={"Cache-Control": "public, max-age=86400"})


# ── SEO Settings Admin API (Meta Override) ──

class SeoSettingUpdate(BaseModel):
    page_path: str
    title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    canonical_url: Optional[str] = None


@router.get("/api/seo/settings")
async def get_seo_settings(current_user: dict = Depends(require_role(["admin"]))):
    """Admin: get all SEO meta overrides."""
    settings = await db.seo_settings.find({}, {"_id": 0}).to_list(100)
    return {"settings": settings}


@router.get("/api/seo/settings/{page_path:path}")
async def get_page_seo(page_path: str, current_user: dict = Depends(require_role(["admin"]))):
    """Admin: get SEO override for a specific page."""
    setting = await db.seo_settings.find_one({"page_path": page_path}, {"_id": 0})
    if not setting:
        return {"page_path": page_path, "title": None, "meta_description": None}
    return setting


@router.put("/api/seo/settings")
async def update_seo_setting(req: SeoSettingUpdate, current_user: dict = Depends(require_role(["admin"]))):
    """Admin: create or update SEO override for a page."""
    update = {k: v for k, v in req.dict().items() if v is not None}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = current_user.get("email", "")

    await db.seo_settings.update_one(
        {"page_path": req.page_path},
        {"$set": update},
        upsert=True,
    )
    return {"message": f"SEO settings updated for {req.page_path}"}


@router.delete("/api/seo/settings/{page_path:path}")
async def delete_seo_setting(page_path: str, current_user: dict = Depends(require_role(["admin"]))):
    """Admin: remove SEO override for a page."""
    result = await db.seo_settings.delete_one({"page_path": page_path})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="No setting found for this page")
    return {"message": f"SEO settings removed for {page_path}"}


# ── IndexNow + Google Indexing API admin endpoints ─────────────────────────


async def _collect_public_urls(limit: int = 5000) -> List[str]:
    """Return every canonical public URL that belongs in our sitemap.
    Shared by the sitemap generator (for pings) and the IndexNow admin
    endpoint so the two never drift.
    """
    urls: List[str] = []

    # 1. Static / evergreen pages.
    for p in [
        "/", "/about", "/services", "/industries", "/careers", "/contact",
        "/global-hiring", "/recruitment-expertise",
        "/industrial-hiring-insights", "/career-insights",
        "/industrial-recruitment", "/hr-consulting-services",
    ]:
        urls.append(f"{BASE_URL}{p}")

    # 2. Published blog posts.
    blogs = await db.blog_posts.find(
        {"status": "published"},
        {"_id": 0, "slug": 1, "blog_type": 1},
    ).to_list(1000)
    for b in blogs:
        path = "industrial-hiring-insights" if b.get("blog_type") == "employer" else "career-insights"
        slug = b.get("slug", "")
        if slug:
            urls.append(f"{BASE_URL}/{path}/{slug}")

    # 3. Active public jobs — same filter as list/sitemap endpoints.
    jobs = await db.jobs.find(
        {"status": "active", "career_page_status": {"$ne": "removed"}},
        {"_id": 0, "id": 1},
    ).to_list(limit)
    for j in jobs:
        jid = j.get("id")
        if jid:
            urls.append(f"{BASE_URL}/jobs/{jid}")

    return urls


class IndexNowSubmitRequest(BaseModel):
    urls: Optional[List[str]] = None  # if None → submit the whole sitemap


@router.post("/api/admin/seo/indexnow/submit")
async def indexnow_submit(
    req: IndexNowSubmitRequest,
    current_user: dict = Depends(require_role(["admin"])),
):
    """Push URLs to Bing / Yandex / Seznam / Naver via IndexNow.

    - No body → submit every URL in the sitemap (careers page + all active jobs + blog posts + static pages).
    - `{"urls": [...]}` → submit an explicit list (max 10,000).
    """
    urls = req.urls if req.urls else await _collect_public_urls()
    if not urls:
        return {"ok": True, "submitted": 0, "total": 0, "message": "no URLs to submit"}
    result = await indexnow.submit_batch(urls)
    result["initiated_by"] = current_user.get("email")
    return result


@router.get("/api/admin/seo/indexnow/status")
async def indexnow_status(current_user: dict = Depends(require_role(["admin"]))):
    """Verify IndexNow is configured and the key file is reachable."""
    key = (os.environ.get("INDEXNOW_KEY") or "").strip()
    if not key:
        return {"configured": False, "reason": "INDEXNOW_KEY not set in backend .env"}
    key_url = f"{BASE_URL}/{key}.txt"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(key_url)
        return {
            "configured": True,
            "key_prefix": key[:6] + "…",
            "key_url": key_url,
            "key_file_status": r.status_code,
            "key_file_reachable": r.status_code == 200 and r.text.strip() == key,
        }
    except Exception as exc:
        return {"configured": True, "key_url": key_url, "error": str(exc)}


class GoogleIndexingRequest(BaseModel):
    url: str
    deleted: bool = False


@router.post("/api/admin/seo/google-indexing/ping")
async def google_indexing_ping(
    req: GoogleIndexingRequest,
    current_user: dict = Depends(require_role(["admin"])),
):
    """Ping Google's Indexing API for a single URL (JobPosting URLs only).

    Requires `GOOGLE_INDEXING_CREDENTIALS_JSON` in backend `.env`. See
    `backend/services/google_indexing.py` docstring for setup.
    """
    if req.deleted:
        result = await google_indexing.ping_url_deleted(req.url)
    else:
        result = await google_indexing.ping_url_updated(req.url)
    result["initiated_by"] = current_user.get("email")
    return result


@router.get("/api/admin/seo/summary")
async def seo_admin_summary(current_user: dict = Depends(require_role(["admin"]))):
    """One-shot SEO dashboard payload — sitemap size, live jobs, published blogs."""
    live_jobs = await db.jobs.count_documents({
        "status": "active",
        "career_page_status": {"$ne": "removed"},
    })
    published_blogs = await db.blog_posts.count_documents({"status": "published"})
    return {
        "sitemap_url":         f"{BASE_URL}/sitemap.xml",
        "sitemap_api_url":     f"{BASE_URL}/api/sitemap.xml",
        "gsc_submit_url":      f"https://search.google.com/search-console/sitemaps?resource_id={BASE_URL}",
        "live_public_jobs":    live_jobs,
        "published_blogs":     published_blogs,
        "static_pages":        12,
        "estimated_url_count": live_jobs + published_blogs + 12,
        "indexnow_configured": bool((os.environ.get("INDEXNOW_KEY") or "").strip()),
        "google_indexing_configured": bool((os.environ.get("GOOGLE_INDEXING_CREDENTIALS_JSON") or "").strip()),
    }
