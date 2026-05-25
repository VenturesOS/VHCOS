"""Unit tests for the BGE sidecar circuit breaker.

Tests the state machine in isolation (no actual sidecar call needed).
Uses a mocked `requests.post` to force success / failure responses.

Run:
    cd /app/backend && BGE_SIDECAR_URL=http://fake.test \
        BGE_BREAKER_THRESHOLD=3 BGE_BREAKER_OPEN_SECS=2 \
        python tests/test_embed_breaker.py
"""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import patch

os.environ.setdefault("BGE_SIDECAR_URL", "http://fake.test")
os.environ.setdefault("BGE_BREAKER_THRESHOLD", "3")
os.environ.setdefault("BGE_BREAKER_OPEN_SECS", "2")

sys.path.insert(0, "/app/backend")

# Import AFTER env vars set so the module-level constants take effect
from services import embed_client as ec  # noqa: E402

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
_results: list[tuple[str, bool, str]] = []


def chk(name, cond, hint=""):
    _results.append((name, bool(cond), "" if cond else f"  {hint}"))


class _FakeResp:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {"embeddings": [[0.0] * 384]}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._body


def _reset():
    """Hard-reset breaker state between tests."""
    ec.reset_breaker()
    # also zero out the counters for clean test reports
    with ec._lock:
        ec._consecutive_failures = 0
        ec._total_failures = 0
        ec._total_successes = 0
        ec._total_short_circuited = 0
        ec._opened_at = 0.0
        ec._last_failure_msg = None


def test_closed_state_normal_call():
    _reset()
    with patch("services.embed_client.requests.post", return_value=_FakeResp()):
        out = ec.embed_remote(["hello"])
    chk("CLOSED: returns embedding on success", out is not None and len(out) == 1)
    chk("CLOSED: state stays closed after success",
        ec.breaker_state()["state"] == "closed")
    chk("CLOSED: success counted", ec.breaker_state()["total_successes"] == 1)


def test_single_failure_keeps_closed():
    _reset()
    import requests as _rq
    with patch("services.embed_client.requests.post",
               side_effect=_rq.ConnectionError("boom")):
        out = ec.embed_remote(["x"])
    chk("1-failure: returns None", out is None)
    chk("1-failure: stays CLOSED (under threshold)",
        ec.breaker_state()["state"] == "closed")
    chk("1-failure: consecutive_failures=1",
        ec.breaker_state()["consecutive_failures"] == 1)


def test_three_failures_open_breaker():
    _reset()
    import requests as _rq
    with patch("services.embed_client.requests.post",
               side_effect=_rq.ConnectionError("boom")):
        for _ in range(3):
            ec.embed_remote(["x"])
    chk("3 failures: state=OPEN", ec.breaker_state()["state"] == "open")
    chk("3 failures: consecutive=3",
        ec.breaker_state()["consecutive_failures"] == 3)


def test_open_state_short_circuits():
    _reset()
    import requests as _rq
    # Trip the breaker first
    with patch("services.embed_client.requests.post",
               side_effect=_rq.ConnectionError("boom")):
        for _ in range(3):
            ec.embed_remote(["x"])
    # Now any further call should NOT touch the network
    call_count = [0]
    def _spy(*a, **k):
        call_count[0] += 1
        return _FakeResp()
    with patch("services.embed_client.requests.post", side_effect=_spy):
        for _ in range(5):
            out = ec.embed_remote(["x"])
            chk_inner = out is None
    chk("OPEN: subsequent 5 calls short-circuit", call_count[0] == 0,
        f"network was called {call_count[0]} times when it shouldn't have been")
    chk("OPEN: short-circuit counter incremented",
        ec.breaker_state()["total_short_circuited"] == 5)


def test_half_open_then_closed_on_success():
    _reset()
    import requests as _rq
    # Trip and wait out the cooldown
    with patch("services.embed_client.requests.post",
               side_effect=_rq.ConnectionError("boom")):
        for _ in range(3):
            ec.embed_remote(["x"])
    chk("Before sleep: state=OPEN", ec.breaker_state()["state"] == "open")
    time.sleep(2.1)  # > BGE_BREAKER_OPEN_SECS=2
    # Next call should probe (HALF_OPEN), succeed, and close the breaker
    with patch("services.embed_client.requests.post", return_value=_FakeResp()):
        out = ec.embed_remote(["x"])
    chk("After cooldown + success probe: result is real", out is not None)
    chk("After cooldown + success probe: state=CLOSED",
        ec.breaker_state()["state"] == "closed")
    chk("After cooldown + success probe: consecutive_failures=0",
        ec.breaker_state()["consecutive_failures"] == 0)


def test_half_open_failed_probe_reopens():
    _reset()
    import requests as _rq
    with patch("services.embed_client.requests.post",
               side_effect=_rq.ConnectionError("boom")):
        for _ in range(3):
            ec.embed_remote(["x"])
    time.sleep(2.1)
    with patch("services.embed_client.requests.post",
               side_effect=_rq.ConnectionError("still down")):
        out = ec.embed_remote(["x"])
    chk("HALF_OPEN failed probe: returns None", out is None)
    chk("HALF_OPEN failed probe: state=OPEN", ec.breaker_state()["state"] == "open")


def test_manual_reset():
    _reset()
    import requests as _rq
    with patch("services.embed_client.requests.post",
               side_effect=_rq.ConnectionError("boom")):
        for _ in range(3):
            ec.embed_remote(["x"])
    chk("Before reset: state=OPEN", ec.breaker_state()["state"] == "open")
    ec.reset_breaker()
    chk("After reset: state=CLOSED", ec.breaker_state()["state"] == "closed")
    chk("After reset: consecutive_failures=0",
        ec.breaker_state()["consecutive_failures"] == 0)


def test_503_treated_as_failure():
    _reset()
    with patch("services.embed_client.requests.post",
               return_value=_FakeResp(status_code=503)):
        out = ec.embed_remote(["x"])
    chk("503 response: returns None", out is None)
    chk("503 response: counted as failure",
        ec.breaker_state()["consecutive_failures"] == 1)


def test_state_snapshot_shape():
    _reset()
    s = ec.breaker_state()
    expected = {"enabled", "state", "consecutive_failures", "threshold",
                "open_for_seconds", "seconds_until_half_open",
                "total_successes", "total_failures",
                "total_short_circuited", "last_failure_msg"}
    chk("breaker_state has all keys", set(s.keys()) == expected,
        f"missing={expected - set(s.keys())} extra={set(s.keys()) - expected}")


def main():
    test_closed_state_normal_call()
    test_single_failure_keeps_closed()
    test_three_failures_open_breaker()
    test_open_state_short_circuits()
    test_half_open_then_closed_on_success()
    test_half_open_failed_probe_reopens()
    test_manual_reset()
    test_503_treated_as_failure()
    test_state_snapshot_shape()

    failed = sum(1 for _, ok, _ in _results if not ok)
    for name, ok, msg in _results:
        print(f"  {PASS if ok else FAIL} {name}{msg}")
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
