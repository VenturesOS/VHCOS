"""
Phase 55.11j — Tests for /app/backend/scripts/reset_admin_password.py

Verifies the emergency admin-password-reset script:
  1. Writes a valid bcrypt hash into password_hash + hashed_password fields
  2. Refuses to touch DB if the target user does not exist
  3. Never prints plaintext password
  4. Flips is_active back to True
  5. Idempotent (two runs both succeed)
  6. Requires --password / $ADMIN_RESET_PASSWORD
  7. bcrypt.checkpw positive / negative controls
  8. Full E2E: after reset, POST /api/auth/login returns 200

Test users are seeded with a `RESET_TEST_` email prefix so we can clean up.
The admin@vhc.in record is NEVER modified by this test-file.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

import bcrypt
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
SCRIPT = "/app/backend/scripts/reset_admin_password.py"


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL, tlsAllowInvalidCertificates=True, serverSelectionTimeoutMS=8000)
    yield c[DB_NAME]
    c.close()


def _seed_user(db, *, email_suffix: str, is_active: bool = True, password_hash_val: str = "") -> str:
    email = f"RESET_TEST_{email_suffix}_{uuid.uuid4().hex[:6]}@example.com"
    doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": "Reset Test User",
        "role": "recruiter",
        "is_active": is_active,
        "password": "",            # login-route field; empty simulates the broken prod state
        "password_hash": password_hash_val,
        "hashed_password": password_hash_val,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "token_version": 1,
        "requires_password_reset": False,
        "company_id": None,
    }
    db.users.insert_one(doc)
    return email


@pytest.fixture
def seeded_user(db):
    email = _seed_user(db, email_suffix="basic")
    yield email
    db.users.delete_one({"email": email})


def _run_script(*args, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, env=env, timeout=60,
    )


# ---------- 1. Writes bcrypt hash to password_hash + hashed_password ----------
def test_writes_valid_bcrypt_hash(db, seeded_user):
    pwd = "TestPass@2026"
    r = _run_script("--email", seeded_user, "--password", pwd)
    assert r.returncode == 0, r.stderr + r.stdout
    u = db.users.find_one({"email": seeded_user})
    ph = u.get("password_hash") or ""
    hp = u.get("hashed_password") or ""
    assert ph.startswith(("$2a$", "$2b$", "$2y$")), f"password_hash bad: {ph[:8]}"
    assert 55 <= len(ph) <= 65, f"len={len(ph)}"
    assert ph == hp, "password_hash and hashed_password must match"


# ---------- 2. Nonexistent email — must not create user ----------
def test_nonexistent_email_exit_3_no_create(db):
    email = f"RESET_TEST_ghost_{uuid.uuid4().hex[:8]}@example.com"
    count_before = db.users.count_documents({})
    r = _run_script("--email", email, "--password", "Whatever@2026")
    assert r.returncode == 3, f"expected exit 3, got {r.returncode}. out={r.stdout} err={r.stderr}"
    assert "user_not_found" in (r.stdout + r.stderr)
    assert db.users.count_documents({"email": email}) == 0
    assert db.users.count_documents({}) == count_before


# ---------- 3. No plaintext password in stdout/stderr ----------
def test_no_plaintext_in_output(db, seeded_user):
    pwd = "SuperSecret_ZZZ9!x"
    r = _run_script("--email", seeded_user, "--password", pwd)
    assert r.returncode == 0
    assert pwd not in r.stdout, f"plaintext leaked in stdout"
    assert pwd not in r.stderr, f"plaintext leaked in stderr"


# ---------- 4. Sets is_active=True on a disabled user ----------
def test_reactivates_disabled_user(db):
    email = _seed_user(db, email_suffix="disabled", is_active=False)
    try:
        r = _run_script("--email", email, "--password", "Reactivate@2026")
        assert r.returncode == 0, r.stdout + r.stderr
        u = db.users.find_one({"email": email})
        assert u["is_active"] is True
    finally:
        db.users.delete_one({"email": email})


# ---------- 5. Idempotency ----------
def test_idempotent_two_runs(db, seeded_user):
    pwd = "Idempotent@2026"
    r1 = _run_script("--email", seeded_user, "--password", pwd)
    assert r1.returncode == 0
    h1 = db.users.find_one({"email": seeded_user})["password_hash"]
    r2 = _run_script("--email", seeded_user, "--password", pwd)
    assert r2.returncode == 0
    h2 = db.users.find_one({"email": seeded_user})["password_hash"]
    # Salted -> different hashes, but both must verify
    assert bcrypt.checkpw(pwd.encode(), h1.encode())
    assert bcrypt.checkpw(pwd.encode(), h2.encode())


# ---------- 6. Missing password argument ----------
def test_requires_password_arg(db, seeded_user):
    env = {k: v for k, v in os.environ.items() if k != "ADMIN_RESET_PASSWORD"}
    r = subprocess.run(
        [sys.executable, SCRIPT, "--email", seeded_user],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert r.returncode == 1, f"expected exit 1, got {r.returncode}"
    # DB must be untouched (password_hash still empty)
    u = db.users.find_one({"email": seeded_user})
    assert not u.get("password_hash")


def test_password_from_env_var(db, seeded_user):
    pwd = "FromEnv@2026"
    r = _run_script("--email", seeded_user, env_extra={"ADMIN_RESET_PASSWORD": pwd})
    assert r.returncode == 0, r.stdout + r.stderr
    u = db.users.find_one({"email": seeded_user})
    assert bcrypt.checkpw(pwd.encode(), u["password_hash"].encode())


# ---------- 7. bcrypt positive/negative controls ----------
def test_bcrypt_positive_negative_control(db, seeded_user):
    pwd = "Control@2026"
    r = _run_script("--email", seeded_user, "--password", pwd)
    assert r.returncode == 0
    stored = db.users.find_one({"email": seeded_user})["password_hash"].encode()
    assert bcrypt.checkpw(pwd.encode(), stored) is True
    assert bcrypt.checkpw(b"WrongPassword@2026", stored) is False


# ---------- 8. Full E2E: reset then login via API ----------
def test_login_endpoint_after_reset(db):
    """
    ACCEPTANCE TEST for the phase-55.11j fix.
    Seeds a user with EMPTY password fields, runs the reset script, then hits
    POST /api/auth/login with the plaintext. Expected: HTTP 200 + bearer token.

    NOTE: The current login route (routes/auth.py) reads user["password"]
    while the reset script writes only to user["password_hash"] and
    user["hashed_password"]. If these disagree, this test will fail — which
    is a real bug we must surface.
    """
    email = _seed_user(db, email_suffix="loginflow")
    pwd = "LoginFlow@2026"
    try:
        r = _run_script("--email", email, "--password", pwd)
        assert r.returncode == 0, r.stdout + r.stderr

        # small wait so any read-your-writes propagation settles
        time.sleep(1)

        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": pwd},
            timeout=20,
        )
        assert resp.status_code == 200, (
            f"login failed after reset — status={resp.status_code}, "
            f"body={resp.text[:300]}. "
            f"Root cause: reset script writes to password_hash/hashed_password, "
            f"but /api/auth/login reads user['password']."
        )
        data = resp.json()
        assert "access_token" in data
        assert isinstance(data["access_token"], str) and len(data["access_token"]) > 20
    finally:
        db.users.delete_one({"email": email})


# ---------- 9. Sanity: real admin login already works (do NOT reset admin) ----------
def test_admin_login_baseline():
    """Baseline: admin@vhc.in should already be able to log in with the
    documented password. We do NOT run the reset script against admin here."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@vhc.in", "password": "VhcAdmin@2024"},
        timeout=20,
    )
    assert resp.status_code == 200, f"admin baseline broken: {resp.status_code} {resp.text[:300]}"
    assert "access_token" in resp.json()


# ---------- 10. Cleanup residual RESET_TEST_ users ----------
def test_cleanup_reset_test_users(db):
    """Housekeeping — deletes any leftover RESET_TEST_ users (safety net)."""
    res = db.users.delete_many({"email": {"$regex": "^RESET_TEST_"}})
    print(f"cleanup: removed {res.deleted_count} RESET_TEST_ users")
