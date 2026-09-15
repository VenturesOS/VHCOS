"""
Regression tests for the `skills_lc / current_company_lc / location_lc`
normalization migration (2026-09-15). Covers:

1. normalize_candidate() populates the three mirrors from any of the
   raw field aliases (skills / key_skills, current_company /
   current_employer, location / current_location).
2. The mirrors are lowercased and stripped.
3. Missing values yield None (not empty string) so the sparse indexes
   backing /candidate-bank/facets remain sparse.
4. Idempotency — re-normalizing a doc that already carries the mirrors
   yields the same result.
"""
from services.schema_normalizer import normalize_candidate


def test_skills_lc_populated_and_lowercased():
    doc = normalize_candidate({"skills": ["Python", "React.js", " Java "]})
    assert doc["skills_lc"] == ["python", "react.js", "java"]
    # Raw skills preserved untouched
    assert doc["skills"] == ["Python", "React.js", "Java"]


def test_skills_lc_reads_key_skills_alias():
    doc = normalize_candidate({"key_skills": ["Go", "Rust"]})
    assert set(doc["skills_lc"]) == {"go", "rust"}


def test_current_company_lc_from_canonical():
    doc = normalize_candidate({"current_company": "Infosys BPM"})
    assert doc["current_company_lc"] == "infosys bpm"


def test_current_company_lc_falls_back_to_current_employer():
    # Common in the 170 k backlog: only alias populated.
    doc = normalize_candidate({"current_employer": "Info Edge"})
    assert doc["current_company_lc"] == "info edge"


def test_location_lc_from_canonical():
    doc = normalize_candidate({"location": "Bangalore"})
    assert doc["location_lc"] == "bangalore"


def test_location_lc_falls_back_to_current_location():
    doc = normalize_candidate({"current_location": "Mumbai, MH"})
    assert doc["location_lc"] == "mumbai, mh"


def test_missing_scalar_fields_yield_none():
    """Sparse index backing /facets stays sparse when values are absent."""
    doc = normalize_candidate({"name": "Jane"})
    assert doc["current_company_lc"] is None
    assert doc["location_lc"] is None
    assert doc["skills_lc"] == []  # empty list — matches the multikey index


def test_normalize_is_idempotent_on_lc_fields():
    seed = {"skills": ["Java"], "current_company": "Google", "location": "London"}
    once = normalize_candidate(seed)
    twice = normalize_candidate(once)
    assert twice["skills_lc"] == once["skills_lc"]
    assert twice["current_company_lc"] == once["current_company_lc"]
    assert twice["location_lc"] == once["location_lc"]
