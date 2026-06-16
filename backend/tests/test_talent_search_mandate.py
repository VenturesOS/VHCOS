"""Regression for the mandate-driven search path (/api/talent/search?job_id).

Tests the pure `_build_query_from_job` helper — composes a hybrid-search
input from a job document. Real end-to-end test happens in the manual
smoke at PRD time.
"""
from __future__ import annotations

from routes.talent_search import _build_query_from_job


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
