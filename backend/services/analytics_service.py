"""
VHC Talent OS - Analytics Service
MongoDB aggregation pipelines for the Advanced Analytics Dashboard.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from config import db


async def get_recruiter_ids_for_filter(
    employer_id: Optional[str] = None,
    team_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
):
    """Resolve filters to a list of recruiter (created_by) IDs."""
    if recruiter_id:
        return [recruiter_id]

    if team_id:
        team = await db.teams.find_one({"id": team_id}, {"_id": 0, "recruiter_ids": 1})
        if team:
            return team.get("recruiter_ids", [])
        return []

    if employer_id:
        teams = await db.teams.find(
            {"employer_id": employer_id},
            {"_id": 0, "recruiter_ids": 1},
        ).to_list(200)
        ids = set()
        for t in teams:
            ids.update(t.get("recruiter_ids", []))
        ids.add(employer_id)
        return list(ids)

    return None  # None means no filter


def _build_match(
    recruiter_ids: Optional[list],
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Build a $match stage for candidate_bank queries."""
    match = {}
    if recruiter_ids is not None:
        match["created_by"] = {"$in": recruiter_ids}
    if date_from or date_to:
        date_filter = {}
        if date_from:
            date_filter["$gte"] = date_from
        if date_to:
            date_filter["$lte"] = date_to + "T23:59:59"
        match["created_at"] = date_filter
    return match


async def get_analytics_summary(
    employer_id: Optional[str] = None,
    team_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    recruiter_ids = await get_recruiter_ids_for_filter(employer_id, team_id, recruiter_id)
    base_match = _build_match(recruiter_ids, date_from, date_to)

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    # --- KPIs ---
    total_captures = await db.candidate_bank.count_documents(base_match or {})

    today_match = {**base_match, "created_at": {"$gte": today_start}}
    captures_today = await db.candidate_bank.count_documents(today_match)

    week_match = {**base_match, "created_at": {"$gte": week_start}}
    captures_this_week = await db.candidate_bank.count_documents(week_match)

    month_match = {**base_match, "created_at": {"$gte": month_start}}
    captures_this_month = await db.candidate_bank.count_documents(month_match)

    # Avg daily rate over last 30 days
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    last30_match = {**base_match, "created_at": {"$gte": thirty_days_ago}}
    last30_count = await db.candidate_bank.count_documents(last30_match)
    avg_daily_rate = round(last30_count / 30, 1)

    # Active sources count
    source_pipeline = [{"$match": base_match}] if base_match else []
    source_pipeline.append({"$group": {"_id": "$source"}})
    active_sources_result = await db.candidate_bank.aggregate(source_pipeline).to_list(50)
    active_sources = len(active_sources_result)

    # --- Source Distribution (for pie chart) ---
    src_pipeline = [{"$match": base_match}] if base_match else []
    src_pipeline.extend([
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ])
    source_raw = await db.candidate_bank.aggregate(src_pipeline).to_list(50)
    source_distribution = [
        {"source": r["_id"] or "unknown", "count": r["count"]}
        for r in source_raw
    ]

    # --- Capture Trends (last 30 days, daily — for line chart) ---
    trend_pipeline = []
    trend_match = {**base_match, "created_at": {"$gte": thirty_days_ago}}
    if trend_match:
        trend_pipeline.append({"$match": trend_match})
    trend_pipeline.extend([
        {"$addFields": {"date_str": {"$substr": ["$created_at", 0, 10]}}},
        {"$group": {"_id": "$date_str", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ])
    trend_raw = await db.candidate_bank.aggregate(trend_pipeline).to_list(60)
    capture_trends = [{"date": r["_id"], "count": r["count"]} for r in trend_raw]

    # --- Recruiter / Team Performance (bar chart) ---
    perf_pipeline = [{"$match": base_match}] if base_match else []
    perf_pipeline.extend([
        {"$group": {"_id": "$created_by", "captures": {"$sum": 1}}},
        {"$sort": {"captures": -1}},
        {"$limit": 20},
    ])
    perf_raw = await db.candidate_bank.aggregate(perf_pipeline).to_list(20)

    # Enrich with user names and team info
    recruiter_performance = []
    for r in perf_raw:
        user_id = r["_id"]
        if not user_id:
            continue
        user = await db.users.find_one({"id": user_id}, {"_id": 0, "name": 1, "role": 1, "email": 1})
        user_name = user.get("name", "Unknown") if user else "Unknown"
        user_role = user.get("role", "") if user else ""

        # Find team for this user
        team = await db.teams.find_one(
            {"recruiter_ids": user_id}, {"_id": 0, "name": 1}
        )
        team_name = team.get("name", "") if team else ""

        recruiter_performance.append({
            "user_id": user_id,
            "name": user_name,
            "role": user_role,
            "team": team_name,
            "captures": r["captures"],
        })

    # --- Funnel Velocity (from applications) ---
    app_match = {}
    if recruiter_ids is not None:
        job_ids = await db.jobs.distinct("id", {"posted_by": {"$in": recruiter_ids}})
        if job_ids:
            app_match["job_id"] = {"$in": job_ids}
        else:
            app_match["job_id"] = {"$in": []}

    stage_pipeline = [{"$match": app_match}] if app_match else []
    stage_pipeline.extend([
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
    ])
    stage_raw = await db.applications.aggregate(stage_pipeline).to_list(20)
    stage_distribution = {r["_id"]: r["count"] for r in stage_raw if r["_id"]}

    total_applications = sum(stage_distribution.values())

    # Funnel velocity — compute avg days between applied_at and updated_at per stage
    funnel_velocity = {}
    for stage in ["shortlisted", "interview", "offered", "hired"]:
        vel_pipeline = [
            {"$match": {**app_match, "stage": stage, "applied_at": {"$exists": True}, "updated_at": {"$exists": True}}},
            {"$project": {"applied_at": 1, "updated_at": 1, "_id": 0}},
        ]
        vel_docs = await db.applications.aggregate(vel_pipeline).to_list(1000)
        if vel_docs:
            total_days = 0
            count = 0
            for doc in vel_docs:
                try:
                    applied = datetime.fromisoformat(doc["applied_at"].replace("Z", "+00:00"))
                    updated = datetime.fromisoformat(doc["updated_at"].replace("Z", "+00:00"))
                    days = (updated - applied).days
                    if days >= 0:
                        total_days += days
                        count += 1
                except (ValueError, TypeError):
                    pass
            funnel_velocity[stage] = round(total_days / count, 1) if count > 0 else 0
        else:
            funnel_velocity[stage] = 0

    # --- Filter options ---
    employers = await db.users.find(
        {"role": "employer"}, {"_id": 0, "id": 1, "name": 1}
    ).to_list(500)
    teams_list = await db.teams.find(
        {}, {"_id": 0, "id": 1, "name": 1, "employer_id": 1}
    ).to_list(500)
    recruiters = await db.users.find(
        {"role": {"$in": ["recruiter", "employer"]}}, {"_id": 0, "id": 1, "name": 1, "role": 1}
    ).to_list(500)

    return {
        "kpis": {
            "total_captures": total_captures,
            "captures_today": captures_today,
            "captures_this_week": captures_this_week,
            "captures_this_month": captures_this_month,
            "avg_daily_rate": avg_daily_rate,
            "active_sources": active_sources,
            "total_applications": total_applications,
            "avg_funnel_days": funnel_velocity.get("hired", 0),
        },
        "source_distribution": source_distribution,
        "capture_trends": capture_trends,
        "recruiter_performance": recruiter_performance,
        "stage_distribution": stage_distribution,
        "funnel_velocity": funnel_velocity,
        "filters": {
            "employers": employers,
            "teams": teams_list,
            "recruiters": recruiters,
        },
    }
