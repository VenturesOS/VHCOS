"""Performance Records (admin archive).

Once a target period closes, the report for every recruiter and employer is
frozen here — monthly, quarterly and annual — with the joinings that made
up the number, each contributor's achievement, and the team/company
rollups. Snapshots are idempotent: opening the page tops up any closed
period that has not been stored yet.
"""
import logging
import uuid
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from config import db
from utils import require_role
from services.joinings_service import fetch_joinings
from services import targets_service as ts

records_router = APIRouter(prefix="/api/performance-records", tags=["Performance Records"])
logger = logging.getLogger(__name__)

COLL = "performance_records"


def period_bounds(period_type: str, period: str) -> tuple:
    """`2026-09` (month) · `2026-Q3` (quarter) · `2026` (year)."""
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
        return f"{y}-01-01", f"{y}-12-31"
    except Exception:
        raise HTTPException(status_code=400, detail="Bad period. Use 2026-09, 2026-Q3 or 2026.")


def is_closed(period_type: str, period: str) -> bool:
    _, end = period_bounds(period_type, period)
    return end < ts.ist_today().date().isoformat()


# A team leader typically fills revenue days after the joining, so a
# freshly-closed period must stay LIVE for a while — otherwise the
# permanent record freezes at a number that is still incomplete.
ARCHIVE_GRACE_DAYS = 15


def ready_to_archive(period_type: str, period: str) -> bool:
    _, end = period_bounds(period_type, period)
    end_dt = datetime.fromisoformat(end).replace(tzinfo=ts.IST)
    return ts.ist_today() >= end_dt + timedelta(days=ARCHIVE_GRACE_DAYS)


async def build_report(period_type: str, period: str) -> dict:
    """Compute a period report live (same shape as a stored snapshot)."""
    start, end = period_bounds(period_type, period)
    year = int(period[:4])

    joinings = await fetch_joinings(db, date_from=start, date_to=end, limit=1000)
    teams = await db.teams.find({"status": {"$ne": "deleted"}}, {"_id": 0}).to_list(500)
    employer_ids = list({t.get("employer_id") for t in teams if t.get("employer_id")})
    employers = {}
    async for u in db.users.find({"id": {"$in": employer_ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1}):
        employers[u["id"]] = u

    # Period revenue per recruiter, straight off the joinings in range
    per_recruiter: dict = {}
    for row in joinings:
        rid = row.get("recruiter_id") or "unassigned"
        acc = per_recruiter.setdefault(rid, {
            "recruiter_id": rid, "recruiter_name": row.get("recruiter_name") or "",
            "joinings": 0, "revenue": 0.0, "candidates": [],
        })
        acc["joinings"] += 1
        acc["revenue"] += float(row.get("revenue") or 0)
        acc["candidates"].append({
            "candidate_name": row.get("candidate_name"),
            "client_name": row.get("client_name"),
            "position": row.get("position"),
            "join_date": row.get("join_date"),
            "joined_ctc": row.get("joined_ctc"),
            "revenue": row.get("revenue"),
            "bill_number": row.get("bill_number"),
        })

    # Annual targets give context to any period (monthly rows show the
    # share of the yearly target that was delivered in that window).
    canonical = ts.canonical_team_members(teams)
    all_member_ids = [uid for ids in canonical.values() for uid in ids]
    annual_targets = await ts.get_targets(db, "user", all_member_ids, year)

    # Names for everyone on the roster — previously a member with no
    # joining in the period had no name and the UI showed their raw id.
    # Deactivated accounts are dropped.
    member_users = await ts.active_users(db, all_member_ids)

    team_rows = []
    for t in teams:
        mids = [uid for uid in canonical.get(t["id"], []) if uid in member_users]
        members = []
        for uid in mids:
            r = per_recruiter.get(uid) or {}
            u = member_users.get(uid) or {}
            target = float((annual_targets.get(uid) or {}).get("target_amount") or 0)
            revenue = round(float(r.get("revenue") or 0), 2)
            p_target = ts.period_target(target, period_type)
            members.append({
                "user_id": uid,
                "name": u.get("name") or r.get("recruiter_name") or u.get("email") or uid,
                "email": u.get("email") or "",
                "joinings": int(r.get("joinings") or 0),
                "revenue": revenue,
                "annual_target": target,
                "period_target": p_target,
                # % of the target that belongs to THIS window (annual/12 for
                # a month, /4 for a quarter) — judging a month against the
                # full-year number made everyone look like a 8% performer.
                "period_achievement_pct": ts.pct(revenue, p_target),
                "share_of_annual_target_pct": ts.pct(revenue, target),
                "candidates": r.get("candidates") or [],
            })
        members.sort(key=lambda m: -m["revenue"])
        team_rows.append({
            "team_id": t["id"],
            "team_name": t.get("name") or "",
            "employer_id": t.get("employer_id") or "",
            "employer_name": (employers.get(t.get("employer_id")) or {}).get("name") or "",
            "members": members,
            "joinings": sum(m["joinings"] for m in members),
            "revenue": round(sum(m["revenue"] for m in members), 2),
            "annual_target": round(sum(m["annual_target"] for m in members), 2),
            "period_target": round(sum(m["period_target"] for m in members), 2),
            "period_achievement_pct": ts.pct(
                sum(m["revenue"] for m in members),
                sum(m["period_target"] for m in members),
            ),
        })
    team_rows.sort(key=lambda r: -r["revenue"])

    # Recruiters with joinings but no team (data hygiene) still get counted
    teamed = {m["user_id"] for r in team_rows for m in r["members"]}
    untracked = [v for k, v in per_recruiter.items() if k not in teamed]

    return {
        "period_type": period_type,
        "period": period,
        "range": {"from": start, "to": end},
        "closed": is_closed(period_type, period),
        "teams": team_rows,
        "untracked_recruiters": untracked,
        "total_joinings": len(joinings),
        "total_revenue": round(sum(float(j.get("revenue") or 0) for j in joinings), 2),
        "total_annual_target": round(sum(r["annual_target"] for r in team_rows), 2),
        "total_period_target": round(sum(r["period_target"] for r in team_rows), 2),
        "period_achievement_pct": ts.pct(
            sum(float(j.get("revenue") or 0) for j in joinings),
            sum(r["period_target"] for r in team_rows),
        ),
        "joinings": joinings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@records_router.get("/report")
async def get_report(
    period_type: str = Query("month", pattern="^(month|quarter|year)$"),
    period: Optional[str] = None,
    user: dict = Depends(require_role(["admin"])),
):
    """Live report for any period. Closed periods are auto-archived."""
    if not period:
        now = ts.ist_today()
        period = {
            "month": now.strftime("%Y-%m"),
            "quarter": f"{now.year}-Q{(now.month - 1) // 3 + 1}",
            "year": str(now.year),
        }[period_type]

    stored = await db[COLL].find_one({"period_type": period_type, "period": period}, {"_id": 0})
    if stored:
        return {**stored, "source": "archive"}

    report = await build_report(period_type, period)
    if report["closed"] and ready_to_archive(period_type, period):
        await _store(report, user, auto=True)
        report["source"] = "archive"
    else:
        report["source"] = "live"
        report["archive_pending"] = report["closed"]
    return report


async def _store(report: dict, user: dict, auto: bool = False) -> dict:
    doc = {
        **report,
        "id": str(uuid.uuid4()),
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "archived_by": user.get("email") if not auto else "system",
    }
    await db[COLL].update_one(
        {"period_type": doc["period_type"], "period": doc["period"]},
        {"$set": doc}, upsert=True,
    )
    return doc


@records_router.post("/snapshot")
async def snapshot(
    period_type: str = Query(..., pattern="^(month|quarter|year)$"),
    period: str = Query(...),
    user: dict = Depends(require_role(["admin"])),
):
    """Freeze a period on demand (also overwrites an existing snapshot)."""
    report = await build_report(period_type, period)
    doc = await _store(report, user)
    return {"message": "Snapshot stored", "period": doc["period"], "period_type": doc["period_type"],
            "total_revenue": doc["total_revenue"], "total_joinings": doc["total_joinings"]}


@records_router.get("/archive")
async def list_archive(user: dict = Depends(require_role(["admin"]))):
    rows = await db[COLL].find(
        {}, {"_id": 0, "id": 1, "period": 1, "period_type": 1, "range": 1, "total_revenue": 1,
             "total_joinings": 1, "archived_at": 1, "archived_by": 1},
    ).sort("period", -1).to_list(200)
    return {"items": rows, "count": len(rows)}


@records_router.delete("/archive/{record_id}")
async def delete_archive(record_id: str, user: dict = Depends(require_role(["admin"]))):
    res = await db[COLL].delete_one({"id": record_id})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"message": "Deleted", "id": record_id}


@records_router.get("/periods")
async def available_periods(user: dict = Depends(require_role(["admin"]))):
    now = datetime.now(timezone.utc)
    months: List[str] = []
    y, m = now.year, now.month
    for _ in range(18):
        months.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    quarters = [f"{yy}-Q{q}" for yy in (now.year, now.year - 1) for q in (4, 3, 2, 1)]
    years = [str(now.year - i) for i in range(4)]
    return {"months": months, "quarters": quarters, "years": years}
