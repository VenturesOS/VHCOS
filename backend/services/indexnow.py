"""
indexnow.py — IndexNow protocol pinger for search-engine URL updates.

IndexNow is a lightweight protocol supported by Bing, Yandex, Seznam, Naver
and (via Bing) all other engines that syndicate from Bing. It tells search
engines within seconds that a URL has appeared or been updated, so they can
crawl it right away instead of waiting for the next scheduled sweep.

Setup (one-time, on the web server):
  1. Pick a strong random key (e.g. `uuid.uuid4().hex`). Set it in the
     backend `.env`:
         INDEXNOW_KEY=<32-hex-chars>
     Optionally override the site host (defaults to ventureshrd.com):
         INDEXNOW_HOST=ventureshrd.com
  2. Publish the key at `https://<host>/<key>.txt` — the file must contain
     ONLY the key. Nginx one-liner:
         location = /<key>.txt { return 200 "<key>"; add_header Content-Type text/plain; }
     Alternatively drop the file into your static docroot.
  3. Fire-and-forget: `await ping_indexnow([url1, url2, ...])` from any
     publish handler. Never raises — failures are logged and swallowed so
     they cannot block the publish flow.

Docs: https://www.indexnow.org/documentation
"""
from __future__ import annotations
import asyncio
import logging
import os
from typing import Iterable, List

import httpx

logger = logging.getLogger(__name__)

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
DEFAULT_HOST = "ventureshrd.com"


def _config() -> tuple[str | None, str, str]:
    """Returns (key, host, key_location) or (None, ...) if disabled."""
    key = os.environ.get("INDEXNOW_KEY", "").strip()
    host = os.environ.get("INDEXNOW_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    key_location = f"https://{host}/{key}.txt" if key else ""
    return (key or None), host, key_location


async def ping_indexnow(urls: Iterable[str]) -> bool:
    """
    Notify IndexNow that the given URLs need re-crawl. Returns True on
    HTTP 200/202, False otherwise (including "disabled" — missing key).
    Never raises.

    Batch limit per IndexNow spec: 10,000 URLs per request. We cap at
    100 here because publish handlers only ever ping a handful, and a
    smaller batch means a smaller failure blast radius.
    """
    key, host, key_location = _config()
    if not key:
        return False

    url_list: List[str] = [u for u in urls if u and u.startswith(("http://", "https://"))][:100]
    if not url_list:
        return False

    payload = {
        "host": host,
        "key": key,
        "keyLocation": key_location,
        "urlList": url_list,
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(INDEXNOW_ENDPOINT, json=payload)
        ok = resp.status_code in (200, 202)
        if ok:
            logger.info("[IndexNow] ok %d urls host=%s status=%d", len(url_list), host, resp.status_code)
        else:
            logger.warning("[IndexNow] non-ok status=%d body=%s", resp.status_code, resp.text[:200])
        return ok
    except Exception as e:
        logger.warning("[IndexNow] ping failed: %s", e)
        return False


async def submit_batch(urls: Iterable[str], chunk_size: int = 100) -> dict:
    """Submit a large URL list in chunks. Aggregates per-batch results so a
    caller (admin endpoint / one-off script) can report totals.

    Never raises — failures inside each batch are absorbed and counted.
    """
    unique: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if not u:
            continue
        u = u.strip()
        if u.startswith(("http://", "https://")) and u not in seen:
            seen.add(u)
            unique.append(u)

    if not unique:
        return {"ok": True, "submitted": 0, "total": 0, "batches": 0}

    key, host, _ = _config()
    if not key:
        return {"ok": False, "skipped": True, "reason": "INDEXNOW_KEY not set", "total": len(unique)}

    submitted = 0
    batches = 0
    failures: list[str] = []
    for i in range(0, len(unique), chunk_size):
        chunk = unique[i : i + chunk_size]
        batches += 1
        ok = await ping_indexnow(chunk)
        if ok:
            submitted += len(chunk)
        else:
            failures.append(f"batch {batches} (starting {chunk[0]!r})")

    return {
        "ok": submitted == len(unique),
        "submitted": submitted,
        "total": len(unique),
        "batches": batches,
        "host": host,
        "failures": failures,
    }


def fire_and_forget(urls: Iterable[str]) -> None:
    """Schedule a ping without awaiting. Safe to call from sync context
    within a running event loop (e.g. FastAPI handlers). If no loop is
    running (test/CLI), silently no-ops rather than crashing."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(ping_indexnow(list(urls)))
