"""
LinkedIn Auto-Posting Service
Posts blog articles to the LinkedIn company page when published.
Uses LinkedIn v2 UGC Posts API with organization URN.
"""
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

    # Build the blog URL
    blog_type = blog.get("blog_type", "employer")
    slug = blog.get("slug", "")
    base_path = "industrial-hiring-insights" if blog_type == "employer" else "career-insights"
    blog_url = f"https://ventureshrd.com/{base_path}/{slug}"

    title = blog.get("title", "New Blog Post")
    description = blog.get("meta_description", "")
    commentary = f"{title}\n\n{description}\n\nRead more: {blog_url}" if description else f"{title}\n\nRead more: {blog_url}"

    if is_test:
        commentary = f"[Test Post] {commentary}"

    author_urn = f"urn:li:organization:{org_id}"

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
