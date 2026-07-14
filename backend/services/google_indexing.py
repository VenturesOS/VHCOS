"""
Google Indexing API client — asks Google to (re-)crawl a specific URL.

⚠️ IMPORTANT: Google restricts the Indexing API to URLs backed by
`JobPosting` or `BroadcastEvent` structured data. Every job detail page
at `/jobs/{id}` already ships JobPosting JSON-LD (see
`frontend/src/lib/structuredData.js::jobPostingLD`), so this is the
right tool for pinging job URLs the moment they go live.

Docs: https://developers.google.com/search/apis/indexing-api/v3/quickstart

Setup (one-time):
    1. In Google Cloud Console, create a service account.
    2. Enable the "Indexing API" for that project.
    3. In Search Console → Settings → Users and permissions,
       add the service account's email as an **Owner** of the property.
    4. Download the service-account JSON key. Paste its full contents
       (as a single-line JSON string) into `.env` as:
           GOOGLE_INDEXING_CREDENTIALS_JSON={"type":"service_account",...}
    5. Restart backend.

Public API:
    async ping_url_updated(url: str) -> dict
    async ping_url_deleted(url: str) -> dict
    fire_and_forget_updated(url: str) -> None

All calls are best-effort — network errors, auth errors, and quota errors
are logged and swallowed. Missing credentials → the client silently
skips (returns `{"ok": False, "skipped": True}`).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Optional

import httpx
import jwt  # PyJWT — already in requirements via emergentintegrations chain

logger = logging.getLogger(__name__)

INDEXING_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/indexing"

# Cached access token so we don't do a full OAuth2 round-trip per URL.
_TOKEN_CACHE: dict = {"token": None, "expires_at": 0.0}


def _load_credentials() -> Optional[dict]:
    raw = (os.environ.get("GOOGLE_INDEXING_CREDENTIALS_JSON") or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("GOOGLE_INDEXING_CREDENTIALS_JSON is not valid JSON: %s", exc)
        return None


async def _get_access_token() -> Optional[str]:
    """Exchange the service-account JWT for a short-lived OAuth2 access token."""
    now = time.time()
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expires_at"] > now + 60:
        return _TOKEN_CACHE["token"]

    creds = _load_credentials()
    if not creds:
        return None

    try:
        assertion = jwt.encode(
            {
                "iss":   creds["client_email"],
                "scope": SCOPE,
                "aud":   TOKEN_ENDPOINT,
                "iat":   int(now),
                "exp":   int(now) + 3600,
            },
            creds["private_key"],
            algorithm="RS256",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[GoogleIndexing] failed to sign JWT: %s", exc)
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                TOKEN_ENDPOINT,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion":  assertion,
                },
            )
        if r.status_code != 200:
            logger.warning("[GoogleIndexing] token exchange %d: %s", r.status_code, r.text[:200])
            return None
        data = r.json()
        _TOKEN_CACHE["token"] = data["access_token"]
        _TOKEN_CACHE["expires_at"] = now + int(data.get("expires_in", 3600))
        return _TOKEN_CACHE["token"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("[GoogleIndexing] token exchange failed: %s", exc)
        return None


async def _notify(url: str, notification_type: str) -> dict:
    """Send URL_UPDATED or URL_DELETED to the Indexing API."""
    if not url or not url.startswith(("http://", "https://")):
        return {"ok": False, "skipped": True, "reason": "invalid url"}

    token = await _get_access_token()
    if not token:
        return {"ok": False, "skipped": True, "reason": "credentials missing or invalid"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                INDEXING_ENDPOINT,
                json={"url": url, "type": notification_type},
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code == 200:
            logger.info("[GoogleIndexing] %s %s", notification_type, url)
            return {"ok": True, "url": url, "type": notification_type}
        logger.warning("[GoogleIndexing] %d %s: %s", r.status_code, url, r.text[:200])
        return {"ok": False, "status": r.status_code, "body": r.text[:200]}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[GoogleIndexing] request failed for %s: %s", url, exc)
        return {"ok": False, "error": str(exc)}


async def ping_url_updated(url: str) -> dict:
    """Tell Google that `url` has new/updated content and should be re-crawled."""
    return await _notify(url, "URL_UPDATED")


async def ping_url_deleted(url: str) -> dict:
    """Tell Google that `url` was removed and should be dropped from the index."""
    return await _notify(url, "URL_DELETED")


def fire_and_forget_updated(url: str) -> None:
    """Schedule a URL_UPDATED ping without awaiting. Safe from FastAPI handlers."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(ping_url_updated(url))
