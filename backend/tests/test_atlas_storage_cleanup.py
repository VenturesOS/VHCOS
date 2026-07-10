"""
Backend tests — Phase 55.11i Atlas storage cleanup endpoints.

Covers:
- Auth/role gating for GET /api/admin/atlas/storage-analysis and POST /api/admin/atlas/prune-raw-fields
- Response schema for storage-analysis
- Dry-run semantics (default true, no mutation)
- Real prune only touches enrichment_status == 'enriched' documents
- Idempotency of the destructive path

Seeds sentinel docs prefixed with 'ATLAS_CLEANUP_TEST_' and cleans them up afterwards.
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://badge-audit-v2.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASS = "VhcAdmin@2024"
NONADMIN_EMAIL = "hr6@vhc.in"
NONADMIN_PASS = "12345678"

MONGO_URL = os.environ.get("MONGO_URL") or "mongodb+srv://vhc_admin:DL4cbb4890@cluster0.vuhdiod.mongodb.net/?retryWrites=true&w=majority"
DB_NAME = os.environ.get("DB_NAME", "vhc_talent_os")

DISPOSABLE = [
    "raw_profile_text",
    "raw_text_for_enrichment",
    "ai_full_text",
    "resume_latex",
    "profile_update_audit",
]

SENTINEL_PREFIX = "ATLAS_CLEANUP_TEST_"


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def nonadmin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": NONADMIN_EMAIL, "password": NONADMIN_PASS}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"nonadmin login failed: {r.status_code} {r.text}")
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=False, serverSelectionTimeoutMS=15000)
    yield client[DB_NAME]
    # cleanup at the very end
    client[DB_NAME].candidate_bank.delete_many({"name": {"$regex": f"^{SENTINEL_PREFIX}"}})
    client.close()


@pytest.fixture()
def seeded_docs(mongo_db):
    """Seed 3 docs: enriched w/ TEST_REMOVE_ME, pending w/ TEST_PRESERVED, enriched w/ all disposables."""
    coll = mongo_db.candidate_bank
    ids = {
        "enriched_remove": f"{SENTINEL_PREFIX}enriched_{uuid.uuid4().hex[:8]}",
        "pending_preserve": f"{SENTINEL_PREFIX}pending_{uuid.uuid4().hex[:8]}",
        "enriched_full": f"{SENTINEL_PREFIX}full_{uuid.uuid4().hex[:8]}",
    }
    coll.insert_many([
        {
            "_id": ids["enriched_remove"],
            "id": ids["enriched_remove"],
            "name": ids["enriched_remove"],
            "enrichment_status": "enriched",
            "raw_profile_text": "TEST_REMOVE_ME",
        },
        {
            "_id": ids["pending_preserve"],
            "id": ids["pending_preserve"],
            "name": ids["pending_preserve"],
            "enrichment_status": "pending",
            "raw_profile_text": "TEST_PRESERVED",
            "raw_text_for_enrichment": "TEST_PRESERVED",
        },
        {
            "_id": ids["enriched_full"],
            "id": ids["enriched_full"],
            "name": ids["enriched_full"],
            "enrichment_status": "enriched",
            "raw_profile_text": "R",
            "raw_text_for_enrichment": "R",
            "ai_full_text": "R",
            "resume_latex": "R",
            "profile_update_audit": [{"x": 1}],
        },
    ])
    yield ids
    coll.delete_many({"_id": {"$in": list(ids.values())}})


# ─────────────────────────────────────────────────────────────
# Auth gating
# ─────────────────────────────────────────────────────────────
class TestAuthGating:
    def test_storage_analysis_no_token(self):
        r = requests.get(f"{BASE_URL}/api/admin/atlas/storage-analysis", timeout=30)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_storage_analysis_nonadmin(self, nonadmin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/atlas/storage-analysis",
            headers={"Authorization": f"Bearer {nonadmin_token}"},
            timeout=30,
        )
        assert r.status_code == 403, f"expected 403 for non-admin, got {r.status_code} {r.text}"

    def test_prune_no_token(self):
        r = requests.post(f"{BASE_URL}/api/admin/atlas/prune-raw-fields", timeout=30)
        assert r.status_code in (401, 403)

    def test_prune_nonadmin(self, nonadmin_token):
        r = requests.post(
            f"{BASE_URL}/api/admin/atlas/prune-raw-fields",
            headers={"Authorization": f"Bearer {nonadmin_token}"},
            timeout=30,
        )
        assert r.status_code == 403


# ─────────────────────────────────────────────────────────────
# Storage analysis schema
# ─────────────────────────────────────────────────────────────
class TestStorageAnalysis:
    def test_schema(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/atlas/storage-analysis",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ["count", "storage_size", "uncompressed_size", "index_size", "avg_doc_size",
                  "enriched_docs", "reclaimable", "disposable_fields"]:
            assert k in data, f"missing key: {k}"
        assert data["disposable_fields"] == DISPOSABLE
        assert isinstance(data["reclaimable"], dict)
        assert set(data["reclaimable"].keys()) == set(DISPOSABLE)
        for f, v in data["reclaimable"].items():
            assert isinstance(v, int) and v >= 0, f"reclaimable[{f}]={v} must be non-neg int"


# ─────────────────────────────────────────────────────────────
# Prune semantics
# ─────────────────────────────────────────────────────────────
class TestPrune:
    def test_dry_run_default_no_mutation(self, admin_token, mongo_db, seeded_docs):
        coll = mongo_db.candidate_bank
        before = coll.count_documents({"raw_profile_text": {"$exists": True}})

        r = requests.post(
            f"{BASE_URL}/api/admin/atlas/prune-raw-fields",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["dry_run"] is True
        assert "would_prune" in data
        assert set(data["would_prune"].keys()) == set(DISPOSABLE)

        after = coll.count_documents({"raw_profile_text": {"$exists": True}})
        assert after == before, f"dry-run must not mutate; before={before} after={after}"

        # sentinel docs untouched
        assert coll.find_one({"_id": seeded_docs["enriched_remove"]})["raw_profile_text"] == "TEST_REMOVE_ME"
        assert coll.find_one({"_id": seeded_docs["pending_preserve"]})["raw_profile_text"] == "TEST_PRESERVED"

    def test_real_prune_only_enriched(self, admin_token, mongo_db, seeded_docs):
        coll = mongo_db.candidate_bank

        r = requests.post(
            f"{BASE_URL}/api/admin/atlas/prune-raw-fields?dry_run=false",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=180,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["dry_run"] is False
        assert "results" in data
        for f in DISPOSABLE:
            assert f in data["results"], f"missing field in results: {f}"
            entry = data["results"][f]
            assert "matched" in entry and "modified" in entry
            assert isinstance(entry["matched"], int)
            assert isinstance(entry["modified"], int)

        # Enriched sentinel: raw_profile_text should be gone
        enriched_doc = coll.find_one({"_id": seeded_docs["enriched_remove"]})
        assert enriched_doc is not None
        assert "raw_profile_text" not in enriched_doc, f"expected field removed on enriched doc: {enriched_doc}"

        # Enriched-full sentinel: all disposable fields removed
        full_doc = coll.find_one({"_id": seeded_docs["enriched_full"]})
        assert full_doc is not None
        for f in DISPOSABLE:
            assert f not in full_doc, f"expected {f} removed from enriched_full doc"

        # Pending sentinel: MUST retain its raw fields
        pending_doc = coll.find_one({"_id": seeded_docs["pending_preserve"]})
        assert pending_doc is not None
        assert pending_doc.get("raw_profile_text") == "TEST_PRESERVED", "pending doc raw_profile_text was clobbered!"
        assert pending_doc.get("raw_text_for_enrichment") == "TEST_PRESERVED"

    def test_idempotent_second_run(self, admin_token, mongo_db, seeded_docs):
        # First real prune (may or may not have anything left after test above; use fresh seed)
        # Reset the enriched_remove sentinel to have raw_profile_text back
        coll = mongo_db.candidate_bank
        coll.update_one(
            {"_id": seeded_docs["enriched_remove"]},
            {"$set": {"raw_profile_text": "TEST_REMOVE_ME_AGAIN"}},
        )

        r1 = requests.post(
            f"{BASE_URL}/api/admin/atlas/prune-raw-fields?dry_run=false",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=180,
        )
        assert r1.status_code == 200

        # Second run — sentinel field must now be absent, so at least for the sentinel,
        # nothing extra happens. Endpoint should still return 200 with modified integers.
        r2 = requests.post(
            f"{BASE_URL}/api/admin/atlas/prune-raw-fields?dry_run=false",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=180,
        )
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data["dry_run"] is False
        for f in DISPOSABLE:
            entry = data["results"][f]
            assert isinstance(entry["matched"], int)
            assert isinstance(entry["modified"], int)
            assert entry["modified"] >= 0

        # Sentinel enriched doc must still be pruned
        enriched_doc = coll.find_one({"_id": seeded_docs["enriched_remove"]})
        assert "raw_profile_text" not in enriched_doc
