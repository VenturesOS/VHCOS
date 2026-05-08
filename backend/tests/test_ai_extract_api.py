"""
Integration tests for:
  - POST /api/extension/ai-extract   (top-card extraction across Naukri layouts)
  - GET  /api/debug/extraction-trace (admin-only audit trail)
  - POST /api/debug/extraction-trace/_ensure-ttl (admin-only)
  - GET  /api/health
  - POST /api/extension/capture (regression)

Run:
  pytest /app/backend/tests/test_ai_extract_api.py -v
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to frontend/.env — testing tool invariant
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
RECRUITER_EMAIL = "rohit@vhc.in"
RECRUITER_PASSWORD = "12345678"


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────

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
    return r.json()["access_token"]


# ────────────────────────────────────────────────────────────────────────────
# Fixtures — raw Naukri layouts
# ────────────────────────────────────────────────────────────────────────────

FIX_LABELED_RAMAKANT = """Ramakant Pandey Save456
Senior Manager - IR and ER at Advik Hi Tech Pvt Ltd since Aug 2023
Experience
19 Years
Current CTC
₹ 25 Lacs
Expected CTC
₹ 34 Lacs
Current Location
Rudrapur, Pantnagar
Notice Period
3 Months
Highest Qualification
MBA/PGDM
Key Skills
Industrial Relations, Employee Relations, Union Management
"""

FIX_COMPACT = """Koushik Sangiri Save123
10y ₹ 18 Lacs (expects: ₹ 25 Lacs) Bangalore
Current: Senior Architect at TCS
Notice Period: 2 Months
Key Skills
Java, Spring Boot, AWS, Kubernetes
"""

FIX_MIXED = """Priya Sharma Save99
14y  ₹ 30 Lacs Pune
Current: Lead Engineer at Wipro
Notice Period
15 Days or less
Key Skills
Python, Django, PostgreSQL
"""


# ────────────────────────────────────────────────────────────────────────────
# Health
# ────────────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "healthy"


# ────────────────────────────────────────────────────────────────────────────
# /api/extension/ai-extract
# ────────────────────────────────────────────────────────────────────────────

class TestAIExtract:
    """Core acceptance: Top-card fields must extract across all 3 layouts."""

    def _post(self, token, raw_text, name=None):
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "raw_text": raw_text,
            "page_url": "https://resdex.naukri.com/candidate/12345",
            "page_title": "Naukri Profile Test",
            "dom_extracted_name": name,
        }
        return requests.post(
            f"{BASE_URL}/api/extension/ai-extract",
            json=payload,
            headers=headers,
            timeout=60,
        )

    def test_requires_auth(self):
        r = requests.post(
            f"{BASE_URL}/api/extension/ai-extract",
            json={"raw_text": FIX_LABELED_RAMAKANT, "page_url": "https://resdex.naukri.com/x"},
            timeout=15,
        )
        assert r.status_code in (401, 403)

    def test_labeled_ramakant_case_full_top_card(self, admin_token):
        """CORE ACCEPTANCE — labeled layout must not leak 0y / Unknown."""
        r = self._post(admin_token, FIX_LABELED_RAMAKANT, name="Ramakant Pandey")
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        body = r.json()
        assert body.get("success") is True, body
        p = body.get("profile_data") or {}

        exp = p.get("total_experience_years") or p.get("experience_years")
        assert exp == 19 or exp == 19.0, f"experience={exp!r}  profile={p}"

        cur = p.get("current_salary") or p.get("current_ctc")
        assert cur == 2_500_000, f"current_salary={cur!r}"

        exp_sal = p.get("expected_salary") or p.get("expected_ctc")
        assert exp_sal == 3_400_000, f"expected_salary={exp_sal!r}"

        np_val = (p.get("notice_period") or "").strip()
        assert "3" in np_val and "Month" in np_val, f"notice_period={np_val!r}"

        loc = (p.get("location") or p.get("current_location") or "")
        assert ("Rudrapur" in loc) or ("Pantnagar" in loc), f"location={loc!r}"

        emp = p.get("current_company") or p.get("current_employer") or ""
        assert "Advik" in emp, f"current_company={emp!r}"

    def test_compact_layout_full_top_card(self, admin_token):
        r = self._post(admin_token, FIX_COMPACT, name="Koushik Sangiri")
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body.get("success") is True
        p = body.get("profile_data") or {}

        exp = p.get("total_experience_years") or p.get("experience_years")
        assert exp == 10 or exp == 10.0, f"experience={exp!r}"

        cur = p.get("current_salary") or p.get("current_ctc")
        assert cur == 1_800_000, f"current_salary={cur!r}"

        exp_sal = p.get("expected_salary") or p.get("expected_ctc")
        assert exp_sal == 2_500_000, f"expected_salary={exp_sal!r}"

        np_val = (p.get("notice_period") or "").strip()
        assert "2" in np_val and "Month" in np_val, f"notice_period={np_val!r}"

        loc = (p.get("location") or p.get("current_location") or "")
        assert "Bangalore" in loc, f"location={loc!r}"

    def test_mixed_layout_full_top_card(self, admin_token):
        r = self._post(admin_token, FIX_MIXED, name="Priya Sharma")
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body.get("success") is True
        p = body.get("profile_data") or {}

        exp = p.get("total_experience_years") or p.get("experience_years")
        assert exp == 14 or exp == 14.0, f"experience={exp!r}"

        cur = p.get("current_salary") or p.get("current_ctc")
        assert cur == 3_000_000, f"current_salary={cur!r}"

        np_val = (p.get("notice_period") or "")
        assert "15 Days" in np_val, f"notice_period={np_val!r}"

        loc = p.get("location") or p.get("current_location") or ""
        assert "Pune" in loc, f"location={loc!r}"

    def test_insufficient_text_returns_success_false(self, admin_token):
        r = self._post(admin_token, "hi")
        assert r.status_code == 200
        body = r.json()
        assert body.get("success") is False


# ────────────────────────────────────────────────────────────────────────────
# /api/debug/extraction-trace (admin-only)
# ────────────────────────────────────────────────────────────────────────────

class TestExtractionTraceEndpoint:

    def test_list_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/debug/extraction-trace", timeout=10)
        assert r.status_code in (401, 403)

    def test_list_forbidden_for_non_admin(self, recruiter_token):
        r = requests.get(
            f"{BASE_URL}/api/debug/extraction-trace",
            headers={"Authorization": f"Bearer {recruiter_token}"},
            timeout=10,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_list_ok_for_admin(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/debug/extraction-trace?limit=5",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "count" in body
        assert "filter" in body
        assert "traces" in body
        assert isinstance(body["traces"], list)
        assert isinstance(body["count"], int)

    def test_ensure_ttl_forbidden_non_admin(self, recruiter_token):
        r = requests.post(
            f"{BASE_URL}/api/debug/extraction-trace/_ensure-ttl",
            headers={"Authorization": f"Bearer {recruiter_token}"},
            timeout=15,
        )
        assert r.status_code == 403

    def test_ensure_ttl_admin_ok(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/debug/extraction-trace/_ensure-ttl",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "index" in body

    def test_trace_recorded_after_ai_extract(self, admin_token):
        """After calling /ai-extract with raw text, a trace row must exist."""
        # Fire a unique extraction (trace requires name + contact)
        unique_name = f"TraceTest_{int(time.time())}"
        unique_email = f"tracetest{int(time.time())}@example.com"
        payload = {
            "raw_text": FIX_LABELED_RAMAKANT.replace("Ramakant Pandey", unique_name),
            "page_url": "https://resdex.naukri.com/candidate/trace-test",
            "page_title": "Naukri Trace Test",
            "dom_extracted_name": unique_name,
            "dom_extracted_email": unique_email,
            "dom_extracted_phone": "9999900000",
        }
        r = requests.post(
            f"{BASE_URL}/api/extension/ai-extract",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=60,
        )
        assert r.status_code == 200, r.text[:300]

        # Background trace write may take a few seconds (Claude bg-enrich)
        matches = []
        for _ in range(10):
            time.sleep(2)
            r = requests.get(
                f"{BASE_URL}/api/debug/extraction-trace?limit=50",
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=15,
            )
            assert r.status_code == 200
            traces = r.json().get("traces", [])
            matches = [t for t in traces if t.get("candidate_name") == unique_name
                       or unique_name in (t.get("raw_text_head") or "")]
            if matches:
                break
        assert matches, f"No extraction trace recorded for {unique_name} after 20s."


# ────────────────────────────────────────────────────────────────────────────
# /api/extension/capture regression
# ────────────────────────────────────────────────────────────────────────────

class TestCaptureRegression:
    def test_capture_endpoint_exists(self, admin_token):
        """Simply ensure /capture doesn't 500 on a minimal payload (schema may validate)."""
        r = requests.post(
            f"{BASE_URL}/api/extension/capture",
            json={},
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=15,
        )
        # Allow 400/422 (schema) but NOT 500 (server error)
        assert r.status_code != 500, f"capture endpoint 500: {r.text[:300]}"
        assert r.status_code in (200, 400, 401, 403, 404, 422), f"unexpected {r.status_code}"
