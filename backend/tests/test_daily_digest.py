"""Backend tests for Daily Team Performance Digest (Phase 54.15)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://badge-audit-v2.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASS = "VhcAdmin@2024"
REC_EMAIL = "maneet@vhc.in"   # employer (non-admin) — rohit@vhc.in is actually role=admin in DB
REC_PASS = "12345678"


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text[:200]}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def admin_headers():
    tok = _login(ADMIN_EMAIL, ADMIN_PASS)
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def recruiter_headers():
    tok = _login(REC_EMAIL, REC_PASS)
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


REQUIRED_KEYS = [
    "date", "weekday", "pretty_date", "recruiter_count",
    "top_overall", "top_per_team",
    "improving_dod", "falling_dod", "improving_wow", "falling_wow",
    "inactive_recruiters", "inactive_employers",
    "best_quality", "best_efficiency", "whatsapp_text",
]


def _assert_schema(d):
    for k in REQUIRED_KEYS:
        assert k in d, f"missing key {k}"
    assert isinstance(d["top_overall"], list) and len(d["top_overall"]) <= 3
    assert isinstance(d["whatsapp_text"], str)
    txt = d["whatsapp_text"]
    assert txt.startswith("*Daily Performance"), f"bad prefix: {txt[:60]}"
    for marker in ["TOP 3 OVERALL", "TOP PER TEAM", "IMPROVING", "FALLING", "WEEK-OVER-WEEK"]:
        assert marker in txt, f"missing section {marker}"


class TestDailyDigest:

    def test_unauth_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/admin/daily-digest", timeout=15)
        assert r.status_code in (401, 403), f"got {r.status_code}"

    def test_recruiter_forbidden(self, recruiter_headers):
        r = requests.get(f"{BASE_URL}/api/admin/daily-digest", headers=recruiter_headers, timeout=15)
        assert r.status_code in (401, 403), f"got {r.status_code} body={r.text[:200]}"

    def test_get_today_digest(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/daily-digest", headers=admin_headers, timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        _assert_schema(d)
        # store today's date for downstream tests
        TestDailyDigest.today_date = d["date"]

    def test_regenerate_today(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/admin/daily-digest/regenerate", headers=admin_headers, timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        _assert_schema(d)

    def test_get_by_date_today(self, admin_headers):
        date = getattr(TestDailyDigest, "today_date", None)
        if not date:
            pytest.skip("today date unavailable")
        r = requests.get(f"{BASE_URL}/api/admin/daily-digest/{date}", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["date"] == date
        _assert_schema(d)

    def test_get_by_date_404(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/daily-digest/1999-01-01", headers=admin_headers, timeout=30)
        assert r.status_code == 404

    def test_get_by_invalid_date(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/daily-digest/not-a-date", headers=admin_headers, timeout=15)
        assert r.status_code == 400

    def test_regenerate_specific_date(self, admin_headers):
        target = "2026-05-11"  # Monday backfill date per request
        r = requests.post(
            f"{BASE_URL}/api/admin/daily-digest/{target}/regenerate",
            headers=admin_headers, timeout=120,
        )
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["date"] == target
        _assert_schema(d)

    def test_recent_list(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/daily-digest/recent?days=7", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "items" in body and "count" in body
        assert isinstance(body["items"], list)
        # Each item must have date + lightweight top_overall
        for it in body["items"]:
            assert "date" in it
            assert "top_overall" in it
            for t in it["top_overall"]:
                # ensure it's the lightweight form
                assert set(t.keys()) <= {"name", "activity_score"}
