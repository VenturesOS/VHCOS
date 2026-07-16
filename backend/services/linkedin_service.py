"""
LinkedIn Auto-Posting Service
Posts blog articles to the LinkedIn company page when published.
Uses LinkedIn v2 UGC Posts API with organization URN.
"""
import os
import logging
from datetime import datetime, timezone
import httpx

from config import db

logger = logging.getLogger(__name__)

LINKEDIN_UGC_URL = "https://api.linkedin.com/v2/ugcPosts"


async def get_linkedin_settings():
    """Get LinkedIn auto-posting settings from DB."""
    settings = await db.linkedin_settings.find_one({"_id": "config"}, {"_id": 0})
    if not settings:
        return {
            "auto_post_enabled": False,
            "organization_id": "",
        }
    return settings


async def save_linkedin_settings(settings: dict):
    """Save LinkedIn auto-posting settings to DB."""
    await db.linkedin_settings.update_one(
        {"_id": "config"},
        {"$set": {**settings, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def get_linkedin_token():
    """Retrieve stored LinkedIn access token."""
    integration = await db.social_integrations.find_one(
        {"platform": "linkedin"},
        {"_id": 0, "access_token": 1, "profile_name": 1}
    )
    if not integration or not integration.get("access_token"):
        return None
    return integration["access_token"]


async def get_linkedin_profile_urn():
    """Get the LinkedIn member URN (sub) for the connected user."""
    integration = await db.social_integrations.find_one(
        {"platform": "linkedin"},
        {"_id": 0, "access_token": 1, "profile_sub": 1}
    )
    if not integration:
        return None, None
    return integration.get("access_token"), integration.get("profile_sub")


async def post_blog_to_linkedin(blog: dict, is_test: bool = False):
    """
    Post a blog article link to LinkedIn.
    Uses w_member_social to post as the authenticated admin user.
    Returns dict with success status and post details.
    """
    settings = await get_linkedin_settings()
    org_id = settings.get("organization_id", "")

    if not org_id:
        return {"success": False, "error": "LinkedIn Organization ID not configured"}

    access_token = await get_linkedin_token()
    if not access_token:
        return {"success": False, "error": "LinkedIn not connected. Please authorize first."}

    # Get the member's profile URN for posting
    token, profile_sub = await get_linkedin_profile_urn()
    if not profile_sub:
        return {"success": False, "error": "LinkedIn profile info missing. Please re-authorize."}

    # Build the blog URL
    blog_type = blog.get("blog_type", "employer")
    slug = blog.get("slug", "")
    base_path = "industrial-hiring-insights" if blog_type == "employer" else "career-insights"
    blog_url = f"{os.environ.get('SITE_URL', 'https://ventureshrd.com').rstrip('/')}/{base_path}/{slug}"

    title = blog.get("title", "New Blog Post")
    description = blog.get("meta_description", "")
    commentary = f"{title}\n\n{description}\n\nRead more: {blog_url}" if description else f"{title}\n\nRead more: {blog_url}"

    if is_test:
        commentary = f"[Test Post] {commentary}"

    # Post as the authenticated member (admin user)
    author_urn = f"urn:li:person:{profile_sub}"

    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": commentary},
                "shareMediaCategory": "ARTICLE",
                "media": [
                    {
                        "status": "READY",
                        "originalUrl": blog_url,
                        "title": {"text": title},
                        "description": {"text": description or title},
                    }
                ],
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202402",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(LINKEDIN_UGC_URL, json=payload, headers=headers)

            if response.status_code == 201:
                post_id = response.json().get("id", "")
                logger.info(f"[LinkedIn] Posted blog '{title}' -> {post_id}")

                # Log the post
                await db.linkedin_post_history.insert_one({
                    "blog_id": blog.get("id", ""),
                    "blog_title": title,
                    "blog_slug": slug,
                    "blog_type": blog_type,
                    "linkedin_post_id": post_id,
                    "blog_url": blog_url,
                    "is_test": is_test,
                    "status": "success",
                    "posted_at": datetime.now(timezone.utc).isoformat(),
                })

                return {"success": True, "post_id": post_id, "blog_url": blog_url}

            else:
                error_text = response.text
                logger.error(f"[LinkedIn] Post failed ({response.status_code}): {error_text}")

                await db.linkedin_post_history.insert_one({
                    "blog_id": blog.get("id", ""),
                    "blog_title": title,
                    "blog_slug": slug,
                    "blog_type": blog_type,
                    "linkedin_post_id": "",
                    "blog_url": blog_url,
                    "is_test": is_test,
                    "status": "failed",
                    "error": error_text[:500],
                    "status_code": response.status_code,
                    "posted_at": datetime.now(timezone.utc).isoformat(),
                })

                return {"success": False, "error": f"LinkedIn API error ({response.status_code}): {error_text[:200]}"}

    except httpx.RequestError as e:
        error_msg = str(e)
        logger.error(f"[LinkedIn] Request error: {error_msg}")
        return {"success": False, "error": f"Connection error: {error_msg[:200]}"}


async def auto_post_on_publish(blog: dict):
    """
    Called when a blog is published. Checks settings and posts if enabled.
    Runs as fire-and-forget (errors are logged, not raised).
    """
    try:
        settings = await get_linkedin_settings()
        if not settings.get("auto_post_enabled", False):
            logger.info("[LinkedIn] Auto-posting disabled, skipping.")
            return

        result = await post_blog_to_linkedin(blog)
        if result["success"]:
            logger.info(f"[LinkedIn] Auto-posted blog: {blog.get('title')}")
        else:
            logger.warning(f"[LinkedIn] Auto-post failed: {result.get('error')}")
    except Exception as e:
        logger.error(f"[LinkedIn] Auto-post exception: {e}")


# ── Job → LinkedIn draft generator ─────────────────────────────────────────
# LinkedIn Marketing Developer Platform approval for `w_organization_social`
# is a multi-week process. Until it lands, this generator produces a ready-to-
# copy narrative post text for each active job that an admin pastes into
# LinkedIn manually. Once the scope is approved we can pipe the same text into
# `post_job_to_linkedin()` and flip a switch — no template rewrites needed.

_DEFAULT_HASHTAGS = ["#Hiring", "#IndustrialRecruitment", "#Careers", "#VenturesHRD"]


def _fmt_experience(job: dict) -> str:
    """Return e.g. '3–7 yrs', '10+ yrs', or '' if no range on the job."""
    lo = job.get("experience_min")
    hi = job.get("experience_max")
    if lo is None and hi is None:
        return ""
    if lo is not None and hi is not None:
        return f"{lo}–{hi} yrs" if lo != hi else f"{lo} yrs"
    if lo is not None:
        return f"{lo}+ yrs"
    return f"up to {hi} yrs"


def _title_case_loc(loc: str | None) -> str:
    if not loc:
        return ""
    return " ".join(w.capitalize() if w.isalpha() else w for w in loc.split())


def generate_job_linkedin_draft(job: dict) -> dict:
    """
    Build a narrative-style "We're hiring" LinkedIn post for a job. Returns
    a dict with both the composed `text` and structured metadata that the
    admin UI can display alongside (title, location, url, etc.).

    Template (Option B — long narrative):
        🚀 New opportunity in {Location}!

        We're partnering with a leading {industry|"industrial"} client to hire
        a {Title} ({seniority}, {experience} yrs).

        Key focus:
        • {skill 1}
        • {skill 2}
        • {skill 3}

        Apply now → {job_url}

        {hashtags}

    Every optional field degrades gracefully — missing seniority just drops the
    parenthetical, missing skills drops the bullet section, etc. Never emits
    "None" or empty lines back-to-back.
    """
    site_url = os.environ.get("SITE_URL", "https://ventureshrd.com").rstrip("/")
    job_id = job.get("id") or job.get("job_public_id") or ""
    job_url = f"{site_url}/jobs/{job_id}"

    title = (job.get("title") or "").strip() or "an exciting new role"
    location = _title_case_loc(job.get("location"))
    industry = (job.get("industry") or "").strip().lower() or "industrial"
    seniority = (job.get("seniority") or "").strip()
    experience = _fmt_experience(job)
    function = (job.get("function") or "").strip()

    # Line 1: hook
    if location:
        line_hook = f"🚀 New opportunity in {location}!"
    else:
        line_hook = "🚀 We're hiring."

    # Line 2: role + industry
    parenthetical_bits = [b for b in [seniority, experience] if b]
    parenthetical = f" ({', '.join(parenthetical_bits)})" if parenthetical_bits else ""
    line_role = f"We're partnering with a leading {industry} client to hire a {title}{parenthetical}."

    # Skills bullets — from `skills` array if present, else fall back to
    # `key_responsibilities` (array or newline-separated string), else omit.
    skills_bullets: list[str] = []
    raw_skills = job.get("skills") or job.get("key_skills") or []
    if isinstance(raw_skills, str):
        raw_skills = [s.strip() for s in raw_skills.replace("\n", ",").split(",") if s.strip()]
    if not raw_skills:
        raw_kr = job.get("key_responsibilities") or job.get("responsibilities") or []
        if isinstance(raw_kr, str):
            raw_kr = [s.strip() for s in raw_kr.split("\n") if s.strip()]
        raw_skills = raw_kr
    for s in raw_skills[:3]:
        if isinstance(s, str) and s.strip():
            skills_bullets.append(f"• {s.strip()}")

    # Compose. Blank lines between blocks; skip the skills block entirely if empty.
    blocks = [line_hook, line_role]
    if skills_bullets:
        blocks.append("Key focus:\n" + "\n".join(skills_bullets))
    blocks.append(f"Apply now → {job_url}")

    # Hashtags — include function as its own tag if we have one.
    tags = list(_DEFAULT_HASHTAGS)
    if function:
        # `Plant Head` → `#PlantHead`
        fn_tag = "#" + "".join(w.capitalize() for w in function.replace("&", "").split())
        if fn_tag not in tags and len(fn_tag) > 1:
            tags.insert(1, fn_tag)
    blocks.append(" ".join(tags))

    text = "\n\n".join(blocks)

    return {
        "job_id":       job.get("id"),
        "title":        title,
        "location":     location,
        "function":     function,
        "seniority":    seniority,
        "experience":   experience,
        "url":          job_url,
        "text":         text,
        "char_count":   len(text),
        "posted_at":    job.get("linkedin_posted_at"),  # None if not yet posted
        "updated_at":   job.get("updated_at"),
    }
