"""Shared "joinings" query logic.

A joining is an application sitting at stage=joined. The row shown in the
Employee Performance table (admin), the employer Joining List and the
performance archive is identical, so the hydration lives here.

Legacy applications never stored `join_date`, so it is derived:
`join_date` → the `stage_history` entry that moved the candidate to
`joined` → `updated_at` → `created_at`.
"""
from typing import List, Optional


def derive_join_date(app: dict) -> str:
    raw = app.get("join_date") or app.get("joined_at") or app.get("joining_date")
    if not raw:
        for h in reversed(app.get("stage_history") or []):
            if (h.get("stage") or "").lower() == "joined" and h.get("timestamp"):
                raw = h["timestamp"]
                break
    raw = raw or app.get("updated_at") or app.get("created_at") or ""
    return str(raw)[:10]


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
