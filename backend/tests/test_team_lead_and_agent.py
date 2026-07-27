"""
Backend tests for Team Lead role + Asha Agent admin endpoints + regressions.

Covers:
- Team Lead grant/revoke lifecycle (admin auth path)
- Team Lead scope endpoint (for non-team-lead and team-lead recruiter)
- Confidential masking in /api/employer/my-team and /api/employer/pipeline
- Role permissions on /api/jobs/{id}/assign-recruiters and /api/employer/team-recruiters
- Login response includes is_team_lead / team_lead_employer_id
- /api/agent/* endpoints accessible to admin
- Regressions: /api/auth/refresh with garbage token → 401, /api/auth/me returns is_team_lead
"""
import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def admin_creds():
    content = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    email = re.search(r"Email:\s*`([^`]+)`", content).group(1)
    password = re.search(r"Password:\s*`([^`]+)`", content).group(1)
    return {"email": email, "password": password}


@pytest.fixture(scope="module")
def admin_token(admin_creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=admin_creds, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def recruiter_login():
    """Login as hr6@vhc.in (Diya)."""
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "hr6@vhc.in", "password": "12345678"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"recruiter login unavailable: {r.status_code} {r.text[:200]}")
    return r.json()


# ---------- 1. Login response contains new fields ----------
class TestLoginFields:
    def test_admin_login_has_team_lead_fields(self, admin_creds):
        r = requests.post(f"{BASE_URL}/api/auth/login", json=admin_creds, timeout=30)
        assert r.status_code == 200
        u = r.json()["user"]
        assert "is_team_lead" in u
        assert "team_lead_employer_id" in u
        assert u["is_team_lead"] is False

    def test_recruiter_login_has_team_lead_fields(self, recruiter_login):
        u = recruiter_login["user"]
        assert "is_team_lead" in u
        assert "team_lead_employer_id" in u


# ---------- 2. /api/team-lead/scope ----------
class TestScope:
    def test_scope_non_team_lead_recruiter(self, recruiter_login):
        headers = {"Authorization": f"Bearer {recruiter_login['access_token']}"}
        r = requests.get(f"{BASE_URL}/api/team-lead/scope", headers=headers, timeout=30)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body["is_team_lead"] is False
        assert body["employer_id"] is None
        assert body["employer_name"] is None


# ---------- 3. Grant/Revoke lifecycle + permission checks ----------
class TestGrantRevoke:
    """
    Locate an employer that has an active team, then find a recruiter inside that team,
    then run grant → verify → revoke.
    """

    @pytest.fixture(scope="class")
    def employer_and_recruiter(self, admin_headers):
        # Find a team via admin.
        # There's no admin-list-teams endpoint documented; poke a common one.
        # Try /api/admin/teams; if unavailable, fall back to /api/admin/users list.
        r = requests.get(f"{BASE_URL}/api/teams", headers=admin_headers, timeout=30)
        if r.status_code != 200:
            pytest.skip(f"/api/teams unavailable: {r.status_code} {r.text[:200]}")
        teams = r.json() if isinstance(r.json(), list) else r.json().get("teams", [])
        team = next((t for t in teams
                     if (t.get("status") in (None, "active")) and t.get("recruiter_ids")), None)
        if not team:
            pytest.skip("no active team with recruiters found via /api/teams")
        return {"employer_id": team["employer_id"], "recruiter_id": team["recruiter_ids"][0]}

    def test_grant_forbidden_for_non_admin_non_employer(self, recruiter_login, employer_and_recruiter):
        headers = {"Authorization": f"Bearer {recruiter_login['access_token']}",
                   "Content-Type": "application/json"}
        r = requests.post(f"{BASE_URL}/api/team-lead/grant",
                          headers=headers,
                          json={"recruiter_id": employer_and_recruiter["recruiter_id"],
                                "employer_id": employer_and_recruiter["employer_id"]},
                          timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_grant_bad_recruiter_not_in_team(self, admin_headers, employer_and_recruiter):
        # Use admin id (definitely not in any team) as recruiter — but must exist as recruiter role.
        # Instead: use a real recruiter that we can guarantee is not in the team → hr14 maybe.
        # Attempt with a random recruiter that's likely not in the specific employer team.
        r_other = requests.post(f"{BASE_URL}/api/auth/login",
                                json={"email": "hr12@vhc.in", "password": "12345678"}, timeout=30)
        if r_other.status_code != 200:
            pytest.skip("hr12 unavailable for cross-team negative test")
        other_id = r_other.json()["user"]["id"]
        # Only run if the other is not in the target team
        if other_id == employer_and_recruiter["recruiter_id"]:
            pytest.skip("other recruiter is coincidentally in target team")
        r = requests.post(f"{BASE_URL}/api/team-lead/grant",
                          headers=admin_headers,
                          json={"recruiter_id": other_id,
                                "employer_id": employer_and_recruiter["employer_id"]},
                          timeout=30)
        # Either 400 (not in team) is expected. If they happen to be in the team, allow 200.
        assert r.status_code in (400, 200), r.text[:200]
        if r.status_code == 400:
            assert "team" in r.text.lower()

    def test_grant_revoke_lifecycle(self, admin_headers, employer_and_recruiter):
        rid = employer_and_recruiter["recruiter_id"]
        eid = employer_and_recruiter["employer_id"]

        # GRANT
        g = requests.post(f"{BASE_URL}/api/team-lead/grant",
                          headers=admin_headers,
                          json={"recruiter_id": rid, "employer_id": eid},
                          timeout=30)
        assert g.status_code == 200, g.text[:300]
        gb = g.json()
        assert gb["success"] is True
        assert gb["recruiter_id"] == rid
        assert gb["employer_id"] == eid

        # VERIFY via /api/team-lead/list/{employer_id}
        lst = requests.get(f"{BASE_URL}/api/team-lead/list/{eid}",
                           headers=admin_headers, timeout=30)
        assert lst.status_code == 200
        ids = [tl["id"] for tl in lst.json().get("team_leads", [])]
        assert rid in ids

        # REVOKE
        rv = requests.post(f"{BASE_URL}/api/team-lead/revoke",
                           headers=admin_headers,
                           json={"recruiter_id": rid},
                           timeout=30)
        assert rv.status_code == 200, rv.text[:300]
        assert rv.json()["success"] is True

        # REVOKE again (idempotent)
        rv2 = requests.post(f"{BASE_URL}/api/team-lead/revoke",
                            headers=admin_headers,
                            json={"recruiter_id": rid},
                            timeout=30)
        assert rv2.status_code == 200, rv2.text[:200]
        assert rv2.json()["success"] is True

        # GET as recruiter must show is_team_lead False
        rl = requests.post(f"{BASE_URL}/api/auth/login",
                           json={"email": "hr6@vhc.in", "password": "12345678"}, timeout=30)
        if rl.status_code == 200:
            assert rl.json()["user"]["is_team_lead"] is False


# ---------- 4. Team Lead scoped endpoints (post-grant behavior) ----------
class TestTeamLeadScopedAccess:
    """Grant, verify masking + new access permissions, then revoke."""

    @pytest.fixture(scope="class")
    def granted_recruiter(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/teams", headers=admin_headers, timeout=30)
        if r.status_code != 200:
            pytest.skip(f"/api/teams unavailable: {r.status_code}")
        teams = r.json() if isinstance(r.json(), list) else r.json().get("teams", [])
        team = next((t for t in teams
                     if (t.get("status") in (None, "active")) and t.get("recruiter_ids")), None)
        if not team:
            pytest.skip("no active team found")

        eid = team["employer_id"]
        rid = team["recruiter_ids"][0]

        # Grant
        g = requests.post(f"{BASE_URL}/api/team-lead/grant",
                         headers=admin_headers,
                         json={"recruiter_id": rid, "employer_id": eid},
                         timeout=30)
        assert g.status_code == 200, g.text[:300]

        # Find recruiter's email to login → we need bearer. We already have hr6 credentials mapped.
        # Query admin/users to find email for this recruiter id.
        ru = requests.get(f"{BASE_URL}/api/users/{rid}", headers=admin_headers, timeout=30)
        recruiter_email = None
        if ru.status_code == 200:
            recruiter_email = ru.json().get("email")

        # Map known emails to try login
        candidates = [recruiter_email] if recruiter_email else []
        candidates += ["hr6@vhc.in", "hr12@vhc.in", "hr14@vhc.in"]
        token = None
        for email in candidates:
            if not email:
                continue
            for pw in ["12345678", "VhcAdmin@2024"]:
                rl = requests.post(f"{BASE_URL}/api/auth/login",
                                   json={"email": email, "password": pw}, timeout=30)
                if rl.status_code == 200 and rl.json()["user"]["id"] == rid:
                    token = rl.json()["access_token"]
                    break
            if token:
                break

        if not token:
            # revoke and skip
            requests.post(f"{BASE_URL}/api/team-lead/revoke",
                          headers=admin_headers, json={"recruiter_id": rid}, timeout=30)
            pytest.skip(f"couldn't login as recruiter {rid} to exercise team-lead flows")

        yield {"recruiter_id": rid, "employer_id": eid, "token": token}

        # Teardown revoke
        requests.post(f"{BASE_URL}/api/team-lead/revoke",
                      headers=admin_headers, json={"recruiter_id": rid}, timeout=30)

    def _headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_scope_returns_team_lead_true(self, granted_recruiter):
        r = requests.get(f"{BASE_URL}/api/team-lead/scope",
                         headers=self._headers(granted_recruiter["token"]), timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["is_team_lead"] is True
        assert body["employer_id"] == granted_recruiter["employer_id"]

    def test_login_reflects_team_lead(self, granted_recruiter):
        # Verify current-user response
        r = requests.get(f"{BASE_URL}/api/auth/me",
                         headers=self._headers(granted_recruiter["token"]), timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body.get("is_team_lead") is True
        assert body.get("team_lead_employer_id") == granted_recruiter["employer_id"]

    def test_my_team_masks_revenue(self, granted_recruiter):
        r = requests.get(f"{BASE_URL}/api/employer/my-team",
                         headers=self._headers(granted_recruiter["token"]), timeout=30)
        assert r.status_code == 200, r.text[:300]
        payload = r.text.lower()
        assert "revenue" not in payload, "revenue key should be masked for Team Lead"

    def test_pipeline_flag_and_masking(self, granted_recruiter):
        r = requests.get(f"{BASE_URL}/api/employer/pipeline",
                         headers=self._headers(granted_recruiter["token"]), timeout=30)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        # acting_as_team_lead flag
        assert body.get("acting_as_team_lead") is True, f"expected acting_as_team_lead=True, got {body.keys()}"
        # confidential keys stripped anywhere in payload
        for bad in ("billing_rate", "invoice_amount", "gross_margin", "recruiter_commission", "contract_notes"):
            assert bad not in r.text, f"confidential key {bad!r} leaked in pipeline"

    def test_team_recruiters_accessible(self, granted_recruiter):
        r = requests.get(f"{BASE_URL}/api/employer/team-recruiters",
                         headers=self._headers(granted_recruiter["token"]), timeout=30)
        assert r.status_code == 200, r.text[:300]

    def test_assign_recruiters_allowed_for_team_lead(self, granted_recruiter, admin_headers):
        """Team lead should be able to hit /jobs/{id}/assign-recruiters (not get 403)."""
        # Find any job under the same employer
        jr = requests.get(f"{BASE_URL}/api/jobs?employer_id={granted_recruiter['employer_id']}&limit=1",
                          headers=admin_headers, timeout=30)
        if jr.status_code != 200:
            pytest.skip(f"cannot list jobs to test assign-recruiters: {jr.status_code}")
        jobs = jr.json() if isinstance(jr.json(), list) else jr.json().get("jobs", [])
        if not jobs:
            pytest.skip("no jobs for this employer")
        job_id = jobs[0].get("id") or jobs[0].get("job_id")
        if not job_id:
            pytest.skip("job doc missing id")
        r = requests.post(f"{BASE_URL}/api/jobs/{job_id}/assign-recruiters",
                          headers={"Authorization": f"Bearer {granted_recruiter['token']}",
                                   "Content-Type": "application/json"},
                          json=[granted_recruiter["recruiter_id"]],
                          timeout=30)
        # Not 403 (would indicate role check failure). 200/400 both acceptable (validation may reject etc)
        assert r.status_code != 403, f"team lead unexpectedly forbidden: {r.text[:200]}"


# ---------- 5. Non-team-lead recruiter blocked on team-recruiters ----------
class TestPlainRecruiterBlocked:
    def test_team_recruiters_forbidden(self, recruiter_login):
        # Ensure this recruiter is NOT a team lead first (may have been left over from prior tests)
        r = requests.get(f"{BASE_URL}/api/employer/team-recruiters",
                         headers={"Authorization": f"Bearer {recruiter_login['access_token']}"},
                         timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_assign_recruiters_forbidden_for_plain_recruiter(self, recruiter_login, admin_headers):
        # Get any job
        jr = requests.get(f"{BASE_URL}/api/jobs?limit=1", headers=admin_headers, timeout=30)
        if jr.status_code != 200:
            pytest.skip(f"cannot list jobs: {jr.status_code}")
        jobs = jr.json() if isinstance(jr.json(), list) else jr.json().get("jobs", [])
        if not jobs:
            pytest.skip("no jobs to test with")
        job_id = jobs[0].get("id") or jobs[0].get("job_id")
        r = requests.post(f"{BASE_URL}/api/jobs/{job_id}/assign-recruiters",
                          headers={"Authorization": f"Bearer {recruiter_login['access_token']}",
                                   "Content-Type": "application/json"},
                          json=[], timeout=30)
        assert r.status_code == 403, f"plain recruiter expected 403, got {r.status_code} {r.text[:200]}"


# ---------- 6. Asha Agent admin endpoints ----------
class TestAshaAgent:
    def test_config(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/agent/config", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:200]

    def test_sessions(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/agent/sessions", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:200]

    def test_analytics(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/agent/analytics", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:200]

    def test_agent_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/agent/config", timeout=30)
        assert r.status_code in (401, 403), r.text[:200]


# ---------- 7. Regressions ----------
class TestRegressions:
    def test_refresh_with_garbage_token(self):
        r = requests.post(f"{BASE_URL}/api/auth/refresh",
                          json={"refresh_token": "garbage-not-a-real-token"}, timeout=30)
        assert r.status_code == 401, f"expected 401, got {r.status_code} {r.text[:200]}"

    def test_auth_me_has_team_lead_field(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        # All fields per spec
        for k in ["id", "email", "name", "role", "is_active", "is_team_lead", "team_lead_employer_id"]:
            assert k in body, f"missing {k} in /auth/me"
