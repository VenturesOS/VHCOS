"""
screening_email.py — email fallback for stalled/unreachable candidates
======================================================================
One nudge email carrying the tokenized web-form link. Uses the
platform's email_service defensively (send function names vary), and
logs-only in AGENT_DRY_RUN. AGENT_EMAIL_FALLBACK=1 enables the sweep.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return os.environ.get("AGENT_EMAIL_FALLBACK", "0") == "1"


async def _send(to: str, subject: str, body_html: str) -> bool:
    if os.environ.get("AGENT_DRY_RUN", "1") == "1":
        logger.info("[AshaEmail][DRY-RUN] → %s: %s", to, subject)
        return True
    try:
        from services import email_service  # platform module
        for fname in ("send_email", "send", "send_mail", "send_html_email"):
            fn = getattr(email_service, fname, None)
            if fn:
                res = fn(to=to, subject=subject, html=body_html) if not callable(getattr(fn, "__await__", None)) else await fn(to=to, subject=subject, html=body_html)
                if hasattr(res, "__await__"):
                    res = await res
                return bool(res) if res is not None else True
        logger.error("[AshaEmail] no known send function in email_service")
        return False
    except Exception as e:
        logger.error("[AshaEmail] send failed: %s", e)
        return False


async def send_stall_nudge(candidate: dict, session: dict) -> bool:
    email = (candidate.get("email") or "").strip()
    if not email:
        return False
    from services.screening_forms import form_url
    link = form_url(session["id"])
    title = session.get("mandate_title") or "a role"
    name = (candidate.get("name") or "").split(" ")[0] or "there"
    subject = f"Quick questions for {title} — Ventures HRD Centre"
    body = f"""<div style="font-family:system-ui,sans-serif;max-width:540px">
<p>Hi {name},</p>
<p>We reached out on WhatsApp about <b>{title}</b> but may have caught you at a
busy time. You can finish the 2-minute screening here instead:</p>
<p><a href="{link}" style="background:#0F2A4A;color:#fff;padding:12px 20px;
border-radius:8px;text-decoration:none;display:inline-block">Answer the questions</a></p>
<p>Or simply reply on WhatsApp anytime. — Asha, Ventures HRD Centre<br>
<span style="color:#888;font-size:12px">Asha is an AI assistant. Reply STOP on
WhatsApp to opt out of these messages.</span></p></div>"""
    return await _send(email, subject, body)
