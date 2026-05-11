#!/usr/bin/env python3
"""
RunPod auto start/stop scheduler — Phase 54.8

Called by cron on EC2 to start/stop the Qwen14B vLLM pod on a fixed
office-hours schedule. Cuts always-on costs by ~63% (only billed for
~57h/week instead of 168h).

Usage (also wired up as bash helpers `runpod-start`, `runpod-stop`,
`runpod-status`):
    python3 runpod_schedule.py start
    python3 runpod_schedule.py stop
    python3 runpod_schedule.py status

Env requirements (read from backend/.env):
    RUNPOD_ACCOUNT_API_KEY  — RunPod REST API key (rpa_...)
    RUNPOD_POD_ID           — Target pod ID (e.g. v5451fppg9smt1)

Schedule (installed by install_runpod_cron.sh):
    Start: 08:50 IST (03:20 UTC) Mon-Sat
    Stop:  18:30 IST (13:00 UTC) Mon-Sat
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────
RUNPOD_BASE = "https://rest.runpod.io/v1"
LOG_FILE = "/var/log/runpod-schedule.log"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_env() -> dict:
    """Tiny dotenv reader. Avoids the python-dotenv dep so this script
    runs even if the backend venv is broken."""
    env: dict[str, str] = {}
    if not ENV_FILE.exists():
        return env
    with ENV_FILE.open() as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _setup_logging() -> logging.Logger:
    """Single-destination logger.

    - When invoked from cron (stdout is redirected to LOG_FILE via `>> ...`),
      we only need StreamHandler → cron's shell redirection writes to the file.
    - When invoked interactively (stdout is a TTY), we ALSO log to LOG_FILE
      via FileHandler so that ad-hoc `runpod-status` calls still leave an
      audit trail.

    This avoids the previous bug where every line was logged twice when
    running under cron (FileHandler wrote once, cron's redirect wrote again).
    """
    log = logging.getLogger("runpod-schedule")
    log.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    # Always log to stdout (cron captures via shell redirect, terminal shows live)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    log.addHandler(ch)
    # ALSO log to file ONLY when stdout is a TTY (interactive run). Cron
    # invocations have stdout connected to the log file already, so adding
    # a FileHandler here would duplicate every line.
    if sys.stdout.isatty():
        try:
            fh = logging.FileHandler(LOG_FILE)
            fh.setFormatter(formatter)
            log.addHandler(fh)
        except PermissionError:
            pass
    return log


def _api_call(method: str, path: str, api_key: str, log: logging.Logger) -> dict:
    url = f"{RUNPOD_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.request(method, url, headers=headers, timeout=30)
    except requests.RequestException as exc:
        log.error(f"network error calling {method} {path}: {exc}")
        sys.exit(2)
    log.info(f"{method} {path} → HTTP {resp.status_code}")
    if resp.status_code >= 400:
        log.error(f"body: {resp.text[:500]}")
        sys.exit(3)
    try:
        return resp.json()
    except json.JSONDecodeError:
        return {"raw": resp.text}


def cmd_start(pod_id: str, api_key: str, log: logging.Logger) -> None:
    log.info(f"▶  starting pod {pod_id}")
    info = _api_call("GET", f"/pods/{pod_id}", api_key, log)
    status = (info.get("desiredStatus") or info.get("status") or "").upper()
    if status == "RUNNING":
        log.info("pod already RUNNING — nothing to do")
        return
    _api_call("POST", f"/pods/{pod_id}/start", api_key, log)
    # Quick sanity poll — give RunPod 30s to flip the desiredStatus flag
    for i in range(6):
        time.sleep(5)
        info = _api_call("GET", f"/pods/{pod_id}", api_key, log)
        status = (info.get("desiredStatus") or info.get("status") or "").upper()
        if status in ("RUNNING", "INITIALIZING"):
            log.info(f"✅ pod transitioning to RUNNING (current={status})")
            return
    log.warning("pod did not flip to RUNNING within 30s — check RunPod console")


def cmd_stop(pod_id: str, api_key: str, log: logging.Logger) -> None:
    log.info(f"⏹  stopping pod {pod_id}")
    info = _api_call("GET", f"/pods/{pod_id}", api_key, log)
    status = (info.get("desiredStatus") or info.get("status") or "").upper()
    if status in ("EXITED", "STOPPED", "TERMINATED"):
        log.info(f"pod already {status} — nothing to do")
        return
    _api_call("POST", f"/pods/{pod_id}/stop", api_key, log)
    log.info("✅ stop request sent — pod will shut down within ~60s")


def cmd_status(pod_id: str, api_key: str, log: logging.Logger) -> None:
    info = _api_call("GET", f"/pods/{pod_id}", api_key, log)
    log.info("=== pod info ===")
    for key in (
        "id", "name", "desiredStatus", "lastStatusChange",
        "machineId", "gpuCount", "machine",
    ):
        if key in info:
            log.info(f"  {key}: {info[key]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="RunPod start/stop scheduler")
    parser.add_argument("action", choices=["start", "stop", "status"])
    args = parser.parse_args()

    log = _setup_logging()
    env = _load_env()
    api_key = env.get("RUNPOD_ACCOUNT_API_KEY") or os.environ.get("RUNPOD_ACCOUNT_API_KEY")
    pod_id = env.get("RUNPOD_POD_ID") or os.environ.get("RUNPOD_POD_ID")
    if not api_key or not pod_id:
        log.error(
            "missing RUNPOD_ACCOUNT_API_KEY or RUNPOD_POD_ID — "
            "add both to backend/.env"
        )
        sys.exit(1)

    {"start": cmd_start, "stop": cmd_stop, "status": cmd_status}[args.action](
        pod_id, api_key, log
    )


if __name__ == "__main__":
    main()
