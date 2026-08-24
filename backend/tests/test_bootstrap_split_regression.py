"""
Regression suite for the 2026-08 bootstrap split (Phase 55.12).

Covers:
  * /api/health after server.py -> bootstrap/{routers,lifespan,middleware}.py split
  * 4 pruned revenue endpoints must be gone (404 / not in OpenAPI)
  * 5 retained revenue endpoints must still be registered + auth-gated
  * critical endpoint smoke test (200) with admin auth
  * middleware chain: gzip, CORS preflight, security headers
  * global exception handler returns JSON not HTML
"""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing from env and /app/frontend/.env")
BASE_URL = base_url.rstrip("/")

ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
RECRUITER_EMAIL = "hr6@vhc.in"
RECRUITER_PASSWORD = "12345678"

# In-process base URL. Used ONLY for assertions about app-level route
# registration (OpenAPI schema) and app-level CORS, both of which the
# preview k8s ingress rewrites/blocks:
#   * /openapi.json is not under /api/* so the ingress serves the SPA
#   * the ingress answers OPTIONS itself with Allow-Origin: *
LOCAL_URL = "http://localhost:8001"


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_token(api):
    r = api.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=60,
    )
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:400]}")
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.fail(f"Login response has no token: {list(data.keys())}")
    return token


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def recruiter_headers(api):
    r = api.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": RECRUITER_EMAIL, "password": RECRUITER_PASSWORD},
        timeout=60,
    )
    if r.status_code != 200:
        pytest.fail(f"Recruiter login failed {r.status_code}: {r.text[:400]}")
    token = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def openapi(api):
    r = api.get(f"{LOCAL_URL}/openapi.json", timeout=60)
    if r.status_code != 200:
        pytest.fail(f"OpenAPI schema unavailable ({r.status_code}): {r.text[:200]}")
    return r.json()


# ── bootstrap / health ──
class TestHealthAfterSplit:
    def test_health_200_and_zero_import_failures(self, api):
        r = api.get(f"{BASE_URL}/api/health", timeout=60)
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body.get("status") == "healthy", body
        failures = body.get("route_import_failures", body.get("import_failures"))
        assert failures == 0 or failures == [], f"route import failures: {failures}"
        assert body.get("checks", {}).get("mongodb") == "ok", body

    def test_login_works(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 20


# ── pruned revenue endpoints ──
REMOVED_REVENUE = [
    "/api/revenue/records",
    "/api/revenue/aggregate/by-company",
    "/api/revenue/aggregate/by-job",
    "/api/revenue/aggregate/by-recruiter",
]


class TestRemovedRevenueEndpoints:
    @pytest.mark.parametrize("path", REMOVED_REVENUE)
    def test_removed_returns_404_unauthenticated(self, api, path):
        r = api.get(f"{BASE_URL}{path}", timeout=60)
        assert r.status_code == 404, f"{path} -> {r.status_code} (expected 404): {r.text[:200]}"

    @pytest.mark.parametrize("path", REMOVED_REVENUE)
    def test_removed_returns_404_authenticated(self, api, auth_headers, path):
        r = api.get(f"{BASE_URL}{path}", headers=auth_headers, timeout=60)
        assert r.status_code == 404, f"{path} -> {r.status_code} (expected 404): {r.text[:200]}"

    @pytest.mark.parametrize("path", REMOVED_REVENUE)
    def test_removed_absent_from_openapi(self, openapi, path):
        assert path not in openapi.get("paths", {}), f"{path} still in OpenAPI schema"


# ── retained revenue endpoints ──
RETAINED_REVENUE = [
    ("post", "/api/revenue/offered/{app_id}"),
    ("post", "/api/revenue/hired/{app_id}"),
    ("post", "/api/revenue/joined/{app_id}"),
    ("get", "/api/revenue/by-application/{app_id}"),
    ("post", "/api/revenue/forecast"),
]


class TestRetainedRevenueEndpoints:
    @pytest.mark.parametrize("method,path", RETAINED_REVENUE)
    def test_present_in_openapi(self, openapi, method, path):
        paths = openapi.get("paths", {})
        assert path in paths, f"{path} missing from OpenAPI"
        assert method in {k.lower() for k in paths[path]}, f"{method.upper()} {path} missing"

    @pytest.mark.parametrize("method,path", RETAINED_REVENUE)
    def test_auth_gated_not_404_not_500(self, api, method, path):
        url = f"{BASE_URL}{path.replace('{app_id}', 'TEST-nonexistent-app-id')}"
        r = api.request(method.upper(), url, json={}, timeout=60)
        assert r.status_code in (401, 403), (
            f"{method.upper()} {path} -> {r.status_code} (expected 401/403): {r.text[:200]}"
        )


# ── critical endpoint smoke ──
CRITICAL_GETS = [
    "/api/candidates?limit=1",
    "/api/bills",
    "/api/analytics/admin",
    "/api/finance/revenue-dashboard?period=current_year",
    "/api/attendance/today",
    "/api/jobs",
    "/api/blog/candidate",
]


class TestCriticalEndpoints:
    @pytest.mark.parametrize("path", CRITICAL_GETS)
    def test_returns_200(self, api, auth_headers, path):
        r = api.get(f"{BASE_URL}{path}", headers=auth_headers, timeout=120)
        if r.status_code >= 500:  # retry once — preview ingress is occasionally flaky
            r = api.get(f"{BASE_URL}{path}", headers=auth_headers, timeout=120)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:300]}"
        # response must be valid JSON (not an HTML error page)
        assert r.headers.get("content-type", "").startswith("application/json"), r.headers
        r.json()

    def test_employer_companies_200_for_recruiter(self, api, recruiter_headers):
        # route is gated to ["employer", "recruiter"] — admin gets 403 by design
        r = api.get(f"{BASE_URL}/api/employer/companies", headers=recruiter_headers, timeout=120)
        assert r.status_code == 200, r.text[:300]
        assert "companies" in r.json()

    def test_notifications_history_route_registered(self, api, auth_headers):
        # settings_router route, gated to ["candidate"] — admin 403 proves the
        # route is registered (404 would mean the router failed to load)
        r = api.get(f"{BASE_URL}/api/notifications/history", headers=auth_headers, timeout=60)
        assert r.status_code == 403, f"-> {r.status_code}: {r.text[:200]}"

    def test_extension_job_info_route_exists(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/extension/job-info?job_id=any", headers=auth_headers, timeout=60)
        assert r.status_code in (200, 404), f"-> {r.status_code}: {r.text[:300]}"
        assert r.status_code != 500
        body = r.json()
        assert isinstance(body, dict)


# ── middleware chain ──
class TestMiddleware:
    def test_gzip_compression(self, auth_headers):
        headers = dict(auth_headers)
        headers["Accept-Encoding"] = "gzip"
        r = requests.get(
            f"{BASE_URL}/api/candidates?limit=50", headers=headers, timeout=120
        )
        assert r.status_code == 200, r.text[:300]
        enc = r.headers.get("Content-Encoding", "")
        assert "gzip" in enc.lower(), (
            f"gzip missing; Content-Encoding={enc!r}, len={len(r.content)}"
        )

    def test_cors_preflight_allowed_origin(self, api):
        # asserted in-process: the preview ingress answers OPTIONS itself with
        # Allow-Origin: * before the app sees it, so hitting BASE_URL cannot
        # verify the app's CORSMiddleware registration.
        r = api.options(
            f"{LOCAL_URL}/api/auth/login",
            headers={
                "Origin": "https://ventureshrd.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
            timeout=60,
        )
        assert r.status_code in (200, 204), f"{r.status_code}: {r.text[:200]}"
        assert r.headers.get("access-control-allow-origin") == "https://ventureshrd.com", dict(r.headers)
        assert r.headers.get("access-control-allow-credentials") == "true", dict(r.headers)

    def test_cors_disallowed_origin_rejected(self, api):
        r = api.options(
            f"{LOCAL_URL}/api/auth/login",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
            timeout=60,
        )
        assert r.headers.get("access-control-allow-origin") != "*"

    def test_security_headers_present(self, api):
        r = api.get(f"{BASE_URL}/api/health", timeout=60)
        for h in (
            "Strict-Transport-Security",
            "X-Content-Type-Options",
            "Content-Security-Policy",
            "X-Frame-Options",
            "Referrer-Policy",
        ):
            assert h in r.headers, f"missing security header {h}: {list(r.headers)}"
        assert r.headers.get("Cache-Control", "").startswith("no-store")


# ── exception handling ──
class TestExceptionHandling:
    def test_unknown_candidate_returns_json_not_html(self, api, auth_headers):
        r = api.get(
            f"{BASE_URL}/api/candidates/nonexistent-uuid-12345", headers=auth_headers, timeout=60
        )
        assert r.status_code != 500, f"500 on unknown candidate id: {r.text[:400]}"
        assert r.headers.get("content-type", "").startswith("application/json"), r.headers
        body = r.json()
        assert isinstance(body, dict)
        assert "<html" not in r.text.lower()

    def test_unknown_route_returns_json_404(self, api):
        r = api.get(f"{BASE_URL}/api/definitely-not-a-route-xyz", timeout=60)
        assert r.status_code == 404
        assert "<html" not in r.text.lower()

    def test_malformed_body_returns_422_json(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login", json={"email": "x"}, timeout=60)
        assert r.status_code in (400, 401, 422), f"{r.status_code}: {r.text[:300]}"
        assert r.headers.get("content-type", "").startswith("application/json")
