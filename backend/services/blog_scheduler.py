"""
Blog Auto-Scheduler Service
Automatically publishes draft blogs on a configurable schedule.
- Employer: 3/week (Mon, Wed, Fri at 9:00 AM IST)
- Candidate: 2-3/week (Tue, Thu at 10:00 AM IST, optional Sat)
"""
import logging
from datetime import datetime, timezone
from config import db
from services.linkedin_service import auto_post_on_publish

logger = logging.getLogger(__name__)

DEFAULT_SCHEDULE = {
    "employer": {
        "enabled": True,
        "posts_per_week": 3,
        "days": ["monday", "wednesday", "friday"],
        "time_utc": "03:30",  # 9:00 AM IST
    },
    "candidate": {
        "enabled": True,
        "posts_per_week": 2,
        "days": ["tuesday", "thursday"],
        "time_utc": "04:30",  # 10:00 AM IST
    },
}


async def get_schedule_config():
    """Get schedule config from DB, or return defaults."""
    config = await db.blog_schedule_config.find_one({"_id": "schedule"}, {"_id": 0})
    if config:
        return config
    return DEFAULT_SCHEDULE


async def save_schedule_config(config: dict):
    """Save schedule config to DB."""
    await db.blog_schedule_config.update_one(
        {"_id": "schedule"},
        {"$set": {**config, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def auto_publish_blog(blog_type: str):
    """Pick the oldest draft of given type and publish it."""
    now = datetime.now(timezone.utc).isoformat()
    config = await get_schedule_config()
    type_config = config.get(blog_type, {})

    if not type_config.get("enabled", False):
        logger.info(f"[BlogScheduler] {blog_type} scheduling disabled, skipping.")
        return None

    # Find oldest draft of this type
    draft = await db.blog_posts.find_one(
        {"blog_type": blog_type, "status": "draft"},
        sort=[("created_at", 1)],
    )
    if not draft:
        logger.info(f"[BlogScheduler] No {blog_type} drafts available to publish.")
        return None

    blog_id = draft["id"]
    await db.blog_posts.update_one(
        {"id": blog_id},
        {"$set": {
            "status": "published",
            "published_at": now,
            "updated_at": now,
            "auto_published": True,
        }},
    )

    # Log the auto-publish event
    await db.blog_schedule_log.insert_one({
        "blog_id": blog_id,
        "blog_type": blog_type,
        "title": draft.get("title", ""),
        "action": "auto_published",
        "timestamp": now,
    })

    logger.info(f"[BlogScheduler] Auto-published {blog_type} blog: {draft.get('title')}")

    # Trigger LinkedIn auto-post
    published_blog = await db.blog_posts.find_one({"id": blog_id}, {"_id": 0})
    if published_blog:
        await auto_post_on_publish(published_blog)

    return blog_id


async def get_schedule_log(limit: int = 50):
    """Get recent schedule log entries."""
    logs = await db.blog_schedule_log.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return logs


async def get_draft_queue_counts():
    """Get count of drafts available for each blog type."""
    employer_count = await db.blog_posts.count_documents({"blog_type": "employer", "status": "draft"})
    candidate_count = await db.blog_posts.count_documents({"blog_type": "candidate", "status": "draft"})
    return {"employer": employer_count, "candidate": candidate_count}
