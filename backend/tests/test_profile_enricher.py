"""Unit tests for the profile enricher (Search Phase 2, 2026-06-15).

These are pure-function unit tests — no DB, no LLM. The LLM tier is
tested separately at smoke-test time against the live RunPod sidecar.
"""
from __future__ import annotations

from services import profile_enricher as pe


# ── Industry ────────────────────────────────────────────────────────

def test_industry_exact_company_name():
    assert pe.infer_industry_from_company("TCS") == "IT/Software"
    assert pe.infer_industry_from_company("Tata Consultancy Services") == "IT/Software"
    assert pe.infer_industry_from_company("HDFC Bank") == "BFSI"
    assert pe.infer_industry_from_company("Mahindra") == "Automotive"


def test_industry_pvt_ltd_normalisation():
    """Company suffixes (Pvt, Ltd, Inc, Corp) must not break the match."""
    assert pe.infer_industry_from_company("Infosys Limited") == "IT/Software"
    assert pe.infer_industry_from_company("Maruti Suzuki India Pvt Ltd") == "Automotive"
    assert pe.infer_industry_from_company("Reliance Industries Limited") == "Energy/Oil & Gas"


def test_industry_unknown_company_returns_none():
    """Returns None on miss → caller's LLM tier fires."""
    assert pe.infer_industry_from_company("Some Tiny Startup We Have Never Heard Of") is None
    assert pe.infer_industry_from_company("") is None
    assert pe.infer_industry_from_company(None) is None


def test_industry_longest_match_wins():
    """`axis bank` (BFSI) wins over `axis` if both substrings were present."""
    # No 'axis' key by itself in the table, so this implicitly tests
    # the longest-match logic against `axis bank`.
    assert pe.infer_industry_from_company("Axis Bank Ltd") == "BFSI"


# ── Seniority ───────────────────────────────────────────────────────

def test_seniority_keywords():
    assert pe.infer_seniority("Senior Software Engineer") == "Senior"
    assert pe.infer_seniority("Lead Data Scientist") == "Lead"
    assert pe.infer_seniority("VP Engineering") == "VP+"
    assert pe.infer_seniority("Engineering Manager") == "Manager"
    assert pe.infer_seniority("Director - Sales") == "Director"
    assert pe.infer_seniority("Software Intern") == "Intern"


def test_seniority_cxo_beats_vp():
    assert pe.infer_seniority("Chief Technology Officer") == "CXO"
    assert pe.infer_seniority("CTO") == "CXO"


def test_seniority_no_signal_returns_none():
    assert pe.infer_seniority("") is None
    assert pe.infer_seniority(None) is None
    assert pe.infer_seniority("Software Engineer") is None  # no senior/lead/etc.


# ── Function ────────────────────────────────────────────────────────

def test_function_devops():
    assert pe.infer_function_domain(["kubernetes", "docker", "terraform"]) == "DevOps/SRE"


def test_function_frontend():
    assert pe.infer_function_domain(["react", "typescript", "css"]) == "Frontend"


def test_function_picks_label_with_most_keyword_hits():
    """A candidate with both backend AND frontend skills should pick the
    label with more hits."""
    # React + Vue + Angular → Frontend (3 hits)
    # Just one node.js → Backend (1 hit)
    skills = ["react", "vue", "angular", "node.js"]
    assert pe.infer_function_domain(skills) == "Frontend"


def test_function_uses_designation_signal():
    """When skills don't fire, designation should still classify."""
    assert pe.infer_function_domain([], designation="Senior DevOps Engineer") == "DevOps/SRE"


def test_function_empty_returns_none():
    assert pe.infer_function_domain([]) is None
    assert pe.infer_function_domain(None) is None


# ── Location ────────────────────────────────────────────────────────

def test_location_aliases():
    assert pe.normalize_location("bglr") == "Bangalore"
    assert pe.normalize_location("Bengaluru") == "Bangalore"
    assert pe.normalize_location("BLR") == "Bangalore"
    assert pe.normalize_location("Bombay") == "Mumbai"
    assert pe.normalize_location("Gurugram") == "Gurgaon"


def test_location_strips_region_suffix():
    """Naukri serves things like 'Bangalore - Karnataka' — we want 'Bangalore'."""
    assert pe.normalize_location("Bangalore - Karnataka") == "Bangalore"


def test_location_unknown_canonicalises_title_case():
    assert pe.normalize_location("nasik") == "Nasik"


def test_location_empty():
    assert pe.normalize_location("") is None
    assert pe.normalize_location(None) is None


# ── Notice period ───────────────────────────────────────────────────

def test_notice_period_immediate():
    assert pe.parse_notice_period_days("currently serving notice, immediate joiner") == 0
    assert pe.parse_notice_period_days("Immediate") == 0


def test_notice_period_days_weeks_months():
    assert pe.parse_notice_period_days("notice period: 90 days") == 90
    assert pe.parse_notice_period_days("Notice period - 60 days") == 60
    assert pe.parse_notice_period_days("2 weeks notice") == 14
    assert pe.parse_notice_period_days("3 months notice") == 90


def test_notice_period_missing():
    assert pe.parse_notice_period_days("Open to work") is None
    assert pe.parse_notice_period_days("") is None
    assert pe.parse_notice_period_days(None) is None


# ── enrich_candidate diff ───────────────────────────────────────────

import asyncio


def test_enrich_candidate_only_returns_missing_fields():
    """If a candidate already has industry, enrich should NOT overwrite."""
    doc = {
        "id": "1",
        "industry": "IT/Software",
        "current_employer": "Mahindra",          # rules would say "Automotive"
        "current_designation": "Senior Engineer",  # would set seniority
        "key_skills": [],
    }
    updates = asyncio.run(pe.enrich_candidate(doc, db=None, allow_llm=False))
    assert "industry" not in updates  # existing value preserved
    assert updates.get("enriched_seniority") == "Senior"


def test_enrich_candidate_full_diff():
    """A bare candidate should pick up all inferable fields."""
    doc = {
        "id": "2",
        "current_employer": "TCS Limited",
        "current_designation": "Lead DevOps Engineer",
        "key_skills": ["kubernetes", "docker", "terraform"],
        "current_location": "Bglr",
        "profile_summary": "3 months notice period; open to relocate.",
    }
    updates = asyncio.run(pe.enrich_candidate(doc, db=None, allow_llm=False))
    assert updates["industry"] == "IT/Software"
    assert updates["enriched_seniority"] == "Lead"
    assert updates["enriched_function"] == "DevOps/SRE"
    assert updates["enriched_location"] == "Bangalore"
    assert updates["notice_period_days"] == 90
    assert "enrichment_meta" in updates
    assert "enriched_at" in updates


def test_enrich_candidate_empty_input():
    assert asyncio.run(pe.enrich_candidate({}, db=None, allow_llm=False)) == {}
    assert asyncio.run(pe.enrich_candidate(None, db=None, allow_llm=False)) == {}
