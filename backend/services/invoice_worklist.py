"""Invoices & Payments worklist — what Accounts actually works through.

Three states, drawn from every place money can sit:

  to_raise  no invoice yet — tracker rows marked IP, platform joinings whose
            revenue hasn't been filled in, and draft bills
  pending   invoice out, payment not in — tracker rows marked PP, and bills
            that have been sent or viewed
  received  collected — tracker rows marked Payment Received, and paid bills

Backouts, credit notes and unmapped statuses land in `written_off` so they
stay visible without polluting the collections pipeline.
"""
from typing import List, Optional

from services import branch_revenue as br
from services.joinings_service import fetch_joinings

STATE_FROM_TRACKER = {
    "Payment Received": "received",
    "PP": "pending",
    "IP": "to_raise",
    "Backout": "written_off",
    "Credit Note": "written_off",
    "Other / Review": "written_off",
}
STATE_FROM_BILL = {
    "draft": "to_raise",
    "sent": "pending",
    "viewed": "pending",
    "paid": "received",
    "cancelled": "written_off",
}


async def worklist(
    db,
    *,
    date_from: str,
    date_to: str,
    team_ids: Optional[List[str]] = None,
    recruiter_ids: Optional[List[str]] = None,
    state: Optional[str] = None,
    q: Optional[str] = None,
    include_bills: bool = True,
) -> dict:
    items: List[dict] = []

    for r in await br.fetch_rows(db, date_from=date_from, date_to=date_to, team_ids=team_ids):
        items.append({
            "key": f"ledger:{r['id']}",
            "kind": "tracker",
            "placement_id": r["id"],
            "state": STATE_FROM_TRACKER.get(r.get("payment_status"), "written_off"),
            "payment_status": r.get("payment_status") or "",
            "payment_date": r.get("payment_date") or "",
            "reference": r.get("invoice_no") or "",
            "client_name": r.get("organization") or "",
            "candidate_name": r.get("candidate_name") or "",
            "recruiter_name": r.get("recruiter_name") or "",
            "branch": r.get("branch") or "",
            "date": r.get("doj") or "",
            "amount": float(r.get("revenue") or 0),
            "application_id": "",
            "bill_id": "",
            # Accounts can record the invoice number and mark the money in
            "can_record_invoice": True,
            "can_mark_received": True,
        })

    # Platform joinings still waiting for revenue / an invoice
    tracker_names = {br.norm_name(n) for n in await db[br.COLL].distinct("candidate_name")}
    for p in await fetch_joinings(db, date_from=date_from, date_to=date_to,
                                  recruiter_ids=recruiter_ids, limit=1000):
        if p.get("bill_number"):
            continue  # already a bill, counted below
        if br.norm_name(p.get("candidate_name")) in tracker_names:
            continue  # the tracker row above already represents this hire
        items.append({
            "key": f"app:{p['application_id']}",
            "kind": "pipeline",
            "placement_id": "",
            "state": "to_raise",
            "payment_status": "Revenue pending" if not p.get("revenue") else "IP",
            "payment_date": "",
            "reference": "",
            "client_name": p.get("client_name") or "",
            "candidate_name": p.get("candidate_name") or "",
            "recruiter_name": p.get("recruiter_name") or "",
            "branch": "",
            "date": p.get("join_date") or "",
            "amount": float(p.get("revenue") or 0),
            "application_id": p["application_id"],
            "bill_id": "",
            "can_record_invoice": False,
            "can_mark_received": False,
            "can_raise_invoice": True,
        })

    if include_bills:
        async for b in db.bills.find({}, {"_id": 0}):
            items.append({
                "key": f"bill:{b['id']}",
                "kind": "bill",
                "placement_id": "",
                "state": STATE_FROM_BILL.get(b.get("status"), "pending"),
                "payment_status": (b.get("status") or "").title(),
                "payment_date": (b.get("paid_at") or "")[:10],
                "reference": b.get("bill_number") or "",
                "client_name": b.get("client_legal_name") or "",
                "candidate_name": ", ".join(
                    li.get("candidate_name") or "" for li in (b.get("line_items") or [])) or "—",
                "recruiter_name": b.get("created_by_email") or "",
                "branch": "",
                "date": (b.get("bill_date") or b.get("created_at") or "")[:10],
                "amount": float((b.get("totals") or {}).get("grand_total") or 0),
                "application_id": "",
                "bill_id": b["id"],
                "can_record_invoice": False,
                "can_mark_received": b.get("status") != "paid",
            })

    if q:
        needle = q.lower()
        items = [i for i in items if needle in " ".join(
            str(i.get(k) or "") for k in
            ("candidate_name", "client_name", "recruiter_name", "reference")).lower()]

    def summary(rows: List[dict]) -> dict:
        return {"count": len(rows), "amount": round(sum(i["amount"] for i in rows), 2)}

    states = {s: summary([i for i in items if i["state"] == s])
              for s in ("to_raise", "pending", "received", "written_off")}

    if state:
        items = [i for i in items if i["state"] == state]
    items.sort(key=lambda i: (i["date"] or "", i["candidate_name"]), reverse=True)

    return {
        "items": items,
        "count": len(items),
        "states": states,
        "totals": summary(items),
        "range": {"from": date_from, "to": date_to},
    }
