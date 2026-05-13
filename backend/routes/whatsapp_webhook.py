"""
WhatsApp webhook receiver — Meta posts delivery status here.

Two endpoints:
  GET  /api/webhooks/whatsapp   — Meta verification handshake
  POST /api/webhooks/whatsapp   — delivery + read receipts

Both are intentionally UNAUTHENTICATED (Meta cannot send a JWT). Meta
authenticates via the `hub.verify_token` echo on subscription and the
optional `X-Hub-Signature-256` HMAC on each callback (verified when
WHATSAPP_APP_SECRET is set).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from config import db
from services.whatsapp_cloud_service import update_status_from_webhook

logger = logging.getLogger(__name__)
webhook_router = APIRouter(prefix="/api/webhooks", tags=["WhatsApp Webhooks"])


@webhook_router.get("/whatsapp")
async def verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    expected = (os.environ.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN") or "").strip()

    if mode == "subscribe" and expected and token == expected:
        logger.info("[WA Webhook] Verification OK")
        try:
            return int(challenge) if challenge is not None else "ok"
        except (TypeError, ValueError):
            return challenge or "ok"
    logger.warning(f"[WA Webhook] Verification rejected (mode={mode})")
    raise HTTPException(status_code=403, detail="Verification failed")


def _signature_ok(raw_body: bytes, header_sig: str) -> bool:
    secret = (os.environ.get("WHATSAPP_APP_SECRET") or "").strip()
    if not secret:
        # No secret configured → skip HMAC check (Meta still requires the
        # verify-token on subscription, so this is acceptable for now).
        return True
    if not header_sig or not header_sig.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_sig)


@webhook_router.post("/whatsapp")
async def receive(request: Request) -> Dict[str, Any]:
    raw = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not _signature_ok(raw, sig):
        logger.warning("[WA Webhook] Bad signature — payload dropped")
        raise HTTPException(status_code=401, detail="Bad signature")

    try:
        payload = await request.json()
    except Exception:
        logger.warning("[WA Webhook] Non-JSON payload — ignored")
        return {"status": "ignored"}

    updates = 0
    for entry in (payload.get("entry") or []):
        for change in (entry.get("changes") or []):
            value = change.get("value") or {}
            statuses = value.get("statuses") or []
            if statuses:
                updates += await update_status_from_webhook(db, statuses)
    return {"status": "ok", "updates": updates}
