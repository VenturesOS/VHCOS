"""Reconciliation — proves every revenue number in the product agrees.

One place that re-derives the same figure from different directions and
compares. If a future change starts double-counting or drops a branch, this
fails loudly instead of quietly inflating someone's achievement.

Checks:
  1. Branch rows add up to the tracker total.
  2. Recruiter rows add up to the tracker total.
  3. Company achieved = tracker active revenue + revenue booked on platform joinings.
  4. Team totals add up to the company total.
  5. Each team's members + its unattributed pot = that team's total.
  6. Every recruiter is counted on exactly one team.
  7. The twelve monthly slices add up to the year.
  8. No hire is billed twice (tracker + platform).
  9. The Joining List totals match the tracker.
"""
from typing import List

from services import branch_revenue as br
from services import targets_service as ts
from services.joinings_service import unified_joinings, _norm_name

PAISE = 1.0  # a rupee of slack for float arithmetic


def _check(name: str, expected: float, actual: float, note: str = "") -> dict:
    diff = round(actual - expected, 2)
    return {
        "check": name,
        "expected": round(expected, 2),
        "actual": round(actual, 2),
        "difference": diff,
        "ok": abs(diff) <= PAISE,
        "note": note,
    }


async def reconcile(db, year: int) -> dict:
    start, end = ts.year_bounds(year)
    rows = await br.fetch_rows(db, date_from=start, date_to=end)
    sheet = br.summarise(rows)
    tracker_active = sheet["kpis"]["active"]

    company = await ts.company_summary(db, year)
    platform = await db.revenue.aggregate([
        {"$match": {"join_date": {"$gte": start, "$lte": end}, "final_revenue": {"$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$final_revenue"}, "n": {"$sum": 1}}},
    ]).to_list(1)
    platform_total = round(platform[0]["total"], 2) if platform else 0.0
    platform_count = platform[0]["n"] if platform else 0

    checks: List[dict] = [
        _check("Branch rows add up to the tracker total",
               tracker_active, sum(b["active"] for b in sheet["branches"]),
               f"{len(sheet['branches'])} branches"),
        _check("Recruiter rows add up to the tracker total",
               tracker_active, sum(r["active"] for r in sheet["recruiters"]),
               f"{len(sheet['recruiters'])} recruiters"),
        _check("Company achieved = tracker + platform revenue",
               tracker_active + platform_total, company["total_achieved"],
               f"tracker ₹{tracker_active:,.0f} + platform ₹{platform_total:,.0f} ({platform_count} joinings)"),
        _check("Team totals add up to the company total",
               company["total_achieved"], sum(t["achieved"] for t in company["teams"]),
               f"{len(company['teams'])} live teams"),
    ]

    # Each team: members + the unattributed pot must equal the team total
    off = [t["team_name"] for t in company["teams"]
           if abs(t["achieved"] - (t["members_achieved"] + t["team_opening_achieved"]
                                   + t["ex_member_revenue"])) > PAISE]
    checks.append({
        "check": "Each team = its members + people who left / unassigned",
        "expected": 0, "actual": len(off), "difference": len(off),
        "ok": not off, "note": ", ".join(off) or "every team reconciles",
    })

    # Nobody counted on two teams
    seen, dupes = set(), []
    for t in company["teams"]:
        for m in t["members"]:
            if m["user_id"] in seen:
                dupes.append(m["name"])
            seen.add(m["user_id"])
    checks.append({
        "check": "Every recruiter counted on exactly one team",
        "expected": 0, "actual": len(dupes), "difference": len(dupes),
        "ok": not dupes, "note": ", ".join(dupes) or f"{len(seen)} people, no overlap",
    })

    # Twelve months must rebuild the year — sliced from the rows already in
    # hand, so this costs nothing extra
    monthly = 0.0
    for m in range(1, 13):
        lo, hi = ts.period_bounds("month", f"{year}-{m:02d}")
        monthly += br.totals([r for r in rows if lo <= (r.get("doj") or "") <= hi])["active"]
    checks.append(_check("The 12 monthly slices add up to the year", tracker_active, monthly))

    # A hire must not be billed by both systems
    tracker_names = {_norm_name(r.get("candidate_name")) for r in rows}
    booked = await db.revenue.find(
        {"join_date": {"$gte": start, "$lte": end}, "final_revenue": {"$gt": 0}},
        {"_id": 0, "application_id": 1},
    ).to_list(2000)
    overlaps = []
    if booked:
        apps = await db.applications.find(
            {"id": {"$in": [b["application_id"] for b in booked]}},
            {"_id": 0, "candidate_name": 1},
        ).to_list(2000)
        overlaps = [a.get("candidate_name") for a in apps
                    if _norm_name(a.get("candidate_name")) in tracker_names]
    checks.append({
        "check": "No hire billed twice (tracker + platform)",
        "expected": 0, "actual": len(overlaps), "difference": len(overlaps),
        "ok": not overlaps,
        "note": ", ".join(overlaps) or "no overlap — the API blocks booking revenue on a tracker hire",
    })

    joinings = await unified_joinings(db, date_from=start, date_to=end, limit=1)
    checks.append(_check("Joining List gross matches the tracker",
                         sheet["kpis"]["gross"] + platform_total, joinings["totals"]["gross"],
                         f"{joinings['count']} rows · {joinings['sources']['both']} in both systems"))

    return {
        "year": year,
        "ok": all(c["ok"] for c in checks),
        "checks": checks,
        "totals": {
            "tracker_gross": sheet["kpis"]["gross"],
            "tracker_active": tracker_active,
            "platform_revenue": platform_total,
            "company_achieved": company["total_achieved"],
            "placements": sheet["kpis"]["placements"],
        },
    }
