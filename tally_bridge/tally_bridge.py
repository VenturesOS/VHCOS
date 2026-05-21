"""VHC ↔ Tally Bridge — Phase 55.8 (Feb 2026).

A standalone Python script that runs on the Windows PC where Tally
Prime / Tally.ERP 9 lives. It bridges the LAN-only Tally to the
internet-facing VHC backend, with **no port forwarding** needed.

Loop, every POLL_INTERVAL_SECONDS:
  1. GET  https://<VHC>/api/tally/queue   → list of bills with pre-built XML
  2. For each bill:
       POST http://127.0.0.1:9000          → Tally XML gateway
       parse response
       POST https://<VHC>/api/tally/ack    → tell VHC the outcome
  3. Sleep, repeat

Idempotency: Tally's REMOTEID dedups re-imports of the same bill. VHC
side keeps `tally.pushed=true` so the bill won't appear in the queue
again unless you manually flip it back to false (e.g. via Mongo).

Running on Windows:
  py -3 tally_bridge.py --config tally_bridge.ini

Install as a service (recommended) — see TALLY_BRIDGE_RUNBOOK.md.

Configuration (tally_bridge.ini):
    [vhc]
    base_url    = https://your-vhc-domain.com
    bridge_token = <copy from server .env>
    poll_seconds = 300

    [tally]
    gateway_url = http://127.0.0.1:9000
    company     = VENTURE HRD CENTRE PVT LTD
    timeout_sec = 30

    [bridge]
    log_path    = C:\\VHCTallyBridge\\bridge.log
    batch_size  = 25
"""
from __future__ import annotations

import argparse
import configparser
import logging
import logging.handlers
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

try:
    import requests
except ImportError:
    print("FATAL: 'requests' missing. Install with: py -3 -m pip install requests", file=sys.stderr)
    sys.exit(1)


# ── Config ────────────────────────────────────────────────────────────
class Config:
    def __init__(self, path: str):
        cp = configparser.ConfigParser()
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found: {path}")
        cp.read(path)
        # VHC
        self.vhc_base = cp.get("vhc", "base_url").rstrip("/")
        self.bridge_token = cp.get("vhc", "bridge_token")
        self.poll_seconds = cp.getint("vhc", "poll_seconds", fallback=300)
        # Tally
        self.tally_gateway = cp.get("tally", "gateway_url", fallback="http://127.0.0.1:9000").rstrip("/")
        self.tally_company = cp.get("tally", "company", fallback="VENTURE HRD CENTRE PVT LTD")
        self.tally_timeout = cp.getint("tally", "timeout_sec", fallback=30)
        # Bridge
        self.log_path = cp.get("bridge", "log_path", fallback="bridge.log")
        self.batch_size = cp.getint("bridge", "batch_size", fallback=25)


# ── Logging ───────────────────────────────────────────────────────────
def setup_logging(path: str) -> logging.Logger:
    log = logging.getLogger("tally_bridge")
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    # rotating file
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    # console
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    log.addHandler(ch)
    return log


# ── VHC client ────────────────────────────────────────────────────────
def vhc_headers(cfg: Config) -> dict:
    return {"X-Tally-Bridge-Token": cfg.bridge_token, "Content-Type": "application/json"}


def fetch_queue(cfg: Config, log: logging.Logger) -> list[dict]:
    url = f"{cfg.vhc_base}/api/tally/queue"
    r = requests.get(
        url,
        headers=vhc_headers(cfg),
        params={"company": cfg.tally_company, "limit": cfg.batch_size},
        timeout=30,
    )
    if r.status_code != 200:
        log.warning("queue fetch failed: HTTP %s — %s", r.status_code, r.text[:200])
        return []
    return r.json() or []


def post_ack(cfg: Config, payload: dict, log: logging.Logger) -> None:
    try:
        r = requests.post(
            f"{cfg.vhc_base}/api/tally/ack",
            headers=vhc_headers(cfg),
            json=payload,
            timeout=20,
        )
        if r.status_code != 200:
            log.warning("ack failed: HTTP %s — %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("ack exception: %s", e)


def heartbeat(cfg: Config, log: logging.Logger) -> None:
    """Optional — lets the VHC dashboard show 'bridge online'."""
    try:
        r = requests.get(
            f"{cfg.vhc_base}/api/tally/status",
            headers=vhc_headers(cfg),
            timeout=15,
        )
        if r.status_code == 200:
            j = r.json()
            log.info("HB | pending=%s pushed_total=%s pushed_today=%s",
                     j.get("pending"), j.get("pushed_total"), j.get("pushed_today"))
    except Exception:
        pass  # silent — heartbeat is best-effort


# ── Tally client ──────────────────────────────────────────────────────
def post_to_tally(cfg: Config, xml: str, log: logging.Logger) -> tuple[bool, str, str | None]:
    """POST a single voucher XML to Tally. Returns (success, raw, vch_id?)."""
    try:
        r = requests.post(
            cfg.tally_gateway,
            data=xml.encode("utf-8"),
            headers={"Content-Type": "text/xml"},
            timeout=cfg.tally_timeout,
        )
    except requests.exceptions.ConnectionError:
        return False, "ConnectionRefused — is Tally running with XML gateway enabled?", None
    except Exception as e:
        return False, f"Tally POST exception: {e}", None
    raw = r.text or ""
    # Quick parse — full parser lives server-side
    success = ("<CREATED>1</CREATED>" in raw) or ("<ALTERED>1</ALTERED>" in raw)
    if not success and "<LINEERROR>" in raw:
        import re
        m = re.search(r"<LINEERROR>(.*?)</LINEERROR>", raw, re.DOTALL)
        if m and m.group(1).strip():
            return False, raw, None
    vch_id = None
    import re as _re
    m = _re.search(r"<LASTVCHID>(.*?)</LASTVCHID>", raw)
    if m:
        vch_id = m.group(1).strip() or None
    return success, raw, vch_id


# ── Main loop ─────────────────────────────────────────────────────────
_running = True


def _stop(_signum, _frame):
    global _running
    _running = False


def run(cfg: Config, log: logging.Logger) -> int:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    log.info("VHC Tally Bridge starting — vhc=%s tally=%s company=%r poll=%ss",
             cfg.vhc_base, cfg.tally_gateway, cfg.tally_company, cfg.poll_seconds)

    heartbeat_every = max(60, cfg.poll_seconds)
    last_hb = 0.0

    while _running:
        loop_start = time.time()
        try:
            queue = fetch_queue(cfg, log)
        except Exception as e:
            log.warning("queue fetch exception: %s", e)
            queue = []

        if queue:
            log.info("Queue: %d bill(s) to push.", len(queue))
            for item in queue:
                if not _running:
                    break
                bill_id = item.get("bill_id")
                bill_no = item.get("bill_number")
                ok, raw, vch_id = post_to_tally(cfg, item.get("xml") or "", log)
                if ok:
                    log.info("✓ %s → Tally voucher created (vch_id=%s)", bill_no, vch_id or "?")
                    err = None
                else:
                    err = _trim_err(raw)
                    log.warning("✗ %s → Tally rejected: %s", bill_no, err)

                post_ack(cfg, {
                    "bill_id": bill_id,
                    "success": ok,
                    "tally_vch_id": vch_id,
                    "error": err,
                    "raw_response": raw[:1500],
                    "pushed_at": datetime.now(timezone.utc).isoformat(),
                }, log)
        else:
            log.debug("Queue empty.")

        # Periodic heartbeat
        if time.time() - last_hb > heartbeat_every:
            heartbeat(cfg, log)
            last_hb = time.time()

        # Sleep until next poll, respecting graceful shutdown
        elapsed = time.time() - loop_start
        sleep_for = max(5.0, cfg.poll_seconds - elapsed)
        end = time.time() + sleep_for
        while _running and time.time() < end:
            time.sleep(1)

    log.info("Bridge stopped.")
    return 0


def _trim_err(raw: str) -> str:
    import re
    m = re.search(r"<LINEERROR>(.*?)</LINEERROR>", raw, re.DOTALL)
    if m:
        return m.group(1).strip()[:500]
    # Fallback: first 200 chars
    return (raw or "no response").strip()[:200]


# ── Entrypoint ────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="tally_bridge.ini")
    parser.add_argument("--once", action="store_true", help="Run one cycle then exit (for testing).")
    args = parser.parse_args()

    cfg = Config(args.config)
    log = setup_logging(cfg.log_path)

    if args.once:
        global _running
        try:
            queue = fetch_queue(cfg, log)
            log.info("One-shot: %d bill(s).", len(queue))
            for item in queue:
                ok, raw, vch_id = post_to_tally(cfg, item.get("xml") or "", log)
                err = None if ok else _trim_err(raw)
                log.info("  %s success=%s vch_id=%s err=%s", item.get("bill_number"), ok, vch_id, err)
                post_ack(cfg, {
                    "bill_id": item.get("bill_id"),
                    "success": ok,
                    "tally_vch_id": vch_id,
                    "error": err,
                    "raw_response": raw[:1500],
                    "pushed_at": datetime.now(timezone.utc).isoformat(),
                }, log)
            heartbeat(cfg, log)
            return 0
        except Exception as e:
            log.error("One-shot failed: %s", e)
            return 1

    return run(cfg, log)


if __name__ == "__main__":
    sys.exit(main())
