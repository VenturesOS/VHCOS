"""
Regression: extension async-capture flow (v5.5.10).

Verifies:
  1. POST /api/extension/capture/async returns 202 + job_id.
  2. GET /api/extension/capture/status/{job_id} surfaces processing → completed.
  3. completed job carries the same CaptureResponse shape as the sync endpoint.
  4. Sync /api/extension/capture still works (backward-compat for v5.5.8 team).
  5. Status endpoint is auth-gated (no-token → 403, bad job_id → 404).
"""
import time
import requests

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, API_BASE


def _login() -> str:
    r = requests.post(
        f"{API_BASE}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _profile_payload(suffix: str) -> dict:
    return {
        "name": f"AsyncTest {suffix}",
        "email": f"asynctest_{suffix}_{int(time.time())}@example.com",
        "phone": "9999999991",
        "current_designation": "QA",
        "current_company": "TestCo",
        "experience_years": 4,
        "location": "Pune",
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_platform": "naukri",
        "extension_version": "5.5.10",
    }


def _wait_for_completion(token: str, job_id: str, *, timeout_s: int = 45) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        r = requests.get(
            f"{API_BASE}/extension/capture/status/{job_id}",
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200, r.text
        last = r.json()
        if last["status"] in ("completed", "failed"):
            return last
        time.sleep(2)
    raise AssertionError(f"job {job_id} did not finish within {timeout_s}s. Last: {last}")


def test_async_capture_submit_poll_complete():
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}

    r = requests.post(
        f"{API_BASE}/extension/capture/async",
        json=_profile_payload("happy"),
        headers=headers,
        timeout=10,
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert "job_id" in body
    assert body["status"] == "pending"

    job = _wait_for_completion(token, body["job_id"])
    assert job["status"] == "completed", f"job not completed: {job}"
    result = job["result"]
    # CaptureResponse contract
    assert result["success"] is True
    assert result["action"] in ("created", "updated", "exists")
    assert isinstance(result["candidate_id"], str) and result["candidate_id"]
    assert "message" in result


def test_sync_capture_backward_compat():
    """Team on v5.5.8 still uses the sync /capture endpoint — must not break."""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(
        f"{API_BASE}/extension/capture",
        json=_profile_payload("synccompat"),
        headers=headers,
        timeout=120,  # sync path is slow; allow generous timeout
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["action"] in ("created", "updated", "exists")


def test_status_endpoint_auth_and_404():
    # No auth
    r = requests.get(f"{API_BASE}/extension/capture/status/nonexistent", timeout=10)
    assert r.status_code in (401, 403)

    # Authed but unknown job_id
    token = _login()
    r = requests.get(
        f"{API_BASE}/extension/capture/status/definitely-not-a-real-job-id",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 404
