"""
RunPod Auto-URL Sync Daemon + Health Probe.

Responsibilities:
1. Poll the RunPod GraphQL API every N seconds and find the currently-running pod
2. Auto-update `.env` with the current pod URL + derive the API key (sk-<pod_id>)
3. Hot-reload the LLM service module so the new URL/key take effect without a gunicorn restart
4. Expose a snapshot of health + current URL for admin dashboards

No gunicorn restart is needed — we mutate `llm_fallback_service` in-place.

Requires:
- RUNPOD_API_KEY in .env (read-only scope is enough)
- pod has port 8000 exposed for vLLM
"""
import os
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

RUNPOD_API_URL = "https://api.runpod.io/graphql"
POLL_INTERVAL_SECONDS = int(os.environ.get("RUNPOD_SYNC_INTERVAL", "120"))  # 2 min default
HEALTH_CACHE_SECONDS = 60

# In-memory snapshot (read by /api/admin/runpod/health endpoint)
_snapshot = {
    "runpod_url": None,
    "pod_id": None,
    "pod_name": None,
    "pod_status": None,
    "pod_machine_gpu": None,
    "vllm_reachable": False,
    "vllm_model": None,
    "last_sync_at": None,
    "last_error": None,
    "auto_sync_enabled": False,
}


# Consecutive auth (401/403) failures — after _AUTH_BACKOFF_AFTER the
# sync loop slows to hourly polls instead of spamming a dead key every
# 2 minutes. Resets on the first successful API response.
_AUTH_BACKOFF_AFTER = 3
_AUTH_BACKOFF_SECONDS = 3600
_auth_failures = 0


def get_snapshot() -> dict:
    return {**_snapshot}


async def _query_runpod_pods(api_key: str) -> list:
    """Fetch all pods for the account. Returns [] on failure."""
    global _auth_failures
    query = """
    query { myself { pods { id name desiredStatus
      machine { podHostId gpuDisplayName }
      runtime { ports { ip isIpPublic privatePort publicPort type } } } } }
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.post(
                RUNPOD_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"query": query},
            )
            if r.status_code in (401, 403):
                _auth_failures += 1
                if _auth_failures <= _AUTH_BACKOFF_AFTER:
                    logger.warning(f"[RunPodSync] API HTTP {r.status_code} (auth failure #{_auth_failures}): {r.text[:200]}")
                return []
            if r.status_code != 200:
                logger.warning(f"[RunPodSync] API HTTP {r.status_code}: {r.text[:200]}")
                return []
            _auth_failures = 0
            data = r.json()
            return (data.get("data") or {}).get("myself", {}).get("pods", []) or []
        except Exception as e:
            logger.warning(f"[RunPodSync] API query failed: {e}")
            return []


def _extract_public_url(pod: dict, target_port: int = 8000) -> Optional[str]:
    """Given a pod record, return https://<pod_id>-<port>.proxy.runpod.net if port is exposed."""
    pod_id = pod.get("id")
    if not pod_id:
        return None
    rt = pod.get("runtime") or {}
    ports = rt.get("ports") or []
    for p in ports:
        if p.get("privatePort") == target_port and p.get("isIpPublic") and p.get("type") == "http":
            return f"https://{pod_id}-{target_port}.proxy.runpod.net"
    # Fall back: if runtime is populated at all, assume the standard URL shape works
    if rt:
        return f"https://{pod_id}-{target_port}.proxy.runpod.net"
    return None


async def _probe_vllm(url: str, api_key: str, timeout: float = 5.0) -> tuple[bool, Optional[str]]:
    """Probe /v1/models — returns (reachable, first_model_id)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(f"{url.rstrip('/')}/v1/models", headers={"Authorization": f"Bearer {api_key}"})
            if r.status_code == 200:
                data = r.json().get("data") or []
                return True, (data[0].get("id") if data else None)
    except Exception as e:
        logger.debug(f"[RunPodSync] vLLM probe failed: {e}")
    return False, None


def _write_env(key: str, value: str, env_path: Path) -> bool:
    """Update a key in .env in place. Returns True if file changed."""
    if not env_path.exists():
        return False
    try:
        lines = env_path.read_text().splitlines()
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                if line == f"{key}={value}":
                    return False  # Already correct
                lines[i] = f"{key}={value}"
                found = True
                break
        if not found:
            lines.append(f"{key}={value}")
        env_path.write_text("\n".join(lines) + "\n")
        return True
    except Exception as e:
        logger.warning(f"[RunPodSync] .env write failed: {e}")
        return False


def _hot_reload_llm_service(new_url: str, new_key: str):
    """Mutate the already-imported llm_fallback_service module so the new URL/key
    take effect without a gunicorn restart. Safe to call on any cycle."""
    try:
        from services import llm_fallback_service as llm
        old_url = getattr(llm, "RUNPOD_VLLM_URL", None)
        llm.RUNPOD_VLLM_URL = new_url
        llm.RUNPOD_API_KEY = new_key
        os.environ["RUNPOD_VLLM_URL"] = new_url
        # Only set the vLLM Bearer key if derivation succeeded
        if new_key:
            os.environ["RUNPOD_API_KEY"] = new_key
        logger.info(f"[RunPodSync] Hot-reloaded LLM service: {old_url} → {new_url}")
    except Exception as e:
        logger.error(f"[RunPodSync] Hot-reload failed: {e}")


async def _one_sync_cycle(api_key: str, env_path: Path) -> dict:
    """One poll + reconcile. Updates _snapshot and .env. Returns the snapshot."""
    now = datetime.now(timezone.utc).isoformat()

    pods = await _query_runpod_pods(api_key)
    if not pods:
        _snapshot.update({"last_sync_at": now, "last_error": "No pods found in account", "vllm_reachable": False})
        return _snapshot

    # Prioritize RUNNING pods, then try STOPPED (in case user just started one)
    running = [p for p in pods if (p.get("desiredStatus") or "").upper() == "RUNNING"]
    candidates = running or pods

    # ── Probe EVERY candidate pod — pick the first one actually serving vLLM ──
    # Multi-pod accounts are common (old + new + experiments); the only
    # reliable way to pick "the right one" is to check which one answers.
    reachable_pod = None
    reachable_url = None
    reachable_model = None
    for pod in candidates:
        url = _extract_public_url(pod, 8000)
        pod_id = pod.get("id")
        if not url or not pod_id:
            continue
        derived = f"sk-{pod_id}"
        ok, model_id = await _probe_vllm(url, derived, timeout=5.0)
        if ok:
            reachable_pod = pod
            reachable_url = url
            reachable_model = model_id
            break

    # Fallback: if NONE reachable, at least report what RunPod says is RUNNING
    if not reachable_pod:
        pod = running[0] if running else pods[0]
        url = _extract_public_url(pod, 8000)
        pod_id = pod.get("id")
        _snapshot.update({
            "runpod_url": url,
            "pod_id": pod_id,
            "pod_name": pod.get("name"),
            "pod_status": pod.get("desiredStatus"),
            "pod_machine_gpu": (pod.get("machine") or {}).get("gpuDisplayName"),
            "vllm_reachable": False,
            "vllm_model": None,
            "last_sync_at": now,
            "last_error": f"No pod serving vLLM on :8000 (probed {len(candidates)} pod(s))",
        })
        return _snapshot

    pod_id = reachable_pod.get("id")
    derived_key = f"sk-{pod_id}"
    _snapshot.update({
        "runpod_url": reachable_url,
        "pod_id": pod_id,
        "pod_name": reachable_pod.get("name"),
        "pod_status": reachable_pod.get("desiredStatus"),
        "pod_machine_gpu": (reachable_pod.get("machine") or {}).get("gpuDisplayName"),
        "vllm_reachable": True,
        "vllm_model": reachable_model,
        "last_sync_at": now,
        "last_error": None,
    })

    url_changed = _write_env("RUNPOD_VLLM_URL", reachable_url, env_path)
    if url_changed:
        logger.info(f"[RunPodSync] .env RUNPOD_VLLM_URL updated to {reachable_url}")
    # Hot-reload the LLM service module so new URL/key apply without a gunicorn restart
    try:
        from services import llm_fallback_service as _llm
        if getattr(_llm, "RUNPOD_VLLM_URL", None) != reachable_url:
            _hot_reload_llm_service(reachable_url, derived_key)
    except Exception:
        _hot_reload_llm_service(reachable_url, derived_key)

    return _snapshot


async def runpod_sync_loop():
    """Background task — polls RunPod API every POLL_INTERVAL_SECONDS."""
    # Use a DEDICATED env var for the RunPod account API key to avoid colliding
    # with RUNPOD_API_KEY which the LLM service uses as the vLLM Bearer token.
    api_key = os.environ.get("RUNPOD_ACCOUNT_API_KEY") or os.environ.get("RUNPOD_GRAPHQL_API_KEY")
    if not api_key:
        logger.info("[RunPodSync] RUNPOD_ACCOUNT_API_KEY not set — auto-sync daemon DISABLED")
        _snapshot["auto_sync_enabled"] = False
        return
    _snapshot["auto_sync_enabled"] = True
    env_path = Path(__file__).parent.parent / ".env"
    logger.info(f"[RunPodSync] Auto-sync daemon STARTED (interval={POLL_INTERVAL_SECONDS}s, env={env_path})")
    while True:
        try:
            await _one_sync_cycle(api_key, env_path)
        except Exception as e:
            logger.error(f"[RunPodSync] Cycle failed: {e}")
            _snapshot["last_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        if _auth_failures >= _AUTH_BACKOFF_AFTER:
            if _auth_failures == _AUTH_BACKOFF_AFTER:
                logger.warning(
                    "[RunPodSync] %d consecutive auth failures — API key is invalid/rotated. "
                    "Backing off to hourly polls. Update RUNPOD_ACCOUNT_API_KEY in .env to restore.",
                    _auth_failures,
                )
            _snapshot["last_error"] = "API key invalid (401) — polling hourly until key is rotated"
            await asyncio.sleep(_AUTH_BACKOFF_SECONDS)
        else:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def manual_sync_now() -> dict:
    """Force an immediate sync cycle (called by admin endpoint)."""
    api_key = os.environ.get("RUNPOD_ACCOUNT_API_KEY") or os.environ.get("RUNPOD_GRAPHQL_API_KEY")
    if not api_key:
        return {"error": "RUNPOD_ACCOUNT_API_KEY not set in .env"}
    env_path = Path(__file__).parent.parent / ".env"
    return await _one_sync_cycle(api_key, env_path)
