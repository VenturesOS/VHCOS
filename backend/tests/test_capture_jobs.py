"""Offline operation deduplication and actual async-submit route checks."""
import ast
import asyncio
import copy
from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from pymongo.errors import DuplicateKeyError
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "services"))
from capture_jobs import CaptureRequestConflict, submit_capture_job  # noqa: E402

NOW = datetime(2026, 9, 11, tzinfo=timezone.utc)
USER = {"id": "user-1", "email": "fixture@person.test"}
PROFILE = {"capture_request_id": "operation-123", "name": "Rahul Sharma", "scraped_at": "now"}


class Jobs:
    def __init__(self):
        self.docs = {}
        self.fail = False

    async def insert_one(self, doc):
        if self.fail:
            raise RuntimeError("Offline storage unavailable")
        if doc["_id"] in self.docs:
            raise DuplicateKeyError("duplicate")
        self.docs[doc["_id"]] = copy.deepcopy(doc)

    async def find_one(self, query):
        return next((copy.deepcopy(doc) for doc in self.docs.values()
                     if all(doc.get(key) == value for key, value in query.items())), None)


def test_concurrent_same_operation_has_one_dispatch():
    db = SimpleNamespace(extension_capture_jobs=Jobs())
    async def run():
        return await asyncio.gather(*(submit_capture_job(db, PROFILE, USER, NOW) for _ in range(12)))
    results = asyncio.run(run())
    assert sum(dispatch for _, dispatch in results) == 1
    assert len({job["_id"] for job, _ in results}) == 1
    assert len(db.extension_capture_jobs.docs) == 1


@pytest.mark.parametrize("status", ["pending", "processing", "completed", "failed"])
def test_repeated_job_state_is_returned_never_redispatched(status):
    db = SimpleNamespace(extension_capture_jobs=Jobs())
    job, _ = asyncio.run(submit_capture_job(db, PROFILE, USER, NOW))
    db.extension_capture_jobs.docs[job["_id"]]["status"] = status
    again, dispatch = asyncio.run(submit_capture_job(db, PROFILE, USER, NOW))
    assert again["status"] == status
    assert not dispatch
    assert again["expires_at"] == job["expires_at"]


def test_changed_payload_is_a_conflict_not_the_wrong_result():
    db = SimpleNamespace(extension_capture_jobs=Jobs())
    asyncio.run(submit_capture_job(db, PROFILE, USER, NOW))
    with pytest.raises(CaptureRequestConflict):
        asyncio.run(submit_capture_job(db, {**PROFILE, "name": "Priya Singh"}, USER, NOW))


def test_operations_are_scoped_to_authenticated_user_not_url():
    db = SimpleNamespace(extension_capture_jobs=Jobs())
    one, _ = asyncio.run(submit_capture_job(db, PROFILE, USER, NOW))
    two, dispatch = asyncio.run(submit_capture_job(db, PROFILE, {**USER, "id": "other-user"}, NOW))
    assert one["_id"] != two["_id"]
    assert dispatch
    fresh, dispatch = asyncio.run(submit_capture_job(db, {**PROFILE, "capture_request_id": "other-operation"}, USER, NOW))
    assert fresh["_id"] != one["_id"] and dispatch


def test_legacy_requests_remain_distinct_and_storage_failure_is_not_success():
    db = SimpleNamespace(extension_capture_jobs=Jobs())
    legacy = {key: value for key, value in PROFILE.items() if key != "capture_request_id"}
    one, _ = asyncio.run(submit_capture_job(db, legacy, USER, NOW))
    two, _ = asyncio.run(submit_capture_job(db, legacy, USER, NOW))
    assert one["_id"] != two["_id"]
    db.extension_capture_jobs.fail = True
    with pytest.raises(RuntimeError):
        asyncio.run(submit_capture_job(db, PROFILE, USER, NOW))


def test_actual_route_dispatches_once_and_validates_conflicting_reuse():
    # Execute the real small route with transport-only dependencies isolated.
    sys.path.insert(0, str(BACKEND))
    from models.extension import CompleteNaukriProfileInput
    db = SimpleNamespace(extension_capture_jobs=Jobs())
    dispatches = []
    async def user():
        return USER
    async def worker(*args):
        dispatches.append(args)
    tree = ast.parse((BACKEND / "routes" / "extension.py").read_text(encoding="utf-8"))
    route = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                 and node.name == "capture_profile_async")
    router = APIRouter(prefix="/api/extension")
    namespace = dict(extension_router=router, CompleteNaukriProfileInput=CompleteNaukriProfileInput,
                     BackgroundTasks=BackgroundTasks, Depends=Depends, get_current_user=user,
                     db=db, submit_capture_job=submit_capture_job, datetime=datetime, timezone=timezone,
                     CaptureRequestConflict=CaptureRequestConflict, HTTPException=HTTPException,
                     _run_capture_job=worker)
    exec(compile(ast.Module(body=[route], type_ignores=[]), str(BACKEND / "routes" / "extension.py"), "exec"), namespace)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        one = client.post("/api/extension/capture/async", json=PROFILE)
        two = client.post("/api/extension/capture/async", json=PROFILE)
        assert one.status_code == two.status_code == 202
        assert one.json() == two.json()
        assert len(dispatches) == 1
        assert client.post("/api/extension/capture/async", json={**PROFILE, "name": "Priya Singh"}).status_code == 409
        assert client.post("/api/extension/capture/async", json={**PROFILE, "capture_request_id": "bad"}).status_code == 422
