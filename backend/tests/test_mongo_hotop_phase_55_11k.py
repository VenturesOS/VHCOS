"""Phase 55.11k — mongo_hotop_analyzer.py + add_hot_indexes.py regression tests.

Run against the shared live Atlas M20 via mongo_production_override.
Read-only-ish: apply script is idempotent; created indexes are left in place
(they are the actual CPU fix).
"""
from __future__ import annotations
import subprocess
import sys
import pytest

sys.path.insert(0, "/app/backend")
from mongo_production_override import MONGO_URL, DB_NAME  # noqa: E402
from pymongo import MongoClient  # noqa: E402

ANALYZER = "/app/backend/scripts/mongo_hotop_analyzer.py"
APPLY    = "/app/backend/scripts/add_hot_indexes.py"


@pytest.fixture(scope="module")
def db():
    return MongoClient(MONGO_URL, tlsAllowInvalidCertificates=True,
                       serverSelectionTimeoutMS=8000)[DB_NAME]


def _run(*args, timeout=90):
    r = subprocess.run(["python3", *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


# ---------- Analyzer ----------

class TestHotopAnalyzer:
    def test_default_run_exits_zero_with_sections(self):
        code, out, err = _run(ANALYZER)
        assert code == 0, f"stderr={err}"
        assert "In-flight ops running >= 1.0s" in out
        assert "Collection sizes" in out
        assert "Index sanity on hot filter fields" in out
        # No python traceback leaked
        assert "Traceback" not in out and "Traceback" not in err
        assert "'Collection' object is not callable" not in (out + err)

    def test_no_hello_or_ismaster_heartbeats_in_hotops(self):
        """Regression: hello/isMaster heartbeats must be filtered out."""
        code, out, _ = _run(ANALYZER)
        assert code == 0
        # Isolate the in-flight section only (up to next '=== ')
        section = out.split("=== In-flight ops", 1)[1].split("\n===", 1)[0]
        low = section.lower()
        assert "'hello':" not in low and "'ismaster':" not in low, \
            f"heartbeat leaked into hotops: {section}"
        assert "admin.$cmd " not in section  # admin.$cmd namespace filter
        # Also should not list oplog tailing
        assert "local.oplog.rs" not in section

    def test_min_secs_999_shows_nothing(self):
        code, out, err = _run(ANALYZER, "--min-secs", "999")
        assert code == 0, f"stderr={err}"
        assert "(nothing long-running right now)" in out, \
            f"Expected empty hotop list, got:\n{out}"


# ---------- Index apply ----------

class TestAddHotIndexes:
    HOT = ("ai_enrichment_source_1", "enrichment_status_1")
    TTL_NAME = "api_metrics_ttl_30d"

    def _cb_names(self, db):
        return {i["name"] for i in db.candidate_bank.list_indexes()}

    def _am_names(self, db):
        return {i["name"] for i in db.api_metrics.list_indexes()}

    def test_dry_run_does_not_create(self, db):
        before_cb = len(list(db.candidate_bank.list_indexes()))
        before_am = len(list(db.api_metrics.list_indexes()))
        code, out, err = _run(APPLY, "--dry-run")
        assert code == 0, err
        # Either DRY or SKIP lines for each expected index — never CREATED
        assert "CREATED" not in out, out
        after_cb = len(list(db.candidate_bank.list_indexes()))
        after_am = len(list(db.api_metrics.list_indexes()))
        assert before_cb == after_cb
        assert before_am == after_am

    def test_apply_indexes_exist_and_are_correct(self, db):
        # Ensure they exist (either created by earlier run or by this call).
        code, out, err = _run(APPLY)
        assert code == 0, err

        cb_idx = {i["name"]: i for i in db.candidate_bank.list_indexes()}
        for name in self.HOT:
            assert name in cb_idx, f"missing {name}"
        assert dict(cb_idx["ai_enrichment_source_1"]["key"]) == {"ai_enrichment_source": 1}
        assert dict(cb_idx["enrichment_status_1"]["key"]) == {"enrichment_status": 1}

        am_idx = {i["name"]: i for i in db.api_metrics.list_indexes()}
        assert self.TTL_NAME in am_idx
        ttl = am_idx[self.TTL_NAME]
        assert dict(ttl["key"]) == {"created_at": 1}
        assert ttl.get("expireAfterSeconds") == 2592000

    def test_idempotent_second_run_skips_all(self, db):
        code, out, err = _run(APPLY)
        assert code == 0, err
        assert "SKIP candidate_bank.ai_enrichment_source_1" in out
        assert "SKIP candidate_bank.enrichment_status_1" in out
        assert f"SKIP api_metrics.{self.TTL_NAME}" in out
        assert "CREATED" not in out

    def test_no_duplicate_indexes_after_reruns(self, db):
        # Names are unique keys in an index list; verify count of hot names.
        cb_names = [i["name"] for i in db.candidate_bank.list_indexes()]
        for name in self.HOT:
            assert cb_names.count(name) == 1
        am_names = [i["name"] for i in db.api_metrics.list_indexes()]
        assert am_names.count(self.TTL_NAME) == 1
