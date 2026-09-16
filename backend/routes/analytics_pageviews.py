"""
VHC Talent OS — Frontend Page-View + Custom Event Tracking (Phase 56)

Lightweight, privacy-aware tracking layer:
  • POST /api/analytics/track             → record a page view OR custom event
  • GET  /api/analytics/hub/dashboard     → admin-only unified dashboard data

Collection: `analytics_pageviews`
  { id, ts, user_id, user_email, user_role, event_type, route, referrer,
    session_id, props, ip_hash }

We deliberately do NOT store full IPs or full user-agents. We hash the IP
(salted, daily-rotated) so we can count distinct visitors without keeping
personally-identifying data — same privacy posture as Plausible.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from config import db
from utils.auth import get_current_user, require_role

logger = logging.getLogger(__name__)

analytics_pageviews_router = APIRouter(
    prefix="/api/analytics", tags=["Analytics Pageviews"]
)

_IP_HASH_SALT = os.environ.get("ANALYTICS_IP_SALT", "vhc-default-salt-rotate-me")
_optional_security = HTTPBearer(auto_error=False)


async def _optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_security),
) -> Optional[dict]:
    """Same as get_current_user but returns None instead of raising 401.
    Lets us record anonymous page views from public/marketing routes."""
    if not credentials or not credentials.credentials:
        return None
    try:
        # delegate full validation (token type, expiry, revocation, deactivated)
        return await get_current_user(credentials)  # type: ignore[arg-type]
    except Exception:
        return None


def _hash_ip(ip: str) -> str:
    """Daily-rotated salted hash so we can dedupe visitors without storing IPs."""
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    raw = f"{_IP_HASH_SALT}|{day}|{ip}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


class TrackEvent(BaseModel):
    event_type: str = Field(default="pageview", description="pageview | custom")
    route: Optional[str] = None  # e.g. "/admin/dashboard"
    referrer: Optional[str] = None
    session_id: Optional[str] = None
    props: Optional[Dict[str, Any]] = None  # arbitrary {key: value}


@analytics_pageviews_router.post("/track")
async def track_event(
    payload: TrackEvent,
    request: Request,
    current_user: Optional[dict] = Depends(_optional_user),
):
    """Record a single page view or custom event. Auth is optional — anonymous
    pageviews are accepted for marketing/landing pages."""
    client_ip = request.client.host if request.client else "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        client_ip = fwd.split(",")[0].strip()

    doc = {
        "id": str(uuid.uuid4()),
        "ts": datetime.now(timezone.utc),
        "event_type": payload.event_type[:32],
        "route": (payload.route or "")[:256],
        "referrer": (payload.referrer or "")[:512],
        "session_id": (payload.session_id or "")[:64],
        "props": payload.props or {},
        "ip_hash": _hash_ip(client_ip),
        "user_id": (current_user or {}).get("id"),
        "user_email": (current_user or {}).get("email"),
        "user_role": (current_user or {}).get("role"),
    }
    try:
        await db.analytics_pageviews.insert_one(doc)
    except Exception as e:
        # never let tracking break the UX
        logger.warning(f"[analytics_pageviews] insert failed: {e}")
    return {"ok": True}


@analytics_pageviews_router.get("/hub/dashboard")
async def hub_dashboard(
    days: int = 7,
    public_only: bool = True,
    current_user: dict = Depends(require_role(["admin"])),
):
    """Unified admin analytics: page views, DAU, top pages, top recruiters,
    capture funnel, top referrers. All aggregations are MongoDB-side for speed.

    fix.docx (2026-09-15): the hub used to bucket the internal employee
    portal (/admin, /employer, /recruiter, /candidate) together with the
    public careers / job / blog pages, drowning out the marketing traffic.
    `public_only=true` (the new default) restricts every route-based
    aggregation to the outward-facing URLs. Toggle to `false` to see
    combined data.
    """
    days = max(1, min(days, 90))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Regex that keeps only public / marketing / careers routes when
    # `public_only` is on. Anonymous ({"user_id": null}) hits from
    # external redirects also count as public even if the URL prefix
    # isn't a canonical marketing one (e.g. custom vanity landing pages).
    _PUBLIC_ROUTE_RE = r"^/(careers|jobs?|job/|blog|apply|company/|companies/|$)"
    _pv_match: dict = {"ts": {"$gte": since}, "event_type": "pageview"}
    if public_only:
        _pv_match["$or"] = [
            {"route": {"$regex": _PUBLIC_ROUTE_RE}},
            {"user_id": None},
        ]

    # 1. Total page views + DAU + unique visitors
    total_pv = await db.analytics_pageviews.count_documents(_pv_match)

    dau_match = {"ts": {"$gte": since}}
    if public_only:
        dau_match["$or"] = _pv_match["$or"]
    dau_pipeline = [
        {"$match": dau_match},
        {
            "$group": {
                "_id": {
                    "day": {"$dateToString": {"format": "%Y-%m-%d", "date": "$ts"}},
                    "ip_hash": "$ip_hash",
                }
            }
        },
        {"$group": {"_id": "$_id.day", "uniques": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "day": "$_id", "uniques": 1}},
    ]
    dau = await db.analytics_pageviews.aggregate(dau_pipeline).to_list(100)

    # 2. Top pages
    top_pages_pipeline = [
        {"$match": _pv_match},
        {"$group": {"_id": "$route", "views": {"$sum": 1}}},
        {"$sort": {"views": -1}},
        {"$limit": 15},
        {"$project": {"_id": 0, "route": "$_id", "views": 1}},
    ]
    top_pages = await db.analytics_pageviews.aggregate(top_pages_pipeline).to_list(15)

    # 3. Top referrers — always excludes empty referrer AND same-origin
    # referrers (we only care about external redirect traffic).
    _ref_match = dict(_pv_match)
    _ref_match["referrer"] = {"$nin": [None, ""]}
    top_referrers_pipeline = [
        {"$match": _ref_match},
        {"$group": {"_id": "$referrer", "hits": {"$sum": 1}}},
        {"$sort": {"hits": -1}},
        {"$limit": 10},
        {"$project": {"_id": 0, "referrer": "$_id", "hits": 1}},
    ]
    top_referrers = await db.analytics_pageviews.aggregate(
        top_referrers_pipeline
    ).to_list(10)

    # 3b. UTM sources (Naukri / LinkedIn / Facebook redirect campaigns).
    utm_pipeline = [
        {"$match": _pv_match},
        {"$match": {"props.utm_source": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {"_id": "$props.utm_source", "hits": {"$sum": 1}}},
        {"$sort": {"hits": -1}},
        {"$limit": 10},
        {"$project": {"_id": 0, "utm_source": "$_id", "hits": 1}},
    ]
    try:
        top_utm_sources = await db.analytics_pageviews.aggregate(utm_pipeline).to_list(10)
    except Exception:
        top_utm_sources = []

    # 4. Top recruiters by activity (from activity_logs)
    top_recruiters_pipeline = [
        {"$match": {"timestamp": {"$gte": since}}},
        {
            "$group": {
                "_id": "$user_id",
                "actions": {"$sum": 1},
                "user_name": {"$first": "$user_name"},
                "user_email": {"$first": "$user_email"},
            }
        },
        {"$sort": {"actions": -1}},
        {"$limit": 10},
        {
            "$project": {
                "_id": 0,
                "user_id": "$_id",
                "user_name": 1,
                "user_email": 1,
                "actions": 1,
            }
        },
    ]
    try:
        top_recruiters = await db.activity_logs.aggregate(
            top_recruiters_pipeline
        ).to_list(10)
    except Exception:
        top_recruiters = []

    # 5. Capture funnel (action counts from activity_logs)
    funnel_pipeline = [
        {"$match": {"timestamp": {"$gte": since}}},
        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
        {"$project": {"_id": 0, "action": "$_id", "count": 1}},
        {"$sort": {"count": -1}},
    ]
    try:
        funnel = await db.activity_logs.aggregate(funnel_pipeline).to_list(20)
    except Exception:
        funnel = []

    # 6. Logged-in vs anonymous split
    auth_split_pipeline = [
        {"$match": {"ts": {"$gte": since}, "event_type": "pageview"}},
        {
            "$group": {
                "_id": {"$cond": [{"$ifNull": ["$user_id", False]}, "auth", "anon"]},
                "count": {"$sum": 1},
            }
        },
        {"$project": {"_id": 0, "type": "$_id", "count": 1}},
    ]
    auth_split = await db.analytics_pageviews.aggregate(
        auth_split_pipeline
    ).to_list(2)

    return {
        "range_days": days,
        "public_only": public_only,
        "total_pageviews": total_pv,
        "dau": dau,
        "top_pages": top_pages,
        "top_referrers": top_referrers,
        "top_utm_sources": top_utm_sources,
        "top_recruiters": top_recruiters,
        "funnel": funnel,
        "auth_split": auth_split,
    }
