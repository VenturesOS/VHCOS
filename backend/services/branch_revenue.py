"""Branch & Recruiter Revenue — the client's offline tracker, in the product.

`placement_ledger` holds one row per placement (branch, recruiter, client,
candidate, DOJ, billing amount, payment status). It is the authoritative
record of revenue booked before the platform tracked joinings, imported from
the client's Excel via `scripts.import_placement_ledger`.

Buckets mirror the sheet exactly:
    Gross Billing   Σ billing amount
    Payment Received / PP (pending payment) / IP (pending invoice)
    Backout · Credit Note · Other / Review  → revenue lost or under review
    Active Revenue  = Gross − Backout − Credit Note − Other
    Realization %   = Payment Received / Gross
Achievement against a target uses Active Revenue (client decision, 2026-09-20).
"""
from typing import Dict, List, Optional

COLL = "placement_ledger"

BUCKET = {
    "Payment Received": "received",
    "PP": "pp",
    "IP": "ip",
    "Backout": "backout",
    "Credit Note": "credit_note",
    "Other / Review": "other",
}
LOST = ("backout", "credit_note", "other")


async def fetch_rows(
    db,
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch: Optional[str] = None,
    team_ids: Optional[List[str]] = None,
    recruiter_ids: Optional[List[str]] = None,
) -> List[dict]:
    q: dict = {}
    if date_from or date_to:
        q["doj"] = {}
        if date_from:
            q["doj"]["$gte"] = date_from
        if date_to:
            q["doj"]["$lte"] = date_to
    if branch:
        q["branch"] = branch
    if team_ids is not None:
        q["team_id"] = {"$in": list(team_ids) or ["__none__"]}
    if recruiter_ids is not None:
        q["recruiter_id"] = {"$in": list(recruiter_ids) or ["__none__"]}
    return await db[COLL].find(q, {"_id": 0}).sort("doj", -1).to_list(5000)


def _blank() -> dict:
    return {"placements": 0.0, "gross": 0.0, "received": 0.0, "pp": 0.0, "ip": 0.0,
            "backout": 0.0, "credit_note": 0.0, "other": 0.0}


def _add(acc: dict, row: dict) -> None:
    acc["placements"] += float(row.get("placement_credit") or 1)
    rev = float(row.get("revenue") or 0)
    acc["gross"] += rev
    acc[BUCKET.get(row.get("payment_status"), "other")] += rev


def _close(acc: dict) -> dict:
    gross = round(acc["gross"], 2)
    lost = sum(acc[k] for k in LOST)
    active = round(gross - lost, 2)
    placements = round(acc["placements"], 2)
    out = {k: round(v, 2) for k, v in acc.items()}
    out.update({
        "placements": int(placements) if placements == int(placements) else placements,
        "gross": gross,
        "pending": round(acc["pp"] + acc["ip"], 2),
        "revenue_lost": round(lost, 2),
        "active": active,
        # The sheet measures realization against Active Revenue, not gross —
        # money written off in a credit note was never collectable.
        "realization_pct": round(acc["received"] / active * 100, 1) if active else 0.0,
        "avg_per_placement": round(gross / placements, 2) if placements else 0.0,
    })
    return out


def summarise(rows: List[dict]) -> dict:
    """KPI strip + branch table + recruiter table, shaped like the sheet."""
    branches: Dict[str, dict] = {}
    recruiters: Dict[tuple, dict] = {}
    total = _blank()

    for r in rows:
        _add(total, r)
        b = branches.setdefault(r.get("branch") or "—", {"branch": r.get("branch") or "—",
                                                         "acc": _blank(), "groups": set()})
        _add(b["acc"], r)
        key = (r.get("branch") or "—", r.get("recruiter_id") or f"label:{r.get('recruiter_name')}")
        b["groups"].add(key)
        rec = recruiters.setdefault(key, {
            "branch": r.get("branch") or "—",
            "team_id": r.get("team_id") or "",
            "account_manager": r.get("account_manager") or "",
            "recruiter_id": r.get("recruiter_id") or "",
            "recruiter": r.get("recruiter_name") or "—",
            "is_ex_employee": bool(r.get("is_ex_employee")),
            "unassigned": bool(r.get("unassigned")),
            "acc": _blank(),
        })
        _add(rec["acc"], r)

    branch_rows = []
    for b in branches.values():
        branch_rows.append({"branch": b["branch"], "recruiter_groups": len(b["groups"]), **_close(b["acc"])})
    branch_rows.sort(key=lambda x: -x["gross"])

    recruiter_rows = [{k: v for k, v in r.items() if k != "acc"} | _close(r["acc"]) for r in recruiters.values()]
    recruiter_rows.sort(key=lambda x: -x["gross"])

    kpis = _close(total)
    kpis["recruiter_groups"] = len(recruiters)
    review = data_quality(rows)
    kpis["records_needing_review"] = sum(1 for r in review if r["blocking"])
    kpis["rows_without_login"] = sum(1 for r in review if not r["blocking"])
    return {"kpis": kpis, "branches": branch_rows, "recruiters": recruiter_rows}


def data_quality(rows: List[dict]) -> List[dict]:
    """Rows the tracker flags: blank billing amount, a payment status that
    isn't one of the five, and placements with no recruiter against them.
    Ex-employees without a login are listed too, but not as blockers."""
    out = []
    for r in rows:
        reasons, blocking = [], False
        if not float(r.get("revenue") or 0):
            reasons.append("Billing amount blank — excluded from revenue")
            blocking = True
        if r.get("payment_status") == "Other / Review":
            reasons.append(f"Payment status needs review: {r.get('payment_status_raw') or '—'}")
            blocking = True
        if str(r.get("recruiter_label") or "").lower().startswith("unassigned"):
            reasons.append("Recruiter blank in the source — held in the branch total")
            blocking = True
        elif r.get("unassigned"):
            reasons.append(f"{r.get('recruiter_name')} has no login — revenue held in the branch total")
        if reasons:
            out.append({
                "s_no": r.get("s_no"), "branch": r.get("branch"),
                "recruiter": r.get("recruiter_name"), "organization": r.get("organization"),
                "candidate_name": r.get("candidate_name"), "revenue": r.get("revenue"),
                "payment_status": r.get("payment_status"), "doj": r.get("doj"),
                "reasons": reasons, "blocking": blocking,
            })
    return out


async def tracker_row_for_candidate(db, candidate_name: str) -> Optional[dict]:
    """The tracker row for this hire, if the branch sheet already bills them.

    Guards the money: a hire that exists in both places must never have
    revenue booked twice (once from the tracker, once from the pipeline).
    """
    import re
    needle = re.sub(r"[^a-z]", "", str(candidate_name or "").lower())
    if not needle:
        return None
    async for row in db[COLL].find({}, {"_id": 0, "candidate_name": 1, "revenue": 1,
                                        "payment_status": 1, "invoice_no": 1, "branch": 1,
                                        "recruiter_name": 1}):
        if re.sub(r"[^a-z]", "", str(row.get("candidate_name") or "").lower()) == needle:
            return row
    return None


async def revenue_by_recruiter(db, date_from: str, date_to: str,
                               recruiter_ids: Optional[List[str]] = None) -> Dict[str, dict]:
    """Active revenue + placement count per recruiter, for target rollups."""
    rows = await fetch_rows(db, date_from=date_from, date_to=date_to, recruiter_ids=recruiter_ids)
    per: Dict[str, dict] = {}
    for r in rows:
        rid = r.get("recruiter_id")
        if not rid:
            continue
        acc = per.setdefault(rid, _blank())
        _add(acc, r)
    return {rid: {"revenue": _close(acc)["active"], "joinings": _close(acc)["placements"]}
            for rid, acc in per.items()}


def totals(rows: List[dict]) -> dict:
    acc = _blank()
    for r in rows:
        _add(acc, r)
    return _close(acc)


async def team_people(db, date_from: str, date_to: str) -> Dict[str, Dict[str, dict]]:
    """team id → {recruiter_id (or `label:Name`) → totals}.

    Used to fold revenue that belongs to nobody on the current roster —
    people who left, blank-recruiter rows — into the team (and therefore
    company) total, which is what the client asked for.
    """
    rows = await fetch_rows(db, date_from=date_from, date_to=date_to)
    per: Dict[str, Dict[str, dict]] = {}
    for r in rows:
        key = r.get("recruiter_id") or f"label:{r.get('recruiter_name')}"
        per.setdefault(r.get("team_id") or "", {}).setdefault(key, []).append(r)
    return {tid: {k: totals(v) for k, v in people.items()} for tid, people in per.items()}
