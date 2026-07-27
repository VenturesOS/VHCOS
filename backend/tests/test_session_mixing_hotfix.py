"""
Regression tests for the Madhuri→Nidhi session-mixing hotfix (2026-07-24).

The bug: on login, the previous user's `vhc_refresh_token` in localStorage was
preserved. On next 401 the frontend axios interceptor would refresh with the
STALE refresh_token — backend correctly issues a new access token for the
OLD user, silently flipping the current session.

The fix is FRONTEND-only. On backend we only assert:
  (a) each successful login returns a fresh, distinct refresh_token
  (b) POST /api/auth/refresh with token X always returns identity X
      (never leaks the wrong user), and token X is single-use.
"""
import os
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing")
BASE_URL = base_url.rstrip("/")

USER_A = {"email": "hr6@vhc.in",  "password": "12345678"}
USER_B = {"email": "hr12@vhc.in", "password": "12345678"}


@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(http, creds):
    r = http.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert "access_token" in body and "refresh_token" in body
    assert body["refresh_token"], "refresh_token must be non-empty"
    return body


class TestSessionMixingRefreshIntegrity:
    """Backend refresh endpoint must return identity of refresh-token owner ONLY."""

    def test_two_logins_return_distinct_refresh_tokens(self, http):
        a = _login(http, USER_A)
        b = _login(http, USER_B)
        assert a["refresh_token"] != b["refresh_token"], "distinct users must get distinct refresh tokens"
        assert a["user"]["id"] != b["user"]["id"]
        assert a["user"]["email"] == USER_A["email"]
        assert b["user"]["email"] == USER_B["email"]

    def test_refresh_returns_owner_identity_A(self, http):
        a = _login(http, USER_A)
        r = http.post(f"{BASE_URL}/api/auth/refresh", json={"refresh_token": a["refresh_token"]}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body["user"]["id"] == a["user"]["id"]
        assert body["user"]["email"] == USER_A["email"]

    def test_refresh_returns_owner_identity_B(self, http):
        b = _login(http, USER_B)
        r = http.post(f"{BASE_URL}/api/auth/refresh", json={"refresh_token": b["refresh_token"]}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body["user"]["id"] == b["user"]["id"]
        assert body["user"]["email"] == USER_B["email"]

    def test_refresh_token_is_single_use(self, http):
        a = _login(http, USER_A)
        stale = a["refresh_token"]
        # First use — succeeds
        r1 = http.post(f"{BASE_URL}/api/auth/refresh", json={"refresh_token": stale}, timeout=30)
        assert r1.status_code == 200
        # Second use of same token — must be rejected
        r2 = http.post(f"{BASE_URL}/api/auth/refresh", json={"refresh_token": stale}, timeout=30)
        assert r2.status_code in (401, 403), f"reused refresh token should be rejected, got {r2.status_code}"

    def test_userA_refresh_never_leaks_userB_identity(self, http):
        """The critical property: even with two active sessions, using A's refresh
        token MUST return A (never B). Frontend fix ensures A's token is wiped
        on B's login; backend fix ensures the tokens are keyed to their owner."""
        a = _login(http, USER_A)
        _ = _login(http, USER_B)  # simulate second user logging in on same device
        # Now use A's still-valid refresh token — backend must return A, not B
        r = http.post(f"{BASE_URL}/api/auth/refresh", json={"refresh_token": a["refresh_token"]}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body["user"]["email"] == USER_A["email"], \
            f"CRITICAL: A's refresh token returned {body['user']['email']} instead of {USER_A['email']}"

    def test_me_endpoint_uses_access_token_owner(self, http):
        a = _login(http, USER_A)
        b = _login(http, USER_B)
        rA = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {a['access_token']}"}, timeout=30)
        rB = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {b['access_token']}"}, timeout=30)
        assert rA.status_code == 200 and rB.status_code == 200
        assert rA.json()["email"] == USER_A["email"]
        assert rB.json()["email"] == USER_B["email"]
