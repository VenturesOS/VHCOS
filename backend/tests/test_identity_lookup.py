"""Offline integration tests: real retrieval + resolver, deterministic fake Mongo.

No application config, credentials, cloud services, or LLMs are imported. Query
matching runs against fixture documents, so tests exercise candidate retrieval
as well as ranking rather than merely returning the requested answer.
"""
import asyncio
import copy
import importlib.util
import re
import sys
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "services"))
import identity_lookup  # noqa: E402
from identity_lookup import lookup_one, lookup_profiles, public_profile, retrieval_paths  # noqa: E402
from identity_resolution import build_identity_signature  # noqa: E402


def values_at(doc, path):
    nodes = [doc]
    for part in path.split("."):
        next_nodes = []
        for node in nodes:
            if isinstance(node, dict) and part in node:
                value = node[part]
                next_nodes.extend(value if isinstance(value, list) else [value])
        nodes = next_nodes
    return nodes


def matches(doc, query):
    for key, expected in query.items():
        if key == "$and":
            if not all(matches(doc, item) for item in expected):
                return False
        elif key == "$or":
            if not any(matches(doc, item) for item in expected):
                return False
        else:
            actual = values_at(doc, key)
            if isinstance(expected, dict) and "$in" in expected:
                if not any(item in expected["$in"] for item in actual):
                    return False
            elif isinstance(expected, dict) and "$regex" in expected:
                flags = re.IGNORECASE if "i" in expected.get("$options", "") else 0
                if not any(isinstance(item, str) and re.search(expected["$regex"], item, flags) for item in actual):
                    return False
            elif expected not in actual:
                return False
    return True


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.cap = len(rows)

    def sort(self, key, _direction):
        self.rows = sorted(self.rows, key=lambda row: row.get(key, ""))
        return self

    def limit(self, count):
        self.cap = count
        return self

    def max_time_ms(self, milliseconds):
        assert milliseconds > 0
        return self

    async def to_list(self, count):
        return copy.deepcopy(self.rows[:min(count, self.cap)])


class Bank:
    def __init__(self, rows, fail=False):
        self.rows = rows
        self.fail = fail
        self.queries = []

    def find(self, query, projection):
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("fixture database failure")
        selected = [row for row in self.rows if matches(row, query)]
        return Cursor([{k: v for k, v in row.items() if projection.get(k)} for row in selected])


def database(rows, fail=False):
    return types.SimpleNamespace(candidate_bank=Bank(copy.deepcopy(rows), fail=fail))


def candidate(cid, location, **extra):
    data = dict(id=cid, name="Rahul Sharma", name_lower="rahul sharma", current_employer="TCS",
                location=location, designation="Backend Engineer", skills=["Java", "Spring"],
                experience_years=8, **extra)
    data["identity"] = build_identity_signature(data)
    return data


def test_delhi_mumbai_end_to_end_and_top_two_are_returned():
    rows = [candidate("A", "Mumbai"), candidate("B", "Delhi")]
    incoming = {k: v for k, v in rows[1].items() if k not in ("id", "identity")}
    result = asyncio.run(lookup_one(database(rows), incoming))
    assert result["top_match"]["candidate_id"] == "B"
    assert result["second_match"]["candidate_id"] == "A"
    assert result["margin"] > 0
    assert result["decision"] == "probable_match"
    assert result["exists"] is False
    assert result["score_kind"] == "evidence_points"


def observed_database(rows, observations):
    db = database(rows)
    db.identity_observations = Bank(copy.deepcopy(observations))
    return db


def linked_observation(oid, cid, snapshot, status="linked"):
    return {"id": oid, "candidate_id": cid, "status": status, "snapshot": snapshot,
            "observed_at": "2026-09-17T00:00:00+00:00", "revision": 1,
            "identity": build_identity_signature(snapshot)}


def test_reviewed_snapshot_retrieves_canonical_person_after_name_and_job_change():
    saved = candidate("permanent-person", "Mumbai")
    saved.update(name="R S Rao", name_lower="r s rao", current_employer="Other Company",
                 designation="Director", skills=["Management"])
    saved["identity"] = build_identity_signature(saved)
    historical = candidate("not-a-person-id", "Delhi", email="private@example.test")
    incoming = {k: v for k, v in historical.items() if k not in ("id", "identity", "email")}
    db = observed_database([saved], [linked_observation("observation-1", saved["id"], historical)])
    result = asyncio.run(lookup_one(db, incoming))
    top = result["top_match"]
    assert top["candidate_id"] == "permanent-person"
    assert top["evidence_observation_id"] == "observation-1"
    assert top["context"]["location"] == "Delhi"
    assert top["current_context"]["location"] == "Mumbai"
    assert result["retrieval_stats"]["observation_views_loaded"] == 1
    assert result["exists"] is False  # Review is not proof the newly viewed card is this person.
    assert "private@example.test" not in str(result)


@pytest.mark.parametrize("status", ["unresolved", "deferred", "resolving"])
def test_unreviewed_or_unlinked_observations_do_not_invent_people(status):
    snapshot = candidate("old", "Delhi")
    db = observed_database([], [linked_observation("obs", "missing-person", snapshot, status)])
    result = asyncio.run(lookup_one(db, snapshot))
    assert not result.get("top_match")
    assert result["retrieval_stats"]["observation_views_loaded"] == 0


def test_orphaned_observation_reports_incomplete_instead_of_existing_person():
    snapshot = candidate("old", "Delhi")
    db = observed_database([], [linked_observation("obs", "missing-person", snapshot)])
    result = asyncio.run(lookup_one(db, snapshot))
    assert not result.get("top_match")
    assert result["retrieval_complete"] is False
    assert "linked_observation_candidate_missing" in result["reason_codes"]


def test_many_observations_are_one_person_and_view_limit_is_explicit():
    saved = candidate("person", "Delhi")
    db = observed_database([saved], [linked_observation(f"obs-{i}", "person", saved) for i in range(12)])
    result = asyncio.run(lookup_one(db, saved))
    assert len(result["ranked_matches"]) == 1
    assert result["retrieval_stats"]["observation_views_loaded"] == 8
    assert result["retrieval_complete"] is False
    assert "retrieval_capped:linked_observation_views:person" in result["reason_codes"]


def test_observation_outage_never_masquerades_as_complete_search():
    saved = candidate("person", "Delhi")
    db = observed_database([saved], [])
    db.identity_observations.fail = True
    result = asyncio.run(lookup_one(db, saved))
    assert result["top_match"]["candidate_id"] == "person"
    assert result["retrieval_complete"] is False
    assert result["exists"] is False


def test_company_alias_retrieval_survives_name_initials():
    row = candidate("A", "Delhi")
    row["name"] = "R Sharma"
    row["name_lower"] = "r sharma"
    row["identity"] = build_identity_signature(row)
    profile = {"name": "Rahul Sharma", "current_employer": "Tata Consultancy Services", "location": "Delhi"}
    db = database([row])
    result = asyncio.run(lookup_one(db, profile))
    assert any(matches(row, query) for query in db.candidate_bank.queries)
    assert "name_company" in result["retrieval_paths"]


def test_legacy_bank_without_codes_remains_searchable():
    row = candidate("legacy", "Delhi")
    row.pop("identity")
    result = asyncio.run(lookup_one(database([row]), row))
    assert result["top_match"]["candidate_id"] == "legacy"
    assert any(p.startswith("legacy_name:") for p in result["retrieval_paths"])


def test_unicode_name_retrieval():
    row = {"id": "unicode", "name": "राहुल शर्मा", "location": "Delhi"}
    result = asyncio.run(lookup_one(database([row]), row))
    assert result["top_match"]["candidate_id"] == "unicode"


def test_current_raw_fields_override_stale_code_index():
    row = candidate("changed", "Delhi")
    row["location"] = "Mumbai"
    other = candidate("current", "Delhi")
    result = asyncio.run(lookup_one(database([row, other]), other))
    assert result["top_match"]["candidate_id"] == "current"


def test_context_never_stringifies_malformed_nested_records():
    row = candidate("malformed-context", "Delhi")
    row["education_details"] = [{"institution": {"email": "private@person.test", "raw_text": "secret"}}]
    row["experience"] = [{"company": {"phone": "9876543210"}, "title": "Engineer"}]
    context = identity_lookup.compact_candidate_context(row)
    assert "education" not in context
    assert context["work_history"] == ["Engineer"]


def test_compound_context_path_recovers_target_beyond_common_name_cap():
    # The exact-name path is deliberately capped. A compound code intersection
    # must still retrieve the late-sorting Delhi record instead of treating the
    # first 100 Rahul Sharma rows as the whole corpus.
    decoys = [candidate(f"decoy-{index:03d}", "Mumbai") for index in range(150)]
    target = candidate("zz-target", "Delhi")
    result = asyncio.run(lookup_one(database(decoys + [target]), target, path_limit=100))
    assert result["top_match"]["candidate_id"] == "zz-target"
    assert "name_company_location" in result["retrieval_paths"]
    assert result["retrieval_stats"]["paths_capped"] >= 1
    assert result["decision"] in {"ambiguous", "probable_match"}


def test_longitudinal_context_is_retrieved_and_explained_without_contacts():
    row = candidate(
        "history", "Delhi", experience=[{
            "company": "Infosys", "designation": "Engineer", "location": "Pune",
        }], education=[{"degree": "BTech", "institute": "IIT Delhi"}],
        certifications=[{"name": "AWS Certified Developer"}],
        projects=[{"name": "Payments Platform"}], languages=["Hindi", "English"],
    )
    profile = {
        "name": "Rahul Sharma", "current_employer": "TCS", "location": "Delhi",
        "experience": [{"company": "Infosys", "designation": "Engineer", "location": "Pune"}],
        "education": [{"degree": "BTech", "institute": "IIT Delhi"}],
        "certifications": [{"name": "AWS Certified Developer"}],
        "projects": [{"name": "Payments Platform"}], "languages": ["Hindi"],
    }
    result = asyncio.run(lookup_one(database([row]), profile))
    top = result["top_match"]
    assert top["candidate_id"] == "history"
    assert "experience_company" in top["matched_signals"]
    assert "institution" in top["matched_signals"]
    assert "name_experience_company" in result["retrieval_paths"]
    assert top["context"]["work_history"] == ["Infosys", "Engineer", "Pune"]
    assert any(item["field"] == "experience_company" and item["status"] == "match"
               for item in top["evidence"])
    # Context packets are deliberately not contact/resume dumps.
    assert "email" not in top["context"] and "phone" not in top["context"]


def test_transport_cannot_inject_trusted_anchor_or_signature():
    raw = {"name": "Rahul Sharma", "_identity_trusted_anchors": [{"source": "naukri", "id": "x"}],
           "identity_evidence": {"source": "naukri", "profile_id": "x", "provenance": "server_verified"},
           "identity": {"verified": True}, "verified": True}
    clean = public_profile(raw)
    assert set(clean) == {"name", "profile_url"}


def test_unverified_naukri_id_never_confirms():
    row = candidate("naukri", "Delhi", naukri_profile_id="naukri_84721")
    incoming = dict(name="Rahul Sharma", naukri_id="84721", source="naukri", source_id_kind="data-target-id")
    result = asyncio.run(lookup_one(database([row]), incoming))
    assert result["top_match"]["candidate_id"] == "naukri"
    assert not result["exists"]


def test_capture_success_cannot_promote_unverified_naukri_id():
    row = candidate(
        "naukri-verified", "Delhi", naukri_profile_id="84721",
        source_details={"identity_anchor": {
            "source": "naukri", "id": "84721", "kind": "source_profile",
            "provenance": "capture_verified", "observed_at": "2026-09-10T00:00:00Z",
        }},
    )
    incoming = {"name": "Rahul Sharma", "source": "naukri", "naukri_id": "84721",
                "source_id_kind": "data-target-id"}
    result = asyncio.run(lookup_one(database([row]), incoming))
    assert result["decision"] != "confirmed_duplicate"
    assert result["exists"] is False
    assert "trusted_source_profile" not in result["matched_signals"]


def test_capture_anchor_must_agree_with_stored_source_id():
    row = candidate(
        "mismatched-anchor", "Delhi", naukri_profile_id="actual-id",
        source_details={"identity_anchor": {
            "source": "naukri", "id": "different-id", "kind": "source_profile",
            "provenance": "capture_verified", "observed_at": "2026-09-10T00:00:00Z",
        }},
    )
    result = asyncio.run(lookup_one(database([row]), {
        "name": "Rahul Sharma", "source": "naukri", "naukri_id": "different-id",
        "source_id_kind": "data-target-id",
    }))
    assert result["decision"] != "confirmed_duplicate"
    assert result["exists"] is False


def test_identical_stored_profile_url_does_not_confirm_identity():
    url = "https://www.linkedin.com/in/rahul-sharma-84721/"
    row = candidate("linkedin", "Mumbai", linkedin_url=url)
    result = asyncio.run(lookup_one(database([row]), {"name": "Rahul Sharma", "profile_url": url, "source": "linkedin"}))
    assert result["decision"] == "insufficient_data"
    assert not result["exists"]
    assert "source_url" not in result["retrieval_paths"]


def test_reused_urls_do_not_add_evidence_for_either_person():
    url = "https://www.linkedin.com/in/rahul-sharma-84721/"
    a, b = candidate("A", "Delhi", linkedin_url=url), candidate("B", "Mumbai", linkedin_url=url)
    b["name"] = "Different Person"
    result = asyncio.run(lookup_one(database([a, b]), {"name": "Rahul Sharma", "profile_url": url}))
    assert result["decision"] == "insufficient_data"
    assert "source_id_hint" not in result["matched_signals"]
    assert not result["exists"]


@pytest.mark.parametrize("kind", [None, "profile-url", "unverified"])
def test_old_client_url_identifiers_do_not_retrieve_or_rank(kind):
    saved = candidate("saved", "Delhi", naukri_profile_id="old-url-identifier")
    incoming = {"name": "Rahul Sharma", "location": "Delhi", "current_employer": "TCS"}
    baseline = asyncio.run(lookup_one(database([saved]), incoming))
    for identifier in ("old-url-identifier", "rotated-new-identifier"):
        result = asyncio.run(lookup_one(database([saved]), {
            **incoming, "naukri_id": identifier, "source_id_kind": kind,
        }))
        assert result == baseline
        assert "source_id" not in result["retrieval_paths"]


def test_retrieval_cap_is_explicit_not_negative_or_confirmation():
    rows = [candidate(str(i), "Delhi") for i in range(4)]
    result = asyncio.run(lookup_one(database(rows), rows[0], path_limit=2))
    assert result["retrieval_complete"] is False
    assert any(r.startswith("retrieval_capped:") for r in result["reason_codes"])
    assert result["decision"] == "ambiguous"
    assert not result["exists"]


def test_database_failure_is_unavailable_not_new():
    result = asyncio.run(lookup_one(database([], fail=True), {"name": "Rahul Sharma"}))
    assert result["decision"] == "unavailable"
    assert not result["exists"]


def test_partial_path_failure_cannot_confirm(monkeypatch):
    row = candidate("A", "Delhi", linkedin_url="https://www.linkedin.com/in/rahul-84721/")
    db = database([row])
    original = db.candidate_bank.find
    def fail_legacy(query, projection):
        if "name_lower" in str(query):
            raise RuntimeError("one retrieval path failed")
        return original(query, projection)
    monkeypatch.setattr(db.candidate_bank, "find", fail_legacy)
    result = asyncio.run(lookup_one(db, {"name": "Rahul Sharma", "profile_url": row["linkedin_url"]}))
    assert result["decision"] == "ambiguous"
    assert not result["retrieval_complete"]
    assert not result["exists"]


def test_deadline_returns_a_result_for_every_input_and_cancels_work(monkeypatch):
    closed = []
    async def slow(*_args, **_kwargs):
        try:
            await asyncio.sleep(10)
        finally:
            closed.append(True)
    monkeypatch.setattr(identity_lookup, "lookup_one", slow)
    monkeypatch.setattr(identity_lookup, "BATCH_TIMEOUT_S", 0.01)
    results = asyncio.run(lookup_profiles(database([]), [{"name": "Rahul"}] * 8, "https://example.test"))
    assert len(results) == 8
    assert [row["index"] for row in results] == list(range(8))
    assert all(row["reason_codes"] == ["lookup_deadline_exceeded"] for row in results)
    assert len(closed) == identity_lookup.MAX_CONCURRENT_PROFILES


def test_frequency_snapshot_uses_published_corpus_only():
    class Stats:
        async def find_one(self, _query):
            return {"_id": "__meta__", "snapshot_id": "published", "version": "identity-v1", "population_size": 100}
        def find(self, query, _projection):
            assert query["snapshot_id"] == "published"
            return Cursor([{"code": "company:tata consultancy services", "document_count": 40},
                           {"code": "name:rahul sharma", "document_count": 101}])
    db = database([])
    db.identity_code_stats = Stats()
    counts, size = asyncio.run(identity_lookup.load_frequency_snapshot(db, [candidate("A", "Delhi")]))
    assert counts == {"company:tata consultancy services": 40}
    assert size == 100


def test_batch_results_have_stable_indices_and_encoded_links():
    row = candidate("x&other=1", "Delhi")
    results = asyncio.run(lookup_profiles(database([row]), [row, {"name": "Unrelated Person", "current_employer": "Unrelated employer"}], "https://example.test"))
    assert [r["index"] for r in results] == [0, 1]
    assert results[0]["profile_url"].endswith("candidateId=x%26other%3D1")
    assert results[1]["decision"] == "no_match_found"
    assert "candidate_id" not in results[1]


def test_no_cross_request_cache_after_capture():
    db = database([])
    incoming = candidate("A", "Delhi")
    assert asyncio.run(lookup_one(db, incoming))["decision"] == "no_match_found"
    db.candidate_bank.rows.append(incoming)
    assert asyncio.run(lookup_one(db, incoming))["top_match"]["candidate_id"] == "A"


def test_empty_profile_never_runs_broad_database_query():
    assert retrieval_paths({"name": "", "current_employer": "TCS"}) == []
    db = database([candidate("A", "Delhi")])
    result = asyncio.run(lookup_one(db, {"name": ""}))
    assert result["decision"] == "insufficient_data"
    assert db.candidate_bank.queries == []


@pytest.fixture
def api(monkeypatch):
    # Import the actual route with config/auth isolated; actual FastAPI request
    # validation/serialization and async endpoint code are exercised below.
    db = database([candidate("delhi", "Delhi"), candidate("mumbai", "Mumbai")])
    config = types.ModuleType("config")
    config.db = db
    auth = types.ModuleType("utils.auth")

    async def fake_user():
        return {"id": "fixture", "email": "fixture@example.test", "role": "admin"}

    auth.get_current_user = fake_user
    monkeypatch.setitem(sys.modules, "config", config)
    monkeypatch.setitem(sys.modules, "utils.auth", auth)
    monkeypatch.setitem(sys.modules, "services.identity_lookup", identity_lookup)
    monkeypatch.setenv("EXTENSION_CHECK_EXISTING_ALLOWLIST", "fixture@example.test")
    monkeypatch.setenv("EXTENSION_CHECK_AUDIT_SAMPLE", "0")
    spec = importlib.util.spec_from_file_location("identity_route_fixture", BACKEND / "routes" / "extension_check.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    app = FastAPI()
    app.include_router(module.ext_check_router)
    with TestClient(app) as client:
        yield client, db


def test_api_roundtrip_decisions_and_schema(api):
    client, _ = api
    response = client.post("/api/extension/check-existing", json={"candidates": [candidate("incoming", "Delhi")]})
    assert response.status_code == 200
    body = response.json()
    assert body["matcher_version"] == "identity-resolution-1"
    assert body["service_status"] == "ready"
    assert body["results"][0]["top_match"]["candidate_id"] == "delhi"
    assert body["results"][0]["decision"] == "probable_match"
    assert body["results"][0]["exists"] is False
    assert body["results"][0]["retrieval_complete"] is True
    assert body["results"][0]["retrieval_stats"]["candidates_retrieved"] == 2
    assert body["results"][0]["top_match"]["context"]["location"] == "Delhi"


def test_api_carries_labelled_education_and_prior_employment(api):
    client, db = api
    db.candidate_bank.rows[0].update({
        "experience": [{"company": "Infosys", "title": "Engineer"}],
        "education": [{"degree": "BTech", "institution": "IIT Delhi"}],
    })
    payload = {"name": "Rahul Sharma", "location": "Delhi", "current_employer": "TCS",
               "experience": [{"company": "Infosys", "title": "Engineer"}],
               "education_details": [{"degree": "BTech", "institution": "IIT Delhi"}]}
    response = client.post("/api/extension/check-existing", json={"candidates": [payload]})
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert "experience_company" in result["matched_signals"]
    assert "institution" in result["matched_signals"]
    assert not result["exists"]


def test_rotating_urls_leave_retrieval_ranking_and_codes_unchanged():
    row = candidate("saved", "Delhi", profile_url="https://resdex.naukri.com/preview?pid=old")
    incoming = {"name": "Rahul Sharma", "location": "Delhi", "current_employer": "TCS"}
    baseline = asyncio.run(lookup_one(database([row]), incoming))
    for url in (row["profile_url"], "https://resdex.naukri.com/preview?pid=rotated",
                "https://linkedin.com/in/another-slug/"):
        assert build_identity_signature({**incoming, "profile_url": url}) == build_identity_signature(incoming)
        result = asyncio.run(lookup_one(database([row]), {**incoming, "profile_url": url}))
        assert result == baseline
        assert result["top_match"]["candidate_id"] == "saved"
        assert result["decision"] == "probable_match"


def test_current_employer_retrieval_can_reach_saved_employment_history():
    row = candidate("past", "Pune", experience=[{"company": "Infosys", "title": "Engineer"}])
    incoming = {"name": "Rahul Sharma", "current_employer": "Infosys", "designation": "Engineer"}
    paths = dict(retrieval_paths(incoming))
    assert matches(row, paths["name_company"])
    result = asyncio.run(lookup_one(database([row]), incoming))
    assert "experience_company" in result["matched_signals"]


def test_api_rejects_oversized_batch_without_truncation(api):
    client, db = api
    response = client.post("/api/extension/check-existing", json={"candidates": [{"name": "Rahul"}] * 51})
    assert response.status_code == 422
    assert db.candidate_bank.queries == []


def test_api_disabled_has_explicit_status_no_lookup(api, monkeypatch):
    client, db = api
    monkeypatch.setenv("EXTENSION_CHECK_EXISTING_ALLOWLIST", "")
    response = client.post("/api/extension/check-existing", json={"candidates": [{"name": "Rahul"}]})
    assert response.status_code == 200
    assert response.json()["service_status"] == "disabled"
    assert response.json()["results"][0]["decision"] == "unavailable"
    assert db.candidate_bank.queries == []


def test_api_empty_batch(api):
    client, _ = api
    response = client.post("/api/extension/check-existing", json={"candidates": []})
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_api_database_outage_preserves_each_input(api):
    client, db = api
    db.candidate_bank.fail = True
    response = client.post("/api/extension/check-existing", json={"candidates": [{"name": "Rahul"}, {"name": "Sharma"}]})
    assert response.status_code == 200
    assert response.json()["service_status"] == "unavailable"
    assert [r["index"] for r in response.json()["results"]] == [0, 1]
    assert all(r["decision"] == "unavailable" for r in response.json()["results"])


def test_api_rejects_invalid_source_hint(api):
    client, _ = api
    response = client.post("/api/extension/check-existing", json={"candidates": [{"name": "Rahul", "source_id_kind": "server_verified"}]})
    assert response.status_code == 422
