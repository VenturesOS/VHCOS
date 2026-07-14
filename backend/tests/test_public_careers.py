"""Tests for Phase 55.11l — Public Careers API + sitemap regression."""
import os
import re
import uuid
import asyncio
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://badge-audit-v2.preview.emergentagent.com").rstrip("/")

# Seed via pymongo (sync) — avoids needing to boot backend event loop
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

_client = MongoClient(os.environ["MONGO_URL"])
_dbsync = _client[os.environ["DB_NAME"]]

SEED_LIVE_ID = f"TEST_careers_live_{uuid.uuid4().hex[:8]}"
SEED_CLOSED_ID = f"TEST_careers_closed_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module", autouse=True)
def seed_and_cleanup():
    now = datetime.now(timezone.utc)

    def _setup():
        _dbsync.jobs.insert_one({
            "id": SEED_LIVE_ID,
            "title": "CAREERS_TEST_role_engineer",
            "status": "active",
            "career_page_status": "live",
            "shareable_link_enabled": False,
            "public_company_alias": "TestCo Alias",
            "industry": "Tech",
            "location": "Remote",
            "function": "Engineering",
            "seniority": "Senior",
            "employment_type": "full_time",
            "experience_min": 3,
            "experience_max": 6,
            "client_name": "REAL_CLIENT_NAME_SHOULD_NOT_LEAK",
            "created_at": now,
            "updated_at": now,
        })
        _dbsync.jobs.insert_one({
            "id": SEED_CLOSED_ID,
            "title": "CAREERS_TEST_closed_role",
            "status": "closed",
            "career_page_status": "live",
            "shareable_link_enabled": True,
            "public_company_alias": "ShouldNotList",
            "created_at": now,
            "updated_at": now,
        })

    def _teardown():
        _dbsync.jobs.delete_many({"id": {"$in": [SEED_LIVE_ID, SEED_CLOSED_ID]}})

    _setup()
    yield
    _teardown()


class TestPublicCareersList:
    def test_list_no_auth(self):
        r = requests.get(f"{BASE_URL}/api/public/careers/jobs", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ["total", "count", "skip", "limit", "jobs"]:
            assert k in data, f"Missing key: {k}"
        assert data["total"] >= 1
        assert isinstance(data["jobs"], list)
        # Verify shape and that client_name is NOT leaked
        for job in data["jobs"]:
            for k in ["id", "title", "company_display", "location", "function",
                      "seniority", "employment_type", "experience_range", "posted_at"]:
                assert k in job, f"job missing key {k}: {job}"
            assert "REAL_CLIENT_NAME_SHOULD_NOT_LEAK" not in (job.get("company_display") or "")

    def test_seeded_job_appears(self):
        r = requests.get(f"{BASE_URL}/api/public/careers/jobs?limit=200", timeout=30)
        assert r.status_code == 200
        ids = [j["id"] for j in r.json()["jobs"]]
        assert SEED_LIVE_ID in ids, f"Seeded live job not in list. ids sample: {ids[:5]}"
        # Confirm closed job is NOT in list
        assert SEED_CLOSED_ID not in ids

    def test_search_query(self):
        r = requests.get(f"{BASE_URL}/api/public/careers/jobs?q=engineer", timeout=30)
        assert r.status_code == 200
        data = r.json()
        # Either 0 hits (unlikely) or all match
        if data["total"] > 0:
            for job in data["jobs"]:
                haystack = " ".join([
                    (job.get("title") or ""),
                    (job.get("function") or ""),
                    (job.get("seniority") or ""),
                ]).lower()
                assert "engineer" in haystack, f"non-matching job returned: {job}"

    def test_pagination(self):
        r = requests.get(f"{BASE_URL}/api/public/careers/jobs?limit=5&skip=10", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["skip"] == 10
        assert data["limit"] == 5
        assert data["count"] <= 5


class TestPublicCareersFilters:
    def test_filters(self):
        r = requests.get(f"{BASE_URL}/api/public/careers/filters", timeout=30)
        assert r.status_code == 200
        data = r.json()
        for k in ["functions", "locations", "seniorities"]:
            assert k in data
            assert isinstance(data[k], list)


class TestPublicCareersDetail:
    def test_get_live_job(self):
        # Grab a live id from list
        r = requests.get(f"{BASE_URL}/api/public/careers/jobs?limit=1", timeout=30)
        assert r.status_code == 200
        jobs = r.json()["jobs"]
        assert len(jobs) >= 1
        jid = jobs[0]["id"]
        r2 = requests.get(f"{BASE_URL}/api/public/careers/jobs/{jid}", timeout=30)
        assert r2.status_code == 200, r2.text
        job = r2.json()
        assert job["id"] == jid
        for k in ["id", "title", "company_display"]:
            assert k in job

    def test_seeded_live_job_by_id(self):
        r = requests.get(f"{BASE_URL}/api/public/careers/jobs/{SEED_LIVE_ID}", timeout=30)
        assert r.status_code == 200
        job = r.json()
        assert job["id"] == SEED_LIVE_ID
        assert job["company_display"] == "TestCo Alias"

    def test_nonexistent_returns_404(self):
        r = requests.get(f"{BASE_URL}/api/public/careers/jobs/nonexistent-id-xyz", timeout=30)
        assert r.status_code == 404
        assert "Job not found or not public" in r.text

    def test_closed_job_returns_404(self):
        r = requests.get(f"{BASE_URL}/api/public/careers/jobs/{SEED_CLOSED_ID}", timeout=30)
        assert r.status_code == 404, f"closed job leaked! {r.text}"


class TestSitemap:
    def test_sitemap_contains_jobs(self):
        r = requests.get(f"{BASE_URL}/api/sitemap.xml", timeout=60)
        assert r.status_code == 200
        body = r.text
        job_locs = re.findall(r"<loc>https://ventureshrd\.com/jobs/[^<]+</loc>", body)
        assert len(job_locs) >= 1, "no job URLs in sitemap"
        total_locs = len(re.findall(r"<loc>", body))
        assert total_locs > 141, f"sitemap total loc={total_locs} not > 141"
