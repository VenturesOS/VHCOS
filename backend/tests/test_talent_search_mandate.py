"""Regression for the mandate-driven search path (/api/talent/search?job_id).

Tests the pure `_build_query_from_job` helper — composes a hybrid-search
input from a job document. Real end-to-end test happens in the manual
smoke at PRD time.
"""
from __future__ import annotations

from routes.talent_search import _build_query_from_job, _apply_structured_filters
from routes.talent_search import (
    _explain_match,
    _expand_location_terms,
    _extract_role_signature,
    _role_relevance,
)



def test_job_query_basic():
    job = {
        "title": "Senior React Developer",
        "company_name": "Acme Corp",
        "location": "Bangalore",
        "required_skills": ["React", "TypeScript", "AWS"],
        "min_experience": 5,
        "max_experience": 10,
        "description": "Build modern UIs.",
    }
    out = _build_query_from_job(job)
    assert "Senior React Developer" in out["query"]
    assert "React, TypeScript, AWS" in out["query"]
    assert "in Bangalore" in out["query"]
    assert "5-10 years" in out["query"]
    assert out["filters"]["skills"] == ["React", "TypeScript", "AWS"]
    assert out["filters"]["location_include"] == ["Bangalore"]
    assert out["filters"]["min_experience"] == 5
    assert out["filters"]["max_experience"] == 10


def test_job_query_handles_missing_fields():
    """A bare job doc must still produce a usable query."""
    job = {"title": "Project Manager"}
    out = _build_query_from_job(job)
    assert out["query"].strip() == "Project Manager"
    assert out["filters"] == {}


def test_job_query_skills_as_string():
    """Some legacy jobs store skills as a comma-separated string — must split."""
    job = {
        "title": "DevOps Engineer",
        "skills": "Kubernetes, Docker; Terraform",
    }
    out = _build_query_from_job(job)
    assert "Kubernetes" in out["filters"]["skills"]
    assert "Docker" in out["filters"]["skills"]
    assert "Terraform" in out["filters"]["skills"]


def test_job_query_skills_as_dict_list():
    """ATS often serialises skills as [{'name': 'React'}, ...]."""
    job = {
        "title": "Frontend Eng",
        "required_skills": [{"name": "React"}, {"skill": "Vue"}, "Svelte"],
    }
    out = _build_query_from_job(job)
    assert "React" in out["filters"]["skills"]
    assert "Vue" in out["filters"]["skills"]
    assert "Svelte" in out["filters"]["skills"]


def test_job_query_experience_one_sided():
    job_min_only = {"title": "X", "min_experience": 8}
    assert "8+ years" in _build_query_from_job(job_min_only)["query"]
    job_max_only = {"title": "X", "max_experience": 3}
    assert "upto 3 years" in _build_query_from_job(job_max_only)["query"]


def test_job_query_jd_snippet_appended():
    """JD body should be appended (truncated to ~600 chars) so the encoder
    picks up nuance the title alone misses."""
    job = {
        "title": "PM",
        "description": "Drive offshore PMO across APAC. " * 50,  # 1500+ chars
    }
    out = _build_query_from_job(job)
    # The full query should be capped to 1500 chars
    assert len(out["query"]) <= 1500
    assert "offshore PMO" in out["query"]


def test_job_query_collapses_whitespace_in_description():
    """JDs are often pasted with newlines/tabs — encoder prefers clean prose."""
    job = {"title": "X", "description": "Line 1.\n\n\tLine 2.\n  Line 3."}
    out = _build_query_from_job(job)
    assert "Line 1. Line 2. Line 3." in out["query"]
    assert "\n" not in out["query"]
    assert "\t" not in out["query"]



# ── Salary extraction from mandate → ctc_min/ctc_max filters ──────────


def test_job_query_extracts_salary_range():
    """salary_min / salary_max on the mandate must surface as ctc_min/ctc_max
    in the filter payload so the strict-filter intersection can enforce
    the bracket."""
    job = {
        "title": "Lead Backend",
        "salary_min": 2_500_000,
        "salary_max": 4_000_000,
    }
    out = _build_query_from_job(job)
    assert out["filters"]["ctc_min"] == 2_500_000
    assert out["filters"]["ctc_max"] == 4_000_000


def test_job_query_salary_partial():
    out_min_only = _build_query_from_job({"title": "X", "salary_min": 1_800_000})
    assert out_min_only["filters"].get("ctc_min") == 1_800_000
    assert "ctc_max" not in out_min_only["filters"]
    out_max_only = _build_query_from_job({"title": "X", "salary_max": 2_000_000})
    assert "ctc_min" not in out_max_only["filters"]
    assert out_max_only["filters"].get("ctc_max") == 2_000_000


def test_job_query_salary_alias_fields():
    """Legacy jobs sometimes use min_salary / max_salary or ctc_*."""
    assert _build_query_from_job({"title": "X", "min_salary": 1_500_000})["filters"]["ctc_min"] == 1_500_000
    assert _build_query_from_job({"title": "X", "ctc_max": 3_500_000})["filters"]["ctc_max"] == 3_500_000


def test_job_query_salary_invalid_ignored():
    """Garbage salary values must not crash and must not populate filters."""
    out = _build_query_from_job({"title": "X", "salary_min": "abc", "salary_max": None})
    assert "ctc_min" not in out["filters"]
    assert "ctc_max" not in out["filters"]


# ── Strict filter enforcement (mandate-driven search) ─────────────────


def _cand(name, **kw):
    base = {"id": name, "name": name}
    base.update(kw)
    return base


def test_strict_location_drops_mismatch():
    cands = [
        _cand("A", current_location="Chennai", experience_years=5),
        _cand("B", current_location="Delhi", experience_years=5),
        _cand("C", current_location=None, experience_years=5),  # missing → drop in strict
    ]
    filters = {"location_include": ["chennai"]}
    out = _apply_structured_filters(cands, filters, strict=True)
    assert [c["id"] for c in out] == ["A"]


def test_strict_experience_drops_outside_band():
    """min/max experience with ±1y tolerance — strict mode drops missing exp too."""
    cands = [
        _cand("ok", experience_years=6, current_location="Chennai"),
        _cand("too_jr", experience_years=2, current_location="Chennai"),
        _cand("too_sr", experience_years=15, current_location="Chennai"),
        _cand("missing", experience_years=None, current_location="Chennai"),
    ]
    filters = {"min_experience": 5, "max_experience": 10}
    out = _apply_structured_filters(cands, filters, strict=True)
    assert [c["id"] for c in out] == ["ok"]


def test_strict_ctc_drops_outside_band_but_keeps_missing():
    """ctc_min/ctc_max with 20% leniency. Missing CTC is SOFT (kept) even in
    strict mode — salary data is missing for ~85% of Indian candidate records.
    Only candidates with KNOWN CTC outside the band are dropped.
    """
    cands = [
        _cand("in_band", current_salary=2_500_000),         # within 2L-4L
        _cand("too_low", current_salary=1_500_000),         # well below
        _cand("too_high", current_salary=6_000_000),        # well above
        _cand("edge_low", current_salary=1_700_000),        # within 20% of 2L floor
        _cand("missing", current_salary=None),              # kept (CTC soft)
    ]
    filters = {"ctc_min": 2_000_000, "ctc_max": 4_000_000}
    out = _apply_structured_filters(cands, filters, strict=True)
    ids = [c["id"] for c in out]
    assert "in_band" in ids
    assert "edge_low" in ids        # 20% leniency
    assert "missing" in ids         # SOFT: kept even in strict mode
    assert "too_low" not in ids
    assert "too_high" not in ids


def test_soft_mode_keeps_missing_fields():
    """Free-text path: missing location/exp/ctc must NOT be dropped."""
    cands = [
        _cand("missing_loc", experience_years=5),
        _cand("missing_exp", current_location="Chennai"),
        _cand("missing_ctc", current_location="Chennai", experience_years=5),
    ]
    filters = {
        "location_include": ["chennai"],
        "min_experience": 3,
        "max_experience": 8,
        "ctc_min": 2_000_000,
        "ctc_max": 4_000_000,
    }
    out = _apply_structured_filters(cands, filters, strict=False)
    # All three are kept because the missing-field rules don't fire in soft mode
    assert {c["id"] for c in out} == {"missing_loc", "missing_exp", "missing_ctc"}


# ── Match-reasons explainer (UI chips) ────────────────────────────────


def test_explain_match_semantic_strong():
    c = {"score": 0.81, "match_type": "vector", "current_location": "Bangalore"}
    rs = _explain_match(c, "react developer bangalore", {}, leg="hybrid")
    labels = [r["label"] for r in rs]
    assert any("Strong semantic" in l for l in labels)
    assert any("Semantic match" in l for l in labels)


def test_explain_match_filter_chips():
    c = {
        "score": 0.62, "match_type": "cross_encoder",
        "current_location": "Bengaluru, KA",
        "experience_years": 8,
        "current_salary": 2_200_000,
        "skills": ["react", "aws"],
    }
    filters = {
        "location_include": ["bangalore"],   # not in cand_loc; should NOT chip
        "min_experience": 5, "max_experience": 10,
        "ctc_min": 2_000_000, "ctc_max": 2_500_000,
        "skills": ["react"],
    }
    rs = _explain_match(c, "react", filters, leg="hybrid")
    labels = [r["label"] for r in rs]
    assert any("Cross-encoder" in l for l in labels)
    assert any("Exp 8y in 5-10y" in l for l in labels)
    assert any("CTC ₹22.0L" in l for l in labels)
    assert any("Skills: React" in l for l in labels)
    # Location chip — "bangalore" now aliases to "bengaluru" so the chip
    # IS produced even though raw strings don't substring-match.
    assert any(l.startswith("Location: Bengaluru") for l in labels)


def test_explain_match_location_alias():
    c = {"current_location": "Bangalore", "score": 0.5, "match_type": "vector"}
    rs = _explain_match(c, "x", {"location_include": ["bangalore"]}, leg="hybrid")
    labels = [r["label"] for r in rs]
    assert any(l.startswith("Location: Bangalore") for l in labels)


def test_explain_match_query_keyword_hits_when_no_skill_filter():
    c = {
        "score": 0.5, "match_type": "vector",
        "current_employer": "Acme Fintech",
        "headline": "Backend engineer",
        "skills": ["python", "kafka"],
    }
    rs = _explain_match(c, "python kafka fintech backend", {}, leg="hybrid")
    labels = [r["label"] for r in rs]
    assert any(l.startswith("Query terms:") for l in labels)


def test_explain_match_ltr_label():
    c = {"score": 0.5, "match_type": "ltr_xgboost"}
    rs = _explain_match(c, "x", {}, leg="hybrid")
    assert any(r["label"] == "AI ranker (LTR)" for r in rs)


def test_explain_match_lexical_skips_semantic_label():
    """Lexical leg must NOT claim semantic match — it's regex only."""
    c = {"current_location": "Pune", "experience_years": 6}
    rs = _explain_match(c, "x", {"location_include": ["pune"], "min_experience": 5, "max_experience": 8}, leg="lexical")
    labels = [r["label"] for r in rs]
    assert not any("Semantic" in l for l in labels)
    assert not any("AI ranker" in l for l in labels)
    assert any(l.startswith("Location:") for l in labels)
    assert any("Exp 6y" in l for l in labels)


def test_explain_match_caps_at_six():
    c = {
        "score": 0.9, "match_type": "vector",
        "current_location": "Mumbai", "experience_years": 7,
        "current_salary": 2_000_000, "skills": ["a", "b", "c", "d", "e"],
    }
    filters = {
        "location_include": ["mumbai"], "min_experience": 5, "max_experience": 10,
        "ctc_min": 1_500_000, "ctc_max": 3_000_000,
        "skills": ["a", "b", "c", "d", "e"],
    }
    rs = _explain_match(c, "engineer mumbai", filters, leg="hybrid")
    assert len(rs) <= 6



# ── City alias resolution (Bangalore ↔ Bengaluru, etc.) ───────────────


def test_expand_location_terms_known_aliases():
    assert set(_expand_location_terms("Bangalore")) == {"bangalore", "bengaluru"}
    assert set(_expand_location_terms("Bengaluru")) == {"bengaluru", "bangalore"}
    assert set(_expand_location_terms("Mumbai")) == {"mumbai", "bombay"}
    assert set(_expand_location_terms("Gurugram")) == {"gurugram", "gurgaon"}


def test_expand_location_terms_unknown_passes_through():
    assert _expand_location_terms("Pune") == ["pune"]
    assert _expand_location_terms("") == []
    assert _expand_location_terms(None) == []


def test_strict_filter_matches_via_alias():
    """Mandate says 'Bangalore', candidate stored as 'Bengaluru' — must match."""
    cands = [
        _cand("A", current_location="Bengaluru", experience_years=8, current_salary=1_500_000),
        _cand("B", current_location="Mumbai",    experience_years=8, current_salary=1_500_000),
    ]
    out = _apply_structured_filters(cands, {"location_include": ["Bangalore"]}, strict=True)
    assert [c["id"] for c in out] == ["A"]


def test_explain_match_chip_uses_alias():
    c = {"current_location": "Bengaluru, KA", "score": 0.5, "match_type": "vector"}
    rs = _explain_match(c, "x", {"location_include": ["Bangalore"]}, leg="hybrid")
    labels = [r["label"] for r in rs]
    assert any(l.startswith("Location: Bengaluru") for l in labels)



# ── Role-signature / relevance (mandate-driven role filter) ────────────


def test_extract_role_signature_pulls_title_and_jd_tokens():
    job = {
        "title": "Utility Project Engineer – Machine Execution Planning",
        "description": "Ensure reliable operation of all utility services (HT/LT power, lighting, compressed air, natural gas, substations). Design AutoCAD layouts for greenfield expansions.",
    }
    tokens = _extract_role_signature(job)
    # Title tokens must be present (with 2× weight) so they rank top
    assert "utility" in tokens
    assert "project" in tokens
    assert "planning" in tokens
    # Generic stopwords must be excluded
    assert "engineer" not in tokens         # too common; in stopwords
    assert "experience" not in tokens
    assert "manager" not in tokens


def test_extract_role_signature_uses_skills_array_when_present():
    job = {
        "title": "Backend Engineer",
        "skills": ["Python", "Kafka", "PostgreSQL"],
        "description": "Build scalable services.",
    }
    tokens = _extract_role_signature(job)
    assert "python" in tokens
    assert "kafka" in tokens
    assert "postgresql" in tokens


def test_role_relevance_designation_match():
    role_tokens = ["utility", "planning", "execution", "machine", "autocad", "gas"]
    c = {
        "current_designation": "Utility Engineer - Planning",
        "skills": ["AutoCAD", "Machine Layout"],
    }
    score, hits = _role_relevance(c, role_tokens)
    assert score >= 0.5
    assert "utility" in hits
    assert "planning" in hits
    assert "autocad" in hits


def test_role_relevance_zero_for_unrelated_role():
    """Area Sales Manager must NOT match a Utility Project Engineer mandate."""
    role_tokens = ["utility", "planning", "execution", "machine", "autocad", "gas", "substation"]
    c = {
        "current_designation": "Area Sales Manager",
        "skills": ["Retail Sales", "CRM", "Excel", "PowerPoint"],
        "summary": "Sales leader for FMCG.",
    }
    score, hits = _role_relevance(c, role_tokens)
    assert score == 0.0
    assert hits == []


def test_role_relevance_empty_tokens_defaults_pass():
    """When the JD has no extractable role signature, every candidate passes
    (returns 1.0) — we don't want to break free-text searches."""
    c = {"current_designation": "Whatever"}
    score, hits = _role_relevance(c, [])
    assert score == 1.0
    assert hits == []

