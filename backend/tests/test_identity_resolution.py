"""Offline identity-resolution regressions; deliberately no config/app imports."""
import copy
import importlib.util
import itertools
import json
import math
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent


def load_standalone(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Importing services normally eagerly initializes cache/storage/embeddings. Load
# this pure module directly so this suite cannot initialize those integrations.
identity = load_standalone(BACKEND / "services" / "identity_resolution.py")
MATCHER_VERSION = identity.MATCHER_VERSION
SIGNATURE_VERSION = identity.SIGNATURE_VERSION
WEIGHTS = identity.WEIGHTS
build_identity_signature = identity.build_identity_signature
canonical_code = identity.canonical_code
normalize_text = identity.normalize_text
resolve_profile = identity.resolve_profile


def rahul(candidate_id="delhi", **updates):
    return {
        "id": candidate_id, "name": "Rahul Sharma", "current_employer": "TCS",
        "location": "Delhi", **updates,
    }


def naukri_input(**updates):
    return rahul(
        naukri_id="source-123",
        identity_evidence={"source": "naukri", "profile_id": "source-123", "provenance": "data-target-id"},
        **updates,
    )


def trusted_naukri(candidate_id="known", **updates):
    return rahul(
        candidate_id, naukri_profile_id="source-123",
        _identity_trusted_anchors=[{
            "source": "naukri", "id": "source-123", "kind": "source_profile",
            "provenance": "server_verified",
        }], **updates,
    )


@pytest.mark.parametrize("value", [None, {}, 7, False, "", "N/A", "Not Disclosed", "UNKNOWN", "***", "R**** Sharma"])
def test_missing_and_masked_values_supply_no_evidence(value):
    assert normalize_text(value) == ""
    assert canonical_code("name", value) == ""


def test_unicode_case_whitespace_and_composed_characters_are_preserved():
    assert normalize_text("  राहुल   शर्मा ") == "राहुल शर्मा"
    assert normalize_text("Jose\u0301") == normalize_text("JOSÉ")
    assert canonical_code("name", "李明") == "name:李明"


def test_aliases_are_field_scoped_and_conservative():
    assert canonical_code("company", "TCS") == canonical_code("company", "Tata Consultancy Services")
    assert canonical_code("location", "Bombay") == canonical_code("location", "Mumbai")
    assert canonical_code("name", "TCS") != canonical_code("company", "TCS")
    assert canonical_code("company", "TCS Logistics") != canonical_code("company", "TCS")
    locations = ["Delhi", "New Delhi", "NCR", "Noida", "Gurgaon", "Mumbai"]
    assert len({canonical_code("location", location) for location in locations}) == len(locations)


def test_programming_languages_do_not_collapse():
    codes = {canonical_code("skill", skill) for skill in ["C", "C++", "C#", ".NET", "NET"]}
    assert len(codes) == 5
    signature = build_identity_signature({"skills": "C, C++; C# | .NET"})
    assert signature["fields"]["skill"] == [".net", "c", "c#", "c++"]


def test_invalid_field_cannot_inject_another_namespace():
    with pytest.raises(ValueError):
        canonical_code("name:company", "TCS")


def test_signature_is_stable_deduplicated_and_does_not_mutate_profile():
    profile = rahul(skills=["C++", "java", "Java"], education=[{"degree": "BTech", "institute": "IIT Delhi"}])
    original = copy.deepcopy(profile)
    signature = build_identity_signature(profile)
    assert profile == original
    assert signature == build_identity_signature(dict(reversed(list(profile.items()))))
    assert signature["version"] == SIGNATURE_VERSION
    assert signature["codes"] == sorted(set(signature["codes"]))
    assert "name_token:rahul" in signature["codes"]
    assert signature["fields"]["education"] == ["btech"]
    assert signature["fields"]["institution"] == ["iit delhi"]


def test_preferred_location_and_headline_do_not_become_current_evidence():
    signature = build_identity_signature({
        "name": "Rahul Sharma", "preferred_location": "Delhi",
        "headline": "Worked at TCS in Delhi", "company_history": ["TCS"],
    })
    assert signature["fields"]["location"] == []
    assert signature["fields"]["company"] == []


def test_rahul_in_delhi_beats_same_name_and_company_in_mumbai():
    result = resolve_profile(rahul(), [rahul("mumbai", location="Mumbai"), rahul()])
    assert result["top_match"]["candidate_id"] == "delhi"
    assert result["second_match"]["candidate_id"] == "mumbai"
    assert result["margin"] == WEIGHTS["location"]
    assert result["decision"] == "probable_match"
    assert result["exists"] is False
    assert result["score_kind"] == "evidence_points"
    assert result["matcher_version"] == MATCHER_VERSION


def test_equal_profiles_remain_ambiguous():
    result = resolve_profile(rahul(), [rahul("a"), rahul("b")])
    assert result["decision"] == "ambiguous"
    assert result["margin"] == 0
    assert result["exists"] is False


def test_missing_location_is_neutral_and_does_not_break_tie():
    result = resolve_profile(
        {"name": "Rahul Sharma", "current_employer": "TCS"},
        [rahul("delhi"), rahul("mumbai", location="Mumbai")],
    )
    assert "location" in result["missing_fields"]
    assert result["margin"] == 0
    assert result["conflicts"] == []
    assert result["decision"] == "ambiguous"


def test_placeholder_equality_cannot_create_probable_match():
    profile = {"name": "Rahul Sharma", "company": "Unknown", "location": "Not Disclosed", "skills": ["N/A"]}
    result = resolve_profile(profile, [{"id": "x", **profile}])
    assert result["matched_signals"] == ["name"]
    assert result["decision"] == "insufficient_data"


def test_even_many_soft_fields_do_not_claim_confirmed_or_calibrated_probability():
    profile = rahul(designation="Senior Engineer", skills=["Java", "C++"], education="IIT Delhi", experience_years=8)
    result = resolve_profile(profile, [{**profile, "id": "x"}])
    assert result["decision"] == "probable_match"
    assert result["match_score"] > 1
    assert result["exists"] is False
    assert not any("probability" in key for key in result)


def test_repeated_skills_and_headline_cannot_inflate_evidence():
    profile = rahul(skills=["Java"], designation="Engineer")
    base = resolve_profile(profile, [profile])
    inflated = resolve_profile(
        {**profile, "skills": ["Java"] * 40, "headline": "TCS Engineer Delhi Java"},
        [{**profile, "skills": ["Java"] * 40}],
    )
    assert base["match_score"] == inflated["match_score"]
    assert base["match_score"] == WEIGHTS["name"] + WEIGHTS["employment_cap"] + WEIGHTS["location"] + WEIGHTS["skill"]


def test_unrelated_rich_profile_does_not_bury_sparsely_observed_name_match():
    profile = rahul(skills=["Java"], designation="Engineer", education="IIT Delhi", experience_years=7)
    result = resolve_profile(profile, [
        {**profile, "id": "different", "name": "Amit Gupta"},
        {"id": "right-name", "name": "Rahul Sharma"},
    ])
    assert result["top_match"]["candidate_id"] == "right-name"
    assert result["exists"] is False


def test_unverified_legacy_id_does_not_confirm():
    result = resolve_profile(naukri_input(), [rahul(naukri_profile_id="source-123")])
    assert result["decision"] == "probable_match"
    assert result["exists"] is False
    assert "source_id_hint" in result["matched_signals"]


def test_forged_verification_flags_do_not_confirm():
    profile = naukri_input(verified=True, _identity_trusted_anchors=trusted_naukri()["_identity_trusted_anchors"])
    candidate = rahul(naukri_profile_id="source-123", verified=True, source_id_verified=True)
    assert resolve_profile(profile, [candidate])["exists"] is False


@pytest.mark.parametrize("provenance", ["pid", "sid", "query_param", "checkbox", "verified", None])
def test_unapproved_dom_id_provenance_cannot_confirm(provenance):
    profile = naukri_input()
    profile["identity_evidence"]["provenance"] = provenance
    assert resolve_profile(profile, [trusted_naukri()])["exists"] is False


def test_unique_server_trusted_source_anchor_with_name_guard_confirms_source_profile():
    result = resolve_profile(naukri_input(), [trusted_naukri()])
    assert result["decision"] == "confirmed_duplicate"
    assert result["exists"] is True
    assert "unique_trusted_source_profile" in result["reason_codes"]
    assert "trusted_source_profile" in result["matched_signals"]
    assert "source_id_hint" not in result["matched_signals"]


def test_moving_city_or_changing_company_does_not_invalidate_verified_source_profile():
    result = resolve_profile(naukri_input(), [trusted_naukri(location="Mumbai", current_employer="Infosys")])
    assert result["decision"] == "confirmed_duplicate"
    assert set(result["conflicts"]) == {"location_differs", "company_differs"}


def test_source_anchor_name_conflict_requires_review():
    result = resolve_profile(naukri_input(), [trusted_naukri(name="Amit Gupta")])
    assert result["decision"] == "ambiguous"
    assert result["exists"] is False
    assert "source_anchor_name_conflict" in result["reason_codes"]


def test_contradictory_middle_names_fail_anchor_name_guard():
    result = resolve_profile(naukri_input(name="Rahul Kumar Sharma"), [trusted_naukri(name="Rahul Mohan Sharma")])
    assert result["decision"] == "ambiguous"
    assert result["exists"] is False


def test_omitted_middle_name_is_compatible():
    result = resolve_profile(naukri_input(), [trusted_naukri(name="Rahul Kumar Sharma")])
    assert result["exists"] is True
    assert "name_compatible" in result["matched_signals"]


def test_shared_source_anchor_across_two_rows_is_ambiguous_even_when_one_name_differs():
    result = resolve_profile(naukri_input(), [trusted_naukri("a"), trusted_naukri("b", name="Amit Gupta")])
    assert result["decision"] == "ambiguous"
    assert "source_anchor_multiple_records" in result["reason_codes"]


def test_contact_changes_and_resume_hash_are_not_identity_proof():
    profile = rahul(email="a@example.test", phone="123", resume_fingerprint="same")
    candidate = rahul(email="b@example.test", phone="456", resume_fingerprint="same")
    result = resolve_profile(profile, [candidate])
    assert result["decision"] == "probable_match"
    assert result["conflicts"] == []


def test_permutation_invariance_including_tied_records():
    records = [rahul("a"), rahul("b"), rahul("mumbai", location="Mumbai")]
    results = [resolve_profile(rahul(), list(order)) for order in itertools.permutations(records)]
    assert all(result == results[0] for result in results)


@pytest.mark.parametrize("candidates,expected", [([], "insufficient_data"), ([trusted_naukri()], "ambiguous")])
def test_incomplete_retrieval_never_claims_unique_match(candidates, expected):
    result = resolve_profile(naukri_input(), candidates, retrieval_complete=False)
    assert result["decision"] == expected
    assert result["exists"] is False
    assert "retrieval_incomplete" in result["reason_codes"]


def test_empty_complete_search_does_not_claim_person_is_new():
    result = resolve_profile(rahul(), [])
    assert result["decision"] == "no_match_found"
    assert result["top_match"] is None
    assert result["second_match"] is None
    assert result["margin"] is None


@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/in/rahul-sharma/", "https://in.linkedin.com/in/rahul-sharma?trk=search",
])
def test_even_canonical_linkedin_urls_do_not_supply_identity(url):
    assert build_identity_signature({"profile_url": url}) == build_identity_signature({})


@pytest.mark.parametrize("url", [
    "http://www.linkedin.com/in/rahul-sharma", "https://linkedin.com.evil.test/in/rahul-sharma",
    "https://evil.test/?profile=https://linkedin.com/in/rahul-sharma", "https://www.linkedin.com/company/tcs",
    "https://linkedin.com/in/rahul-sharma/posts", "https://linkedin.com/in/rahul%2Fsharma",
    "https://user:secret@linkedin.com/in/rahul-sharma", "https://linkedin.com:8080/in/rahul-sharma",
    "https://resdex.naukri.com/profile?pid=source-123", "https://resdex.naukri.com/profile?sid=source-123",
    "https://linkedin.com:invalid/in/rahul-sharma", None, {},
])
def test_urls_with_unvalidated_identity_semantics_are_rejected(url):
    assert build_identity_signature({"profile_url": url}) == build_identity_signature({})


def test_even_identical_canonical_urls_cannot_confirm_identity():
    anchor = {"source": "linkedin", "id": "rahul-sharma", "kind": "source_profile",
              "provenance": "canonical_profile_url", "canonical_url": "https://linkedin.com/in/rahul-sharma/"}
    candidate = rahul(_identity_trusted_anchors=[anchor])
    profile = rahul(identity_evidence={
        "source": "linkedin", "profile_id": "rahul-sharma", "provenance": "canonical_profile_url",
        "profile_url": "https://linkedin.com/in/someone-else/",
    })
    assert resolve_profile(profile, [candidate])["exists"] is False
    profile["identity_evidence"]["profile_url"] = anchor["canonical_url"]
    assert resolve_profile(profile, [candidate])["exists"] is False


def test_name_alone_or_unusable_input_is_insufficient():
    assert resolve_profile({"name": "Rahul Sharma"}, [rahul()])["decision"] == "insufficient_data"
    assert resolve_profile({}, [rahul()])["decision"] == "insufficient_data"


def test_resolver_does_not_mutate_candidate_or_request_data():
    profile, candidates = naukri_input(), [trusted_naukri()]
    before = copy.deepcopy((profile, candidates))
    resolve_profile(profile, candidates)
    assert (profile, candidates) == before


def test_current_designation_alias_and_alternative_source_url_fields():
    profile = {"current_designation": "Engineer", "source_details": {"profile_url": "https://linkedin.com/in/rahul-sharma/"}}
    signature = build_identity_signature(profile)
    assert signature["fields"]["title"] == ["engineer"]
    assert signature["source_ids"]["linkedin"] == []
    assert build_identity_signature({"source_profile_url": "https://linkedin.com/in/rahul-sharma/"})["source_ids"] == signature["source_ids"]


def test_corpus_document_frequency_downweights_common_codes_only():
    profile = rahul(skills=["Java", "C++"])
    codes = build_identity_signature(profile)["codes"]
    rare = {code: 1 for code in codes}
    common = {code: 1000 for code in codes}
    baseline = resolve_profile(profile, [profile])
    rare_result = resolve_profile(profile, [profile], code_frequencies=rare, population_size=1000)
    common_result = resolve_profile(profile, [profile], code_frequencies=common, population_size=1000)
    assert rare_result["match_score"] == baseline["match_score"]
    assert common_result["match_score"] < rare_result["match_score"]
    assert all(0.2 <= item["factor"] <= 1 for item in common_result["frequency_adjustments"])
    assert "corpus_frequencies_unavailable" in baseline["reason_codes"]
    assert common_result["corpus_frequencies_available"] is True
    assert common_result["decision"] == "insufficient_data"
    assert not common_result["exists"]


@pytest.mark.parametrize("count", [0, -1, 101, 0.5, float("nan"), True, "1", None])
def test_invalid_corpus_counts_are_disclosed_and_do_not_boost_scores(count):
    profile = rahul()
    baseline = resolve_profile(profile, [profile])
    codes = build_identity_signature(profile)["codes"]
    result = resolve_profile(profile, [profile], code_frequencies={code: count for code in codes}, population_size=100)
    assert result["match_score"] == baseline["match_score"]
    assert "corpus_frequency_coverage_partial" in result["reason_codes"]


@pytest.mark.parametrize("population", [0, -1, 1.5, float("nan"), True, None])
def test_invalid_population_uses_baseline_with_unavailable_reason(population):
    result = resolve_profile(rahul(), [rahul()], code_frequencies={"name:rahul sharma": 1}, population_size=population)
    assert "corpus_frequencies_unavailable" in result["reason_codes"]
    assert result["corpus_frequencies_available"] is False


def test_ranking_does_not_estimate_frequencies_from_retrieved_subset():
    profile = rahul()
    frequencies = {code: 10 for code in build_identity_signature(profile)["codes"]}
    baseline = resolve_profile(profile, [profile], code_frequencies=frequencies, population_size=1000)
    crowded = resolve_profile(profile, [profile] + [rahul(str(i), name="Amit Gupta") for i in range(30)],
                              code_frequencies=frequencies, population_size=1000)
    assert baseline["match_score"] == crowded["match_score"]
    assert baseline["top_match"] == crowded["top_match"]


def test_corpus_weighting_cannot_suppress_trusted_source_profile_anchor():
    profile, candidate = naukri_input(), trusted_naukri()
    frequencies = {code: 1000 for code in build_identity_signature(profile)["codes"]}
    result = resolve_profile(profile, [candidate], code_frequencies=frequencies, population_size=1000)
    assert result["decision"] == "confirmed_duplicate"
    assert result["match_score"] >= WEIGHTS["trusted_source_profile"]


def test_plain_experience_text_does_not_become_company_title_and_location():
    signature = build_identity_signature({"experience": "TCS, Engineer, Mumbai", "education": "BTech"})
    for field in ("experience_company", "experience_title", "experience_location", "institution"):
        assert signature["fields"][field] == []
    assert signature["context"]["employment"] == []


def test_explicitly_typed_history_strings_are_kept_in_their_own_field():
    signature = build_identity_signature({"company_history": ["TCS"], "title_history": ["Engineer"], "location_history": ["Bombay"]})
    assert signature["fields"]["experience_company"] == ["tata consultancy services"]
    assert signature["fields"]["experience_title"] == ["engineer"]
    assert signature["fields"]["experience_location"] == ["mumbai"]
    assert signature["context"]["employment"] == [{"company": "tata consultancy services", "kind": "history"}]


def test_school_does_not_double_count_as_degree_and_institution():
    profile = {"name": "Rahul Sharma", "education": [{"institution": "IIT Delhi"}]}
    result = resolve_profile(profile, [{"id": "x", **profile}])
    assert "institution" in result["matched_signals"]
    assert "education" not in result["matched_signals"]
    assert result["match_score"] == WEIGHTS["name"] + WEIGHTS["institution"]


def test_degree_and_school_share_one_education_group_cap():
    profile = {"name": "Rahul Sharma", "education": [{"degree": "BTech", "institution": "IIT Delhi"}]}
    result = resolve_profile(profile, [{"id": "x", **profile}])
    assert {"education", "institution"}.issubset(result["matched_signals"])
    assert result["match_score"] == WEIGHTS["name"] + WEIGHTS["education_cap"]


def test_issuer_only_is_not_a_matching_certification():
    profile = {"name": "Rahul Sharma", "certifications": [{"issuer": "Microsoft"}]}
    assert build_identity_signature(profile)["fields"]["certification"] == []
    assert "certification" not in resolve_profile(profile, [{"id": "x", **profile}])["matched_signals"]


def test_current_company_and_role_match_past_record_without_claiming_identity():
    profile = {"name": "Rahul Sharma", "company": "TCS", "designation": "Engineer", "location": "Mumbai"}
    candidate = {"id": "past", "name": "Rahul Sharma", "experience": [{"company": "Tata Consultancy Services", "title": "Engineer", "location": "Bombay"}]}
    result = resolve_profile(profile, [candidate])
    assert {"experience_company", "experience_title", "experience_location"}.issubset(result["matched_signals"])
    assert result["exists"] is False
    reverse = resolve_profile(candidate, [{**profile, "id": "current"}])
    assert reverse["match_score"] == result["match_score"]


def test_unrelated_roles_at_different_employers_are_not_combined():
    profile = {"name": "Rahul Sharma", "experience": [{"company": "TCS", "title": "Engineer"}, {"company": "Infosys", "title": "Manager"}]}
    swapped = {"id": "swapped", "name": "Rahul Sharma", "experience": [{"company": "TCS", "title": "Manager"}, {"company": "Infosys", "title": "Engineer"}]}
    matched = {"id": "matched", **profile}
    result = resolve_profile(profile, [swapped, matched])
    assert result["top_match"]["candidate_id"] == "matched"
    assert "experience_title" not in result["second_match"]["matched_signals"]
    assert result["top_match"]["score"] > result["second_match"]["score"]


def test_repeating_current_job_in_history_does_not_inflate_same_evidence():
    profile = rahul(designation="Engineer")
    repeated = {**profile, "experience": [{"company": "TCS", "title": "Engineer", "location": "Delhi"}] * 20}
    base = resolve_profile(profile, [profile])
    result = resolve_profile(repeated, [repeated])
    assert result["match_score"] == base["match_score"]
    assert not set(result["matched_signals"]) & {"experience_company", "experience_title", "experience_location"}


def test_history_context_is_bounded_and_preserves_current_record():
    profile = rahul(experience=[{"company": f"Company {index}", "title": "Engineer"} for index in range(500)])
    signature = build_identity_signature(profile)
    assert len(signature["context"]["employment"]) <= 40
    assert len(signature["fields"]["experience_company"]) <= 40
    assert signature["context"]["employment"][0]["kind"] == "current"


def test_massive_soft_context_cannot_outrank_unique_anchor_after_frequency_weighting():
    profile = naukri_input(
        designation="Engineer", skills=["Java"], experience_years=8,
        experience=[{"company": "Infosys", "title": "Developer", "location": "Mumbai"}],
        education=[{"degree": "BTech", "institution": "IIT Delhi"}],
        certifications=["AWS Architect"], projects=["Platform"], languages=["English"],
    )
    rich = {**profile, "id": "rich-soft"}
    anchor = trusted_naukri("unique-source", name="Rahul Kumar Sharma", current_employer=None, location=None)
    frequencies = {"name:rahul kumar sharma": 1000}
    result = resolve_profile(profile, [rich, anchor], code_frequencies=frequencies, population_size=1000)
    assert result["top_match"]["candidate_id"] == "unique-source"
    assert result["decision"] == "confirmed_duplicate"
    assert result["second_match"]["score"] <= identity.SOFT_SCORE_CAP
    assert result["top_match"]["source_anchor_points"] == WEIGHTS["trusted_source_profile"]


def test_authoritative_complete_flag_without_actual_anchor_cannot_bypass_incomplete_retrieval():
    result = resolve_profile(rahul(), [rahul()], retrieval_complete=False, authoritative_retrieval_complete=True)
    assert result["decision"] == "ambiguous"
    assert "retrieval_incomplete" in result["reason_codes"]
    assert result["exists"] is False


@pytest.mark.parametrize("left,right,expected", [
    ("Rahul Sharma", "Rahul Kumar Sharma", True),
    ("Rahul Kumar Sharma", "Rahul Mohan Sharma", False),
    ("Rahul", "Rahul", False),
    ("Dr. Rahul", "Rahul", False),
    ("राहुल शर्मा", "राहुल शर्मा", True),
    ("Unknown", "Unknown", False),
])
def test_public_capture_name_guard_requires_multiple_meaningful_tokens(left, right, expected):
    assert identity.names_are_compatible(left, right, require_multiple_tokens=True) is expected


evaluation = load_standalone(BACKEND / "scripts" / "evaluate_identity_resolution.py")


def test_exact_one_sided_precision_lower_bound_against_closed_form_cases():
    assert evaluation.precision_lower_bound(0, 0) == 0
    assert evaluation.precision_lower_bound(0, 10) == 0
    assert evaluation.precision_lower_bound(10, 10) == pytest.approx(0.05 ** 0.1)
    assert evaluation.precision_lower_bound(1, 2) == pytest.approx(1 - math.sqrt(0.95))
    lower = evaluation.precision_lower_bound(2, 3)
    assert 3 * lower ** 2 - 2 * lower ** 3 == pytest.approx(0.05)
    assert evaluation.precision_lower_bound(298, 298) < 0.99
    assert evaluation.precision_lower_bound(299, 299) >= 0.99


@pytest.mark.parametrize("successes,total", [(1, 0), (-1, 3), (1.5, 3), (True, 3), (0, -1)])
def test_invalid_precision_denominators_are_rejected(successes, total):
    with pytest.raises(ValueError):
        evaluation.precision_lower_bound(successes, total)


def test_synthetic_evaluation_has_correct_denominators_and_cannot_pass_release_gate():
    cases = json.loads((BACKEND / "tests" / "fixtures" / "identity_resolution_cases.json").read_text(encoding="utf-8"))["cases"]
    report = evaluation.evaluate_cases(cases)
    assert report["dataset"]["cases"] == 9
    assert report["decisions"]["accuracy"] == 1
    assert report["confirmed"]["precision"] == 1
    assert report["confirmed"]["recall"] == pytest.approx(1 / 7)
    assert report["confirmed"]["precision_lower_95_one_sided"] == pytest.approx(0.05)
    assert report["top_choice"]["evaluated"] == 6
    assert report["top_choice"]["accuracy"] == pytest.approx(5 / 6)
    assert report["retrieval"]["recall"] == pytest.approx(6 / 7)
    assert report["longitudinal_context"]["cases_observing_context"] == 1
    assert report["longitudinal_context"]["top_matches_using_context"] == 1
    assert report["review"]["coverage"] == pytest.approx(7 / 9)
    assert report["release_gate"] is False
    assert "synthetic_labels_cannot_establish_production_precision" in report["release_gate_reasons"]


def test_evaluation_zero_confirmations_reports_unavailable_precision_not_perfect_precision():
    report = evaluation.evaluate_cases([{
        "profile": rahul(), "candidates": [rahul()], "expected_candidate_id": "delhi", "label_source": "human",
    }])
    assert report["confirmed"]["precision"] is None
    assert report["confirmed"]["recall"] == 0
    assert report["release_gate"] is False
    assert "no_evaluated_confirmations" in report["release_gate_reasons"]


def test_evaluation_counts_wrong_confirmation_as_error_and_duplicate_queries_cannot_inflate_gate():
    case = {"profile": naukri_input(), "candidates": [trusted_naukri()], "expected_candidate_id": None, "label_source": "human"}
    report = evaluation.evaluate_cases([case, copy.deepcopy(case)])
    assert report["confirmed"]["incorrect"] == 2
    assert report["confirmed"]["precision"] == 0
    assert "duplicate_query_observations" in report["release_gate_reasons"]
    assert report["release_gate"] is False


@pytest.mark.parametrize("case", [
    {}, {"profile": {}, "candidates": [], "label_source": "human"},
    {"profile": {}, "candidates": [], "expected_candidate_id": "", "label_source": "human"},
    {"profile": {}, "candidates": [], "expected_candidate_id": None, "label_source": "model"},
    {"profile": {}, "candidates": [], "expected_candidate_id": None, "label_source": "human", "retrieval_complete": "true"},
])
def test_evaluation_requires_explicit_valid_ground_truth(case):
    with pytest.raises(ValueError):
        evaluation.evaluate_cases([case])
