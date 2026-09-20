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
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from services import branch_revenue as br

TARGETS = "revenue_targets"
TEAMS = "teams"
IST = timezone(timedelta(hours=5, minutes=30))

# Teams that count. `merged` teams exist only as history — their account
# manager was folded into another team (Manorma → Delhi, Jatin → Gurgaon),
# so counting them again would double the company total.
TEAM_LIVE = {"status": {"$nin": ["deleted", "merged"]}}


async def live_teams(db) -> List[dict]:
    return await db[TEAMS].find(TEAM_LIVE, {"_id": 0}).to_list(500)


async def teams_for_employer(db, user_id: str) -> List[dict]:
    """Teams an account manager owns. A team can have more than one manager
    (`additional_employer_ids`) — Delhi is run by Maneet + Manorma, Gurgaon
    by Ajit + Jatin + Rohit."""
    return await db[TEAMS].find(
        {**TEAM_LIVE, "$or": [{"employer_id": user_id}, {"additional_employer_ids": user_id}]},
        {"_id": 0},
    ).to_list(50)


def ist_today() -> datetime:
    """Business day in IST. Using UTC made a new month/year start 5.5 h
    late, so period defaults and closure flipped a day behind."""
    return datetime.now(IST)


def current_year() -> int:
    return ist_today().year


def year_bounds(year: int) -> tuple:
    return f"{year}-01-01", f"{year}-12-31"


def period_bounds(period_type: str, period: str) -> Optional[tuple]:
    """`2026-09` (month) · `2026-Q3` (quarter) · `2026` (year) → ISO range."""
    try:
        if period_type == "month":
            y, m = int(period[:4]), int(period[5:7])
            return f"{y}-{m:02d}-01", f"{y}-{m:02d}-{monthrange(y, m)[1]:02d}"
        if period_type == "quarter":
            y, q = int(period[:4]), int(period[-1])
            start_m = (q - 1) * 3 + 1
            end_m = start_m + 2
            return f"{y}-{start_m:02d}-01", f"{y}-{end_m:02d}-{monthrange(y, end_m)[1]:02d}"
        y = int(period[:4])
        return year_bounds(y)
    except Exception:
        return None


def period_target(annual_target: float, period_type: str) -> float:
    """Annual target pro-rated for the window being reported."""
    divisor = {"month": 12, "quarter": 4, "year": 1}.get(period_type, 1)
    return round((annual_target or 0) / divisor, 2)


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

    Two sources, added together:
      • `placement_ledger` — the branch revenue tracker (active revenue).
      • `revenue` — booked on joinings the platform tracked itself.
    `revenue` rows carry `recruiter_id` + `join_date`, so this is a small
    indexed scan.
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
    out = {r["_id"]: {"revenue": round(r["revenue"], 2), "joinings": r["joinings"]}
           for r in rows if r["_id"]}
    for rid, led in (await br.revenue_by_recruiter(db, start, end, recruiter_ids)).items():
        acc = out.setdefault(rid, {"revenue": 0.0, "joinings": 0})
        acc["revenue"] = round(acc["revenue"] + led["revenue"], 2)
        acc["joinings"] += led["joinings"]
    return out


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
            "joinings": whole(b.get("joinings") or 0),
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


def canonical_team_members(teams: List[dict]) -> Dict[str, List[str]]:
    """Map team id → members, with every recruiter attributed to exactly
    ONE team.

    A recruiter listed on two teams used to have their full revenue added
    to both team totals and therefore counted twice in the company total.
    The first team (oldest by `created_at`, then by name) keeps them.
    """
    ordered = sorted(teams, key=lambda t: (str(t.get("created_at") or ""), str(t.get("name") or "")))
    claimed: set = set()
    out: Dict[str, List[str]] = {}
    for t in ordered:
        mine = [uid for uid in team_member_ids(t) if uid not in claimed]
        claimed.update(mine)
        out[t["id"]] = mine
    return out


def team_member_ids(team: dict) -> List[str]:
    """Roster for revenue purposes: the recruiters, the lead, and every
    account manager on the team — AMs place candidates themselves, so their
    revenue belongs on the team table rather than in the unattributed pot.
    """
    ids = list(team.get("recruiter_ids") or [])
    extras = [team.get("team_lead_id"), team.get("employer_id"), *(team.get("additional_employer_ids") or [])]
    for extra in extras:
        if extra and extra not in ids:
            ids.append(extra)
    return ids


def whole(n: float) -> float:
    """Placement counts can be fractional (shared credit) — keep them tidy."""
    n = round(float(n or 0), 1)
    return int(n) if n == int(n) else n


async def roster_ids(db) -> set:
    """Every recruiter attributed to a team, across all teams. Used so a
    person counted on their own team is never also counted as
    'unattributed' on another team's ledger rows."""
    return {uid for ids in canonical_team_members(await live_teams(db)).values() for uid in ids}


async def ex_member_revenue(db, team_id: str, year: int, member_ids: List[str],
                            people: Optional[Dict[str, Dict[str, dict]]] = None,
                            exclude_ids: Optional[set] = None) -> dict:
    """Ledger revenue inside a team that belongs to nobody on the current
    roster — recruiters who left, and blank-recruiter rows. Client rule:
    it stays with the team they worked for."""
    if people is None:
        people = await br.team_people(db, *year_bounds(year))
    roster = set(member_ids) | (exclude_ids if exclude_ids is not None else await roster_ids(db))
    raw = {k: v for k, v in (people.get(team_id) or {}).items() if k not in roster}
    # Someone who left still has a user id on their ledger rows — resolve it
    # to a name so the UI never shows a raw id.
    ids = [k for k in raw if not k.startswith("label:")]
    names = {}
    if ids:
        async for u in db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1}):
            names[u["id"]] = u.get("name") or u.get("email") or u["id"]
    rows = [{"name": names.get(k, k.split("label:", 1)[-1]), **v} for k, v in raw.items()]
    return {
        "revenue": round(sum(r["active"] for r in rows), 2),
        "joinings": whole(sum(r["placements"] for r in rows)),
        "people": sorted(rows, key=lambda r: -r["active"]),
    }


async def team_summary(db, team: dict, year: int, *, members: Optional[List[dict]] = None,
                       team_target_doc: Optional[dict] = None,
                       ledger_people: Optional[Dict[str, Dict[str, dict]]] = None,
                       all_roster_ids: Optional[set] = None) -> dict:
    """One team: members + rolled-up totals. Team target falls back to the
    sum of member targets when the admin hasn't set an explicit one.

    `members` / `team_target_doc` / `ledger_people` can be pre-fetched by the
    caller (see `company_summary`) to avoid one round-trip per team.
    """
    if members is None:
        members = await member_rows(db, team_member_ids(team), year)
    if team_target_doc is None:
        team_target_doc = (await get_targets(db, "team", [team["id"]], year)).get(team["id"]) or {}
    ex = await ex_member_revenue(db, team["id"], year, [m["user_id"] for m in members],
                                 people=ledger_people, exclude_ids=all_roster_ids)
    members_target = round(sum(m["target_amount"] for m in members), 2)
    members_achieved = round(sum(m["achieved"] for m in members), 2)
    team_opening = float(team_target_doc.get("opening_achieved") or 0)
    explicit_target = float(team_target_doc.get("target_amount") or 0)
    target = explicit_target or members_target
    achieved = round(members_achieved + team_opening + ex["revenue"], 2)
    return {
        "team_id": team["id"],
        "team_name": team.get("name") or "",
        "employer_id": team.get("employer_id") or "",
        "members": members,
        "members_target": members_target,
        "members_achieved": members_achieved,
        "team_target": explicit_target,
        "team_opening_achieved": team_opening,
        "ex_member_revenue": ex["revenue"],
        "ex_members": ex["people"],
        "target_amount": target,
        "achieved": achieved,
        "achievement_pct": pct(achieved, target),
        "joinings": whole(sum(m["joinings"] for m in members) + ex["joinings"]),
    }


async def company_summary(db, year: int) -> dict:
    """Every active team rolled into the company number (admin view).

    All lookups are batched — the per-team version took ~19 s on 7 teams.
    """
    teams = await live_teams(db)
    canonical = canonical_team_members(teams)
    all_member_ids = sorted({uid for ids in canonical.values() for uid in ids})
    employer_ids = list({t.get("employer_id") for t in teams if t.get("employer_id")})

    users = await active_users(db, sorted(set(all_member_ids) | set(employer_ids)))
    all_member_ids = [uid for uid in all_member_ids if uid in users]
    user_targets = await get_targets(db, "user", all_member_ids, year)
    team_targets = await get_targets(db, "team", [t["id"] for t in teams], year)
    booked = await revenue_by_recruiter(db, year, all_member_ids)
    ledger_people = await br.team_people(db, *year_bounds(year))

    rows = []
    for t in teams:
        members = build_member_rows(
            [uid for uid in canonical.get(t["id"], []) if uid in users], user_targets, booked, users)
        s = await team_summary(db, t, year, members=members,
                               team_target_doc=team_targets.get(t["id"]) or {},
                               ledger_people=ledger_people,
                               all_roster_ids=set(all_member_ids))
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
        "total_joinings": whole(sum(r["joinings"] for r in rows)),
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
