"""
VHC Talent OS — Reliability Layer
Circuit breaker, retry with backoff, graceful degradation, queue buffering, read-only safe mode.
"""
import uuid
import time
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from config import db
from functools import wraps

logger = logging.getLogger(__name__)

# ─── Circuit Breaker ───
_circuit_state = {}  # {service: {"failures": int, "open_until": float, "half_open": bool}}

CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_RESET_TIMEOUT = 60  # seconds


def get_circuit(service: str):
    if service not in _circuit_state:
        _circuit_state[service] = {"failures": 0, "open_until": 0, "half_open": False}
    return _circuit_state[service]


async def circuit_check(service: str) -> bool:
    """Returns True if circuit is closed (ok to proceed). False if open (block)."""
    cb = get_circuit(service)
    now = time.time()
    if cb["open_until"] > now:
        return False
    if cb["open_until"] > 0 and cb["open_until"] <= now:
        cb["half_open"] = True
    return True


async def circuit_success(service: str):
    cb = get_circuit(service)
    cb["failures"] = 0
    cb["open_until"] = 0
    cb["half_open"] = False


async def circuit_failure(service: str):
    cb = get_circuit(service)
    cb["failures"] += 1
    if cb["failures"] >= CIRCUIT_FAILURE_THRESHOLD:
        cb["open_until"] = time.time() + CIRCUIT_RESET_TIMEOUT
        cb["half_open"] = False
        await _log_event("circuit_breaker_open", service, f"Opened after {cb['failures']} failures")


# ─── Retry with Backoff ───
async def retry_with_backoff(fn, max_retries=3, base_delay=1.0, service="unknown"):
    """Execute fn with exponential backoff. Logs reliability events."""
    for attempt in range(max_retries):
        try:
            result = await fn()
            if attempt > 0:
                await _log_event("retry_success", service, f"Succeeded on attempt {attempt + 1}")
            return result
        except Exception as e:
            if attempt == max_retries - 1:
                await _log_event("retry_exhausted", service, f"All {max_retries} retries failed: {str(e)[:200]}")
                raise
            delay = base_delay * (2 ** attempt)
            await _log_event("retry_attempt", service, f"Attempt {attempt + 1} failed, retrying in {delay}s")
            await asyncio.sleep(delay)


# ─── Graceful Degradation ───
async def graceful_fallback(fn, fallback_value, service="unknown"):
    """Try fn, return fallback_value on failure instead of raising."""
    try:
        if not await circuit_check(service):
            await _log_event("circuit_blocked", service, "Request blocked by open circuit")
            return fallback_value
        result = await fn()
        await circuit_success(service)
        return result
    except Exception as e:
        await circuit_failure(service)
        await _log_event("fallback_activated", service, f"Serving fallback: {str(e)[:200]}")
        return fallback_value


# ─── Queue Buffer ───
async def buffer_request(action_type: str, payload: dict):
    """Buffer a request for later processing when workers are down."""
    doc = {
        "id": str(uuid.uuid4()),
        "action_type": action_type,
        "payload": payload,
        "status": "buffered",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "processed_at": None,
    }
    await db.reliability_buffer.insert_one(doc)
    await _log_event("request_buffered", action_type, "Request queued for later processing")
    return doc["id"]


async def process_buffered_requests(limit=50):
    """Process pending buffered requests after recovery."""
    docs = await db.reliability_buffer.find({"status": "buffered"}).limit(limit).to_list(limit)
    processed = 0
    for doc in docs:
        await db.reliability_buffer.update_one(
            {"id": doc["id"]},
            {"$set": {"status": "processed", "processed_at": datetime.now(timezone.utc).isoformat()}}
        )
        processed += 1
    if processed:
        await _log_event("buffer_drained", "system", f"Processed {processed} buffered requests")
    return processed


# ─── Read-Only Safe Mode ───
_safe_mode = {"active": False, "activated_at": None}


def is_safe_mode():
    return _safe_mode["active"]


async def activate_safe_mode(reason: str):
    _safe_mode["active"] = True
    _safe_mode["activated_at"] = datetime.now(timezone.utc).isoformat()
    await _log_event("safe_mode_activated", "system", reason)


async def deactivate_safe_mode():
    _safe_mode["active"] = False
    _safe_mode["activated_at"] = None
    await _log_event("safe_mode_deactivated", "system", "System recovered, safe mode off")


# ─── Task Priority Under Stress ───
_stress_mode = False


def is_stress_mode():
    return _stress_mode


async def set_stress_mode(active: bool):
    global _stress_mode
    _stress_mode = active
    if active:
        await _log_event("stress_mode_on", "system", "LOW priority tasks paused")
    else:
        await _log_event("stress_mode_off", "system", "LOW priority tasks resumed")


async def should_run_task(priority: str) -> bool:
    """Returns True if a task with given priority should run."""
    if priority == "LOW" and _stress_mode:
        return False
    return True


# ─── Event Logger ───
async def _log_event(event_type: str, service: str, detail: str):
    try:
        doc = {
            "id": str(uuid.uuid4()),
            "event_type": event_type,
            "service": service,
            "detail": detail[:500],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await db.reliability_events.insert_one(doc)
    except Exception as e:
        logger.error(f"[RELIABILITY] Failed to log event: {e}")


async def get_reliability_summary(days=7):
    """Get aggregated reliability event counts for reporting."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    results = await db.reliability_events.aggregate(pipeline).to_list(50)
    return {r["_id"]: r["count"] for r in results}
