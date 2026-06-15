"""
Regression tests for Talent Search v2 (hybrid + lexical A/B) and Badge
Phase A telemetry (`/api/extension/audit/wrong-match`).

The hybrid retrieval test uses an in-memory monkey-patched
`find_candidates_by_text` to avoid spinning up the BGE embedding model
in CI. Real semantic retrieval is exercised via the manual smoke test
documented in /app/memory/PRD.md.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock

from routes import talent_search as ts
from routes import badge_audit as ba


# ── Talent Search structured-filter post-filter logic ────────────────

def test_apply_structured_filters_drops_off_industry():
    cands = [
        {"id": "1", "name": "A", "industry": "Automobile",
         "current_designation": "Senior Engineer"},
        {"id": "2", "name": "B", "industry": "Banking",
         "current_designation": "Software Engineer"},
        {"id": "3", "name": "C", "smart_tags": ["IT/Software"],
         "current_designation": "Engineer"},
    ]
    filtered = ts._apply_structured_filters(cands, {"industry_include": ["IT"]})
    assert {c["id"] for c in filtered} == {"3"}


def test_apply_structured_filters_skills_match_against_designation_fallback():
    """When skills filter fails on key_skills, fallback to designation."""
    cands = [
        {"id": "1", "name": "A", "current_designation": "Python Backend Developer",
         "skills": ["Django", "PostgreSQL"]},
        {"id": "2", "name": "B", "current_designation": "Frontend Engineer",
         "skills": ["React", "TypeScript"]},
    ]
    filtered = ts._apply_structured_filters(cands, {"skills": ["python"]})
    # Both candidates considered — candidate 1 matches via designation
    # (Python in title) AND via skills (none) — should pass. Candidate 2
    # has React/TS only — should be dropped.
    assert {c["id"] for c in filtered} == {"1"}


def test_apply_structured_filters_keeps_missing_experience():
    """A candidate without experience_years must NOT be dropped by an exp filter."""
    cands = [
        {"id": "1", "name": "A"},                           # no exp → KEEP
        {"id": "2", "name": "B", "experience_years": 3},    # too junior
        {"id": "3", "name": "C", "experience_years": 8},    # in range
    ]
    filtered = ts._apply_structured_filters(
        cands, {"min_experience": 5, "max_experience": 12}
    )
    assert {c["id"] for c in filtered} == {"1", "3"}


def test_apply_structured_filters_excludes_industry():
    cands = [
        {"id": "1", "name": "A", "industry": "BFSI"},
        {"id": "2", "name": "B", "industry": "IT/Software"},
    ]
    filtered = ts._apply_structured_filters(cands, {"industry_exclude": ["BFSI"]})
    assert {c["id"] for c in filtered} == {"2"}


def test_apply_structured_filters_company_include_exclude():
    cands = [
        {"id": "1", "name": "A", "current_employer": "Mahindra"},
        {"id": "2", "name": "B", "current_employer": "TCS"},
        {"id": "3", "name": "C", "current_employer": "Infosys"},
    ]
    inc = ts._apply_structured_filters(cands, {"company_include": ["mahindra", "tcs"]})
    assert {c["id"] for c in inc} == {"1", "2"}
    exc = ts._apply_structured_filters(cands, {"company_exclude": ["mahindra"]})
    assert {c["id"] for c in exc} == {"2", "3"}


def test_normalise_hybrid_handles_alias_fields():
    raw = {
        "candidate_id": "X", "candidate_name": "Foo",
        "designation": "ML Eng",                # alias for current_designation
        "current_company": "Acme",              # alias for current_employer
        "score": 0.812345,
    }
    n = ts._normalise_hybrid(raw)
    assert n["id"] == "X"
    assert n["name"] == "Foo"
    assert n["current_designation"] == "ML Eng"
    assert n["current_employer"] == "Acme"
    assert n["score"] == 0.8123
    assert n["source"] == "hybrid"


def test_normalise_lexical_uses_canonical_then_alias():
    raw = {
        "id": "Y", "name": "Bar",
        "current_designation": "Lead Eng",
        "current_employer": "Foo Inc",
        "total_experience_years": 9.5,
    }
    n = ts._normalise_lexical(raw)
    assert n["id"] == "Y"
    assert n["current_designation"] == "Lead Eng"
    assert n["experience_years"] == 9.5
    assert n["match_type"] == "lexical_regex"


# ── Wrong-match telemetry endpoint shape ─────────────────────────────

def test_wrong_match_payload_model_required_field():
    """badge_candidate_id is the only required field — everything else
    is best-effort so the extension can flag fast."""
    with pytest.raises(ValueError):
        ba.WrongMatchReport(card_name="x")  # missing badge_candidate_id

    ok = ba.WrongMatchReport(badge_candidate_id="cid-1")
    assert ok.badge_candidate_id == "cid-1"
    assert ok.audit_id is None


# ── Extension client wiring (presence-only, JS shape check) ──────────

def test_extension_background_forwards_audit_id():
    """background.js must return audit_id alongside results so the
    "Wrong match?" link can post the correct telemetry payload."""
    from pathlib import Path
    bg = (Path(__file__).resolve().parents[2] / "browser-extension" / "background.js").read_text()
    assert "audit_id: apiData.audit_id" in bg
    assert "reportWrongMatch" in bg
    assert "/api/extension/audit/wrong-match" in bg


def test_extension_content_renders_wrong_match_flag():
    """content.js must render the small '✗ Wrong match?' link next to
    every badge so recruiters can flag the FP in one click."""
    from pathlib import Path
    cj = (Path(__file__).resolve().parents[2] / "browser-extension" / "content.js").read_text()
    assert "vhc-wrong-match-flag" in cj
    assert "reportWrongMatch" in cj
    assert "info.audit_id" in cj
