"""
Blog Digest Generator — Weekly automated digest creation.
Pulls recent blogs, generates executive summary via GPT-4o-mini, stores in blog_digests.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from config import db
from services.llm_service import chat_completion

logger = logging.getLogger(__name__)

PILLAR_SLUGS = ["industrial-recruitment", "hr-consulting-services", "career-insights"]


def _week_key(dt: datetime) -> str:
    """ISO year-week string for duplicate prevention. e.g. '2026-W08'"""
    return f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"


async def generate_weekly_digest():
    """Generate and store a weekly blog digest. Idempotent per ISO week."""
    now = datetime.now(timezone.utc)
    week_key = _week_key(now)

    logger.info(f"[Digest] Starting generation for week {week_key}")

    # Duplicate check
    existing = await db.blog_digests.find_one({"week_key": week_key})
    if existing:
        logger.info(f"[Digest] Digest for {week_key} already exists, skipping")
        return {"status": "skipped", "reason": "duplicate", "week_key": week_key}

    # Pull blogs published in last 7 days
    cutoff = now - timedelta(days=7)
    recent_blogs = await db.blog_posts.find(
        {"status": "published", "published_at": {"$gte": cutoff.isoformat()}},
        {"_id": 0, "title": 1, "slug": 1, "excerpt": 1, "category": 1, "blog_type": 1}
    ).sort("published_at", -1).to_list(20)

    # If no published_at field, try created_at
    if not recent_blogs:
        recent_blogs = await db.blog_posts.find(
            {"status": "published", "created_at": {"$gte": cutoff.isoformat()}},
            {"_id": 0, "title": 1, "slug": 1, "excerpt": 1, "category": 1, "blog_type": 1}
        ).sort("created_at", -1).to_list(20)

    has_recent_blogs = len(recent_blogs) > 0
    logger.info(f"[Digest] Found {len(recent_blogs)} blogs from last 7 days")

    # Build the LLM prompt
    if has_recent_blogs:
        blog_list_text = "\n".join([
            f"- Title: {b.get('title', 'Untitled')}\n  Slug: {b.get('slug', '')}\n  Excerpt: {b.get('excerpt', 'N/A')[:200]}"
            for b in recent_blogs[:10]
        ])
        user_prompt = f"""Generate a weekly recruitment industry digest for the week of {now.strftime('%B %d, %Y')}.

Here are the blog posts published this week:
{blog_list_text}

Pillar pages to reference (use at least 1):
- /industrial-recruitment — Industrial Recruitment Services
- /hr-consulting-services — HR Consulting Services
- /career-insights — Career Insights

Return JSON with this exact structure:
{{
  "title": "Weekly Recruitment Insights – Week of [date range]",
  "summary": "2-3 sentence executive summary of this week's key themes",
  "highlights": [
    {{"title": "blog title", "slug": "blog-slug", "short_summary": "1-2 sentence summary"}}
  ],
  "pillar_mentions": ["slug1", "slug2"],
  "cta_text": "A compelling call-to-action sentence"
}}

Include 3-5 highlights. Reference at least one pillar page in context."""
    else:
        user_prompt = f"""Generate a weekly recruitment industry digest for the week of {now.strftime('%B %d, %Y')}.

No new blog posts were published this week. Generate an industry trend summary covering:
- Current hiring trends in Indian industrial and manufacturing sectors
- Relevant HR consulting insights
- Career market observations

Pillar pages to reference (use at least 1):
- /industrial-recruitment — Industrial Recruitment Services
- /hr-consulting-services — HR Consulting Services
- /career-insights — Career Insights

Return JSON with this exact structure:
{{
  "title": "Weekly Recruitment Insights – Week of [date range]",
  "summary": "2-3 sentence executive summary of industry trends",
  "highlights": [
    {{"title": "trend title", "slug": "", "short_summary": "1-2 sentence insight"}}
  ],
  "pillar_mentions": ["slug1"],
  "cta_text": "A compelling call-to-action sentence"
}}

Include 3-5 highlights. Make them specific to the Indian recruitment market."""

    system_prompt = (
        "You are a recruitment industry analyst at VHC Talent Advisory, India's specialist "
        "industrial recruitment firm. Write concise, authoritative weekly digests for HR leaders "
        "and hiring managers. Tone: professional, data-aware, India-focused. Return valid JSON only."
    )

    try:
        raw = await chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.6,
            max_tokens=1500,
            json_mode=True,
        )
        digest_data = json.loads(raw)
    except Exception as e:
        logger.error(f"[Digest] LLM generation failed: {e}", exc_info=True)
        return {"status": "error", "reason": str(e), "week_key": week_key}

    # Validate and normalize
    if not isinstance(digest_data.get("highlights"), list):
        digest_data["highlights"] = []
    if not isinstance(digest_data.get("pillar_mentions"), list):
        digest_data["pillar_mentions"] = PILLAR_SLUGS[:1]

    # Ensure at least one pillar mention
    if not digest_data["pillar_mentions"]:
        digest_data["pillar_mentions"] = PILLAR_SLUGS[:1]

    doc = {
        "week_key": week_key,
        "title": digest_data.get("title", f"Weekly Recruitment Insights – {week_key}"),
        "summary": digest_data.get("summary", ""),
        "highlights": digest_data["highlights"][:5],
        "pillar_mentions": digest_data["pillar_mentions"],
        "cta_text": digest_data.get("cta_text", ""),
        "blog_count": len(recent_blogs),
        "generated_at": now.isoformat(),
        "status": "generated",
    }

    await db.blog_digests.insert_one(doc)
    doc.pop("_id", None)

    logger.info(f"[Digest] Successfully generated digest for {week_key}: {doc['title']}")
    return {"status": "success", "week_key": week_key, "digest": doc}
