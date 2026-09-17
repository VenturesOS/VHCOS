"""Resend mailer wrapper for bills + reminders — Phase 55.6.

Uses Resend's transactional API.  Sync SDK called via `asyncio.to_thread`
so the FastAPI loop stays non-blocking.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import List, Optional

import resend

logger = logging.getLogger(__name__)

# Resend SDK reads the key from this module-level attribute
resend.api_key = os.environ.get("RESEND_API_KEY") or ""

# Mail config — user-confirmed 2026-09-17: invoices go OUT from
# accounts@vhc.in, reply-to the same box, and accounts@ is always BCC'd.
SENDER_EMAIL = (
    os.environ.get("BILLING_SENDER_EMAIL")
    or os.environ.get("SENDER_EMAIL")
    or "accounts@vhc.in"
)
SENDER_NAME = os.environ.get("BILLING_SENDER_NAME") or "Venture HRD Center"
ACCOUNTS_EMAIL = os.environ.get("BILLING_ACCOUNTS_EMAIL") or "accounts@vhc.in"
REPLY_TO = os.environ.get("BILLING_REPLY_TO") or ACCOUNTS_EMAIL

# Always BCC the accounts mailbox so every invoice lands in that inbox.
LOCKED_BCC = [ACCOUNTS_EMAIL] if ACCOUNTS_EMAIL else []
LOCKED_CC: List[str] = []
DEFAULT_DYNAMIC_CC = [e for e in [
    os.environ.get("BILLING_DEFAULT_CC_1") or "bsy@vhc.in",
    os.environ.get("BILLING_DEFAULT_CC_2") or "rohit@vhc.in",
] if e]


def build_cc_list(employer_email: Optional[str], extra_cc: Optional[List[str]] = None) -> List[str]:
    """Build the canonical CC list for a bill send.

    Order: accounts (locked) → employer (if known) → bsy → rohit → admin extras.
    De-duped + lowercased.
    """
    out: List[str] = []
    seen = set()
    for e in LOCKED_CC + ([employer_email] if employer_email else []) + DEFAULT_DYNAMIC_CC + list(extra_cc or []):
        if not e:
            continue
        ek = e.strip().lower()
        if not ek or ek in seen:
            continue
        seen.add(ek)
        out.append(ek)
    return out


async def send_bill_email(
    *,
    to_email: str,
    cc_emails: List[str],
    subject: str,
    html_body: str,
    plain_body: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
    pdf_filename: str = "invoice.pdf",
    bcc_emails: Optional[List[str]] = None,
    tags: Optional[List[dict]] = None,
) -> dict:
    """Send a bill (or reminder) email via Resend.

    Returns a dict with `success`, `id`, `error` keys. Never raises — always
    returns a structured result so the caller can append to mail_events.
    """
    if not resend.api_key:
        return {"success": False, "error": "RESEND_API_KEY not configured"}

    params: dict = {
        "from": f"{SENDER_NAME} <{SENDER_EMAIL}>",
        "to": [to_email],
        "cc": list(cc_emails or []),
        "subject": subject,
        "html": html_body,
        "reply_to": REPLY_TO,
    }
    if plain_body:
        params["text"] = plain_body
    bcc = list(dict.fromkeys([*(bcc_emails or []), *LOCKED_BCC]))
    if bcc:
        params["bcc"] = bcc
    if pdf_bytes:
        params["attachments"] = [{
            "filename": pdf_filename,
            "content": base64.b64encode(pdf_bytes).decode("ascii"),
        }]
    if tags:
        params["tags"] = tags

    try:
        resp = await asyncio.to_thread(resend.Emails.send, params)
        mid = resp.get("id") if isinstance(resp, dict) else None
        logger.info("[Bill mailer] sent to=%s cc=%d id=%s", to_email, len(cc_emails or []), mid)
        return {"success": True, "id": mid, "raw": resp}
    except Exception as exc:
        logger.warning("[Bill mailer] send failed: %s", exc)
        return {"success": False, "error": str(exc)}
