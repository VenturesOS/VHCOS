"""
Blog Analytics Service
Tracks page views, CTA clicks, and provides aggregated metrics.
"""
import logging
from datetime import datetime, timezone, timedelta
from config import db

logger = logging.getLogger(__name__)


async def track_event(blog_id: str, event_type: str, metadata: dict = None):
    """Track a blog analytics event (view or cta_click)."""
    now = datetime.now(timezone.utc)
    doc = {
        "blog_id": blog_id,
        "event_type": event_type,
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": now.isoformat(),
    }
    if metadata:
        doc["metadata"] = metadata
    await db.blog_analytics.insert_one(doc)


async def get_blog_stats(days: int = 30):
    """Get aggregated blog stats for the admin dashboard."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    # Total published counts
    employer_published = await db.blog_posts.count_documents({"blog_type": "employer", "status": "published"})
    candidate_published = await db.blog_posts.count_documents({"blog_type": "candidate", "status": "published"})
    employer_drafts = await db.blog_posts.count_documents({"blog_type": "employer", "status": "draft"})
    candidate_drafts = await db.blog_posts.count_documents({"blog_type": "candidate", "status": "draft"})

    # Views & clicks aggregation
    views_pipeline = [
        {"$match": {"event_type": "view", "date": {"$gte": cutoff}}},
        {"$group": {"_id": None, "total": {"$sum": 1}}},
    ]
    clicks_pipeline = [
        {"$match": {"event_type": "cta_click", "date": {"$gte": cutoff}}},
        {"$group": {"_id": None, "total": {"$sum": 1}}},
    ]
    views_result = await db.blog_analytics.aggregate(views_pipeline).to_list(1)
    clicks_result = await db.blog_analytics.aggregate(clicks_pipeline).to_list(1)

    total_views = views_result[0]["total"] if views_result else 0
    total_clicks = clicks_result[0]["total"] if clicks_result else 0

    return {
        "employer_published": employer_published,
        "candidate_published": candidate_published,
        "employer_drafts": employer_drafts,
        "candidate_drafts": candidate_drafts,
        "total_views": total_views,
        "total_cta_clicks": total_clicks,
        "ctr": round((total_clicks / total_views * 100) if total_views > 0 else 0, 2),
        "period_days": days,
    }


async def get_views_over_time(days: int = 30):
    """Get daily view counts over time."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    pipeline = [
        {"$match": {"event_type": "view", "date": {"$gte": cutoff}}},
        {"$group": {"_id": "$date", "views": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "date": "$_id", "views": 1}},
    ]
    return await db.blog_analytics.aggregate(pipeline).to_list(60)


async def get_top_blogs(limit: int = 10, days: int = 30):
    """Get top blogs by view count."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    pipeline = [
        {"$match": {"event_type": "view", "date": {"$gte": cutoff}}},
        {"$group": {"_id": "$blog_id", "views": {"$sum": 1}}},
        {"$sort": {"views": -1}},
        {"$limit": limit},
        {"$lookup": {
            "from": "blog_posts",
            "localField": "_id",
            "foreignField": "id",
            "as": "blog",
        }},
        {"$unwind": {"path": "$blog", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 0,
            "blog_id": "$_id",
            "views": 1,
            "title": {"$ifNull": ["$blog.title", "Unknown"]},
            "blog_type": {"$ifNull": ["$blog.blog_type", "unknown"]},
            "slug": {"$ifNull": ["$blog.slug", ""]},
        }},
    ]
    return await db.blog_analytics.aggregate(pipeline).to_list(limit)


async def get_clicks_by_blog(limit: int = 10, days: int = 30):
    """Get CTA click counts by blog."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    pipeline = [
        {"$match": {"event_type": "cta_click", "date": {"$gte": cutoff}}},
        {"$group": {"_id": "$blog_id", "clicks": {"$sum": 1}}},
        {"$sort": {"clicks": -1}},
        {"$limit": limit},
        {"$lookup": {
            "from": "blog_posts",
            "localField": "_id",
            "foreignField": "id",
            "as": "blog",
        }},
        {"$unwind": {"path": "$blog", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 0,
            "blog_id": "$_id",
            "clicks": 1,
            "title": {"$ifNull": ["$blog.title", "Unknown"]},
            "blog_type": {"$ifNull": ["$blog.blog_type", "unknown"]},
        }},
    ]
    return await db.blog_analytics.aggregate(pipeline).to_list(limit)
