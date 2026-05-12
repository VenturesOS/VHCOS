"""
RunPod BGE Sidecar Keeper — Feb 2026.

Runs on EC2 via cron every ~5 min. Idempotent + safe to over-run.

What it does
------------
1. Curl the BGE sidecar's /health via the RunPod HTTP proxy.
   If 200 → exit 0 silently. (99 % of the time.)
2. If not reachable AND the pod is running, query RunPod GraphQL for the
   pod's current direct-TCP SSH endpoint (IP + public port → :22).
3. SSH in with /home/ubuntu/.ssh/runpod_bge and run the start command.
4. If pod is stopped (off-hours per the nightly cron), exit 0 silently —
   nothing to do.

Why this design
---------------
- No pod template edit needed → zero pod resets.
- Survives pod migrations: pod ID + SSH IP/port resolved at runtime via
  the RunPod API. Just keep `BGE_POD_ID` and the SSH key in place.
- Survives the daily auto-stop/start: dormant during off-hours, restarts
  the sidecar shortly after the pod boots in the morning.

Required env vars (read from /home/ubuntu/vhc-platform/backend/.env)
--------------------------------------------------------------------
RUNPOD_API_KEY       — existing key, R/W scope already in use
BGE_POD_ID           — defaults to t41o9p01whlrfe if not set
BGE_SIDECAR_URL      — used only for health probe (already in .env)
BGE_SSH_KEY_PATH     — optional; defaults to /home/ubuntu/.ssh/runpod_bge

Exit codes
----------
0  — sidecar is healthy (or pod stopped — nothing to do)
1  — could not query RunPod API (likely creds problem)
2  — could not SSH to the pod
3  — sidecar refused to start (start command errored)
"""
from __future__ import annotations

import os
import sys
import subprocess
import time
from pathlib import Path
from typing import Optional

import httpx

ENV_PATH = Path("/home/ubuntu/vhc-platform/backend/.env")
DEFAULT_POD_ID = "t41o9p01whlrfe"
RUNPOD_API_URL = "https://api.runpod.io/graphql"
HEALTH_TIMEOUT = 6.0
SSH_TIMEOUT = 25


def _load_env() -> dict:
    """Cheap .env reader — avoids dotenv dep on the cron path."""
    out = {}
    if not ENV_PATH.exists():
        return out
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _sidecar_url(env: dict) -> str:
    pod_id = env.get("BGE_POD_ID") or DEFAULT_POD_ID
    return env.get("BGE_SIDECAR_URL") or f"https://{pod_id}-8001.proxy.runpod.net"


def _health_ok(url: str) -> bool:
    try:
        r = httpx.get(f"{url.rstrip('/')}/health", timeout=HEALTH_TIMEOUT)
        if r.status_code != 200:
            return False
        body = r.json()
        return bool(body.get("ok") and body.get("model_loaded"))
    except Exception:
        return False


def _query_pod(api_key: str, pod_id: str) -> Optional[dict]:
    """Return the pod record we care about, or None."""
    query = """
    query { myself { pods { id name desiredStatus
      runtime { ports { ip isIpPublic privatePort publicPort type } } } } }
    """
    try:
        r = httpx.post(
            RUNPOD_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"query": query},
            timeout=10.0,
        )
        if r.status_code != 200:
            print(f"[Keeper] RunPod API HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
            return None
        pods = (r.json().get("data") or {}).get("myself", {}).get("pods") or []
        for p in pods:
            if p.get("id") == pod_id:
                return p
        print(f"[Keeper] Pod {pod_id} not found in account", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[Keeper] RunPod API error: {e}", file=sys.stderr)
        return None


def _ssh_endpoint(pod: dict) -> Optional[tuple[str, int]]:
    """Pull SSH (privatePort=22, public, type=tcp) IP+port from pod runtime."""
    rt = pod.get("runtime") or {}
    for p in (rt.get("ports") or []):
        if (
            p.get("privatePort") == 22
            and p.get("isIpPublic")
            and (p.get("type") or "").lower() == "tcp"
        ):
            ip = p.get("ip")
            pub = p.get("publicPort")
            if ip and pub:
                return ip, int(pub)
    return None


START_CMD = (
    "set -e; "
    "if curl -sf -o /dev/null --max-time 4 http://localhost:8001/health; then "
    "  echo 'already-up'; exit 0; "
    "fi; "
    "test -f /workspace/bge_sidecar/embed_service.py "
    "  || (echo 'sidecar files missing'; exit 7); "
    "cd /workspace/bge_sidecar && "
    "nohup uvicorn embed_service:app --host 0.0.0.0 --port 8001 "
    "  --app-dir /workspace/bge_sidecar > /workspace/bge_sidecar/bge.log 2>&1 & "
    "disown; sleep 1; echo 'started'"
)


def _ssh_run(ip: str, port: int, key_path: str, remote_cmd: str) -> tuple[int, str]:
    cmd = [
        "ssh",
        "-i", key_path,
        "-p", str(port),
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10",
        "-o", "BatchMode=yes",
        f"root@{ip}",
        remote_cmd,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=SSH_TIMEOUT)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "ssh timed out"
    except Exception as e:
        return 125, str(e)


def main() -> int:
    env = _load_env()
    url = _sidecar_url(env)

    if _health_ok(url):
        return 0  # silent OK

    api_key = env.get("RUNPOD_API_KEY") or os.environ.get("RUNPOD_API_KEY")
    if not api_key:
        print("[Keeper] RUNPOD_API_KEY missing", file=sys.stderr)
        return 1

    pod_id = env.get("BGE_POD_ID") or DEFAULT_POD_ID
    pod = _query_pod(api_key, pod_id)
    if not pod:
        return 1

    if (pod.get("desiredStatus") or "").upper() != "RUNNING":
        # Off-hours per nightly cron — nothing to do.
        return 0

    endpoint = _ssh_endpoint(pod)
    if not endpoint:
        print("[Keeper] No public SSH endpoint on pod yet (still booting?)", file=sys.stderr)
        return 2

    ip, port = endpoint
    key_path = env.get("BGE_SSH_KEY_PATH") or "/home/ubuntu/.ssh/runpod_bge"

    rc, out = _ssh_run(ip, port, key_path, START_CMD)
    if rc != 0:
        print(f"[Keeper] SSH/start failed rc={rc} out={out}", file=sys.stderr)
        return 3

    # Wait briefly for the sidecar to warm up before re-probing.
    for _ in range(8):
        time.sleep(3)
        if _health_ok(url):
            print(f"[Keeper] Sidecar started ({out}) — healthy after retry")
            return 0
    print(f"[Keeper] Sidecar started but /health not yet 200 — out={out}", file=sys.stderr)
    return 0  # don't error: the warmup may finish on the next cron tick


if __name__ == "__main__":
    sys.exit(main())
