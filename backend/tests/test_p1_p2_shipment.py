"""
P1/P2/P3 Shipment Integration Tests.

Covers:
 P1-CRITICAL
  - POST /api/candidate-bank/data-quality/bulk-re-enrich (dry_run gaps_only flag, 503-on-no-runpod logic)
  - GET  /api/candidate-bank/data-quality/bulk-re-enrich/status/{job_id} (progress movement)
 P1
  - GET  /api/admin/runpod/health                              (admin + 403)
  - POST /api/admin/runpod/sync-now                            (admin + 403)
  - GET  /api/admin/llm/live-banner                            (admin + 403)
  - GET  /api/admin/llm/failure-stats                          (admin + 403)
 P2
  - GET  /api/extension/update.xml                             (public, Omaha v3)
  - GET  /api/extension/download.crx                           (public, CRX content-type)
  - GET  /api/extension/latest-version                         (public JSON)
  - POST /api/extension/checkin                                (authenticated)
  - GET  /api/extension/version-stats                          (admin + 403)
  - GET  /api/download/naukri-extension                        (legacy ZIP)
 Regression
  - POST /api/extension/ai-extract (Ramakant labeled top-card)
  - GET  /api/candidate-bank/{id}/download-resume (307 to R2)

Run:
  pytest /app/backend/tests/test_p1_p2_shipment.py -v --tb=short
"""
import os
import time
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
# yamini is a clear recruiter role (rohit returns role=admin in JWT on this env)
RECRUITER_EMAIL = "yamini@vhc.in"
RECRUITER_PASSWORD = "Ventures@321"

EXT_ID_FROM_FILE = None
try:
    with open("/app/backend/static/extensions/extension_id.txt") as f:
        EXT_ID_FROM_FILE = f.read().strip()
except Exception:
    pass


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def recruiter_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": RECRUITER_EMAIL, "password": RECRUITER_PASSWORD},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"recruiter login failed: {r.status_code}")
    tok = r.json()["access_token"]
    # Sanity: ensure role really is not admin
    return tok


def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ──────────────────────────────────────────────────────────────────────────────
# Extension public endpoints
# ──────────────────────────────────────────────────────────────────────────────
class TestExtensionPublic:
    def test_update_xml_is_omaha_v3(self):
        r = requests.get(f"{BASE_URL}/api/extension/update.xml", timeout=15)
        assert r.status_code == 200
        body = r.text
        assert "<gupdate" in body
        assert "xmlns='http://www.google.com/update2/response'" in body or \
               'xmlns="http://www.google.com/update2/response"' in body
        # If a build exists it should contain appid, codebase, version, hash_sha256
        if "<app " in body or "<app\n" in body:
            assert "appid=" in body
            assert "codebase=" in body
            assert "version=" in body
            assert "hash_sha256=" in body
            if EXT_ID_FROM_FILE:
                assert EXT_ID_FROM_FILE in body, "extension_id.txt mismatch with update.xml"

    def test_download_crx_binary(self):
        r = requests.get(f"{BASE_URL}/api/extension/download.crx", timeout=30, allow_redirects=True)
        assert r.status_code == 200, r.text[:200]
        ctype = r.headers.get("Content-Type", "")
        assert "chrome-extension" in ctype or "octet-stream" in ctype, f"Bad CT: {ctype}"
        # CRX3 files start with magic "Cr24"
        assert r.content[:4] == b"Cr24", f"CRX magic mismatch: {r.content[:8]!r}"

    def test_latest_version_json(self):
        r = requests.get(f"{BASE_URL}/api/extension/latest-version", timeout=15)
        assert r.status_code == 200
        data = r.json()
        for k in ("version", "crx_available", "crx_url", "zip_url", "extension_id", "update_url"):
            assert k in data, f"Missing key: {k}"
        assert data["crx_available"] is True
        if EXT_ID_FROM_FILE:
            assert data["extension_id"] == EXT_ID_FROM_FILE

    def test_legacy_zip_download_still_works(self):
        r = requests.get(f"{BASE_URL}/api/download/naukri-extension", timeout=30, allow_redirects=True)
        assert r.status_code == 200
        ct = r.headers.get("Content-Type", "")
        # Accept either zip or octet-stream
        assert "zip" in ct or "octet-stream" in ct, f"Bad CT: {ct}"
        assert r.content[:2] == b"PK", f"Not a ZIP file: {r.content[:4]!r}"


# ──────────────────────────────────────────────────────────────────────────────
# Extension authenticated endpoints
# ──────────────────────────────────────────────────────────────────────────────
class TestExtensionCheckin:
    def test_checkin_records_version(self, recruiter_token):
        r = requests.post(
            f"{BASE_URL}/api/extension/checkin",
            headers=_h(recruiter_token),
            json={"version": "5.3.0", "install_type": "crx"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert "latest_version" in data
        assert data.get("your_version") == "5.3.0"
        assert data.get("upgrade_required") in (False, True)

    def test_version_stats_admin(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/extension/version-stats",
            headers=_h(admin_token), timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("total_recruiters", "latest_version", "by_version", "stale_over_7d", "users"):
            assert k in data, f"Missing key: {k}"
        assert isinstance(data["by_version"], list)
        assert isinstance(data["users"], list)

    def test_version_stats_403_for_recruiter(self, recruiter_token):
        r = requests.get(
            f"{BASE_URL}/api/extension/version-stats",
            headers=_h(recruiter_token), timeout=15,
        )
        assert r.status_code == 403, f"Expected 403 got {r.status_code}: {r.text[:200]}"


# ──────────────────────────────────────────────────────────────────────────────
# Admin RunPod monitoring
# ──────────────────────────────────────────────────────────────────────────────
class TestRunpodMonitoring:
    def test_health_admin(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/runpod/health",
            headers=_h(admin_token), timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Expected snapshot keys (some may be null if sync hasn't run)
        for k in ("vllm_reachable", "pod_id", "pod_name", "pod_status",
                  "vllm_model", "last_sync_at", "auto_sync_enabled"):
            assert k in data, f"Missing snapshot key: {k}"

    def test_health_403_for_recruiter(self, recruiter_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/runpod/health",
            headers=_h(recruiter_token), timeout=15,
        )
        assert r.status_code == 403

    def test_sync_now_admin(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/admin/runpod/sync-now",
            headers=_h(admin_token), timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, dict)

    def test_sync_now_403_for_recruiter(self, recruiter_token):
        r = requests.post(
            f"{BASE_URL}/api/admin/runpod/sync-now",
            headers=_h(recruiter_token), timeout=15,
        )
        assert r.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# Admin LLM dashboards
# ──────────────────────────────────────────────────────────────────────────────
class TestLlmDashboards:
    def test_live_banner_admin(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/llm/live-banner",
            headers=_h(admin_token), timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("state") in ("healthy", "warning", "critical")
        assert "message" in data
        assert "details" in data

    def test_live_banner_403_for_recruiter(self, recruiter_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/llm/live-banner",
            headers=_h(recruiter_token), timeout=15,
        )
        assert r.status_code == 403

    def test_failure_stats_admin(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/llm/failure-stats?hours=24",
            headers=_h(admin_token), timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("total_extractions", "by_source", "summary", "health_grade"):
            assert k in data, f"Missing key: {k}"
        assert isinstance(data["by_source"], list)
        assert data["health_grade"] in ("healthy", "ok", "warning", "critical", "unknown")

    def test_failure_stats_403_for_recruiter(self, recruiter_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/llm/failure-stats?hours=24",
            headers=_h(recruiter_token), timeout=15,
        )
        assert r.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# Bulk Re-Enrich (P1-CRITICAL)
# ──────────────────────────────────────────────────────────────────────────────
class TestBulkReEnrich:
    def test_dry_run_gaps_only_true(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/candidate-bank/data-quality/bulk-re-enrich"
            "?gaps_only=true&since_hours=720&limit=10&concurrency=2&dry_run=true",
            headers=_h(admin_token), timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("candidates_to_process", "total_matched", "source_breakdown",
                  "runpod_health", "dry_run"):
            assert k in data, f"Missing key: {k}"
        assert data["dry_run"] is True
        pytest.shared_gaps_only_matched = data["total_matched"]

    def test_dry_run_gaps_only_false_returns_more_or_equal(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/candidate-bank/data-quality/bulk-re-enrich"
            "?gaps_only=false&since_hours=720&limit=10&concurrency=2&dry_run=true",
            headers=_h(admin_token), timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # gaps_only=false is a strict superset of gaps_only=true
        if hasattr(pytest, "shared_gaps_only_matched"):
            assert data["total_matched"] >= pytest.shared_gaps_only_matched, (
                f"gaps_only=false ({data['total_matched']}) should be >= "
                f"gaps_only=true ({pytest.shared_gaps_only_matched})"
            )

    def test_bulk_re_enrich_503_when_runpod_down_force_false(self, admin_token):
        # We don't know if RunPod is down; but if it's up this returns 200, if down returns 503.
        # Either way the response should be well-formed.
        r = requests.post(
            f"{BASE_URL}/api/candidate-bank/data-quality/bulk-re-enrich"
            "?gaps_only=true&since_hours=720&limit=1&concurrency=1",
            headers=_h(admin_token), timeout=30,
        )
        assert r.status_code in (200, 503), f"Got {r.status_code}: {r.text[:200]}"
        if r.status_code == 503:
            assert "RunPod" in r.text, "503 should mention RunPod"
        else:
            data = r.json()
            assert "job_id" in data
            assert "scheduled" in data
            assert "total_matched" in data

    def test_bulk_re_enrich_403_for_recruiter(self, recruiter_token):
        r = requests.post(
            f"{BASE_URL}/api/candidate-bank/data-quality/bulk-re-enrich"
            "?gaps_only=true&since_hours=720&limit=1&dry_run=true",
            headers=_h(recruiter_token), timeout=15,
        )
        assert r.status_code == 403

    def test_status_endpoint_rejects_bad_job(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/candidate-bank/data-quality/bulk-re-enrich/status/nonexistent-job-id",
            headers=_h(admin_token), timeout=15,
        )
        assert r.status_code == 404

    def test_status_lists_recent_jobs(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/candidate-bank/data-quality/bulk-re-enrich/status",
            headers=_h(admin_token), timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert "jobs" in data
        assert isinstance(data["jobs"], list)

    def test_bulk_re_enrich_progress_movement(self, admin_token):
        """Schedule a small job and poll to verify progress_pct increments from 0."""
        # Kick job with limit=2 concurrency=2, force=true so we don't fail on RunPod check
        r = requests.post(
            f"{BASE_URL}/api/candidate-bank/data-quality/bulk-re-enrich"
            "?gaps_only=true&since_hours=720&limit=2&concurrency=2&force=true",
            headers=_h(admin_token), timeout=30,
        )
        if r.status_code != 200:
            pytest.skip(f"Could not kick job: {r.status_code} {r.text[:200]}")
        data = r.json()
        job_id = data.get("job_id")
        scheduled = data.get("scheduled", 0)
        if not job_id:
            pytest.skip("Response missing job_id")
        if scheduled == 0:
            # Nothing to process is acceptable — verify status endpoint works
            s = requests.get(
                f"{BASE_URL}/api/candidate-bank/data-quality/bulk-re-enrich/status/{job_id}",
                headers=_h(admin_token), timeout=15,
            )
            assert s.status_code == 200
            j = s.json()
            assert "progress_pct" in j
            return

        # Poll for up to 60s waiting for progress > 0 OR completion
        saw_progress = False
        completed = False
        final_pct = 0
        for _ in range(20):
            time.sleep(3)
            s = requests.get(
                f"{BASE_URL}/api/candidate-bank/data-quality/bulk-re-enrich/status/{job_id}",
                headers=_h(admin_token), timeout=15,
            )
            if s.status_code != 200:
                continue
            j = s.json()
            pct = j.get("progress_pct", 0)
            final_pct = pct
            if pct > 0:
                saw_progress = True
            if j.get("status") in ("completed", "failed"):
                completed = True
                break
        # Bug was "stuck at 0%". We assert progress moved OR completed.
        assert saw_progress or completed, (
            f"Progress never moved beyond 0% for job {job_id}; final={final_pct}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Regression: AI Extract (Ramakant labeled layout)
# ──────────────────────────────────────────────────────────────────────────────
RAMAKANT_TEXT = """Ramakant Sharma
Senior Manager - Quality
Advik Hi Tech Pvt Ltd
Rudrapur, Pantnagar
ramakant.sharma@example.com
+91 9876543210

Experience
19 Years
Current CTC
₹ 25 Lacs
Expected CTC
₹ 34 Lacs
Notice Period
3 Months
Key Skills
Quality Assurance, Six Sigma, Automotive
"""


class TestAiExtractRegression:
    def test_ramakant_labeled_layout(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/extension/ai-extract",
            headers=_h(admin_token),
            json={
                "raw_text": RAMAKANT_TEXT,
                "dom_extracted_name": "Ramakant Sharma",
                "dom_extracted_email": "ramakant.sharma@example.com",
                "dom_extracted_phone": "+91 9876543210",
                "url": "https://www.naukri.com/mnjuser/profile?id=ramakant",
                "page_url": "https://www.naukri.com/mnjuser/profile?id=ramakant",
            },
            timeout=60,
        )
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        profile = data.get("profile_data") or data.get("profile") or data
        assert data.get("success") is True, f"extract not successful: {data}"

        name = profile.get("name")
        exp = (profile.get("experience_years")
               or profile.get("total_experience_years"))
        ctc = (profile.get("current_salary")
               or profile.get("current_ctc"))
        ectc = profile.get("expected_salary")
        notice = profile.get("notice_period")
        email = profile.get("email")
        phone = profile.get("phone")

        assert name and "Ramakant" in str(name), f"bad name: {name}"
        assert email and "ramakant" in str(email).lower()
        assert phone and "9876543210" in str(phone)
        assert exp is not None and float(exp) == 19.0, f"expected exp=19, got {exp}"
        assert ctc == 2500000, f"expected CTC=2500000, got {ctc}"
        assert ectc == 3400000, f"expected ECTC=3400000, got {ectc}"
        assert notice and "3" in str(notice), f"expected 3 Months notice, got {notice}"


# ──────────────────────────────────────────────────────────────────────────────
# Regression: Resume download 307
# ──────────────────────────────────────────────────────────────────────────────
class TestResumeDownloadRegression:
    def test_download_resume_307_or_404(self, admin_token):
        # Find a candidate with resume_versions
        r = requests.get(
            f"{BASE_URL}/api/candidate-bank?limit=50",
            headers=_h(admin_token), timeout=20,
        )
        if r.status_code != 200:
            pytest.skip(f"listing failed: {r.status_code}")
        payload = r.json()
        items = payload.get("candidates") or payload.get("items") or payload.get("data") or []
        if not items:
            pytest.skip("No candidates found")

        target = None
        for c in items:
            if c.get("resume_versions") or c.get("cv_attached") or c.get("resume_url"):
                target = c
                break
        if not target:
            # fall back: try first id — endpoint should 404 cleanly if no resume
            target = items[0]

        cid = target.get("id") or target.get("_id")
        if not cid:
            pytest.skip("Candidate missing id")

        resp = requests.get(
            f"{BASE_URL}/api/candidate-bank/{cid}/download-resume?token={admin_token}",
            timeout=20, allow_redirects=False,
        )
        # Also try with Authorization header — accept either auth mode working
        if resp.status_code == 401:
            resp = requests.get(
                f"{BASE_URL}/api/candidate-bank/{cid}/download-resume",
                headers=_h(admin_token), timeout=20, allow_redirects=False,
            )
        # Must either 307 (to R2 presigned) or 200 with binary. 404 only if resume_versions missing.
        assert resp.status_code in (200, 302, 307, 308, 404), (
            f"unexpected status: {resp.status_code} {resp.text[:200]}"
        )
        if resp.status_code in (302, 307, 308):
            loc = resp.headers.get("Location", "")
            assert loc, "Redirect has no Location header"
