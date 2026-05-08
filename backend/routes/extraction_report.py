"""
Extraction Tracking Report — Admin endpoint to view daily LLM layer performance.
"""
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/extraction-report", tags=["Extraction Report"])


async def get_db():
    from config import db
    return db


from utils.auth import get_current_user


@router.get("/daily")
async def get_daily_extraction_report(
    date: Optional[str] = None,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Daily extraction performance report — which layer handled what."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    target_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Aggregate by source
    pipeline = [
        {"$match": {"date": target_date}},
        {"$group": {
            "_id": "$source",
            "count": {"$sum": 1},
            "avg_ms": {"$avg": "$elapsed_ms"},
            "successes": {"$sum": {"$cond": ["$success", 1, 0]}},
            "failures": {"$sum": {"$cond": ["$success", 0, 1]}},
        }},
        {"$sort": {"count": -1}},
    ]
    results = await db.extraction_tracking.aggregate(pipeline).to_list(20)

    total = sum(r["count"] for r in results)
    layers = []
    for r in results:
        layers.append({
            "source": r["_id"],
            "count": r["count"],
            "percentage": round((r["count"] / total * 100) if total > 0 else 0, 1),
            "avg_time_ms": round(r["avg_ms"]) if r["avg_ms"] else 0,
            "successes": r["successes"],
            "failures": r["failures"],
        })

    # Recent extractions with fallback chain detail
    recent = await db.extraction_tracking.find(
        {"date": target_date},
        {"_id": 0}
    ).sort("timestamp", -1).limit(50).to_list(50)

    # Fallback analysis — how many times each layer was attempted
    fallback_pipeline = [
        {"$match": {"date": target_date}},
        {"$unwind": "$fallback_chain"},
        {"$group": {"_id": "$fallback_chain", "attempts": {"$sum": 1}}},
        {"$sort": {"attempts": -1}},
    ]
    fallback_stats = await db.extraction_tracking.aggregate(fallback_pipeline).to_list(20)

    return {
        "date": target_date,
        "total_extractions": total,
        "layer_breakdown": layers,
        "fallback_attempts": {r["_id"]: r["attempts"] for r in fallback_stats},
        "recent_extractions": recent,
    }
