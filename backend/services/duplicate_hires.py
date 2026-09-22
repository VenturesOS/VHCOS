"""Possible duplicate hires — flagged for a human, never merged automatically.

Exact name matching misses transposed letters ("Muadillar"/"Maudillar"),
initials ("Vignesh"/"Vignesh.S") and added surnames ("Kunal Kumar"/"Kunal
Kumar Jha"). It also can't tell two real people apart when they share a name,
which is common here — so everything below is a suggestion for review.

Three kinds:
  cross_system   a pipeline joining that looks like an existing tracker row
  same_client    the same name twice in the tracker against the same client
  same_amount    the same name twice with an identical billing amount
"""
from difflib import SequenceMatcher
from typing import List

from services.branch_revenue import COLL, fetch_rows, norm_name
from services.joinings_service import fetch_joinings

NEAR = 0.85


def _similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if sorted(a) == sorted(b):
        return 1.0          # same letters, different order
    return SequenceMatcher(None, a, b).ratio()


def _row_brief(r: dict) -> dict:
    return {
        "id": r.get("id"),
        "candidate_name": r.get("candidate_name"),
        "recruiter_name": r.get("recruiter_name"),
        "client_name": r.get("organization"),
        "branch": r.get("branch"),
        "date": r.get("doj"),
        "amount": float(r.get("revenue") or 0),
        "payment_status": r.get("payment_status"),
        "invoice_no": r.get("invoice_no") or "",
    }


async def find_duplicates(db, date_from: str, date_to: str) -> dict:
    rows = await fetch_rows(db, date_from=date_from, date_to=date_to)
    pipeline = await fetch_joinings(db, date_from=date_from, date_to=date_to, limit=1000)

    known = {}
    for r in rows:
        for name in [r.get("candidate_name"), *(r.get("name_aliases") or [])]:
            known.setdefault(norm_name(name), r)

    pairs: List[dict] = []

    # 1. A pipeline joining that is probably an existing tracker row
    for p in pipeline:
        n = norm_name(p.get("candidate_name"))
        if not n or n in known:
            continue
        best, score = None, 0.0
        for r in rows:
            s = _similar(n, norm_name(r.get("candidate_name")))
            if s > score:
                best, score = r, s
        if best and score >= NEAR and p["application_id"] not in (best.get("not_duplicate_of") or []):
            pairs.append({
                "kind": "cross_system",
                "confidence": round(score, 2),
                "reason": "Same hire recorded in the pipeline under a different spelling",
                "left": {"source": "pipeline", "application_id": p["application_id"],
                         "candidate_name": p.get("candidate_name"),
                         "recruiter_name": p.get("recruiter_name"),
                         "client_name": p.get("client_name"), "date": p.get("join_date"),
                         "amount": float(p.get("revenue") or 0),
                         "payment_status": "Revenue pending" if not p.get("revenue") else "IP"},
                "right": {"source": "tracker", **_row_brief(best)},
            })

    # 2 & 3. The same name twice inside the tracker
    by_name: dict = {}
    for r in rows:
        by_name.setdefault(norm_name(r.get("candidate_name")), []).append(r)
    for group in by_name.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if b.get("id") in (a.get("not_duplicate_of") or []):
                    continue
                if a.get("shared_credit") and b.get("shared_credit"):
                    continue    # the deliberate 50-50 split, not a duplicate
                same_client = (a.get("organization") or "").lower() == (b.get("organization") or "").lower()
                same_amount = round(float(a.get("revenue") or 0), 2) == round(float(b.get("revenue") or 0), 2) \
                    and float(a.get("revenue") or 0) > 0
                if same_client and same_amount:
                    reason = "Same name, same client, identical amount — very likely entered twice"
                    conf = 0.95
                elif same_client:
                    reason = "Same name against the same client — check it isn't the same hire twice"
                    conf = 0.7
                elif same_amount:
                    reason = "Same name, identical amount, different client — worth a look"
                    conf = 0.6
                else:
                    continue    # same name, different client and amount = two different people
                pairs.append({
                    "kind": "same_client" if same_client else "same_amount",
                    "confidence": conf, "reason": reason,
                    "left": {"source": "tracker", **_row_brief(a)},
                    "right": {"source": "tracker", **_row_brief(b)},
                })

    pairs.sort(key=lambda p: -p["confidence"])
    return {
        "pairs": pairs,
        "count": len(pairs),
        "at_risk_amount": round(sum(
            p["right"]["amount"] for p in pairs if p["kind"] != "cross_system"), 2),
        "range": {"from": date_from, "to": date_to},
    }
