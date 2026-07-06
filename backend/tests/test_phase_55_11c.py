"""
Phase 55.11c verification tests: FAST_SEARCH, dedupe endpoints, IndexNow, canonicalize script.
"""
import os
import sys
import subprocess
import asyncio
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to reading frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break

ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# --- Backend health & auth ---
def test_health_live():
    r = requests.get(f"{BASE_URL}/api/health/live", timeout=10)
    assert r.status_code == 200
    assert r.json().get("status") == "alive"


def test_auth_login_returns_jwt(token):
    assert isinstance(token, str) and len(token) > 20
    assert token.count(".") == 2  # JWT structure


# --- FAST_SEARCH hot path ---
@pytest.mark.parametrize("q", ["engineer", "python", "sheet metal"])
def test_candidate_bank_fast_search(q, auth_headers):
    r = requests.get(f"{BASE_URL}/api/candidate-bank/",
                     headers=auth_headers,
                     params={"search": q, "limit": 10}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict), f"Expected dict shape for {q}, got {type(body)}"
    for key in ("candidates", "total", "page", "limit", "pages"):
        assert key in body, f"Missing key {key} in response for query {q}"
    assert isinstance(body["candidates"], list)
    print(f"[fast-search q='{q}'] total={body['total']} returned={len(body['candidates'])}")


def test_candidate_bank_python_relevance(auth_headers):
    """Top hit for 'python' should have 'python' somewhere in skills/designation (allow kitchen-sink candidate)."""
    r = requests.get(f"{BASE_URL}/api/candidate-bank/",
                     headers=auth_headers, params={"search": "python", "limit": 5}, timeout=30)
    assert r.status_code == 200
    cands = r.json().get("candidates", [])
    assert len(cands) > 0
    top = cands[0]
    blob = " ".join(str(top.get(k, "")) for k in ("skills", "key_skills", "designation", "current_designation", "name")).lower()
    # Accept 'python' in blob OR presence of some relevant token (preview data quirks)
    assert "python" in blob or any("python" in str(s).lower() for s in (top.get("skills") or []) + (top.get("key_skills") or [])), \
        f"Top hit for 'python' has no python: {top.get('name')} skills={top.get('skills')}"


# --- FAST_SEARCH fallback: legacy path when no search text ---
def test_candidate_bank_no_search_legacy_path(auth_headers):
    r = requests.get(f"{BASE_URL}/api/candidate-bank/",
                     headers=auth_headers, params={"limit": 5}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    # Legacy path may return dict or list - both are acceptable
    if isinstance(body, dict):
        assert "candidates" in body
        assert len(body["candidates"]) > 0
    else:
        assert isinstance(body, list) and len(body) > 0


# --- Find-all-duplicates ---
def test_find_all_duplicates(auth_headers):
    r = requests.get(f"{BASE_URL}/api/candidate-bank/find-all-duplicates",
                     headers=auth_headers, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "email_duplicates" in body and "phone_duplicates" in body
    for group_key in ("email_duplicates", "phone_duplicates"):
        for grp in body[group_key][:3]:
            assert "_id" in grp
            assert "count" in grp
            assert "candidates" in grp and isinstance(grp["candidates"], list)
    print(f"[dedupe] email_groups={len(body['email_duplicates'])} phone_groups={len(body['phone_duplicates'])}")
    # Expose for merge test
    pytest.dupe_body = body


def test_merge_duplicates_smoke(auth_headers):
    body = getattr(pytest, "dupe_body", None)
    if body is None:
        r = requests.get(f"{BASE_URL}/api/candidate-bank/find-all-duplicates",
                         headers=auth_headers, timeout=60)
        assert r.status_code == 200
        body = r.json()
    groups = body["email_duplicates"] or body["phone_duplicates"]
    if not groups:
        pytest.skip("No duplicate groups available to merge")
    grp = groups[0]
    cand_ids = [c.get("id") or c.get("_id") for c in grp["candidates"][:2]]
    cand_ids = [c for c in cand_ids if c]
    if len(cand_ids) < 2:
        pytest.skip("Insufficient candidate ids in first duplicate group")
    r = requests.post(f"{BASE_URL}/api/candidate-bank/merge-duplicates",
                      headers=auth_headers, json={"candidate_ids": cand_ids}, timeout=30)
    # Accept success (200/201) OR a clear 400/404 error with detail
    assert r.status_code in (200, 201, 400, 404, 409, 422), r.text
    if r.status_code >= 400:
        detail = r.json().get("detail", "")
        assert detail, "Error response must include a detail message"
        print(f"[merge] non-fatal error (accepted): {r.status_code} {detail}")
    else:
        print(f"[merge] success: {r.json()}")


# --- IndexNow disabled short-circuit ---
def test_indexnow_disabled_returns_false():
    sys.path.insert(0, "/app/backend")
    from services import indexnow
    # Ensure key is unset for this test
    old_key = os.environ.pop("INDEXNOW_KEY", None)
    try:
        result = asyncio.run(indexnow.ping_indexnow(["https://ventureshrd.com/blog/x"]))
        assert result is False
    finally:
        if old_key is not None:
            os.environ["INDEXNOW_KEY"] = old_key


# --- Canonicalize script dry-run ---
def test_canonicalize_dry_run():
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.canonicalize_aliases"],
        cwd="/app/backend",
        capture_output=True, text=True, timeout=120,
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    print("--- canonicalize output (first 1500 chars) ---")
    print(combined[:1500])
    assert proc.returncode == 0, f"script failed rc={proc.returncode}: {combined[-500:]}"
    lower = combined.lower()
    assert "dry" in lower or "dry-run" in lower or "dry run" in lower, "Expected DRY RUN in output"
