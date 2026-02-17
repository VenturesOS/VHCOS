"""
SEO Monitoring Dashboard — Admin-only endpoints.
Collections: seo_snapshots, seo_alerts
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends

from config import db
from utils import require_role

router = APIRouter(tags=["seo-dashboard"])
logger = logging.getLogger(__name__)

PILLAR_SLUGS = ["industrial-recruitment", "hr-consulting-services", "career-insights"]


def _strip_html(html: str) -> str:
    return re.sub(r'<[^>]+>', ' ', html)


def _count_internal_links(html: str) -> int:
    return len(re.findall(r'<a\s[^>]*href=["\']/(industrial-recruitment|hr-consulting-services|career-insights)', html))


# ── Live dashboard metrics ──

@router.get("/api/admin/seo-dashboard")
async def get_seo_dashboard(current_user: dict = Depends(require_role(["admin"]))):
    """Compute and return live SEO metrics (not stored)."""

    # Pillar page metrics
    pillar_metrics = {}
    for slug in PILLAR_SLUGS:
        page = await db.pillar_pages.find_one({"slug": slug}, {"_id": 0})
        if page:
            content = page.get("content", "")
            faq = page.get("faq", [])
            pillar_metrics[slug] = {
                "word_count": len(_strip_html(content).split()),
                "internal_links": _count_internal_links(content),
                "faq_count": len(faq),
                "meta_title_length": len(page.get("meta_title", "")),
                "meta_description_length": len(page.get("meta_description", "")),
                "has_json_ld": len(faq) > 0,
                "status": page.get("status", "draft"),
            }
        else:
            pillar_metrics[slug] = None

    # Blog metrics
    total_posts = await db.blog_posts.count_documents({"status": "published"})
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    posts_last_30 = await db.blog_posts.count_documents({
        "status": "published",
        "$or": [
            {"published_at": {"$gte": cutoff_30d}},
            {"created_at": {"$gte": cutoff_30d}},
        ]
    })

    # Digest status
    last_digest = await db.blog_digests.find_one(
        {}, {"_id": 0, "generated_at": 1, "week_key": 1}
    )
    weeks_without = 0
    last_digest_date = None
    if last_digest and last_digest.get("generated_at"):
        last_digest_date = last_digest["generated_at"]
        try:
            gen_dt = datetime.fromisoformat(last_digest_date)
            weeks_without = max(0, (datetime.now(timezone.utc) - gen_dt).days // 7)
        except Exception:
            pass

    # Internal linking — count across all pillar content
    total_internal_links = sum(
        m["internal_links"] for m in pillar_metrics.values() if m
    )

    # Technical health: sitemap URL count
    sitemap_count = 6 + total_posts  # static pages + blog posts

    # Check for orphan pages (pillar pages with status != published)
    orphan_pages = [s for s, m in pillar_metrics.items() if m and m["status"] != "published"]

    # Missing meta
    missing_meta = []
    for slug, m in pillar_metrics.items():
        if not m:
            missing_meta.append(slug)
        elif m["meta_title_length"] == 0 or m["meta_description_length"] == 0:
            missing_meta.append(slug)

    # Blog slug duplicates
    pipeline = [
        {"$match": {"status": "published"}},
        {"$group": {"_id": "$slug", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
    ]
    dup_cursor = db.blog_posts.aggregate(pipeline)
    duplicate_slugs = [d["_id"] async for d in dup_cursor]

    # Active alerts count
    active_alerts = await db.seo_alerts.count_documents({"status": "active"})

    return {
        "pillar_metrics": pillar_metrics,
        "blog_metrics": {
            "total_posts": total_posts,
            "posts_last_30_days": posts_last_30,
        },
        "internal_linking": {
            "total_links_detected": total_internal_links,
            "orphan_pages": orphan_pages,
        },
        "digest_status": {
            "last_generated": last_digest_date,
            "weeks_without_digest": weeks_without,
        },
        "technical_health": {
            "sitemap_count": sitemap_count,
            "duplicate_slugs": duplicate_slugs,
            "missing_meta_pages": missing_meta,
        },
        "active_alerts": active_alerts,
    }


# ── Snapshot generation ──

@router.post("/api/admin/seo-snapshot")
async def create_seo_snapshot(current_user: dict = Depends(require_role(["admin"]))):
    """Generate a point-in-time SEO snapshot and store it. Also generates alerts."""
    dashboard = await get_seo_dashboard(current_user)
    now = datetime.now(timezone.utc)

    doc = {
        "snapshot_date": now.isoformat(),
        "pillar_metrics": dashboard["pillar_metrics"],
        "blog_metrics": dashboard["blog_metrics"],
        "internal_linking": dashboard["internal_linking"],
        "digest_status": dashboard["digest_status"],
        "technical_health": dashboard["technical_health"],
        "created_at": now.isoformat(),
    }
    await db.seo_snapshots.insert_one(doc)
    doc.pop("_id", None)

    # Generate alerts from the snapshot
    alerts_created = await _generate_alerts(dashboard, now)

    return {"snapshot": doc, "alerts_created": alerts_created}


async def _generate_alerts(dashboard: dict, now: datetime) -> int:
    """Create seo_alerts from dashboard data. Only creates if no active alert of same type+slug."""
    alerts = []

    # Missing digest
    if dashboard["digest_status"]["weeks_without_digest"] > 1:
        alerts.append({
            "type": "missing_digest",
            "slug": None,
            "message": f"No blog digest generated for {dashboard['digest_status']['weeks_without_digest']} weeks",
            "severity": "warning",
        })

    # Orphan pages
    for slug in dashboard["internal_linking"]["orphan_pages"]:
        alerts.append({
            "type": "orphan_page",
            "slug": slug,
            "message": f"Pillar page '{slug}' is not published",
            "severity": "critical",
        })

    # Missing meta
    for slug in dashboard["technical_health"]["missing_meta_pages"]:
        alerts.append({
            "type": "missing_meta",
            "slug": slug,
            "message": f"Page '{slug}' has missing meta title or description",
            "severity": "warning",
        })

    # Duplicate slugs
    for slug in dashboard["technical_health"]["duplicate_slugs"]:
        alerts.append({
            "type": "duplicate_slug",
            "slug": slug,
            "message": f"Blog slug '{slug}' has duplicate entries",
            "severity": "warning",
        })

    # Low word count
    for slug, m in dashboard["pillar_metrics"].items():
        if m and m["word_count"] < 1000:
            alerts.append({
                "type": "low_word_count",
                "slug": slug,
                "message": f"Pillar page '{slug}' has only {m['word_count']} words (target: 1500+)",
                "severity": "warning",
            })

    count = 0
    for a in alerts:
        existing = await db.seo_alerts.find_one({
            "type": a["type"], "slug": a.get("slug"), "status": "active"
        })
        if not existing:
            a["status"] = "active"
            a["created_at"] = now.isoformat()
            await db.seo_alerts.insert_one(a)
            count += 1

    return count


# ── Snapshot history ──

@router.get("/api/admin/seo-snapshots")
async def list_seo_snapshots(current_user: dict = Depends(require_role(["admin"]))):
    """List historical SEO snapshots."""
    snapshots = await db.seo_snapshots.find(
        {}, {"_id": 0}
    ).sort("snapshot_date", -1).to_list(50)
    return {"snapshots": snapshots}


# ── Alerts CRUD ──

@router.get("/api/admin/seo-alerts")
async def list_seo_alerts(current_user: dict = Depends(require_role(["admin"]))):
    """List all SEO alerts (active first)."""
    alerts = await db.seo_alerts.find(
        {}, {"_id": 0, "type": 1, "slug": 1, "message": 1, "severity": 1, "status": 1, "created_at": 1, "resolved_at": 1}
    ).sort([("status", 1), ("severity", 1), ("created_at", -1)]).to_list(100)
    # Add a string id for frontend resolve action
    all_alerts = await db.seo_alerts.find({}).sort([("status", 1), ("created_at", -1)]).to_list(100)
    result = []
    for a in all_alerts:
        result.append({
            "id": str(a["_id"]),
            "type": a.get("type"),
            "slug": a.get("slug"),
            "message": a.get("message"),
            "severity": a.get("severity"),
            "status": a.get("status"),
            "created_at": a.get("created_at"),
            "resolved_at": a.get("resolved_at"),
        })
    return {"alerts": result}


@router.post("/api/admin/seo-alerts/resolve/{alert_id}")
async def resolve_seo_alert(alert_id: str, current_user: dict = Depends(require_role(["admin"]))):
    """Mark an alert as resolved."""
    from bson import ObjectId
    try:
        oid = ObjectId(alert_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid alert ID")

    result = await db.seo_alerts.update_one(
        {"_id": oid, "status": "active"},
        {"$set": {"status": "resolved", "resolved_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found or already resolved")
    return {"message": "Alert resolved"}
