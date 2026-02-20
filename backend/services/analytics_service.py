"""
VHC Talent OS - Analytics Service (Optimized)
Uses asyncio.gather for parallel MongoDB queries and batched lookups.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
from config import db


async def get_recruiter_ids_for_filter(
    employer_id: Optional[str] = None,
    team_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
):
    if recruiter_id:
        return [recruiter_id]
    if team_id:
        team = await db.teams.find_one({"id": team_id}, {"_id": 0, "recruiter_ids": 1})
        return team.get("recruiter_ids", []) if team else []
    if employer_id:
        teams = await db.teams.find({"employer_id": employer_id}, {"_id": 0, "recruiter_ids": 1}).to_list(200)
        ids = {employer_id}
        for t in teams:
            ids.update(t.get("recruiter_ids", []))
        return list(ids)
    return None


def _build_match(recruiter_ids, date_from=None, date_to=None):
    match = {}
    if recruiter_ids is not None:
        match["created_by"] = {"$in": recruiter_ids}
    if date_from or date_to:
        df = {}
        if date_from:
            df["$gte"] = date_from
        if date_to:
            df["$lte"] = date_to + "T23:59:59"
        match["created_at"] = df
    return match


async def get_analytics_summary(
    employer_id=None, team_id=None, recruiter_id=None,
    date_from=None, date_to=None,
):
    recruiter_ids = await get_recruiter_ids_for_filter(employer_id, team_id, recruiter_id)
    base_match = _build_match(recruiter_ids, date_from, date_to)

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    thirty_days_ago = (now - timedelta(days=30)).isoformat()

    # Build app_match for application queries
    app_match = {}
    if recruiter_ids is not None:
        job_ids = await db.jobs.distinct("id", {"posted_by": {"$in": recruiter_ids}})
        app_match["job_id"] = {"$in": job_ids or []}

    # ── Run ALL independent queries in parallel ──
    (
        total_captures,
        captures_today,
        captures_this_week,
        captures_this_month,
        last30_count,
        active_sources_result,
        source_raw,
        trend_raw,
        perf_raw,
        stage_raw,
        vel_docs_all,
        employers,
        teams_list,
        recruiters_list,
        ai_total,
        ai_skills_raw,
        zero_result_prompts,
        cost_raw,
    ) = await asyncio.gather(
        # KPI counts
        db.candidate_bank.count_documents(base_match or {}),
        db.candidate_bank.count_documents({**base_match, "created_at": {"$gte": today_start}}),
        db.candidate_bank.count_documents({**base_match, "created_at": {"$gte": week_start}}),
        db.candidate_bank.count_documents({**base_match, "created_at": {"$gte": month_start}}),
        db.candidate_bank.count_documents({**base_match, "created_at": {"$gte": thirty_days_ago}}),
        # Source count
        db.candidate_bank.aggregate([
            *(([{"$match": base_match}] if base_match else [])),
            {"$group": {"_id": "$source"}},
        ]).to_list(50),
        # Source distribution
        db.candidate_bank.aggregate([
            *(([{"$match": base_match}] if base_match else [])),
            {"$group": {"_id": "$source", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]).to_list(50),
        # Capture trends (30 days)
        db.candidate_bank.aggregate([
            {"$match": {**base_match, "created_at": {"$gte": thirty_days_ago}}},
            {"$addFields": {"date_str": {"$substr": ["$created_at", 0, 10]}}},
            {"$group": {"_id": "$date_str", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]).to_list(60),
        # Recruiter performance (top 20)
        db.candidate_bank.aggregate([
            *(([{"$match": base_match}] if base_match else [])),
            {"$group": {"_id": "$created_by", "captures": {"$sum": 1}}},
            {"$sort": {"captures": -1}},
            {"$limit": 20},
        ]).to_list(20),
        # Stage distribution
        db.applications.aggregate([
            *(([{"$match": app_match}] if app_match else [])),
            {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
        ]).to_list(20),
        # Funnel velocity - single query for all stages
        db.applications.aggregate([
            {"$match": {
                **app_match,
                "stage": {"$in": ["shortlisted", "interview", "offered", "hired"]},
                "applied_at": {"$exists": True},
                "updated_at": {"$exists": True},
            }},
            {"$project": {"stage": 1, "applied_at": 1, "updated_at": 1, "_id": 0}},
        ]).to_list(5000),
        # Filter options
        db.users.find({"role": "employer"}, {"_id": 0, "id": 1, "name": 1}).to_list(500),
        db.teams.find({}, {"_id": 0, "id": 1, "name": 1, "employer_id": 1}).to_list(500),
        db.users.find({"role": {"$in": ["recruiter", "employer"]}}, {"_id": 0, "id": 1, "name": 1, "role": 1}).to_list(500),
        # AI search
        db.ai_search_logs.count_documents({}),
        db.ai_search_logs.aggregate([
            {"$unwind": {"path": "$extracted_filters.skills", "preserveNullAndEmptyArrays": False}},
            {"$group": {"_id": {"$toLower": "$extracted_filters.skills"}, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]).to_list(10),
        db.ai_search_logs.aggregate([
            {"$match": {"candidates_found": 0}},
            {"$sort": {"extraction_time_s": -1}},
            {"$limit": 5},
            {"$project": {"_id": 0, "raw_prompt": 1, "extracted_filters.skills": 1}},
        ]).to_list(5),
        db.ai_search_logs.aggregate([
            {"$group": {
                "_id": None,
                "total_input_tokens": {"$sum": "$token_usage.prompt_tokens"},
                "total_output_tokens": {"$sum": "$token_usage.completion_tokens"},
                "total_searches": {"$sum": 1},
                "avg_time": {"$avg": "$total_time_s"},
            }},
        ]).to_list(1),
    )

    # ── Process results ──
    avg_daily_rate = round(last30_count / 30, 1)
    active_sources = len(active_sources_result)
    source_distribution = [{"source": r["_id"] or "unknown", "count": r["count"]} for r in source_raw]
    capture_trends = [{"date": r["_id"], "count": r["count"]} for r in trend_raw]
    stage_distribution = {r["_id"]: r["count"] for r in stage_raw if r["_id"]}
    total_applications = sum(stage_distribution.values())

    # Batch user + team lookups for recruiter performance
    user_ids = [r["_id"] for r in perf_raw if r["_id"]]
    users_batch, teams_batch = await asyncio.gather(
        db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1, "role": 1}).to_list(50),
        db.teams.find({"recruiter_ids": {"$in": user_ids}}, {"_id": 0, "name": 1, "recruiter_ids": 1}).to_list(200),
    )
    user_map = {u["id"]: u for u in users_batch}
    team_map = {}
    for t in teams_batch:
        for rid in t.get("recruiter_ids", []):
            if rid not in team_map:
                team_map[rid] = t.get("name", "")

    recruiter_performance = []
    for r in perf_raw:
        uid = r["_id"]
        if not uid:
            continue
        u = user_map.get(uid, {})
        recruiter_performance.append({
            "user_id": uid,
            "name": u.get("name", "Unknown"),
            "role": u.get("role", ""),
            "team": team_map.get(uid, ""),
            "captures": r["captures"],
        })

    # Compute funnel velocity from single batch query
    funnel_velocity = {}
    stage_docs = {}
    for doc in vel_docs_all:
        stage_docs.setdefault(doc["stage"], []).append(doc)

    for stage in ["shortlisted", "interview", "offered", "hired"]:
        docs = stage_docs.get(stage, [])
        if docs:
            total_days, count = 0, 0
            for doc in docs:
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

    # AI cost
    ai_cost_data = {}
    if cost_raw:
        c = cost_raw[0]
        input_cost = (c.get("total_input_tokens", 0) / 1_000_000) * 0.15
        output_cost = (c.get("total_output_tokens", 0) / 1_000_000) * 0.60
        total_cost = round(input_cost + output_cost, 4)
        total_searches = c.get("total_searches", 1)
        ai_cost_data = {
            "total_input_tokens": c.get("total_input_tokens", 0),
            "total_output_tokens": c.get("total_output_tokens", 0),
            "total_cost_usd": total_cost,
            "avg_cost_per_search_usd": round(total_cost / max(total_searches, 1), 4),
            "avg_time_s": round(c.get("avg_time", 0), 2),
        }

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
        "ai_search": {
            "total_searches": ai_total,
            "top_searched_skills": [{"skill": r["_id"], "count": r["count"]} for r in ai_skills_raw],
            "zero_result_prompts": zero_result_prompts,
            "cost_data": ai_cost_data,
        },
        "filters": {
            "employers": employers,
            "teams": teams_list,
            "recruiters": recruiters_list,
        },
    }
