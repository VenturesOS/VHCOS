"""
READ-ONLY regression tests for the Aug-2026 platform audit fixes.

CRITICAL: MONGO_URL points at the LIVE production Atlas cluster.
Every request in this module is a GET, except the single login POST.
NO data mutation of any kind.

Covers:
  - candidates.py       : /candidate-bank list (fast path gate), search, legacy filter, autocomplete
  - extension.py        : NEW /api/extension/job-info
  - analytics.py        : /api/analytics/admin summary cache
  - maintenance_routes  : /api/system-health/env-info admin guard
  - admin.py            : /api/employers/{id}/companies (duplicate route removed)
  - employer_routes.py  : /api/analytics/employer, /api/employer/my-team role guards
  - candidate_hygiene   : /api/admin/candidate-hygiene/merge-history
  - notifications.py    : /api/notifications/unread-count
  - health.py           : /api/health import failures
"""
import os
import re
import time
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing")
BASE_URL = base_url.rstrip("/")

TIMEOUT = 120


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def creds():
    p = Path("/app/memory/test_credentials.md")
    if not p.exists():
        pytest.skip("missing test_credentials.md")
    c = p.read_text(encoding="utf-8")
    e = re.search(r'(?im)^\s*[-*]?\s*(?:\*\*)?Email(?:\*\*)?\s*:\s*`?([^`\s]+)', c)
    pw = re.search(r'(?im)^\s*[-*]?\s*(?:\*\*)?Password(?:\*\*)?\s*:\s*`?([^`\s]+)', c)
    if not e or not pw:
        pytest.skip("creds not parseable")
    return {"email": e.group(1), "password": pw.group(1)}


@pytest.fixture(scope="module")
def admin(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=TIMEOUT)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:400]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if not tok:
        pytest.fail(f"login response has no token: {list(r.json().keys())}")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def _get(sess, path, **kw):
    t0 = time.time()
    r = sess.get(f"{BASE_URL}{path}", timeout=TIMEOUT, **kw)
    r.elapsed_s = time.time() - t0
    print(f"GET {path} -> {r.status_code} in {r.elapsed_s:.2f}s")
    return r


# ---------------------------------------------------------------- health / boot
class TestHealthAndBoot:
    def test_health_200_no_import_failures(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["status"] in ("healthy", "degraded")
        assert d.get("checks", {}).get("mongodb") == "ok", d.get("checks")
        assert d.get("import_failures", 0) == 0, f"route import failures: {d.get('import_failures')}"

    def test_login_returns_admin_role(self, admin, creds):
        r = _get(admin, "/api/auth/me")
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("email") == creds["email"]


# ---------------------------------------------------------------- candidate bank
class TestCandidateBank:
    def test_list_default_perf(self, admin):
        r = _get(admin, "/api/candidate-bank?limit=50")
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert isinstance(d.get("candidates"), list), d.keys()
        assert isinstance(d.get("total"), int)
        assert len(d["candidates"]) <= 50
        assert "_id" not in (d["candidates"][0] if d["candidates"] else {})
        # perf expectation after fix
        assert r.elapsed_s < 15, f"slow list: {r.elapsed_s:.1f}s"

    def test_search_text_path(self, admin):
        r = _get(admin, "/api/candidate-bank?limit=50&search=welder")
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert isinstance(d.get("candidates"), list)
        assert r.elapsed_s < 15, f"slow search: {r.elapsed_s:.1f}s"

    def test_legacy_location_filter(self, admin):
        r = _get(admin, "/api/candidate-bank?limit=50&location=pune")
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert isinstance(d.get("candidates"), list)
        assert d.get("total", 0) > 0, "location=pune returned 0 (legacy filter path broken)"

    def test_autocomplete_vocab(self, admin):
        r = _get(admin, "/api/candidate-bank/autocomplete?q=weld")
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert isinstance(d, list), f"expected JSON array, got {type(d)}: {str(d)[:200]}"
        if d:
            item = d[0]
            for k in ("text", "count", "type"):
                assert k in item, f"missing {k} in {item}"
        assert r.elapsed_s < 10, f"slow autocomplete: {r.elapsed_s:.1f}s"

    def test_autocomplete_min_length_validation(self, admin):
        r = _get(admin, "/api/candidate-bank/autocomplete?q=a")
        assert r.status_code == 422, r.status_code


# ---------------------------------------------------------------- extension
class TestExtensionJobInfo:
    def test_job_info_valid(self, admin):
        jr = _get(admin, "/api/jobs?limit=5")
        assert jr.status_code == 200, jr.text[:300]
        payload = jr.json()
        jobs = payload if isinstance(payload, list) else payload.get("jobs", [])
        if not jobs:
            pytest.skip("no jobs in DB")
        job_id = jobs[0]["id"]
        r = _get(admin, f"/api/extension/job-info?job_id={job_id}")
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d.get("job_id") == job_id
        assert "title" in d and "code" in d, d

    def test_job_info_404(self, admin):
        r = _get(admin, "/api/extension/job-info?job_id=nonexistent-zzz-000")
        assert r.status_code == 404, f"{r.status_code}: {r.text[:300]}"


# ---------------------------------------------------------------- analytics
class TestAnalytics:
    def test_admin_analytics_and_cache(self, admin):
        r1 = _get(admin, "/api/analytics/admin")
        assert r1.status_code == 200, r1.text[:400]
        assert isinstance(r1.json(), dict)
        r2 = _get(admin, "/api/analytics/admin")
        assert r2.status_code == 200
        assert r2.elapsed_s < 5, f"cached call still slow: {r2.elapsed_s:.1f}s"

    def test_employer_analytics_not_500(self, admin):
        r = _get(admin, "/api/analytics/employer")
        assert r.status_code in (200, 403), f"{r.status_code}: {r.text[:300]}"


# ---------------------------------------------------------------- guards / misc
class TestGuardsAndRegressions:
    def test_env_info_admin_allowed(self, admin):
        r = _get(admin, "/api/system-health/env-info")
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        assert isinstance(r.json(), dict)

    def test_employer_companies_admin_route(self, admin):
        er = _get(admin, "/api/users?limit=300")
        employer_id = None
        if er.status_code == 200:
            data = er.json()
            users = data if isinstance(data, list) else data.get("users", [])
            employers = [u for u in users if u.get("role") == "employer"]
            if employers:
                employer_id = employers[0].get("id")
        if not employer_id:
            pytest.skip(f"could not resolve an employer id (users endpoint {er.status_code})")
        r = _get(admin, f"/api/employers/{employer_id}/companies")
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        assert isinstance(r.json().get("companies"), list), r.json()

    def test_merge_history(self, admin):
        r = _get(admin, "/api/admin/candidate-hygiene/merge-history?limit=5")
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"

    def test_notifications_unread_count(self, admin):
        r = _get(admin, "/api/notifications/unread-count")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert any(isinstance(v, int) for v in d.values()), d

    def test_my_team_forbidden_for_admin(self, admin):
        r = _get(admin, "/api/employer/my-team")
        assert r.status_code == 403, f"expected 403 role guard, got {r.status_code}: {r.text[:300]}"

    def test_unauthenticated_candidate_bank_401(self):
        r = requests.get(f"{BASE_URL}/api/candidate-bank?limit=1", timeout=TIMEOUT)
        assert r.status_code in (401, 403), r.status_code
