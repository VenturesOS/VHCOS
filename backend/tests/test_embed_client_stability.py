"""BGE sidecar client stability regressions.

Locks in the fixes shipped 2026-09-08:

1. Uses a shared `requests.Session` (connection pool) — a fresh session per
   call would negate pooling and re-open the TCP socket every time.
2. Requests pass a `(connect, read)` tuple timeout to keep an unreachable
   sidecar from blocking for the full read window.
3. `HTTPAdapter` is mounted with `max_retries=0` so transient failures are
   visible to the circuit breaker instead of being masked by retries.
4. Three consecutive failures trip the breaker to OPEN and short-circuit
   subsequent calls in <1 ms until the cooldown elapses.
"""
from __future__ import annotations

import importlib

import requests


def _reload_client(monkeypatch, **env):
    """Reload embed_client with a clean module-level state and given env."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import services.embed_client as mod
    importlib.reload(mod)
    mod.reset_breaker()
    return mod


def test_session_is_shared_and_pooled(monkeypatch):
    mod = _reload_client(monkeypatch, BGE_SIDECAR_URL="http://127.0.0.1:8002")
    assert isinstance(mod._session, requests.Session)
    # Adapter must exist for both schemes and have retries disabled
    http_adapter = mod._session.get_adapter("http://x")
    https_adapter = mod._session.get_adapter("https://x")
    assert http_adapter is https_adapter, "expected the same pooled HTTPAdapter"
    # requests HTTPAdapter stores retry policy on `max_retries.total`; 0 means "no retries"
    assert getattr(http_adapter.max_retries, "total", None) == 0


def test_request_uses_split_connect_read_timeout(monkeypatch):
    mod = _reload_client(
        monkeypatch,
        BGE_SIDECAR_URL="http://127.0.0.1:8002",
        BGE_SIDECAR_TIMEOUT="8",
        BGE_SIDECAR_CONNECT_TIMEOUT="2",
    )
    captured = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): return None
        def json(self): return {"embeddings": [[0.0] * 384]}

    def _fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(mod._session, "post", _fake_post)
    out = mod.embed_remote(["hello"])
    assert out == [[0.0] * 384]
    assert captured["timeout"] == (2.0, 8.0), captured


def test_three_consecutive_failures_open_breaker(monkeypatch):
    mod = _reload_client(monkeypatch, BGE_SIDECAR_URL="http://127.0.0.1:8002")
    calls = {"n": 0}

    def _boom(*_a, **_k):
        calls["n"] += 1
        raise requests.ConnectionError("simulated sidecar unreachable")

    monkeypatch.setattr(mod._session, "post", _boom)

    # Three real attempts, each fails
    for _ in range(3):
        assert mod.embed_remote(["hello"]) is None
    assert calls["n"] == 3
    snap = mod.breaker_state()
    assert snap["state"] == "open", snap
    assert snap["consecutive_failures"] >= 3

    # Fourth call must short-circuit without touching HTTP
    assert mod.embed_remote(["hello"]) is None
    assert calls["n"] == 3, "expected short-circuit; got extra HTTP call"
    assert mod.breaker_state()["total_short_circuited"] >= 1


def test_disabled_when_url_empty(monkeypatch):
    mod = _reload_client(monkeypatch, BGE_SIDECAR_URL="")
    assert mod.is_remote_enabled() is False
    assert mod.embed_remote(["hello"]) is None
    assert mod.rerank_remote("q", ["a", "b"]) is None


def test_success_closes_breaker_and_records_metric(monkeypatch):
    mod = _reload_client(monkeypatch, BGE_SIDECAR_URL="http://127.0.0.1:8002")

    class _Resp:
        status_code = 200
        def raise_for_status(self): return None
        def json(self): return {"embeddings": [[0.1] * 384]}

    monkeypatch.setattr(mod._session, "post", lambda *_a, **_k: _Resp())
    out = mod.embed_remote(["hello"])
    assert out and out[0] and len(out[0]) == 384
    snap = mod.breaker_state()
    assert snap["state"] == "closed"
    assert snap["total_successes"] >= 1
