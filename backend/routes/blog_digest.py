"""
Blog Digest Admin Routes — Manual trigger + list digests.
"""
import logging
from fastapi import APIRouter, Depends
from config import db
from utils import require_role
from services.blog_digest import generate_weekly_digest

router = APIRouter(tags=["blog-digest"])
logger = logging.getLogger(__name__)


@router.post("/api/admin/blog-digest/trigger")
async def admin_trigger_digest(current_user: dict = Depends(require_role(["admin"]))):
    """Admin: Manually trigger weekly digest generation."""
    result = await generate_weekly_digest()
    return result


@router.get("/api/admin/blog-digests")
async def admin_list_digests(current_user: dict = Depends(require_role(["admin"]))):
    """Admin: List all generated digests."""
    digests = await db.blog_digests.find(
        {}, {"_id": 0}
    ).sort("generated_at", -1).to_list(50)
    return {"digests": digests}
