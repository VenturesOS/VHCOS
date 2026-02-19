"""
SEO Routes — Sitemap, robots.txt, SEO settings admin API
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from xml.sax.saxutils import escape as xml_escape
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import Response, PlainTextResponse
from pydantic import BaseModel

from config import db
from utils import require_role

router = APIRouter(tags=["seo"])
logger = logging.getLogger(__name__)

BASE_URL = "https://ventureshrd.com"


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

    # Active job listings with shareable links
    jobs = await db.jobs.find(
        {"shareable_link_enabled": True},
        {"_id": 0, "id": 1, "title": 1, "updated_at": 1, "created_at": 1}
    ).to_list(500)

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

Sitemap: {BASE_URL}/api/sitemap.xml
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
