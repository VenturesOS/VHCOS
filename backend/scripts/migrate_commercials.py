"""
Migration: Embed commercials into company documents.
- Reads all records from `commercials` collection
- Embeds the active commercial into each company's `commercial` field
- For level_based: preserves named-key mapping as legacy_level_mapping, sets level_config=[]
- For percentage: maps fee_percentage → percentage_value
- For fixed: maps fixed_amount → fixed_fee_amount
- Does NOT delete old collection (kept as backup)
"""
import asyncio
import logging
from config import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    logger.info("=== COMMERCIAL MIGRATION START ===")

    commercials = await db.commercials.find({}, {"_id": 0}).to_list(1000)
    logger.info(f"Found {len(commercials)} records in commercials collection")

    # Group by company_id, prefer active ones
    by_company = {}
    for c in commercials:
        cid = c.get("company_id")
        if not cid:
            continue
        # Prefer active commercial; if multiple active, take the latest
        existing = by_company.get(cid)
        if existing is None:
            by_company[cid] = c
        elif c.get("is_active") and not existing.get("is_active"):
            by_company[cid] = c
        elif c.get("is_active") and existing.get("is_active"):
            # Both active — keep the one with later effective_from
            if (c.get("effective_from", "") or "") > (existing.get("effective_from", "") or ""):
                by_company[cid] = c

    migrated = 0
    skipped = 0

    for company_id, comm in by_company.items():
        company = await db.companies.find_one({"id": company_id}, {"_id": 0, "name": 1, "commercial": 1})
        if not company:
            logger.warning(f"  SKIP: Company {company_id} not found in companies collection")
            skipped += 1
            continue

        # Already migrated?
        if company.get("commercial"):
            logger.info(f"  SKIP: {company.get('name')} already has embedded commercial")
            skipped += 1
            continue

        comm_type = comm.get("type", "percentage")
        embedded = {"type": comm_type}

        if comm_type == "percentage":
            embedded["percentage_value"] = comm.get("fee_percentage")
        elif comm_type == "fixed":
            embedded["fixed_fee_amount"] = comm.get("fixed_amount")
        elif comm_type == "level_based":
            # Preserve named-key mapping as legacy, set level_config empty for manual config
            legacy = comm.get("level_config", {})
            embedded["legacy_level_mapping"] = legacy
            embedded["level_config"] = []

        await db.companies.update_one(
            {"id": company_id},
            {"$set": {"commercial": embedded}}
        )
        migrated += 1
        logger.info(f"  MIGRATED: {company.get('name')} → {comm_type} (active={comm.get('is_active')})")

    logger.info(f"=== MIGRATION COMPLETE: {migrated} migrated, {skipped} skipped ===")
    logger.info("Old commercials collection preserved as backup.")
    return {"migrated": migrated, "skipped": skipped, "total_commercials": len(commercials)}


if __name__ == "__main__":
    asyncio.run(migrate())
