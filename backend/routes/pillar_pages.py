"""
Pillar Pages — Admin CRUD + Public read by slug
Collection: pillar_pages
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends

from config import db
from utils import require_role
from models.pillar_page import PillarPageCreate, PillarPageUpdate

router = APIRouter(tags=["pillar-pages"])
logger = logging.getLogger(__name__)

ALLOWED_SLUGS = {"industrial-recruitment", "hr-consulting-services", "career-insights"}


# ── Public endpoint — fetch published pillar page by slug ──

@router.get("/api/pillar-pages/{slug}")
async def get_pillar_page(slug: str):
    """Public: fetch a published pillar page by slug."""
    if slug not in ALLOWED_SLUGS:
        raise HTTPException(status_code=404, detail="Page not found")

    page = await db.pillar_pages.find_one(
        {"slug": slug, "status": "published"},
        {"_id": 0}
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


# ── Admin CRUD ──

@router.get("/api/admin/pillar-pages")
async def admin_list_pillar_pages(current_user: dict = Depends(require_role(["admin"]))):
    """Admin: list all pillar pages."""
    pages = await db.pillar_pages.find({}, {"_id": 0}).sort("slug", 1).to_list(50)
    return {"pages": pages}


@router.get("/api/admin/pillar-pages/{slug}")
async def admin_get_pillar_page(slug: str, current_user: dict = Depends(require_role(["admin"]))):
    """Admin: get a single pillar page by slug."""
    page = await db.pillar_pages.find_one({"slug": slug}, {"_id": 0})
    if not page:
        raise HTTPException(status_code=404, detail="Pillar page not found")
    return page


@router.post("/api/admin/pillar-pages", status_code=201)
async def admin_create_pillar_page(
    body: PillarPageCreate,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin: create a new pillar page. Slug must be unique."""
    if body.slug not in ALLOWED_SLUGS:
        raise HTTPException(
            status_code=400,
            detail=f"Slug must be one of: {', '.join(sorted(ALLOWED_SLUGS))}"
        )

    existing = await db.pillar_pages.find_one({"slug": body.slug})
    if existing:
        raise HTTPException(status_code=409, detail=f"Pillar page with slug '{body.slug}' already exists")

    now = datetime.now(timezone.utc).isoformat()
    doc = body.model_dump()
    doc["created_at"] = now
    doc["last_updated"] = now
    doc["updated_by"] = current_user.get("email", "")

    await db.pillar_pages.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/api/admin/pillar-pages/{slug}")
async def admin_update_pillar_page(
    slug: str,
    body: PillarPageUpdate,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin: update an existing pillar page."""
    existing = await db.pillar_pages.find_one({"slug": slug})
    if not existing:
        raise HTTPException(status_code=404, detail="Pillar page not found")

    updates = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates["last_updated"] = datetime.now(timezone.utc).isoformat()
    updates["updated_by"] = current_user.get("email", "")

    await db.pillar_pages.update_one({"slug": slug}, {"$set": updates})

    updated = await db.pillar_pages.find_one({"slug": slug}, {"_id": 0})
    return updated


@router.delete("/api/admin/pillar-pages/{slug}")
async def admin_delete_pillar_page(
    slug: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin: delete a pillar page."""
    result = await db.pillar_pages.delete_one({"slug": slug})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Pillar page not found")
    return {"message": f"Pillar page '{slug}' deleted"}
