"""Shared "joinings" query logic.

A joining is an application sitting at stage=joined. The row shown in the
Employee Performance table (admin), the employer Joining List and the
performance archive is identical, so the hydration lives here.

Legacy applications never stored `join_date`, so it is derived:
`join_date` → the `stage_history` entry that moved the candidate to
`joined` → `updated_at` → `created_at`.
"""
from typing import List, Optional

import re


def derive_join_date(app: dict) -> str:
    raw = app.get("join_date") or app.get("joined_at") or app.get("joining_date")
    if not raw:
        for h in reversed(app.get("stage_history") or []):
            if (h.get("stage") or "").lower() == "joined" and h.get("timestamp"):
                raw = h["timestamp"]
                break
    raw = raw or app.get("updated_at") or app.get("created_at") or ""
    return str(raw)[:10]


async def unified_joinings(
    db,
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    team_ids: Optional[List[str]] = None,
    recruiter_ids: Optional[List[str]] = None,
    company_id: Optional[str] = None,
    position_q: Optional[str] = None,
    location_q: Optional[str] = None,
    payment_status: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 500,
) -> dict:
    """One joining list: the branch tracker plus the platform pipeline.

    77 of the platform's `joined` applications are the same hires that sit
    in the tracker, so rows are matched on the candidate's name and merged —
    otherwise every one of them would be listed (and counted) twice. The
    tracker holds the money, the application holds the editable fields, so a
    matched row keeps both and is marked `both`.
    """
    from services import branch_revenue as br

    ledger = await br.fetch_rows(db, date_from=date_from, date_to=date_to, team_ids=team_ids)
    pipeline = await fetch_joinings(
        db, date_from=date_from, date_to=date_to, company_id=company_id,
        recruiter_ids=recruiter_ids, limit=1000,
    )

    rows: List[dict] = []
    by_name: dict = {}
    for r in ledger:
        row = {
            "key": f"ledger:{r['id']}",
            "source": "tracker",
            "in_tracker": True,
            "in_pipeline": False,
            "application_id": "",
            "join_date": r.get("doj") or "",
            "candidate_name": r.get("candidate_name") or "",
            "recruiter_id": r.get("recruiter_id") or "",
            "recruiter_name": r.get("recruiter_name") or "",
            "client_name": r.get("organization") or "",
            "position": r.get("designation") or "",
            "location": r.get("location") or "",
            "branch": r.get("branch") or "",
            "team_id": r.get("team_id") or "",
            "joined_ctc": r.get("offered_ctc") or 0,
            "revenue": r.get("revenue") or 0,
            "payment_status": r.get("payment_status") or "",
            "bill_number": r.get("invoice_no") or "",
            "editable": False,
        }
        rows.append(row)
        by_name.setdefault(_norm_name(row["candidate_name"]), row)

    for p in pipeline:
        match = by_name.get(_norm_name(p.get("candidate_name")))
        if match:
            match["source"] = "both"
            match["in_pipeline"] = True
            match["application_id"] = p["application_id"]
            match["editable"] = True
            if not match["position"]:
                match["position"] = p.get("position") or ""
            continue
        rows.append({
            "key": f"app:{p['application_id']}",
            "source": "pipeline",
            "in_tracker": False,
            "in_pipeline": True,
            "application_id": p["application_id"],
            "join_date": p.get("join_date") or "",
            "candidate_name": p.get("candidate_name") or "",
            "recruiter_id": p.get("recruiter_id") or "",
            "recruiter_name": p.get("recruiter_name") or "",
            "client_name": p.get("client_name") or "",
            "position": p.get("position") or "",
            "location": p.get("location") or "",
            "branch": "",
            "team_id": "",
            "joined_ctc": p.get("joined_ctc") or 0,
            "revenue": p.get("revenue") or 0,
            # Platform rows carry their own state: nothing filled in yet →
            # revenue pending; filled but no invoice → IP; invoiced → PP.
            "payment_status": (
                "PP" if p.get("bill_number")
                else "IP" if p.get("revenue")
                else "Revenue pending"
            ),
            "bill_number": p.get("bill_number") or "",
            "commercial_rate_pct": p.get("commercial_rate_pct"),
            "editable": True,
        })

    def keep(r: dict) -> bool:
        if payment_status and r["payment_status"] != payment_status:
            return False
        if source and r["source"] != source:
            return False
        if position_q and position_q.lower() not in (r["position"] or "").lower():
            return False
        if location_q and location_q.lower() not in (r["location"] or "").lower():
            return False
        if q:
            needle = q.lower()
            blob = " ".join(str(r.get(k) or "") for k in
                            ("candidate_name", "client_name", "position", "recruiter_name", "bill_number"))
            if needle not in blob.lower():
                return False
        return True

    rows = [r for r in rows if keep(r)]
    rows.sort(key=lambda r: (r["join_date"] or "", r["candidate_name"]), reverse=True)

    buckets: dict = {}
    for r in rows:
        acc = buckets.setdefault(r["payment_status"] or "—", {"count": 0, "amount": 0.0})
        acc["count"] += 1
        acc["amount"] = round(acc["amount"] + float(r["revenue"] or 0), 2)

    return {
        "items": rows[:limit],
        "count": len(rows),
        "truncated": len(rows) > limit,
        "buckets": buckets,
        "totals": {
            "gross": round(sum(float(r["revenue"] or 0) for r in rows), 2),
            "received": round(sum(float(r["revenue"] or 0) for r in rows
                                  if r["payment_status"] == "Payment Received"), 2),
            "pending": round(sum(float(r["revenue"] or 0) for r in rows
                                 if r["payment_status"] in ("PP", "IP")), 2),
            "lost": round(sum(float(r["revenue"] or 0) for r in rows
                              if r["payment_status"] in ("Backout", "Credit Note", "Other / Review")), 2),
        },
        "sources": {
            "tracker_only": sum(1 for r in rows if r["source"] == "tracker"),
            "pipeline_only": sum(1 for r in rows if r["source"] == "pipeline"),
            "both": sum(1 for r in rows if r["source"] == "both"),
        },
        "revenue_pending_count": sum(1 for r in rows if r["payment_status"] == "Revenue pending"),
    }


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z]", "", str(s or "").lower())


async def fetch_joinings(
    db,
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    company_id: Optional[str] = None,
    position_q: Optional[str] = None,
    location_q: Optional[str] = None,
    recruiter_ids: Optional[List[str]] = None,
    limit: int = 200,
) -> List[dict]:
    q: dict = {"stage": "joined"}
    if recruiter_ids is not None:
        q["created_by"] = {"$in": list(recruiter_ids) or ["__none__"]}

    apps = await db.applications.find(q, {"_id": 0}).sort("updated_at", -1).to_list(2000)
    if not apps:
        return []

    for a in apps:
        a["_join_date"] = derive_join_date(a)
    if date_from:
        apps = [a for a in apps if a["_join_date"] and a["_join_date"] >= date_from]
    if date_to:
        apps = [a for a in apps if a["_join_date"] and a["_join_date"] <= date_to]
    apps.sort(key=lambda a: a["_join_date"], reverse=True)
    apps = apps[: max(1, min(limit, 1000))]
    if not apps:
        return []

    app_ids = [a["id"] for a in apps]
    job_ids = list({a.get("job_id") for a in apps if a.get("job_id")})
    cand_ids = list({a.get("candidate_id") for a in apps if a.get("candidate_id")})
    user_ids = list({a.get("created_by") for a in apps if a.get("created_by")})

    jobs, companies, cands, revs, users = {}, {}, {}, {}, {}
    async for j in db.jobs.find({"id": {"$in": job_ids}}, {"_id": 0, "id": 1, "title": 1, "company_id": 1, "location": 1}):
        jobs[j["id"]] = j
    company_ids = list({j.get("company_id") for j in jobs.values() if j.get("company_id")})
    async for c in db.companies.find({"id": {"$in": company_ids}}, {"_id": 0, "id": 1, "name": 1, "legal_name": 1, "logo_url": 1}):
        companies[c["id"]] = c
    async for c in db.candidate_bank.find({"id": {"$in": cand_ids}}, {"_id": 0, "id": 1, "name": 1, "location": 1, "current_location": 1}):
        cands[c["id"]] = c
    async for r in db.revenue.find({"application_id": {"$in": app_ids}}, {"_id": 0}):
        revs[r["application_id"]] = r
    async for u in db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1}):
        users[u["id"]] = u

    rows = []
    for a in apps:
        job = jobs.get(a.get("job_id"), {}) or {}
        client = companies.get(job.get("company_id"), {}) or {}
        cand = cands.get(a.get("candidate_id"), {}) or {}
        rev = revs.get(a["id"], {}) or {}
        if company_id and client.get("id") != company_id:
            continue
        row = {
            "application_id": a["id"],
            "join_date": a.get("_join_date") or "",
            "recruiter_id": a.get("created_by") or "",
            "recruiter_name": (users.get(a.get("created_by")) or {}).get("name") or "",
            "candidate_name": a.get("candidate_name") or cand.get("name") or "",
            "candidate_id": a.get("candidate_id") or "",
            "client_id": client.get("id") or "",
            "client_name": client.get("legal_name") or client.get("name") or "",
            "client_logo_url": client.get("logo_url") or "",
            "position": a.get("job_title") or job.get("title") or "",
            "location": cand.get("location") or cand.get("current_location") or job.get("location") or "",
            "joined_ctc": a.get("joined_ctc") or a.get("offered_ctc") or 0,
            "revenue": rev.get("final_revenue"),
            "revenue_status": rev.get("revenue_status") or "",
            "commercial_rate_pct": rev.get("commercial_rate_pct"),
            "bill_id": rev.get("bill_id") or "",
            "bill_number": rev.get("bill_number") or "",
        }
        if position_q and position_q.lower() not in (row["position"] or "").lower():
            continue
        if location_q and location_q.lower() not in (row["location"] or "").lower():
            continue
        rows.append(row)
    return rows
