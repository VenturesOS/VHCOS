"""Offline persistence, explicit review, replay and recovery regressions."""

import ast
import asyncio
import copy
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import List

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "services"))
import identity_observations as observations  # noqa: E402

NOW = datetime(2026, 9, 17, tzinfo=timezone.utc)
USER = {"id": "recruiter-1", "role": "recruiter"}
ADMIN = {"id": "admin-1", "role": "admin"}
INPUT = {
    "name": "Rahul Sharma",
    "capture_request_id": "operation-123",
    "scraped_at": "client-date",
}
SNAPSHOT = {
    "id": "temporary",
    "name": "Rahul Sharma",
    "current_employer": "TCS",
    "location": "Delhi",
    "email": "private@person.test",
    "phone": "9876543210",
    "experience": [
        {
            "company": "Infosys",
            "title": "Engineer",
            "start_date": "2019",
            "end_date": "2022",
        }
    ],
    "education": [{"degree": "BTech", "institution": "IIT Delhi"}],
}


def matches(doc, query):
    for key, expected in query.items():
        value = doc.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and value not in expected["$in"]:
                return False
        elif value != expected:
            return False
    return True


class Cursor:
    def __init__(self, docs):
        self.docs = copy.deepcopy(docs)

    def sort(self, key, direction):
        self.docs.sort(key=lambda doc: doc.get(key, ""), reverse=direction < 0)
        return self

    def limit(self, count):
        self.docs = self.docs[:count]
        return self

    def max_time_ms(self, value):
        assert value > 0
        return self

    async def to_list(self, count):
        return self.docs[:count]


class Collection:
    def __init__(self, docs=()):
        self.docs = copy.deepcopy(list(docs))
        self.fail_insert = False
        self.fail_finalize = False

    async def find_one(self, query, projection=None):
        return next(
            (copy.deepcopy(doc) for doc in self.docs if matches(doc, query)), None
        )

    def find(self, query, projection=None):
        return Cursor([doc for doc in self.docs if matches(doc, query)])

    async def insert_one(self, doc):
        if self.fail_insert:
            raise RuntimeError("fixture insert failure")
        if any(row.get("_id") == doc.get("_id") for row in self.docs):
            raise DuplicateKeyError("duplicate fixture key")
        self.docs.append(copy.deepcopy(doc))

    async def update_one(self, query, operation):
        if self.fail_finalize and operation.get("$set", {}).get("status") == "linked":
            raise RuntimeError("fixture finalize failure")
        for doc in self.docs:
            if matches(doc, query):
                doc.update(copy.deepcopy(operation.get("$set", {})))
                for key in operation.get("$unset", {}):
                    doc.pop(key, None)
                for key, value in operation.get("$inc", {}).items():
                    doc[key] = doc.get(key, 0) + value
                for key, value in operation.get("$push", {}).items():
                    doc.setdefault(key, []).append(copy.deepcopy(value))
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


@pytest.fixture
def db(monkeypatch):
    async def suggestions(*_args):
        return {
            "decision": "probable_match",
            "exists": False,
            "ranked_matches": [],
            "reason_codes": ["review_required"],
        }

    monkeypatch.setattr(observations, "observation_suggestions", suggestions)
    return SimpleNamespace(
        identity_observations=Collection(),
        candidate_bank=Collection(
            [
                {
                    "_id": "person",
                    "id": "person",
                    "name": "Rahul Sharma",
                    "location": "Mumbai",
                },
            ]
        ),
    )


def capture(db, submitted=None):
    return asyncio.run(
        observations.record_capture_observation(
            db, submitted or INPUT, SNAPSHOT, USER, NOW
        )
    )


def review(db, doc, decision, **extra):
    return asyncio.run(
        observations.review_observation(
            db,
            doc["id"],
            {
                "revision": doc["revision"],
                "decision": decision,
                "reason": "Checked independent evidence with the recruiter.",
                **extra,
            },
            ADMIN,
        )
    )


def test_capture_persists_dated_observation_not_an_extra_person(db):
    before = copy.deepcopy(db.candidate_bank.docs)
    doc = capture(db)
    assert doc["status"] == "unresolved" and doc["candidate_id"] is None
    assert doc["observed_at"] == NOW.isoformat()
    assert doc["snapshot"]["experience"][0]["start_date"] == "2019"
    assert "id" not in doc["snapshot"]
    assert db.candidate_bank.docs == before
    assert SNAPSHOT["id"] == "temporary"


def test_same_operation_replays_original_snapshot_without_duplicate(db):
    one, two = capture(db), capture(db)
    assert one == two and len(db.identity_observations.docs) == 1
    with pytest.raises(observations.ObservationConflict):
        capture(db, {**INPUT, "name": "Priya Singh"})
    three = capture(db, {**INPUT, "capture_request_id": "operation-456"})
    assert three["id"] != one["id"]
    assert len(db.candidate_bank.docs) == 1


def test_link_is_audited_and_does_not_overwrite_a_person(db):
    doc = capture(db)
    before = copy.deepcopy(db.candidate_bank.docs)
    linked = review(db, doc, "link", candidate_id="person")
    assert linked["status"] == "linked" and linked["candidate_id"] == "person"
    assert linked["revision"] == 1
    assert linked["snapshot"] == doc["snapshot"]
    assert linked["review_history"][0]["reviewer_id"] == ADMIN["id"]
    assert db.candidate_bank.docs == before
    with pytest.raises(observations.ObservationConflict):
        review(db, doc, "new_person")


def test_unlink_is_reversible_without_deleting_the_person_or_evidence(db):
    linked = review(db, capture(db), "link", candidate_id="person")
    unlinked = review(db, linked, "defer")
    assert unlinked["status"] == "deferred" and unlinked["candidate_id"] is None
    assert unlinked["review_history"][-1]["previous_candidate_id"] == "person"
    relinked = review(db, unlinked, "link", candidate_id="person")
    assert relinked["candidate_id"] == "person" and len(relinked["review_history"]) == 3
    assert len(db.candidate_bank.docs) == 1


@pytest.mark.parametrize("failure", ["insert", "finalize"])
def test_new_person_resume_after_failure_creates_exactly_one_canonical_row(db, failure):
    doc = capture(db)
    if failure == "insert":
        db.candidate_bank.fail_insert = True
    else:
        db.identity_observations.fail_finalize = True
    with pytest.raises(RuntimeError):
        review(db, doc, "new_person")
    pending = db.identity_observations.docs[0]
    assert pending["status"] == "resolving"
    assert pending["pending_review"]["decision"] == "new_person"
    db.candidate_bank.fail_insert = db.identity_observations.fail_finalize = False
    linked = review(db, copy.deepcopy(pending), "new_person")
    assert linked["status"] == "linked"
    created = [
        row
        for row in db.candidate_bank.docs
        if row.get("identity_origin_observation_id") == doc["id"]
    ]
    assert len(created) == 1 and created[0]["id"] == linked["candidate_id"]
    assert created[0]["identity"]["version"] == "identity-v1"
    assert linked["snapshot"] == doc["snapshot"]


def test_stale_or_invalid_reviews_never_create_people(db):
    doc = capture(db)
    with pytest.raises(observations.ObservationMissing):
        review(db, doc, "link", candidate_id="does-not-exist")
    with pytest.raises(ValueError):
        review(db, doc, "new_person", reason="short")
    with pytest.raises(PermissionError):
        asyncio.run(
            observations.review_observation(
                db, doc["id"], {"revision": 0, "decision": "new_person"}, USER
            )
        )
    assert len(db.candidate_bank.docs) == 1


def test_public_view_keeps_paired_history_but_not_private_contacts_or_raw_payload(db):
    view = observations.public_observation(capture(db), detail=True)
    assert view["snapshot"]["experience"][0]["company"] == "Infosys"
    assert "email" not in view["snapshot"] and "phone" not in view["snapshot"]
    assert "payload_hash" not in view and "capture_request_id" not in view
    assert "private@person.test" not in str(view)


def test_observation_insert_failure_is_not_success(db):
    db.identity_observations.fail_insert = True
    with pytest.raises(RuntimeError):
        capture(db)
    assert not db.identity_observations.docs


def test_zero_experience_is_not_treated_as_missing():
    assert observations.lookup_input({"experience_years": 0})["experience_years"] == 0


def test_concurrent_reviews_have_one_winner_and_one_canonical_insert(db):
    doc = capture(db)

    async def competing_reviews():
        request = {
            "revision": 0,
            "decision": "new_person",
            "reason": "Checked independent evidence.",
        }
        return await asyncio.gather(
            *[
                observations.review_observation(db, doc["id"], request, ADMIN)
                for _ in range(2)
            ],
            return_exceptions=True,
        )

    outcomes = asyncio.run(competing_reviews())
    assert sum(isinstance(result, dict) for result in outcomes) == 1
    assert (
        sum(isinstance(result, observations.ObservationConflict) for result in outcomes)
        == 1
    )
    assert (
        len(
            [
                row
                for row in db.candidate_bank.docs
                if row.get("identity_origin_observation_id") == doc["id"]
            ]
        )
        == 1
    )


def test_capture_route_only_saves_observations_not_people():
    tree = ast.parse((BACKEND / "routes" / "extension.py").read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "capture_profile"
    )
    calls = [
        ast.unparse(node.func)
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
    ]
    assert "record_capture_observation" in calls
    assert not any(call.startswith("db.candidate_bank.") for call in calls)


def test_actual_review_http_routes_role_and_revision_guards(db, monkeypatch):
    config = ModuleType("config")
    config.db = db
    auth = ModuleType("utils.auth")
    current = dict(ADMIN)

    async def user():
        return current

    auth.get_current_user = user
    auth.__dict__.update(Depends=Depends, HTTPException=HTTPException, List=List)
    tree = ast.parse((BACKEND / "utils" / "auth.py").read_text(encoding="utf-8"))
    checker = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "require_role"
    )
    exec(
        compile(
            ast.Module(body=[checker], type_ignores=[]), "actual_role_checker", "exec"
        ),
        auth.__dict__,
    )
    monkeypatch.setitem(sys.modules, "config", config)
    monkeypatch.setitem(sys.modules, "utils.auth", auth)
    monkeypatch.setitem(sys.modules, "services.identity_observations", observations)
    spec = importlib.util.spec_from_file_location(
        "observation_routes_fixture", BACKEND / "routes" / "identity_observations.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = FastAPI()
    app.include_router(module.router)
    doc = capture(db)
    with TestClient(app) as client:
        base = "/api/admin/identity-observations"
        assert client.get(base).json()["items"][0]["id"] == doc["id"]
        assert client.get(base + "/" + doc["id"]).status_code == 200
        body = {
            "revision": 0,
            "decision": "link",
            "candidate_id": "person",
            "reason": "Independently checked the matching evidence.",
        }
        assert (
            client.post(base + "/" + doc["id"] + "/review", json=body).status_code
            == 200
        )
        assert (
            client.post(base + "/" + doc["id"] + "/review", json=body).status_code
            == 409
        )
        current["role"] = "recruiter"
        for path in (base, base + "/" + doc["id"]):
            assert client.get(path).status_code == 403
        assert (
            client.post(base + "/" + doc["id"] + "/review", json=body).status_code
            == 403
        )
