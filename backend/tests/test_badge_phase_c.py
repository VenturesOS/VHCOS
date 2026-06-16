"""Regression tests for Badge Phase C — medium-band BGE re-verification.

Pure-function checks on the helpers + presence checks on the wiring in
`extension_check.py`. The actual embedding call is mocked so we don't
require the BGE model to be loaded during CI.
"""
from __future__ import annotations

from unittest.mock import patch, AsyncMock
import pytest

from routes import extension_check as ec
from routes.extension_check import CandidateIn


# ── Phase C feature-flag helpers ────────────────────────────────────

def test_phase_c_enabled_default_true(monkeypatch):
    monkeypatch.delenv("BADGE_PHASE_C_ENABLED", raising=False)
    assert ec._phase_c_enabled() is True


def test_phase_c_can_be_disabled(monkeypatch):
    monkeypatch.setenv("BADGE_PHASE_C_ENABLED", "false")
    assert ec._phase_c_enabled() is False
    monkeypatch.setenv("BADGE_PHASE_C_ENABLED", "0")
    assert ec._phase_c_enabled() is False


def test_phase_c_threshold_default_0_60(monkeypatch):
    monkeypatch.delenv("BADGE_PHASE_C_THRESHOLD", raising=False)
    assert ec._phase_c_threshold() == 0.60


def test_phase_c_threshold_overrideable(monkeypatch):
    monkeypatch.setenv("BADGE_PHASE_C_THRESHOLD", "0.55")
    assert ec._phase_c_threshold() == 0.55


# ── Text-pair builder ───────────────────────────────────────────────

def _make_card(**kw):
    """Minimal CandidateIn for the text builder."""
    defaults = dict(name="Amit Kumar", index=0)
    defaults.update(kw)
    return CandidateIn(**defaults)


def test_text_pair_combines_canonical_fields():
    c = _make_card(designation="Senior Engineer", current_employer="TCS",
                   location="Bangalore", headline="ML Engineer at TCS")
    doc = {"name": "Amit Kumar", "designation": "ML Engineer",
           "current_employer": "TCS", "location": "Bangalore",
           "headline": "Machine Learning Engineer @ TCS"}
    card_text, doc_text = ec._build_phase_c_text_pair(c, doc)
    assert "Amit Kumar" in card_text
    assert "TCS" in card_text
    assert "Bangalore" in card_text
    assert "Amit Kumar" in doc_text
    assert "Machine Learning" in doc_text


def test_text_pair_ignores_empty_fields():
    c = _make_card(designation=None, current_employer=None, location=None, headline=None)
    doc = {"name": "X", "designation": "", "current_employer": "", "location": "", "headline": ""}
    card_text, doc_text = ec._build_phase_c_text_pair(c, doc)
    # Should still have the name in both — no empty " | " join leaks
    assert " |  | " not in card_text
    assert " |  | " not in doc_text


# ── Verify medium band — mocked embeddings ──────────────────────────

import asyncio


def test_phase_c_keeps_when_cosine_above_threshold():
    """Two highly similar text pairs → cosine > T → both KEPT."""
    pairs = [
        (0, _make_card(name="A", designation="Eng"), {"name": "A", "designation": "Eng"}),
        (5, _make_card(name="B", designation="Mgr"), {"name": "B", "designation": "Mgr"}),
    ]
    # Mock embed_texts_batch to return identical pairs → cosine = 1.0
    mock_vecs = [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0],   # pair 0
                 [0.0, 1.0, 0.0], [0.0, 1.0, 0.0]]    # pair 1
    with patch("services.talent_graph_service.embed_texts_batch", return_value=mock_vecs):
        out = asyncio.run(ec._phase_c_verify_medium_band(pairs, threshold=0.60))
    assert out[0]["decision"] == "keep"
    assert out[0]["cosine"] == pytest.approx(1.0)
    assert out[5]["decision"] == "keep"


def test_phase_c_rejects_when_cosine_below_threshold():
    """Orthogonal pairs → cosine = 0 → REJECTED."""
    pairs = [(0, _make_card(name="Amit"), {"name": "Amit"})]
    mock_vecs = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]  # orthogonal
    with patch("services.talent_graph_service.embed_texts_batch", return_value=mock_vecs):
        out = asyncio.run(ec._phase_c_verify_medium_band(pairs, threshold=0.60))
    assert out[0]["decision"] == "reject"
    assert out[0]["cosine"] == pytest.approx(0.0)


def test_phase_c_fail_open_on_embed_error():
    """If the embedder fails, Phase C must NOT reject — fail-open
    preserves the V2 recall the code already passed."""
    pairs = [(0, _make_card(name="X"), {"name": "X"})]
    with patch("services.talent_graph_service.embed_texts_batch", side_effect=RuntimeError("boom")):
        out = asyncio.run(ec._phase_c_verify_medium_band(pairs, threshold=0.60))
    assert out == {}


def test_phase_c_empty_pairs_returns_empty():
    out = asyncio.run(ec._phase_c_verify_medium_band([], threshold=0.60))
    assert out == {}


# ── Presence checks on the integration wiring ──────────────────────

def test_extension_check_wires_phase_c_into_match_loop():
    """Static check: the V2 finalisation pass must call
    `_phase_c_verify_medium_band` and act on its decision."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "routes" / "extension_check.py").read_text()
    assert "_phase_c_verify_medium_band" in src
    assert "phase_c_reject" in src
    assert "phase_c_keep" in src
    # Medium-band gating bounds
    assert "badge_thr <= score < high_thr" in src
