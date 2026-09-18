"""Revenue targets & achievement rollups.

User-confirmed model (2026-09-17):
  • A target is ONE number per person (or per team) for a calendar year,
    1 Jan → 31 Dec.
  • "Already achieved" is a manual opening balance so a target set mid-year
    can still reflect revenue booked before the system tracked it.
  • Achievement = opening_achieved + revenue booked against that person's
    joinings inside the year.
  • Team achievement  = Σ its recruiters' achievement (+ team opening).
  • Company achievement = Σ all teams.
  • Recruiters only ever receive a percentage — never the rupee amounts.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional

TARGETS = "revenue_targets"


def current_year() -> int:
    return datetime.now(timezone.utc).year


def year_bounds(year: int) -> tuple:
    return f"{year}-01-01", f"{year}-12-31"


def pct(achieved: float, target: float) -> float:
    if not target:
        return 0.0
    return round(achieved / target * 100.0, 1)


async def get_targets(db, scope: str, scope_ids: List[str], year: int) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    async for t in db[TARGETS].find(
        {"scope": scope, "scope_id": {"$in": scope_ids}, "year": year}, {"_id": 0}
    ):
        out[t["scope_id"]] = t
    return out


async def upsert_target(
    db, scope: str, scope_id: str, year: int,
    target_amount: Optional[float], opening_achieved: Optional[float], user: dict,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    set_doc: dict = {"updated_at": now, "updated_by": user.get("id"), "updated_by_email": user.get("email")}
    if target_amount is not None:
        set_doc["target_amount"] = float(target_amount)
    if opening_achieved is not None:
        set_doc["opening_achieved"] = float(opening_achieved)
    await db[TARGETS].update_one(
        {"scope": scope, "scope_id": scope_id, "year": year},
        {"$set": set_doc,
         "$setOnInsert": {"scope": scope, "scope_id": scope_id, "year": year, "created_at": now}},
        upsert=True,
    )
    return await db[TARGETS].find_one({"scope": scope, "scope_id": scope_id, "year": year}, {"_id": 0})


async def revenue_by_recruiter(db, year: int, recruiter_ids: Optional[List[str]] = None) -> Dict[str, dict]:
    """Booked revenue per recruiter for the calendar year.

    `revenue` rows carry `recruiter_id` + `join_date` (written when a team
    leader fills the joining), so this is a small indexed scan.
    """
    start, end = year_bounds(year)
    match: dict = {"join_date": {"$gte": start, "$lte": end}, "final_revenue": {"$gt": 0}}
    if recruiter_ids is not None:
        match["recruiter_id"] = {"$in": list(recruiter_ids) or ["__none__"]}
    rows = await db.revenue.aggregate([
        {"$match": match},
        {"$group": {
            "_id": "$recruiter_id",
            "revenue": {"$sum": "$final_revenue"},
            "joinings": {"$sum": 1},
        }},
    ]).to_list(500)
    return {r["_id"]: {"revenue": round(r["revenue"], 2), "joinings": r["joinings"]} for r in rows if r["_id"]}


def build_member_rows(member_ids: List[str], targets: Dict[str, dict],
                      booked: Dict[str, dict], users: Dict[str, dict]) -> List[dict]:
    rows = []
    for uid in member_ids:
        t = targets.get(uid) or {}
        b = booked.get(uid) or {}
        opening = float(t.get("opening_achieved") or 0)
        earned = float(b.get("revenue") or 0)
        achieved = opening + earned
        target = float(t.get("target_amount") or 0)
        rows.append({
            "user_id": uid,
            "name": (users.get(uid) or {}).get("name") or "",
            "email": (users.get(uid) or {}).get("email") or "",
            "target_amount": target,
            "opening_achieved": opening,
            "revenue_booked": earned,
            "achieved": achieved,
            "achievement_pct": pct(achieved, target),
            "joinings": int(b.get("joinings") or 0),
        })
    rows.sort(key=lambda r: (-r["achieved"], r["name"]))
    return rows


async def active_users(db, user_ids: List[str]) -> Dict[str, dict]:
    """Roster lookup that drops deactivated accounts — team `recruiter_ids`
    keep ex-employees (emails prefixed `_deact_`), which polluted the
    target tables and the performance report."""
    out: Dict[str, dict] = {}
    async for u in db.users.find(
        {"id": {"$in": list(user_ids)}, "is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "name": 1, "email": 1},
    ):
        if str(u.get("email") or "").startswith("_deact_"):
            continue
        out[u["id"]] = u
    return out


async def member_rows(db, member_ids: List[str], year: int) -> List[dict]:
    """Per-recruiter target / achieved / % rows (rupee values included —
    only served to employer + admin)."""
    users = await active_users(db, member_ids)
    member_ids = [uid for uid in member_ids if uid in users]
    targets = await get_targets(db, "user", member_ids, year)
    booked = await revenue_by_recruiter(db, year, member_ids)
    return build_member_rows(member_ids, targets, booked, users)


def team_member_ids(team: dict) -> List[str]:
    ids = list(team.get("recruiter_ids") or [])
    if team.get("team_lead_id") and team["team_lead_id"] not in ids:
        ids.append(team["team_lead_id"])
    return ids


async def team_summary(db, team: dict, year: int, *, members: Optional[List[dict]] = None,
                       team_target_doc: Optional[dict] = None) -> dict:
    """One team: members + rolled-up totals. Team target falls back to the
    sum of member targets when the admin hasn't set an explicit one.

    `members` / `team_target_doc` can be pre-fetched by the caller (see
    `company_summary`) to avoid one round-trip per team.
    """
    if members is None:
        members = await member_rows(db, team_member_ids(team), year)
    if team_target_doc is None:
        team_target_doc = (await get_targets(db, "team", [team["id"]], year)).get(team["id"]) or {}
    members_target = round(sum(m["target_amount"] for m in members), 2)
    members_achieved = round(sum(m["achieved"] for m in members), 2)
    team_opening = float(team_target_doc.get("opening_achieved") or 0)
    explicit_target = float(team_target_doc.get("target_amount") or 0)
    target = explicit_target or members_target
    achieved = round(members_achieved + team_opening, 2)
    return {
        "team_id": team["id"],
        "team_name": team.get("name") or "",
        "employer_id": team.get("employer_id") or "",
        "members": members,
        "members_target": members_target,
        "members_achieved": members_achieved,
        "team_target": explicit_target,
        "team_opening_achieved": team_opening,
        "target_amount": target,
        "achieved": achieved,
        "achievement_pct": pct(achieved, target),
        "joinings": sum(m["joinings"] for m in members),
    }


async def company_summary(db, year: int) -> dict:
    """Every active team rolled into the company number (admin view).

    All lookups are batched — the per-team version took ~19 s on 7 teams.
    """
    teams = await db.teams.find({"status": {"$ne": "deleted"}}, {"_id": 0}).to_list(500)
    all_member_ids = sorted({uid for t in teams for uid in team_member_ids(t)})
    employer_ids = list({t.get("employer_id") for t in teams if t.get("employer_id")})

    users = await active_users(db, sorted(set(all_member_ids) | set(employer_ids)))
    all_member_ids = [uid for uid in all_member_ids if uid in users]
    user_targets = await get_targets(db, "user", all_member_ids, year)
    team_targets = await get_targets(db, "team", [t["id"] for t in teams], year)
    booked = await revenue_by_recruiter(db, year, all_member_ids)

    rows = []
    for t in teams:
        members = build_member_rows(
            [uid for uid in team_member_ids(t) if uid in users], user_targets, booked, users)
        s = await team_summary(db, t, year, members=members,
                               team_target_doc=team_targets.get(t["id"]) or {})
        s["employer_name"] = (users.get(t.get("employer_id")) or {}).get("name") or ""
        rows.append(s)
    rows.sort(key=lambda r: -r["achieved"])
    total_target = round(sum(r["target_amount"] for r in rows), 2)
    total_achieved = round(sum(r["achieved"] for r in rows), 2)
    return {
        "year": year,
        "teams": rows,
        "total_target": total_target,
        "total_achieved": total_achieved,
        "achievement_pct": pct(total_achieved, total_target),
        "total_joinings": sum(r["joinings"] for r in rows),
    }


async def my_achievement_pct(db, user_id: str, year: int) -> dict:
    """Recruiter-safe payload: percentage only, no rupee values."""
    rows = await member_rows(db, [user_id], year)
    r = rows[0] if rows else {}
    return {
        "year": year,
        "target_set": bool(r.get("target_amount")),
        "achievement_pct": r.get("achievement_pct", 0.0),
        "joinings": r.get("joinings", 0),
    }
