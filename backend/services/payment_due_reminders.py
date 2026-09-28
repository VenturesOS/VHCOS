"""Payment-due reminders (step 10 of the sourcing → payment flow).

One mail, on a schedule, with the list of candidates whose invoice is out
but whose money has not landed:

  * Accounts + Admin   → every pending candidate
  * Employer           → only the candidates of the team(s) they run

This is one of the three mail flows the Resend quota is reserved for, so
nothing is sent when there is nothing pending.
"""
import logging
from datetime import datetime, timedelta, timezone

from config import db
from services.email_service import send_email
from services.invoice_worklist import worklist
from services import targets_service as ts

logger = logging.getLogger(__name__)


def _rupees(v: float) -> str:
    return f"₹{float(v or 0):,.0f}"


def _table(rows: list) -> str:
    head = "".join(
        f'<th align="left" style="padding:6px 10px;border-bottom:1px solid #e5e7eb;'
        f'font-size:12px;color:#6b7280;">{h}</th>'
        for h in ("DOJ", "Candidate", "Client", "Recruiter", "Invoice", "Amount")
    )
    body = ""
    for r in rows:
        cells = [r.get("date") or "—", r.get("candidate_name") or "—", r.get("client_name") or "—",
                 r.get("recruiter_name") or "—", r.get("reference") or "—", _rupees(r.get("amount"))]
        body += "<tr>" + "".join(
            f'<td style="padding:6px 10px;border-bottom:1px solid #f3f4f6;font-size:13px;">{c}</td>'
            for c in cells) + "</tr>"
    total = _rupees(sum(float(r.get("amount") or 0) for r in rows))
    return (
        f'<table cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;">'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
        f'<p style="font-size:14px;margin-top:14px;"><strong>Total outstanding: {total}</strong></p>'
    )


def _html(name: str, rows: list, scope_note: str) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:760px;margin:0 auto;padding:24px;">
      <h2 style="color:#111827;margin:0 0 4px;">Payments pending from clients</h2>
      <p style="color:#6b7280;font-size:13px;margin:0 0 18px;">{scope_note}</p>
      <p style="font-size:14px;">Hi {name},</p>
      <p style="font-size:14px;">{len(rows)} invoiced candidate(s) are still awaiting payment.</p>
      {_table(rows)}
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
      <p style="color:#9ca3af;font-size:12px;">Ventures HRD Centre Pvt Ltd · automated payment reminder</p>
    </div>
    """


def _norm(s: str) -> str:
    return " ".join(str(s or "").lower().split())


async def collect_pending() -> list:
    """Every invoiced-but-unpaid row, tracker + platform, last 3 years."""
    today = datetime.now(timezone.utc).date()
    data = await worklist(
        db,
        date_from=(today - timedelta(days=1095)).isoformat(),
        date_to=today.isoformat(),
        state="pending",
    )
    return data["items"]


async def run_payment_due_reminders(dry_run: bool = False) -> dict:
    rows = await collect_pending()
    sent, skipped = [], []

    if not rows:
        logger.info("[PaymentDue] Nothing pending — no mail sent")
        return {"rows": 0, "sent": [], "skipped": []}

    staff = await db.users.find(
        {"role": {"$in": ["admin", "accounts", "employer"]}, "is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1},
    ).to_list(200)

    users_by_id = {}
    async for u in db.users.find({}, {"_id": 0, "id": 1, "name": 1, "email": 1}):
        users_by_id[u["id"]] = u

    for u in staff:
        if not u.get("email"):
            continue
        if u["role"] in ("admin", "accounts"):
            mine, note = rows, "All clients · all teams"
        else:
            teams = await ts.teams_for_employer(db, u["id"])
            member_ids = {mid for t in teams for mid in ts.team_member_ids(t)}
            names = {_norm((users_by_id.get(m) or {}).get("name")) for m in member_ids}
            names |= {_norm((users_by_id.get(m) or {}).get("email")) for m in member_ids}
            names.discard("")
            mine = [r for r in rows
                    if any(_norm(n) in names for n in (r.get("recruiter_name") or "").split(","))]
            note = "Candidates joined through your team"
        if not mine:
            skipped.append(u["email"])
            continue
        if dry_run:
            sent.append({"email": u["email"], "rows": len(mine)})
            continue
        res = await send_email(
            category="payment_due",
            recipient_email=u["email"],
            subject=f"Payment pending — {len(mine)} candidate(s) awaiting client payment",
            html_content=_html(u.get("name") or u["email"], mine, note),
        )
        (sent if res.get("status") == "sent" else skipped).append(u["email"])

    logger.warning("[PaymentDue] rows=%s sent=%s skipped=%s", len(rows), len(sent), len(skipped))
    return {"rows": len(rows), "sent": sent, "skipped": skipped, "dry_run": dry_run}
