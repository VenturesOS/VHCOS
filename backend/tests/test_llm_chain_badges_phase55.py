"""Phase-55 targeted regression: approved LLM chain + badge/enrichment safeguards.

Scope:
- Live provider adapter checks (synthetic prompt only, no DB writes)
- Fallback traversal + all-fail error recording (mocked fault injection)
- _apply_bg_enrichment atomic conditional write behavior (mocked PyMongo only)
"""

from __future__ import annotations

import json
import asyncio
import re
from dataclasses import dataclass

import pytest

from services.llm_fallback_service import APPROVED_SOURCES, call_llm_chain
from services.llm_providers import call_nvidia_fallback, call_haiku, call_nemotron, ProviderError
from services.profile_extraction_helpers import _extract_json_from_response


SYNTHETIC_PROMPT = (
    "Return ONLY valid JSON object with keys: name, key_skills. "
    "Use name='Synthetic Candidate' and at least 3 realistic key_skills."
)


def _extract_obj(text: str) -> dict:
    parsed = json.loads(_extract_json_from_response(text))
    assert isinstance(parsed, dict), f"expected dict json, got {type(parsed)}"
    return parsed


def _assert_profile_shape(obj: dict):
    assert isinstance(obj.get("name"), str) and obj["name"].strip(), obj
    assert isinstance(obj.get("key_skills"), list) and len(obj["key_skills"]) >= 1, obj


# ── Live adapters (synthetic payload only; no persistence) ───────────────────


def test_live_nemotron_adapter_synthetic_json():
    response = asyncio.run(call_nemotron(
        "You are a strict JSON generator.", SYNTHETIC_PROMPT, temperature=0, text_mode=False, max_tokens=250
    ))
    obj = _extract_obj(response["content"])
    _assert_profile_shape(obj)


def test_live_nemotron_super_adapter_synthetic_json():
    response = asyncio.run(call_nvidia_fallback(
        "You are a strict JSON generator.", SYNTHETIC_PROMPT, temperature=0, text_mode=False, max_tokens=250
    ))
    obj = _extract_obj(response["content"])
    _assert_profile_shape(obj)


def test_live_haiku_adapter_synthetic_json():
    response = asyncio.run(call_haiku(
        "You are a strict JSON generator.", SYNTHETIC_PROMPT, temperature=0, text_mode=False, max_tokens=250
    ))
    obj = _extract_obj(response["content"])
    _assert_profile_shape(obj)


# ── Fallback traversal / quality gates ───────────────────────────────────────


def test_fallback_forced_to_nvidia_fallback_when_nemotron_fails(monkeypatch):
    from services import llm_fallback_service as lfs

    async def _fail_nemo(*_, **__):
        raise ProviderError("mock_nemotron_failure")

    monkeypatch.setattr(lfs, "_call_nemotron", _fail_nemo)

    out = asyncio.run(call_llm_chain(
        "You are a strict JSON generator.",
        SYNTHETIC_PROMPT,
        temperature=0,
        max_tokens=250,
        json_mode=True,
        validator=lambda d: bool(d.get("name") and d.get("key_skills")),
    ))

    assert out.get("source") == "nvidia_nemotron_super_120b", out
    assert out.get("_fallback_chain")[:2] == ["nvidia_nemotron_550b", "nvidia_nemotron_super_120b"]
    assert out.get("_fallback_errors") and out["_fallback_errors"][0]["source"] == "nvidia_nemotron_550b"


def test_fallback_forced_to_haiku_when_nemo_and_fallback_fail(monkeypatch):
    from services import llm_fallback_service as lfs

    async def _fail(*_, **__):
        raise ProviderError("mock_upstream_failure")

    monkeypatch.setattr(lfs, "_call_nemotron", _fail)
    monkeypatch.setattr(lfs, "_call_nvidia_fallback", _fail)

    out = asyncio.run(call_llm_chain(
        "You are a strict JSON generator.",
        SYNTHETIC_PROMPT,
        temperature=0,
        max_tokens=250,
        json_mode=True,
        validator=lambda d: bool(d.get("name") and d.get("key_skills")),
    ))

    assert out.get("source") == "emergent_haiku_4_5", out
    assert out.get("_fallback_chain") == list(APPROVED_SOURCES), out.get("_fallback_chain")
    assert [e["source"] for e in out.get("_fallback_errors", [])] == [
        "nvidia_nemotron_550b",
        "nvidia_nemotron_super_120b",
    ]


@pytest.mark.parametrize("bad_payload", [None, "", "[]", "123", "{}", '{"x":1}'])
def test_invalid_or_empty_json_triggers_next_provider(monkeypatch, bad_payload):
    from services import llm_fallback_service as lfs

    async def _bad_nemo(*_, **__):
        return {"content": bad_payload}

    async def _good_gpt(*_, **__):
        return {"content": '{"name":"Synthetic Candidate","key_skills":["python","fastapi","mongodb"]}'}

    monkeypatch.setattr(lfs, "_call_nemotron", _bad_nemo)
    monkeypatch.setattr(lfs, "_call_nvidia_fallback", _good_gpt)

    out = asyncio.run(call_llm_chain(
        "sys",
        "user",
        json_mode=True,
        validator=lambda d: bool(d.get("name") and d.get("key_skills")),
    ))
    assert out["source"] == "nvidia_nemotron_super_120b", out
    assert out["_fallback_errors"][0]["source"] == "nvidia_nemotron_550b"


def test_all_failed_contains_only_approved_chain_and_sanitized_reasons(monkeypatch):
    from services import llm_fallback_service as lfs

    async def _fail_500(*_, **__):
        raise ProviderError("http_500")

    monkeypatch.setattr(lfs, "_call_nemotron", _fail_500)
    monkeypatch.setattr(lfs, "_call_nvidia_fallback", _fail_500)
    monkeypatch.setattr(lfs, "_call_emergent_llm_haiku", _fail_500)

    out = asyncio.run(call_llm_chain("sys", "user", json_mode=True))
    assert out["error"] == "All LLM providers failed"
    assert out["source"] == "all_failed"
    assert out["_fallback_chain"] == list(APPROVED_SOURCES)
    reasons = [e["reason"] for e in out["_fallback_errors"]]
    assert reasons == ["http_500", "http_500", "http_500"]
    # No retired provider id/reason should appear
    assert all("qwen" not in (r or "").lower() for r in reasons)


# ── _apply_bg_enrichment: mocked persistence only ────────────────────────────


@dataclass
class _Result:
    matched_count: int


class _Collection:
    def __init__(self, doc: dict | None, matched_count: int = 1):
        self.doc = doc
        self.matched_count = matched_count
        self.last_query = None
        self.last_operation = None

    def find_one(self, query, _projection=None):
        self.last_query = query
        if not self.doc:
            return None
        for k, v in query.items():
            if self.doc.get(k) != v:
                return None
        return dict(self.doc)

    def update_one(self, query, operation):
        self.last_query = query
        self.last_operation = operation
        return _Result(self.matched_count)


class _DB:
    def __init__(self, coll):
        self.candidate_bank = coll


class _Client:
    def __init__(self, coll):
        self._db = _DB(coll)

    def __getitem__(self, _name):
        return self._db

    def close(self):
        return None


def _patch_bg_dependencies(monkeypatch, coll):
    from routes import extension

    monkeypatch.setenv("MONGO_URL", "mongodb://mocked")
    monkeypatch.setenv("DB_NAME", "mocked")
    monkeypatch.setattr("pymongo.MongoClient", lambda *a, **k: _Client(coll))
    monkeypatch.setattr(
        "services.naukri_regex_parser.extract_full_profile_regex",
        lambda *a, **k: {},
        raising=False,
    )
    monkeypatch.setattr(
        "services.smart_tags_service.generate_smart_tags",
        lambda *_a, **_k: ["synthetic_tag"],
        raising=False,
    )
    monkeypatch.setattr(extension, "_validate_work_experience", lambda *_a, **_k: True)
    return extension


def test_apply_bg_enrichment_returns_false_when_candidate_missing(monkeypatch):
    coll = _Collection(doc=None)
    ext = _patch_bg_dependencies(monkeypatch, coll)
    ok = ext._apply_bg_enrichment(
        "cand-1", "Synthetic Candidate", {"source": "nvidia_nemotron_550b"},
        "raw", "", "", write_filter={"raw_text_for_enrichment": "raw"}
    )
    assert ok is False


def test_apply_bg_enrichment_returns_false_when_atomic_filter_does_not_match(monkeypatch):
    doc = {"id": "cand-1", "raw_text_for_enrichment": "old", "enrichment_status": "pending"}
    coll = _Collection(doc=doc)
    ext = _patch_bg_dependencies(monkeypatch, coll)
    ok = ext._apply_bg_enrichment(
        "cand-1", "Synthetic Candidate", {"source": "nvidia_nemotron_550b"},
        "raw", "", "", write_filter={"raw_text_for_enrichment": "raw"}
    )
    assert ok is False


def test_apply_bg_enrichment_marks_success_and_clears_stale_error(monkeypatch):
    doc = {
        "id": "cand-1",
        "raw_text_for_enrichment": "raw",
        "enrichment_status": "pending",
        "ai_enrichment_error": "old_error",
    }
    coll = _Collection(doc=doc, matched_count=1)
    ext = _patch_bg_dependencies(monkeypatch, coll)

    ok = ext._apply_bg_enrichment(
        "cand-1",
        "Synthetic Candidate",
        {
            "source": "nvidia_nemotron_550b",
            "name": "Synthetic Candidate",
            "key_skills": ["python", "fastapi"],
            "current_employer": "TestCo",
            "experience_years": 6,
            "_fallback_chain": ["nvidia_nemotron_550b"],
            "_fallback_errors": [],
        },
        "raw",
        "",
        "",
        write_filter={"raw_text_for_enrichment": "raw"},
    )

    assert ok is True
    assert coll.last_query == {"raw_text_for_enrichment": "raw", "id": "cand-1"}
    assert coll.last_operation and "$set" in coll.last_operation
    assert coll.last_operation["$set"]["enrichment_status"] == "enriched"
    assert coll.last_operation["$set"]["ai_enrichment_source"] == "nvidia_nemotron_550b"
    assert coll.last_operation.get("$unset") == {"ai_enrichment_error": ""}


def test_apply_bg_enrichment_returns_false_when_write_match_fails(monkeypatch):
    doc = {"id": "cand-1", "raw_text_for_enrichment": "raw", "enrichment_status": "pending"}
    coll = _Collection(doc=doc, matched_count=0)
    ext = _patch_bg_dependencies(monkeypatch, coll)

    ok = ext._apply_bg_enrichment(
        "cand-1",
        "Synthetic Candidate",
        {"source": "nvidia_nemotron_550b", "key_skills": ["python"]},
        "raw",
        "",
        "",
        write_filter={"raw_text_for_enrichment": "raw"},
    )
    assert ok is False


# ── Static checks: retired-provider residue and approved A/B labeling ─────────


def test_retry_script_readonly_but_no_qwen_chain_residue():
    path = "/app/backend/scripts/retry_all_failed_enrichment.py"
    text = open(path, "r", encoding="utf-8").read()
    assert "retry_enabled" in text
    assert "strict_qwen_no_fallback" not in text


def test_llm_ab_comparison_model_is_nemotron_super_and_no_qwen_labeling():
    path = "/app/backend/routes/llm_ab.py"
    text = open(path, "r", encoding="utf-8").read()
    assert re.search(r'"comparison_model"\s*:\s*"nemotron_super"', text)
    assert "qwen" not in text.lower()


def test_llm_ab_extract_one_uses_nemotron_and_nemotron_super_with_mocks(monkeypatch):
    from routes import llm_ab

    async def _nemo(*_a, **_k):
        return {"content": '{"name":"Synthetic Candidate","key_skills":["python"]}'}

    async def _gpt(*_a, **_k):
        return {"content": '{"name":"Synthetic Candidate","key_skills":["fastapi"]}'}

    monkeypatch.setattr(llm_ab, "_call_nemotron", _nemo)
    monkeypatch.setattr(llm_ab, "_call_nvidia_fallback", _gpt)

    out = asyncio.run(llm_ab._extract_one("synthetic raw", "Synthetic Candidate"))
    assert out["candidate_name"] == "Synthetic Candidate"
    assert out["nemotron"]["ok"] is True
    assert out["nemotron_super"]["ok"] is True
    assert out["nemotron"]["output"]["name"] == "Synthetic Candidate"
    assert out["nemotron_super"]["output"]["name"] == "Synthetic Candidate"
