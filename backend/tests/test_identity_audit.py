"""Offline tests of actual audit routes, role enforcement, and feedback writes.

Only the authentication transport and database are replaced. The role checker
is compiled from utils/auth.py so these tests cannot pass by inventing a more
restrictive authorization function than the application actually uses.
"""
from __future__ import annotations

import ast
import asyncio
import copy
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import List

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
import pytest

BACKEND = Path(__file__).resolve().parents[1]


def _at(document, path):
    value = document
    for part in path.split("."):
        if isinstance(value, list) and part.isdigit():
            index = int(part)
            if index >= len(value):
                return None
            value = value[index]
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _set(document, path, value):
    parts = path.split(".")
    target = document
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    if isinstance(target, list):
        target[int(parts[-1])] = value
    else:
        target[parts[-1]] = value


class Cursor:
    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)

    def sort(self, *_args):
        return self

    def limit(self, number):
        self.rows = self.rows[:number]
        return self

    async def to_list(self, number):
        return copy.deepcopy(self.rows[:number])


class Collection:
    def __init__(self):
        self.docs = []
        self.calls = []
        self.fail_insert = False
        self.fail_update = False

    async def insert_one(self, document):
        self.calls.append(("insert", copy.deepcopy(document)))
        if self.fail_insert:
            raise RuntimeError("fixture storage outage")
        self.docs.append(copy.deepcopy(document))
        return SimpleNamespace(inserted_id=document.get("id"))

    async def update_one(self, query, operation):
        self.calls.append(("update", copy.deepcopy(query), copy.deepcopy(operation)))
        if self.fail_update:
            raise RuntimeError("fixture update outage")
        for document in self.docs:
            if all(_at(document, key) == value for key, value in query.items()):
                before = copy.deepcopy(document)
                for key, value in operation.get("$set", {}).items():
                    _set(document, key, copy.deepcopy(value))
                return SimpleNamespace(matched_count=1, modified_count=int(before != document))
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def find_one(self, query, projection=None):
        self.calls.append(("find_one", copy.deepcopy(query)))
        row = next((doc for doc in self.docs if all(_at(doc, key) == value for key, value in query.items())), None)
        if row is None:
            return None
        result = copy.deepcopy(row)
        if projection and projection.get("_id") == 0:
            result.pop("_id", None)
        return result

    def find(self, query, projection=None):
        self.calls.append(("find", copy.deepcopy(query)))
        return Cursor([])

    def aggregate(self, pipeline):
        self.calls.append(("aggregate", copy.deepcopy(pipeline)))
        return Cursor([])

    async def count_documents(self, query):
        self.calls.append(("count", copy.deepcopy(query)))
        return 0


@pytest.fixture
def audit_api(monkeypatch):
    db = SimpleNamespace(
        badge_audit=Collection(), badge_feedback=Collection(),
        badge_view_stats=Collection(), badge_view_stats_user=Collection(),
    )
    identity = {"id": "recruiter-1", "email": "Recruiter@Example.test", "role": "recruiter"}

    async def authenticated_user():
        return dict(identity)

    auth_tree = ast.parse((BACKEND / "utils" / "auth.py").read_text(encoding="utf-8"))
    role_function = next(node for node in auth_tree.body if isinstance(node, ast.FunctionDef) and node.name == "require_role")
    namespace = {
        "List": List, "Depends": Depends, "HTTPException": HTTPException,
        "get_current_user": authenticated_user,
    }
    exec(compile(ast.Module(body=[role_function], type_ignores=[]), "actual_require_role", "exec"), namespace)

    config = ModuleType("config")
    config.db = db
    auth = ModuleType("utils.auth")
    auth.get_current_user = authenticated_user
    auth.require_role = namespace["require_role"]
    utils_package = ModuleType("utils")
    utils_package.__path__ = []
    services_package = ModuleType("services")
    services_package.__path__ = []
    digest = ModuleType("services.weekly_digest")

    async def protected_digest(*_args, **_kwargs):
        raise AssertionError("A denied user reached the digest service")

    digest.send_weekly_digest = protected_digest
    digest.build_weekly_digest_rows = protected_digest
    for name, module in {
        "config": config, "utils": utils_package, "utils.auth": auth,
        "services": services_package, "services.weekly_digest": digest,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("identity_audit_route_fixture", BACKEND / "routes" / "badge_audit.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    app = FastAPI()
    app.include_router(module.router)
    app.include_router(module.ext_feedback_router)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=db, module=module, user=identity)


def test_every_admin_audit_route_rejects_recruiter_before_database_access(audit_api):
    routes = audit_api.module.router.routes
    assert len(routes) >= 8
    for route in routes:
        path = route.path.replace("{audit_id}", "audit-1").replace("{card_idx}", "0")
        for method in route.methods - {"HEAD", "OPTIONS"}:
            payload = {"label": "correct", "notes": "fixture"} if method == "POST" else None
            response = audit_api.client.request(method, path, json=payload)
            assert response.status_code == 403, (method, path, response.text)
            assert response.json()["detail"] == "Insufficient permissions"
    assert all(not collection.calls for collection in vars(audit_api.db).values())


def test_real_role_gate_allows_an_admin_to_read_audit_detail(audit_api):
    audit_api.user["role"] = "admin"
    audit_api.db.badge_audit.docs.append({"id": "audit-1", "cards": []})
    response = audit_api.client.get("/api/admin/badge-audit/audit-1")
    assert response.status_code == 200
    assert response.json()["id"] == "audit-1"


@pytest.mark.parametrize("failed_collection", ["badge_feedback", "badge_audit"])
def test_wrong_match_storage_failure_returns_503(audit_api, failed_collection):
    if failed_collection == "badge_feedback":
        audit_api.db.badge_feedback.fail_insert = True
    else:
        audit_api.db.badge_audit.fail_update = True
    response = audit_api.client.post("/api/extension/audit/wrong-match", json={
        "audit_id": "audit-1", "card_idx": 0, "badge_candidate_id": "candidate-1",
    })
    assert response.status_code == 503
    assert response.json() == {"detail": "Could not save match feedback"}


def _audited_card(owner="recruiter@example.test", index=0, candidate_id="candidate-1"):
    return {
        "id": "audit-1", "user_email": owner,
        "cards": [{"card_idx": index, "matched_candidate_id": candidate_id}],
    }


def test_wrong_match_update_is_scoped_to_owner_batch_card_and_candidate(audit_api):
    audit_api.db.badge_audit.docs.append(_audited_card())
    response = audit_api.client.post("/api/extension/audit/wrong-match", json={
        "audit_id": "audit-1", "card_idx": 0, "badge_candidate_id": "candidate-1", "reason": "Different person",
    })
    assert response.status_code == 200
    assert response.json() == {"ok": True, "stored": True}
    update = next(call for call in audit_api.db.badge_audit.calls if call[0] == "update")
    assert update[1] == {
        "id": "audit-1", "user_email": "recruiter@example.test",
        "cards.0.card_idx": 0, "cards.0.matched_candidate_id": "candidate-1",
    }
    card = audit_api.db.badge_audit.docs[0]["cards"][0]
    assert card["user_flagged_wrong"] is True
    assert card["user_flagged_by"] == "recruiter@example.test"
    assert audit_api.db.badge_feedback.docs[0]["user_id"] == "recruiter-1"


@pytest.mark.parametrize("changed_field,value", [
    ("owner", "another@example.test"), ("index", 1), ("candidate_id", "another-candidate"),
])
def test_wrong_match_cannot_flag_another_owner_card_or_candidate(audit_api, changed_field, value):
    document = _audited_card(**{changed_field: value})
    audit_api.db.badge_audit.docs.append(copy.deepcopy(document))
    response = audit_api.client.post("/api/extension/audit/wrong-match", json={
        "audit_id": "audit-1", "card_idx": 0, "badge_candidate_id": "candidate-1",
    })
    assert response.status_code == 200  # Report retained; unrelated audit row untouched.
    assert audit_api.db.badge_audit.docs[0] == document


@pytest.mark.parametrize("index", [-1, 50])
def test_wrong_match_rejects_out_of_range_card_indices(audit_api, index):
    response = audit_api.client.post("/api/extension/audit/wrong-match", json={
        "audit_id": "audit-1", "card_idx": index, "badge_candidate_id": "candidate-1",
    })
    assert response.status_code == 422
    assert not audit_api.db.badge_feedback.calls
    assert not audit_api.db.badge_audit.calls


class AuditShape(BaseModel):
    model_config = ConfigDict(extra="allow")


@pytest.mark.parametrize("use_models", [False, True])
def test_audit_preserves_zero_values_and_safe_profile_context(audit_api, use_models):
    profile = {
        "name": "Rahul Sharma", "location": "Delhi", "skills": ["Java"],
        "experience_years": 0, "education": [{"institution": "IIT Delhi"}],
        "experience": [{"company": "Previous Employer"}],
        "certifications": ["Cloud Architect"], "projects": [{"title": "Apollo"}],
        "languages": ["Hindi"], "email": "private@example.test", "phone": "private-phone",
        "raw_profile_text": "PRIVATE RAW TEXT", "_identity_trusted_anchors": ["NOT TRUSTED"],
    }
    top = {"candidate_id": "candidate-1", "score": 0, "context": {"location": "Delhi", "skills": ["Java"]}}
    result = {
        "index": 0, "exists": False, "match_score": 0, "margin": 0,
        "matched_signals": [], "decision": "ambiguous", "matcher_version": "identity-resolution-1",
        "score_kind": "evidence_points", "candidate_id": "candidate-1", "top_match": top,
        "ranked_matches": [top], "retrieval_complete": False,
        "retrieval_stats": {"candidates_retrieved": 0}, "missing_fields": ["company"],
        "context_fields_observed": ["education", "experience"],
    }
    audit_id = asyncio.run(audit_api.module.write_audit_doc(
        user=audit_api.user, used_v2=False,
        candidates_in=[AuditShape(**profile) if use_models else profile],
        results_out=[AuditShape(**result) if use_models else result],
        docs_by_idx={0: {"name": "Rahul Sharma", "current_employer": "TCS", "location": "Delhi", "email": "private@example.test", "phone": "private-phone"}},
        conflicts_by_idx={0: "insufficient_evidence"}, page_url="https://example.test/search", took_ms=0,
    ))
    assert audit_id is not None
    document = audit_api.db.badge_audit.docs[0]
    assert document["id"] == audit_id
    assert document["took_ms"] == 0
    assert document["n_exists"] == 0
    assert document["hit_rate"] == 0
    card = document["cards"][0]
    assert card["card_idx"] == 0
    assert card["match_score"] == 0
    assert card["margin"] == 0
    assert card["card_experience_years"] == 0
    assert card["retrieval_complete"] is False
    assert card["matched_candidate_id"] == "candidate-1"
    assert card["input_profile"]["skills"] == ["Java"]
    assert card["input_profile"]["education"] == profile["education"]
    assert card["input_profile"]["experience"] == profile["experience"]
    assert card["top_match"]["context"] == top["context"]
    assert card["ranked_matches"] == [top]
    for private_value in ("private@example.test", "private-phone", "PRIVATE RAW TEXT", "NOT TRUSTED"):
        assert private_value not in repr(document)
