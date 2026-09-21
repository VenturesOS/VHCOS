"""Offline persistence/capture regressions. No application config or DB imports."""
from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "services"))

from identity_resolution import build_identity_signature  # noqa: E402
from identity_store import persist_candidate_identity, refresh_candidate_identity, refresh_candidate_identity_sync, refresh_identity_frequencies  # noqa: E402


def matches(doc, query):
    if "$and" in query:
        return all(matches(doc, clause) for clause in query["$and"])
    for field, expected in query.items():
        if isinstance(expected, dict) and any(str(k).startswith("$") for k in expected):
            if "$exists" in expected and (field in doc) != expected["$exists"]:
                return False
            if "$eq" in expected and doc.get(field) != expected["$eq"]:
                return False
        elif doc.get(field) != expected:
            return False
    return True


class MemoryCollection:
    def __init__(self, docs=()):
        self.docs = copy.deepcopy(list(docs))
        self.updates = 0
        self.indexes = 0

    async def update_one(self, query, operation, upsert=False):
        self.updates += 1
        for doc in self.docs:
            if matches(doc, query):
                old = copy.deepcopy(doc)
                doc.update(copy.deepcopy(operation.get("$set", {})))
                return SimpleNamespace(matched_count=1, modified_count=int(doc != old))
        if upsert:
            self.docs.append({**query, **copy.deepcopy(operation.get("$setOnInsert", {})), **copy.deepcopy(operation.get("$set", {}))})
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def find_one(self, query):
        return next((copy.deepcopy(doc) for doc in self.docs if matches(doc, query)), None)

    async def create_index(self, *args, **kwargs):
        self.indexes += 1


def memory_db(candidate):
    return SimpleNamespace(candidate_bank=MemoryCollection([candidate]), identity_codes=MemoryCollection(), identity_code_stats=MemoryCollection())


class FrequencyCandidates(MemoryCollection):
    """Small expression evaluator for the frequency pipeline's Mongo operators."""

    @staticmethod
    def value(doc, expression):
        if isinstance(expression, str) and expression.startswith("$"):
            result = doc
            for key in expression[1:].split("."):
                result = result.get(key) if isinstance(result, dict) else None
            return result
        if isinstance(expression, dict):
            operator, args = next(iter(expression.items()))
            if operator == "$isArray":
                return isinstance(FrequencyCandidates.value(doc, args), list)
            if operator == "$cond":
                return FrequencyCandidates.value(doc, args[1] if FrequencyCandidates.value(doc, args[0]) else args[2])
            if operator == "$setUnion":
                return list(dict.fromkeys(value for arg in args for value in FrequencyCandidates.value(doc, arg)))
            raise AssertionError(f"Unsupported expression: {operator}")
        return expression

    async def count_documents(self, query):
        return sum(all(self.value(doc, "$" + key) == value for key, value in query.items()) for doc in self.docs)

    def aggregate(self, pipeline, **kwargs):
        rows = copy.deepcopy(self.docs)
        for stage in pipeline:
            operator, args = next(iter(stage.items()))
            if operator == "$match":
                for key, expected in args.items():
                    if isinstance(expected, dict) and expected.get("$type") == "string":
                        rows = [row for row in rows if isinstance(self.value(row, "$" + key), str)]
                    else:
                        rows = [row for row in rows if self.value(row, "$" + key) == expected]
            elif operator == "$project":
                rows = [{key: self.value(row, expression) for key, expression in args.items()} for row in rows]
            elif operator == "$unwind":
                rows = [{**row, args[1:]: value} for row in rows for value in self.value(row, args)]
            elif operator == "$group":
                grouped = {}
                for row in rows:
                    key = self.value(row, args["_id"])
                    grouped[key] = grouped.get(key, 0) + args["document_count"]["$sum"]
                rows = [{"_id": key, "document_count": value} for key, value in grouped.items()]
            else:
                raise AssertionError(f"Unsupported stage: {operator}")

        async def iterator():
            for row in rows:
                yield row
        return iterator()


class IdentityPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.candidate = {
            "_id": "mongo-1", "id": "candidate-1", "name": "Rahul Sharma",
            "current_employer": "TCS", "location": "Delhi", "skills": ["C++", "Java"],
            "updated_at": "t1", "phone": "kept-private", "has_resume": True,
        }
        self.db = memory_db(self.candidate)

    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    def test_codes_are_idempotent_and_do_not_replace_raw_values(self):
        first = self.run_async(persist_candidate_identity(self.db, self.candidate))
        self.assertEqual(first["status"], "updated")
        stored = copy.deepcopy(self.db.candidate_bank.docs[0])
        dictionary = copy.deepcopy(self.db.identity_codes.docs)
        self.assertEqual(stored["identity"], build_identity_signature(self.candidate))
        self.assertEqual(stored["phone"], "kept-private")
        self.assertTrue(stored["has_resume"])
        self.assertFalse(any("kept-private" in str(doc) for doc in dictionary))
        second = self.run_async(persist_candidate_identity(self.db, stored))
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(self.db.identity_codes.docs, dictionary)

    def test_new_values_extend_dictionary_without_changing_old_codes(self):
        self.run_async(persist_candidate_identity(self.db, self.candidate))
        old_entries = {d["_id"]: copy.deepcopy(d) for d in self.db.identity_codes.docs}
        self.db.candidate_bank.docs[0]["location"] = "Mumbai"
        self.run_async(refresh_candidate_identity(self.db, "candidate-1"))
        entries = {d["_id"]: d for d in self.db.identity_codes.docs}
        self.assertIn("location:delhi", entries)
        self.assertIn("location:mumbai", entries)
        self.assertTrue(all(entries[k] == v for k, v in old_entries.items()))

    def test_concurrent_raw_field_change_without_timestamp_is_not_overwritten(self):
        self.db.candidate_bank.docs[0]["location"] = "Mumbai"
        result = self.run_async(persist_candidate_identity(self.db, self.candidate))
        self.assertEqual(result["status"], "stale")
        self.assertNotIn("identity", self.db.candidate_bank.docs[0])

    def test_concurrent_missing_to_present_field_prevents_stale_signature(self):
        self.db.candidate_bank.docs[0]["naukri_profile_id"] = "new-source-id"
        result = self.run_async(persist_candidate_identity(self.db, self.candidate))
        self.assertEqual(result["status"], "stale")

    def test_null_and_absent_are_different_snapshot_states(self):
        self.candidate["naukri_profile_id"] = None
        result = self.run_async(persist_candidate_identity(self.db, self.candidate))
        self.assertEqual(result["status"], "stale")

    def test_newer_signature_is_not_overwritten(self):
        self.db.candidate_bank.docs[0]["identity"] = {"version": "future-version"}
        result = self.run_async(persist_candidate_identity(self.db, self.candidate))
        self.assertEqual(result["status"], "stale")
        self.assertEqual(self.db.candidate_bank.docs[0]["identity"]["version"], "future-version")

    def test_refresh_uses_complete_effective_profile(self):
        self.run_async(refresh_candidate_identity(self.db, "candidate-1"))
        identity = self.db.candidate_bank.docs[0]["identity"]
        self.assertIn("company:tata consultancy services", identity["codes"])
        self.assertIn("location:delhi", identity["codes"])
        self.assertEqual(self.run_async(refresh_candidate_identity(self.db, "missing"))["status"], "missing")

    def test_unverified_legacy_id_cannot_generate_trusted_anchor(self):
        self.candidate["naukri_profile_id"] = "123456789"
        self.db = memory_db(self.candidate)
        self.run_async(persist_candidate_identity(self.db, self.candidate))
        self.assertNotIn("_identity_trusted_anchors", self.db.candidate_bank.docs[0])
        self.assertNotIn("verified", self.db.candidate_bank.docs[0]["identity"])

    def test_refresh_retries_a_race_with_a_fresh_full_snapshot(self):
        normal_update = self.db.candidate_bank.update_one
        races = []

        async def race_once(query, operation, **kwargs):
            if not races:
                races.append(True)
                self.db.candidate_bank.docs[0]["location"] = "Mumbai"
            return await normal_update(query, operation, **kwargs)

        self.db.candidate_bank.update_one = race_once
        result = self.run_async(refresh_candidate_identity(self.db, "candidate-1"))
        self.assertEqual(result["status"], "updated")
        self.assertIn("location:mumbai", result["signature"]["codes"])
        self.assertNotIn("location:delhi", result["signature"]["codes"])

    def test_new_history_and_source_fields_cannot_race_a_signature_write(self):
        changed_fields = {
            "experience": [{"company": "Previous Employer"}],
            "work_experience": [{"company": "Previous Employer"}],
            "employment_history": [{"company": "Previous Employer"}],
            "company_history": ["Previous Employer"],
            "previous_employers": ["Previous Employer"],
            "title_history": ["Platform Engineer"],
            "location_history": ["Mumbai"],
            "education_details": [{"institution": "IIT Delhi"}],
            "highest_degree": "B.Tech",
            "highest_qualification": "B.Tech",
            "certifications": [{"name": "AWS Architect"}],
            "certification": "AWS Architect",
            "projects": [{"title": "Apollo Migration"}],
            "project": "Apollo Migration",
            "languages": [{"language": "Marathi"}],
            "language": "Marathi",
            "source_profile_url": "https://www.linkedin.com/in/rahul-sharma/",
            "source_details": {"profile_url": "https://www.linkedin.com/in/rahul-sharma/"},
            "current_designation": "Platform Engineer",
        }
        original_signature = build_identity_signature(self.candidate)
        for field, new_value in changed_fields.items():
            with self.subTest(field=field):
                db = memory_db(self.candidate)
                db.candidate_bank.docs[0][field] = new_value
                if field in {"source_profile_url", "source_details"}:
                    # Navigation metadata changes never alter identity codes.
                    self.assertEqual(build_identity_signature(db.candidate_bank.docs[0]), original_signature)
                else:
                    self.assertNotEqual(build_identity_signature(db.candidate_bank.docs[0]), original_signature)
                result = self.run_async(persist_candidate_identity(db, self.candidate))
                self.assertEqual(result["status"], "stale")
                self.assertNotIn("identity", db.candidate_bank.docs[0])


class SynchronousPersistenceTests(unittest.TestCase):
    def make_sync_db(self):
        candidate = {"id": "candidate-1", "name": "Rahul Sharma", "location": "Delhi"}
        db = memory_db(candidate)

        def adapt(collection):
            async_find, async_update = collection.find_one, collection.update_one
            collection.find_one = lambda *args, **kwargs: asyncio.run(async_find(*args, **kwargs))
            collection.update_one = lambda *args, **kwargs: asyncio.run(async_update(*args, **kwargs))

            def bulk_write(requests, ordered):
                self.assertFalse(ordered)
                for request in requests:
                    collection.update_one(request._filter, request._doc, upsert=request._upsert)
            collection.bulk_write = bulk_write

        adapt(db.candidate_bank)
        adapt(db.identity_codes)
        return db

    def test_sync_worker_refreshes_changed_full_profile_without_async_client(self):
        db = self.make_sync_db()
        first = refresh_candidate_identity_sync(db, "candidate-1")
        self.assertEqual(first["status"], "updated")
        db.candidate_bank.docs[0]["location"] = "Mumbai"
        db.candidate_bank.docs[0]["experience"] = [{"company": "Previous Employer"}]
        second = refresh_candidate_identity_sync(db, "candidate-1")
        self.assertIn("location:mumbai", second["signature"]["codes"])
        self.assertIn("experience_company:previous employer", second["signature"]["codes"])
        self.assertNotIn("location:delhi", second["signature"]["codes"])
        self.assertEqual(refresh_candidate_identity_sync(db, "candidate-1")["status"], "unchanged")
        self.assertEqual(db.identity_code_stats.updates, 0)

    def test_sync_worker_retries_concurrent_enrichment(self):
        db = self.make_sync_db()
        normal_update = db.candidate_bank.update_one
        attempts = []

        def race_once(query, operation, **kwargs):
            if not attempts:
                attempts.append(True)
                db.candidate_bank.docs[0]["location"] = "Mumbai"
            return normal_update(query, operation, **kwargs)

        db.candidate_bank.update_one = race_once
        result = refresh_candidate_identity_sync(db, "candidate-1")
        self.assertEqual(result["status"], "updated")
        self.assertIn("location:mumbai", result["signature"]["codes"])
        self.assertEqual(refresh_candidate_identity_sync(db, "missing")["status"], "missing")


class CapturePreservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Isolate the service's config dependency for tests. Do not import the
        # real config module (it creates live database clients on import).
        config_stub = ModuleType("config")
        config_stub.db = None
        spec = importlib.util.spec_from_file_location("identity_test_extension_service", BACKEND / "services" / "extension_service.py")
        cls.service = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"config": config_stub}):
            spec.loader.exec_module(cls.service)
        from models.extension import CompleteNaukriProfileInput
        cls.profile_model = CompleteNaukriProfileInput

    def update(self, existing=None, **fields):
        profile = self.profile_model(name="Rahul Sharma", scraped_at="now", **fields)
        return self.service.build_complete_update(profile, {"id": "user-1"}, "now", existing=existing)

    def test_omitted_ids_contacts_and_boolean_defaults_are_preserved(self):
        update = self.update(career_preferences={"current_location": "Delhi"}, personal_details={"gender": "Male"})
        for field in ("naukri_profile_id", "naukri_profile_url", "phone", "email", "has_resume", "notice_negotiable", "is_serving_notice", "has_passport", "source_platform"):
            self.assertNotIn(field, update)
        self.assertNotIn("contact_hidden", update["source_details"])
        self.assertEqual(update["location"], "Delhi")

    def test_empty_ids_and_hidden_contacts_do_not_erase_identifiers(self):
        update = self.update(naukri_profile_id="", naukri_profile_url=None, phone="", email="")
        for field in ("naukri_profile_id", "naukri_profile_url", "phone", "phone_normalized", "email"):
            self.assertNotIn(field, update)

    def test_completed_capture_records_unverified_naukri_observation(self):
        update = self.update(naukri_profile_id="84721", source_platform="naukri")
        self.assertEqual(update["source_details"]["identity_observation"], {
            "source": "naukri", "id": "84721", "kind": "unverified_identifier",
            "provenance": "capture_observed", "observed_at": "now",
        })
        self.assertNotIn("identity_anchor", update["source_details"])

    def test_explicit_false_and_zero_remain_updates(self):
        update = self.update(has_resume=False, total_experience_years=0, career_preferences={"is_negotiable": False, "current_salary": 0}, personal_details={"has_passport": False})
        self.assertIs(update["has_resume"], False)
        self.assertIs(update["notice_negotiable"], False)
        self.assertIs(update["has_passport"], False)
        self.assertEqual(update["current_salary"], 0)
        self.assertEqual(update["experience_years"], 0)

    def test_capture_phone_normalization_matches_write_gate(self):
        for phone, normalized in [
            ("+44 7911 123456", "447911123456"),
            ("+91 98765 43210", "9876543210"),
            ("0091 98765 43210", "9876543210"),
        ]:
            update = self.update(phone=phone)
            self.assertEqual(update["phone_normalized"], normalized)
            profile = self.profile_model(name="Rahul Sharma", scraped_at="now", phone=phone)
            created = self.service.build_complete_candidate(profile, "new-id", {"id": "user-1"}, "now")
            self.assertEqual(created["phone_normalized"], normalized)

    def test_recapture_keeps_existing_source_metadata(self):
        existing = {"source_details": {"contact_hidden": True, "identifier_provenance": {"source": "server"}, "extension_version": "7.0"}}
        update = self.update(existing=existing)
        self.assertTrue(update["source_details"]["contact_hidden"])
        self.assertEqual(update["source_details"]["identifier_provenance"], {"source": "server"})
        self.assertEqual(update["source_details"]["extension_version"], "7.0")
        self.assertNotIn("captured_at", existing["source_details"])


class FrequencySnapshotTests(unittest.TestCase):
    def make_db(self):
        docs = [
            {"id": "a", "identity": {"version": "identity-v1", "codes": ["name:rahul", "name:rahul", "location:delhi"]}},
            {"id": "b", "identity": {"version": "identity-v1", "codes": ["name:rahul", "location:mumbai"]}},
            {"id": "old", "identity": {"version": "old-version", "codes": ["name:rahul"]}},
            {"id": "raw-only", "name": "Rahul"},
        ]
        return SimpleNamespace(candidate_bank=FrequencyCandidates(docs), identity_code_stats=MemoryCollection())

    def test_document_frequency_is_deduplicated_and_snapshot_bound(self):
        db = self.make_db()
        meta = asyncio.run(refresh_identity_frequencies(db))
        self.assertEqual(meta["population_size"], 2)
        rows = {row["code"]: row for row in db.identity_code_stats.docs if row.get("code")}
        self.assertEqual(rows["name:rahul"]["document_count"], 2)
        self.assertEqual(rows["location:delhi"]["document_count"], 1)
        self.assertTrue(all(row["snapshot_id"] == meta["snapshot_id"] for row in rows.values()))
        published = asyncio.run(db.identity_code_stats.find_one({"_id": "__meta__"}))
        self.assertEqual(published["snapshot_id"], meta["snapshot_id"])
        again = asyncio.run(refresh_identity_frequencies(db))
        self.assertNotEqual(again["snapshot_id"], meta["snapshot_id"])
        self.assertEqual(again["population_size"], 2)
        repeated = [row for row in db.identity_code_stats.docs if row.get("snapshot_id") == again["snapshot_id"] and row.get("code") == "name:rahul"]
        self.assertEqual(repeated[0]["document_count"], 2)

    def test_failed_refresh_does_not_publish_partial_snapshot(self):
        db = self.make_db()
        old = {"_id": "__meta__", "snapshot_id": "previous", "population_size": 2}
        db.identity_code_stats.docs.append(copy.deepcopy(old))
        normal_update = db.identity_code_stats.update_one

        async def fail_one(query, operation, **kwargs):
            if operation.get("$setOnInsert", {}).get("code") == "location:mumbai":
                raise RuntimeError("simulated write outage")
            return await normal_update(query, operation, **kwargs)

        db.identity_code_stats.update_one = fail_one
        with self.assertRaises(RuntimeError):
            asyncio.run(refresh_identity_frequencies(db))
        self.assertEqual(asyncio.run(db.identity_code_stats.find_one({"_id": "__meta__"})), old)

    def test_capture_persistence_does_not_increment_corpus_stats(self):
        candidate = {"id": "a", "name": "Rahul Sharma"}
        db = memory_db(candidate)
        asyncio.run(persist_candidate_identity(db, candidate))
        self.assertEqual(db.identity_code_stats.updates, 0)


class BackfillSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("identity_test_backfill", BACKEND / "scripts" / "backfill_identity_codes.py")
        cls.backfill = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.backfill)

    def test_default_is_dry_run_and_connection_is_explicit(self):
        parser = self.backfill.build_parser()
        args = parser.parse_args(["--uri", "mongodb://localhost:27017", "--database", "offline_test"])
        self.assertFalse(args.apply)
        required = {action.dest for action in parser._actions if action.required}
        self.assertEqual(required, {"uri", "database"})

    def test_standalone_import_does_not_initialize_application_services(self):
        script = str(BACKEND / "scripts" / "backfill_identity_codes.py")
        code = (
            "import builtins, runpy, sys\n"
            "original_import = builtins.__import__\n"
            "def guarded_import(name, *args, **kwargs):\n"
            "    if name == 'config' or name == 'services' or name.startswith('services.'):\n"
            "        raise AssertionError('application initialization attempted: ' + name)\n"
            "    return original_import(name, *args, **kwargs)\n"
            "builtins.__import__ = guarded_import\n"
            f"runpy.run_path({script!r}, run_name='offline_backfill_import')\n"
            "assert 'config' not in sys.modules\n"
        )
        completed = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_dry_run_never_writes_or_creates_indexes(self):
        candidate = {"_id": "record-1", "id": "candidate-1", "name": "Rahul Sharma"}
        db = memory_db(candidate)

        class Cursor:
            def sort(self, *args): return self
            def batch_size(self, *args): return self
            def limit(self, *args): return self
            def __aiter__(self):
                async def items():
                    yield copy.deepcopy(candidate)
                return items()

        db.candidate_bank.find = lambda query: Cursor()

        class Client:
            def __init__(self, *args, **kwargs): pass
            def __getitem__(self, name): return db
            def close(self): pass

        motor_stub = ModuleType("motor.motor_asyncio")
        motor_stub.AsyncIOMotorClient = Client
        bson_stub = ModuleType("bson")
        bson_stub.json_util = SimpleNamespace(loads=json.loads, dumps=json.dumps)
        args = self.backfill.build_parser().parse_args(["--uri", "mongodb://offline.invalid", "--database", "offline_test", "--refresh-frequencies"])
        with patch.dict(sys.modules, {"motor.motor_asyncio": motor_stub, "bson": bson_stub}), patch("builtins.print") as printed:
            self.assertEqual(asyncio.run(self.backfill.run(args)), 0)
        report = json.loads(printed.call_args.args[0])
        self.assertEqual(report["frequencies"], {"status": "skipped", "reason": "dry-run"})
        self.assertEqual(db.candidate_bank.updates, 0)
        self.assertEqual(db.identity_codes.updates, 0)
        self.assertEqual(db.candidate_bank.indexes + db.identity_codes.indexes, 0)
        self.assertEqual(db.identity_code_stats.updates + db.identity_code_stats.indexes, 0)


if __name__ == "__main__":
    unittest.main()
