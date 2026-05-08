"""
Blog Auto-Scheduler Service
- Auto-generates draft blogs using AI topic research + content generation
- Auto-publishes oldest drafts on a configurable schedule
- Maintains a minimum draft queue so the pipeline never runs dry
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from config import db
from services.linkedin_service import auto_post_on_publish

logger = logging.getLogger(__name__)

# Industries to rotate through for auto-generation
AUTO_GEN_INDUSTRIES = [
    "Manufacturing", "Automotive", "Pharma", "Steel", "Cement",
    "FMCG", "Chemical", "Engineering", "Power & Energy", "Textiles",
    "Food Processing", "Electronics", "Infrastructure", "Mining",
]

CANDIDATE_CATEGORIES = [
    "career-growth", "job-switching", "resume-interview",
    "salary-trends", "industry-opportunities",
]

DEFAULT_SCHEDULE = {
    "employer": {
        "enabled": True,
        "posts_per_week": 3,
        "days": ["monday", "wednesday", "friday"],
        "time_utc": "03:30",
    },
    "candidate": {
        "enabled": True,
        "posts_per_week": 2,
        "days": ["tuesday", "thursday"],
        "time_utc": "04:30",
    },
    "auto_generate": {
        "enabled": True,
        "min_employer_drafts": 6,
        "min_candidate_drafts": 4,
        "batch_size": 3,
    },
}


async def get_schedule_config():
    config = await db.blog_schedule_config.find_one({"_id": "schedule"}, {"_id": 0})
    if config:
        # Ensure auto_generate key exists
        if "auto_generate" not in config:
            config["auto_generate"] = DEFAULT_SCHEDULE["auto_generate"]
        return config
    return DEFAULT_SCHEDULE


async def save_schedule_config(config: dict):
    await db.blog_schedule_config.update_one(
        {"_id": "schedule"},
        {"$set": {**config, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def get_draft_queue_counts():
    employer_count = await db.blog_posts.count_documents({"blog_type": "employer", "status": "draft"})
    candidate_count = await db.blog_posts.count_documents({"blog_type": "candidate", "status": "draft"})
    return {"employer": employer_count, "candidate": candidate_count}


async def get_schedule_log(limit: int = 50):
    logs = await db.blog_schedule_log.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return logs


# ── Auto-Generation Pipeline ──

async def _pick_industry(blog_type: str) -> str:
    """Pick an industry that hasn't been used recently."""
    recent = await db.blog_posts.find(
        {"blog_type": blog_type},
        {"_id": 0, "industry": 1}
    ).sort("created_at", -1).limit(5).to_list(5)
    recent_industries = [b.get("industry", "").lower() for b in recent]

    for ind in AUTO_GEN_INDUSTRIES:
        if ind.lower() not in recent_industries:
            return ind
    return AUTO_GEN_INDUSTRIES[0]


async def _pick_category() -> str:
    """Pick a candidate category not used recently."""
    recent = await db.blog_posts.find(
        {"blog_type": "candidate"},
        {"_id": 0, "category": 1}
    ).sort("created_at", -1).limit(3).to_list(3)
    recent_cats = [b.get("category", "") for b in recent]

    for cat in CANDIDATE_CATEGORIES:
        if cat not in recent_cats:
            return cat
    return CANDIDATE_CATEGORIES[0]


async def auto_generate_single(blog_type: str, industry: str = None, category: str = None) -> dict:
    """Generate a single blog post using AI research + generation. Returns the saved blog doc."""
    from services.blog_generator import research_topics, generate_employer_blog, generate_candidate_blog
    from services.llm_service import get_model

    if not industry:
        industry = await _pick_industry(blog_type)
    if blog_type == "candidate" and not category:
        category = await _pick_category()

    region = "india"
    now = datetime.now(timezone.utc).isoformat()

    # Step 1: Research a topic
    try:
        topics = await research_topics(blog_type, industry, region, count=3)
        if topics and len(topics) > 0:
            topic_data = topics[0]
            topic = topic_data.get("topic", f"Latest trends in {industry} hiring")
            keywords = ", ".join(topic_data.get("secondary_keywords", []))
        else:
            topic = f"Latest trends in {industry} {'recruitment' if blog_type == 'employer' else 'careers'}"
            keywords = f"{industry} hiring, {industry} jobs, talent acquisition"
    except Exception as e:
        logger.warning(f"[AutoGen] Topic research failed, using fallback: {e}")
        topic = f"Latest trends in {industry} {'recruitment' if blog_type == 'employer' else 'careers'}"
        keywords = f"{industry} hiring, {industry} jobs"

    # Step 2: Generate blog content
    try:
        if blog_type == "employer":
            result = await generate_employer_blog(topic, industry, region, keywords)
        else:
            result = await generate_candidate_blog(topic, category or "career-growth", industry, keywords)
    except Exception as e:
        logger.error(f"[AutoGen] Content generation failed: {e}")
        raise

    # Step 3: Save as draft
    blog_doc = {
        "id": str(uuid.uuid4()),
        "title": result.get("title", ""),
        "slug": result.get("slug", ""),
        "meta_description": result.get("meta_description", ""),
        "content": result.get("content", ""),
        "blog_type": blog_type,
        "region": region if blog_type == "employer" else None,
        "category": category if blog_type == "candidate" else None,
        "industry": industry,
        "keywords": result.get("keywords", []),
        "internal_links": result.get("internal_links", []),
        "cta_type": result.get("cta_type", ""),
        "word_count_estimate": result.get("word_count_estimate", 0),
        "status": "draft",
        "generated_by": "auto_pipeline",
        "generation_log": {
            "topic_source": topic,
            "target_keywords": keywords,
            "region": region,
            "blog_type": blog_type,
            "industry": industry,
            "category": category,
            "model_used": get_model(),
            "generated_at": now,
            "auto_generated": True,
        },
        "created_at": now,
        "updated_at": now,
        "published_at": None,
    }
    await db.blog_posts.insert_one(blog_doc)
    blog_doc.pop("_id", None)

    # Log the auto-generation
    await db.blog_schedule_log.insert_one({
        "blog_id": blog_doc["id"],
        "blog_type": blog_type,
        "title": blog_doc["title"],
        "action": "auto_generated",
        "industry": industry,
        "timestamp": now,
    })

    logger.info(f"[AutoGen] Generated {blog_type} blog: {blog_doc['title']}")
    return blog_doc


async def auto_generate_pipeline():
    """Check draft queue levels and generate blogs if below minimum thresholds."""
    config = await get_schedule_config()
    ag_config = config.get("auto_generate", DEFAULT_SCHEDULE["auto_generate"])

    if not ag_config.get("enabled", True):
        logger.info("[AutoGen] Auto-generation disabled, skipping.")
        return {"generated": 0}

    queue = await get_draft_queue_counts()
    min_emp = ag_config.get("min_employer_drafts", 6)
    min_cand = ag_config.get("min_candidate_drafts", 4)
    batch_size = ag_config.get("batch_size", 3)

    generated = []

    # Generate employer blogs if below threshold
    emp_needed = min(max(min_emp - queue["employer"], 0), batch_size)
    for _ in range(emp_needed):
        try:
            blog = await auto_generate_single("employer")
            generated.append({"id": blog["id"], "title": blog["title"], "type": "employer"})
        except Exception as e:
            logger.error(f"[AutoGen] Failed to generate employer blog: {e}")
            break  # Stop on error to avoid burning API credits

    # Generate candidate blogs if below threshold
    cand_needed = min(max(min_cand - queue["candidate"], 0), batch_size)
    for _ in range(cand_needed):
        try:
            blog = await auto_generate_single("candidate")
            generated.append({"id": blog["id"], "title": blog["title"], "type": "candidate"})
        except Exception as e:
            logger.error(f"[AutoGen] Failed to generate candidate blog: {e}")
            break

    logger.info(f"[AutoGen] Pipeline complete. Generated {len(generated)} blogs.")
    return {"generated": len(generated), "blogs": generated}


# ── Auto-Publish (existing) ──

async def auto_publish_blog(blog_type: str):
    """Pick the oldest draft of given type and publish it."""
    lock_name = f"blog_publish_{blog_type}"
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    try:
        await db.cron_job_locks.insert_one({
            "job_name": lock_name,
            "locked_at": now_iso,
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        })
    except Exception:
        logger.info(f"[BlogScheduler] {blog_type} publish already running, skipping.")
        return None

    try:
        config = await get_schedule_config()
        type_config = config.get(blog_type, {})

        if not type_config.get("enabled", False):
            logger.info(f"[BlogScheduler] {blog_type} scheduling disabled, skipping.")
            return None

        # If no drafts, try to generate one first
        draft = await db.blog_posts.find_one(
            {"blog_type": blog_type, "status": "draft"},
            sort=[("created_at", 1)],
        )
        if not draft:
            ag_config = config.get("auto_generate", {})
            if ag_config.get("enabled", True):
                logger.info(f"[BlogScheduler] No {blog_type} drafts — auto-generating one...")
                try:
                    blog = await auto_generate_single(blog_type)
                    draft = await db.blog_posts.find_one({"id": blog["id"]})
                except Exception as e:
                    logger.error(f"[BlogScheduler] Auto-generate failed: {e}")
                    return None
            else:
                logger.info(f"[BlogScheduler] No {blog_type} drafts available.")
                return None

        blog_id = draft["id"]
        await db.blog_posts.update_one(
            {"id": blog_id},
            {"$set": {
                "status": "published",
                "published_at": now_iso,
                "updated_at": now_iso,
                "auto_published": True,
            }},
        )

        await db.blog_schedule_log.insert_one({
            "blog_id": blog_id,
            "blog_type": blog_type,
            "title": draft.get("title", ""),
            "action": "auto_published",
            "timestamp": now_iso,
        })

        logger.info(f"[BlogScheduler] Auto-published {blog_type} blog: {draft.get('title')}")

        published_blog = await db.blog_posts.find_one({"id": blog_id}, {"_id": 0})
        if published_blog:
            await auto_post_on_publish(published_blog)

        return blog_id
    finally:
        await db.cron_job_locks.delete_one({"job_name": lock_name})
