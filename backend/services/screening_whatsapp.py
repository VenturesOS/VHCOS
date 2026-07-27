"""
agent_whatsapp.py — outbound free-form text for Asha sessions
=============================================================

The existing whatsapp_cloud_service is template/digest oriented; Asha
needs free-form session messages (allowed inside the 24-hour customer
service window that opens when the candidate replies). Same env vars:

  WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID,
  WHATSAPP_API_VERSION (default v25.0)

AGENT_DRY_RUN=1 → nothing is sent; messages are logged and returned as
{"dry_run": True} so the whole flow is testable in preview.

Note on the FIRST outbound message: if the candidate has never messaged
this number, Meta requires a template to open the conversation. Register
a utility template (suggested name: asha_screening_intro, one body
variable = the compiled consent text) and set
AGENT_INTRO_TEMPLATE=asha_screening_intro. When unset, the first message
is attempted free-form — fine for candidates who have messaged you
before (e.g., via the Phase-7 job posts), and the API error for others
is surfaced into the task for the recruiter to see.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"


def dry_run() -> bool:
    return os.environ.get("AGENT_DRY_RUN", "1") == "1"


def _cfg() -> Optional[Dict[str, str]]:
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    if not token or not phone_id:
        return None
    version = os.environ.get("WHATSAPP_API_VERSION", "v25.0")
    return {"url": f"{GRAPH_BASE}/{version}/{phone_id}/messages", "token": token}


async def send_text(to_msisdn: str, text: str) -> Dict[str, Any]:
    """to_msisdn: digits with country code, no '+' (e.g. 919876543210)."""
    if dry_run():
        logger.info("[Asha][DRY-RUN] → %s: %s", to_msisdn, text[:200])
        return {"ok": True, "dry_run": True}
    cfg = _cfg()
    if not cfg:
        logger.error("[Asha] WhatsApp env not configured — message not sent")
        return {"ok": False, "error": "whatsapp_not_configured"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_msisdn,
        "type": "text",
        "text": {"preview_url": False, "body": text[:4000]},
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                cfg["url"],
                headers={"Authorization": f"Bearer {cfg['token']}"},
                json=payload,
            )
        if r.status_code >= 300:
            logger.error("[Asha] send failed HTTP %s: %s", r.status_code, r.text[:300])
            return {"ok": False, "error": f"http_{r.status_code}", "detail": r.text[:300]}
        msg_id = ((r.json().get("messages") or [{}])[0]).get("id")
        return {"ok": True, "message_id": msg_id}
    except Exception as e:
        logger.error("[Asha] send exception: %s", e)
        return {"ok": False, "error": "network", "detail": str(e)}


async def send_intro(to_msisdn: str, consent_text: str) -> Dict[str, Any]:
    """First-contact message; uses the intro template when configured."""
    template = os.environ.get("AGENT_INTRO_TEMPLATE")
    if not template:
        return await send_text(to_msisdn, consent_text)
    if dry_run():
        logger.info("[Asha][DRY-RUN] intro template '%s' → %s", template, to_msisdn)
        return {"ok": True, "dry_run": True}
    cfg = _cfg()
    if not cfg:
        return {"ok": False, "error": "whatsapp_not_configured"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_msisdn,
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": os.environ.get("AGENT_INTRO_TEMPLATE_LANG", "en")},
            "components": [{
                "type": "body",
                "parameters": [{"type": "text", "text": consent_text[:1000]}],
            }],
        },
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(cfg["url"], headers={"Authorization": f"Bearer {cfg['token']}"}, json=payload)
        if r.status_code >= 300:
            logger.error("[Asha] intro template failed HTTP %s: %s — trying free-form", r.status_code, r.text[:200])
            return await send_text(to_msisdn, consent_text)
        return {"ok": True}
    except Exception as e:
        logger.error("[Asha] intro exception: %s", e)
        return {"ok": False, "error": "network"}
