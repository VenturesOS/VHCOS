"""Daily bill-reminder runner — Phase 55.6.

Scans `bills` collection for bills that are:
  - status = 'sent'
  - reminders_enabled = true
  - sent_at older than next-due offset in `reminder_schedule_days`

For each match, generates an LLM reminder body via Qwen, mails the CC
parties (NOT the client), and records the reminder in `reminders_sent`.

Idempotent — each (bill_id, day_offset) pair only fires once.

Schedule (cron / systemd timer): once daily, ~09:30 IST is recommended.
    OnCalendar=Mon..Sun 04:00 UTC  (== 09:30 IST)

Usage:
    cd /home/ubuntu/vhc-platform/backend && source venv/bin/activate
    python scripts/run_bill_reminders.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone


def _bootstrap() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    backend_root = os.path.dirname(here)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)


_bootstrap()

from config import db, initialize_db  # noqa: E402
from services.bill_llm_body import generate_reminder_body, plain_to_html  # noqa: E402
from services.bill_mailer import build_cc_list, send_bill_email  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bill_reminders")


async def _due_reminder(bill: dict, now: datetime) -> int:
    if not bill.get("reminders_enabled", True):
        return 0
    if bill.get("status") != "sent":
        return 0
    sent_at_s = bill.get("sent_at")
    if not sent_at_s:
        return 0
    try:
        sent_at = datetime.fromisoformat(sent_at_s.replace("Z", "+00:00"))
    except Exception:
        return 0
    days = (now - sent_at).days
    schedule = bill.get("reminder_schedule_days") or [7, 14, 30]
    already_sent_for = {r["day_offset"] for r in (bill.get("reminders_sent") or [])}
    # Pick the LARGEST schedule day that is <= days and not yet sent
    eligible = [d for d in schedule if d <= days and d not in already_sent_for]
    return max(eligible) if eligible else 0


async def _send_one(bill: dict, day_offset: int, dry_run: bool) -> bool:
    n = len(bill.get("reminders_sent") or []) + 1
    plain = await generate_reminder_body(bill, n, day_offset)
    html = plain_to_html(plain)

    # Find employer email
    employer_email = None
    cid = bill.get("client_company_id")
    if cid:
        company = await db.companies.find_one({"id": cid}, {"_id": 0, "assigned_employer_id": 1})
        if company and company.get("assigned_employer_id"):
            emp = await db.users.find_one(
                {"id": company["assigned_employer_id"], "role": "employer"}, {"_id": 0, "email": 1}
            )
            if emp:
                employer_email = emp.get("email")
    cc_list = build_cc_list(employer_email)
    if not cc_list:
        logger.warning("[%s] no CC list — skipping reminder", bill.get("bill_number"))
        return False

    subject = (
        f"Reminder #{n} — Unpaid invoice {bill.get('bill_number')} "
        f"({day_offset} days)"
    )
    logger.info(
        "[%s] Reminder #%d (D+%d) → cc=%s subject=%s%s",
        bill.get("bill_number"), n, day_offset, cc_list, subject,
        " [DRY-RUN]" if dry_run else "",
    )

    if dry_run:
        return True

    res = await send_bill_email(
        to_email=cc_list[0],         # accounts mailbox is the primary TO
        cc_emails=cc_list[1:],       # everyone else on CC
        subject=subject,
        html_body=html,
        plain_body=plain,
        tags=[
            {"name": "kind", "value": "bill_reminder"},
            {"name": "bill_id", "value": bill["id"]},
            {"name": "n", "value": str(n)},
        ],
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "n": n,
        "day_offset": day_offset,
        "subject": subject,
        "to": cc_list[0],
        "cc": cc_list[1:],
        "success": res.get("success"),
        "message_id": res.get("id"),
        "error": res.get("error"),
        "at": now_iso,
        "by": "bill-reminder-cron",
    }
    await db.bills.update_one(
        {"id": bill["id"]},
        {
            "$push": {"reminders_sent": record, "mail_events": {**record, "kind": "reminder"}},
            "$set": {"updated_at": now_iso},
        },
    )
    return bool(res.get("success"))


async def main(dry_run: bool) -> int:
    initialize_db()
    now = datetime.now(timezone.utc)
    logger.info("Bill reminders scan — now=%s dry_run=%s", now.isoformat(), dry_run)

    matched = 0
    sent = 0
    cursor = db.bills.find(
        {"status": "sent", "reminders_enabled": True},
        {"_id": 0},
    )
    async for bill in cursor:
        offset = await _due_reminder(bill, now)
        if not offset:
            continue
        matched += 1
        ok = await _send_one(bill, offset, dry_run)
        if ok:
            sent += 1

    logger.info("Scan done — matched=%d sent=%d", matched, sent)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    sys.exit(asyncio.run(main(args.dry_run)))
