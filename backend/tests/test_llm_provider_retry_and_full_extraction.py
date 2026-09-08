"""LLM provider retry policy + synthetic full-profile extraction flow tests.

Scope:
- Provider transport retry boundaries (mocked httpx transport only)
- Full extraction post-processing + metadata with mocked chain/logger (no DB writes)
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from services.llm_providers import ProviderError, call_nemotron
from services.llm_fallback_service import extract_full_profile_fallback


class _FakeResponse:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data
        self.request = httpx.Request("POST", "https://example.test/chat/completions")

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status={self.status_code}", request=self.request, response=self
            )


class _FakeAsyncClient:
    def __init__(self, *, scripted, calls, payloads):
        self._scripted = scripted
        self._calls = calls
        self._payloads = payloads

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, _url, json=None, headers=None):
        self._calls.append({"url": _url, "headers": headers})
        self._payloads.append(json)
        event = self._scripted.pop(0)
        if event == "network":
            raise httpx.NetworkError("mock_network")
        if event == "slow":
            await asyncio.sleep(0.02)
            return _FakeResponse(200, {
                "choices": [{"message": {"content": "{\"ok\": true}"}, "finish_reason": "stop"}],
                "usage": {},
            })
        return event


def _ok_response(content='{"name":"Synthetic Candidate","key_skills":["python"]}'):
    return _FakeResponse(200, {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"total_tokens": 1},
    })


def _patch_provider_env(monkeypatch):
    monkeypatch.setenv("NEMOTRON_API_KEY", "test-key")
    monkeypatch.setenv("NEMOTRON_BASE_URL", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setenv("NEMOTRON_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")


def test_nemotron_retries_on_transient_503_then_succeeds(monkeypatch):
    from services import llm_providers as lp

    _patch_provider_env(monkeypatch)
    calls, payloads = [], []
    scripted = [
        _FakeResponse(503, {}),
        _FakeResponse(503, {}),
        _ok_response(),
    ]
    monkeypatch.setattr(lp.httpx, "AsyncClient", lambda **kwargs: _FakeAsyncClient(scripted=scripted, calls=calls, payloads=payloads))
    monkeypatch.setattr(lp.random, "uniform", lambda _a, _b: 0)

    out = asyncio.run(call_nemotron("sys", "user", temperature=0, text_mode=False, max_tokens=80))
    assert len(calls) == 3
    assert json.loads(out["content"])["name"] == "Synthetic Candidate"


@pytest.mark.parametrize("status", [400, 401, 404, 410, 429])
def test_nemotron_does_not_retry_on_permanent_or_throttle_errors(monkeypatch, status):
    from services import llm_providers as lp

    _patch_provider_env(monkeypatch)
    calls, payloads = [], []
    scripted = [_FakeResponse(status, {})]
    monkeypatch.setattr(lp.httpx, "AsyncClient", lambda **kwargs: _FakeAsyncClient(scripted=scripted, calls=calls, payloads=payloads))

    with pytest.raises(ProviderError, match=fr"http_{status}"):
        asyncio.run(call_nemotron("sys", "user", temperature=0, text_mode=False, max_tokens=80))
    assert len(calls) == 1


def test_nemotron_request_payload_has_supported_params_only(monkeypatch):
    from services import llm_providers as lp

    _patch_provider_env(monkeypatch)
    calls, payloads = [], []
    scripted = [_ok_response()]
    monkeypatch.setattr(lp.httpx, "AsyncClient", lambda **kwargs: _FakeAsyncClient(scripted=scripted, calls=calls, payloads=payloads))

    asyncio.run(call_nemotron("sys", "user", temperature=0.3, text_mode=False, max_tokens=123))
    payload = payloads[0]
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert payload["reasoning_effort"] == "none"
    assert "response_format" not in payload


def test_nemotron_timeout_when_provider_wall_budget_expires(monkeypatch):
    from services import llm_providers as lp

    _patch_provider_env(monkeypatch)
    calls, payloads = [], []
    scripted = ["slow"]
    monkeypatch.setattr(lp.httpx, "AsyncClient", lambda **kwargs: _FakeAsyncClient(scripted=scripted, calls=calls, payloads=payloads))
    monkeypatch.setattr(lp, "PROVIDER_TIMEOUT", 0.01)

    with pytest.raises(ProviderError, match="timeout"):
        asyncio.run(call_nemotron("sys", "user", temperature=0, text_mode=False, max_tokens=80))
    assert len(calls) == 1


def test_extract_full_profile_synthetic_success_has_postprocessing_and_metadata(monkeypatch):
    from services import llm_fallback_service as lfs

    async def _mock_chain(*_a, **_k):
        return {
            "source": "nvidia_nemotron_super_120b",
            "parsed": {
                "name": "Synthetic Candidate",
                "key_skills": ["python", "fastapi"],
                "experience_years": 0,
                "current_employer": "Acme",
                "work_experience": [
                    {"company": "Acme", "designation": "Engineer", "from_date": "Jan 2020", "to_date": "Present", "is_current": True, "duration": "0y 0m"}
                ],
            },
            "_fallback_chain": ["nvidia_nemotron_550b", "nvidia_nemotron_super_120b"],
            "_fallback_errors": [{"source": "nvidia_nemotron_550b", "reason": "quality_check_failed"}],
        }

    calls = []

    async def _mock_log(_db, candidate_name, source, success, fallback_chain, elapsed_ms):
        calls.append({
            "candidate_name": candidate_name,
            "source": source,
            "success": success,
            "fallback_chain": fallback_chain,
            "elapsed_ms": elapsed_ms,
        })

    monkeypatch.setattr(lfs, "call_llm_chain", _mock_chain)
    monkeypatch.setattr(lfs, "_log_extraction_event", _mock_log)

    raw = "Synthetic Candidate 6 years 3 months at Acme. Current CTC: 22 LPA"
    out = asyncio.run(extract_full_profile_fallback(raw, candidate_name="Synthetic Candidate"))

    assert out["source"] == "nvidia_nemotron_super_120b"
    assert out["_extraction_source"] == "nvidia_nemotron_super_120b"
    assert out["experience_years"] == 6.03
    assert out["current_ctc"] == 2200000
    assert out["work_experience"][0]["duration"] != "0y 0m"
    assert calls and calls[0]["success"] is True


def test_extract_full_profile_all_failed_shape_and_event_logged(monkeypatch):
    from services import llm_fallback_service as lfs

    async def _mock_chain(*_a, **_k):
        return {
            "error": "All LLM providers failed",
            "source": "all_failed",
            "_fallback_chain": ["nvidia_nemotron_550b", "nvidia_nemotron_super_120b", "emergent_haiku_4_5"],
            "_fallback_errors": [{"source": "nvidia_nemotron_550b", "reason": "http_503"}],
        }

    calls = []

    async def _mock_log(_db, candidate_name, source, success, fallback_chain, elapsed_ms):
        calls.append({"candidate_name": candidate_name, "source": source, "success": success, "fallback_chain": fallback_chain})

    monkeypatch.setattr(lfs, "call_llm_chain", _mock_chain)
    monkeypatch.setattr(lfs, "_log_extraction_event", _mock_log)

    out = asyncio.run(extract_full_profile_fallback("synthetic raw", candidate_name="Synthetic Candidate"))
    assert out["error"] == "All LLM providers failed"
    assert out["source"] == "all_failed"
    assert out["_extraction_source"] == "all_failed"
    assert calls and calls[0]["success"] is False
