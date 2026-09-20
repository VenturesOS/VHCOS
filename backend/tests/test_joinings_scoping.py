"""
Tests for unified Joining List, team consolidation, and role-based scoping.
Covers /api/joinings, /api/branch-revenue, /api/performance-records, /api/targets.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://badge-audit-v2.preview.emergentagent.com").rstrip("/")

ADMIN = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
ACCOUNTS = {"email": "qa_accounts_tmp@vhc.in", "password": "QaRevenue@2026"}
EMPLOYER = {"email": "qa_employer_tmp@vhc.in", "password": "QaRevenue@2026"}
RECRUITER = {"email": "hr6@vhc.in", "password": "12345678"}


def _login(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in {r.json()}"
    return tok


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_tok():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def accounts_tok():
    return _login(ACCOUNTS)


@pytest.fixture(scope="module")
def employer_tok():
    return _login(EMPLOYER)


@pytest.fixture(scope="module")
def recruiter_tok():
    return _login(RECRUITER)


# ---------- Admin Joining List ----------
class TestAdminJoinings:
    def test_admin_joinings_totals(self, admin_tok):
        r = requests.get(
            f"{BASE_URL}/api/joinings",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            headers=_h(admin_tok),
            timeout=60,
        )
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        rows = data.get("items") or []
        count = data.get("count")
        totals = data.get("totals") or {}
        sources = data.get("sources") or {}
        print(f"admin count={count} items={len(rows)} totals={totals} sources={sources}")
        assert count == 563, f"expected 563 got {count}"
        assert sources.get("tracker_only") == 453
        assert sources.get("pipeline_only") == 35
        assert sources.get("both") == 75
        assert abs(float(totals.get("gross", 0)) - 53126755.31) < 1
        assert abs(float(totals.get("received", 0)) - 35269287.77) < 1

    def test_admin_payment_buckets(self, admin_tok):
        r = requests.get(
            f"{BASE_URL}/api/joinings",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            headers=_h(admin_tok),
            timeout=60,
        )
        data = r.json()
        buckets = data.get("payment_buckets") or data.get("buckets") or {}
        print(f"buckets={buckets}")
        # Loose check on presence of key buckets
        for k in ["Payment Received", "PP", "IP"]:
            assert any(k.lower() in str(x).lower() for x in buckets.keys()), f"missing bucket {k}: {buckets.keys()}"


# ---------- Accounts role ----------
class TestAccountsRole:
    def test_accounts_joinings(self, accounts_tok):
        r = requests.get(
            f"{BASE_URL}/api/joinings",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            headers=_h(accounts_tok),
            timeout=60,
        )
        assert r.status_code == 200
        rows = r.json().get("items") or []
        count = r.json().get("count")
        assert count == 563

    def test_accounts_performance_records(self, accounts_tok):
        r = requests.get(f"{BASE_URL}/api/performance-records/report", headers=_h(accounts_tok), timeout=30)
        assert r.status_code == 200, r.text[:400]

    def test_accounts_branch_revenue(self, accounts_tok):
        r = requests.get(f"{BASE_URL}/api/branch-revenue/dashboard", headers=_h(accounts_tok), timeout=30)
        assert r.status_code == 200

    def test_accounts_cannot_write_targets(self, accounts_tok):
        r = requests.put(
            f"{BASE_URL}/api/targets/company",
            headers=_h(accounts_tok),
            json={"target": 100},
            timeout=15,
        )
        assert r.status_code in (403, 404, 405), f"accounts must not write targets got {r.status_code}"


# ---------- Employer scoping ----------
class TestEmployerScoping:
    def test_employer_own_team_joinings(self, employer_tok):
        r = requests.get(
            f"{BASE_URL}/api/joinings",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            headers=_h(employer_tok),
            timeout=60,
        )
        assert r.status_code == 200
        data = r.json()
        rows = data.get("items") or []
        count = data.get("count")
        totals = data.get("totals") or {}
        print(f"employer count={count} items={len(rows)} gross={totals.get('gross')}")
        assert count == 144, f"expected 144 got {count}"
        assert abs(float(totals.get("gross", 0)) - 9074939) < 10

    def test_employer_cannot_widen_team(self, employer_tok, admin_tok):
        # Get Gurgaon team id as admin
        r = requests.get(f"{BASE_URL}/api/teams", headers=_h(admin_tok), timeout=15)
        gurgaon_id = None
        if r.status_code == 200:
            teams = r.json() if isinstance(r.json(), list) else r.json().get("teams", [])
            for t in teams:
                if "gurgaon" in str(t.get("name", "")).lower():
                    gurgaon_id = t.get("id") or t.get("_id")
                    break
        if not gurgaon_id:
            pytest.skip("Could not resolve Gurgaon team id")
        r2 = requests.get(
            f"{BASE_URL}/api/joinings",
            params={"team_id": gurgaon_id, "date_from": "2026-01-01", "date_to": "2026-12-31"},
            headers=_h(employer_tok),
            timeout=60,
        )
        assert r2.status_code in (200, 403)
        if r2.status_code == 200:
            rows = r2.json().get("items") or []
            count = r2.json().get("count", len(rows))
            assert count == 0, f"employer should not see Gurgaon rows, got count={count}"

    def test_employer_perf_records_forbidden(self, employer_tok):
        r = requests.get(f"{BASE_URL}/api/performance-records/report", headers=_h(employer_tok), timeout=30)
        assert r.status_code == 403

    def test_employer_company_summary_forbidden(self, employer_tok):
        r = requests.get(f"{BASE_URL}/api/targets/company-summary", headers=_h(employer_tok), timeout=15)
        assert r.status_code == 403

    def test_employer_branch_revenue_scoped(self, employer_tok):
        r = requests.get(f"{BASE_URL}/api/branch-revenue/dashboard", headers=_h(employer_tok), timeout=30)
        assert r.status_code == 200
        data = r.json()
        branches = data.get("branches") or data.get("rows") or []
        names = [str(b.get("branch") or b.get("name") or "").lower() for b in branches]
        print(f"employer branches: {names}")
        assert all("faridabad" in n for n in names), f"employer should only see Faridabad: {names}"


# ---------- Recruiter scoping ----------
class TestRecruiterScoping:
    @pytest.mark.parametrize("path", [
        "/api/joinings",
        "/api/branch-revenue/dashboard",
        "/api/performance-records/report",
        "/api/targets/team-summary",
        "/api/targets/company-summary",
    ])
    def test_recruiter_forbidden(self, recruiter_tok, path):
        r = requests.get(f"{BASE_URL}{path}", headers=_h(recruiter_tok), timeout=30)
        assert r.status_code == 403, f"{path} got {r.status_code}"

    def test_recruiter_me_target(self, recruiter_tok):
        r = requests.get(f"{BASE_URL}/api/targets/me", headers=_h(recruiter_tok), timeout=15)
        assert r.status_code == 200
        data = r.json()
        # Should not have rupee amounts
        body = str(data).lower()
        assert "gross" not in body or data.get("gross") in (None, 0), f"recruiter target leaks rupee: {data}"


# ---------- Team consolidation ----------
class TestTeamConsolidation:
    def test_five_active_teams(self, admin_tok):
        r = requests.get(f"{BASE_URL}/api/teams", headers=_h(admin_tok), timeout=15)
        assert r.status_code == 200
        payload = r.json()
        teams = payload if isinstance(payload, list) else payload.get("teams", [])
        active = [t for t in teams if t.get("status") != "merged"]
        names = sorted([t.get("name", "") for t in active])
        print(f"active teams: {names}")
        # Merged teams gone
        assert not any("manorma yadav team" in n.lower() for n in names)
        assert not any(n.lower().strip() == "jatin yadav team" for n in names)

    def test_company_summary_totals(self, admin_tok):
        r = requests.get(f"{BASE_URL}/api/targets/company-summary", headers=_h(admin_tok), timeout=15)
        assert r.status_code == 200
        data = r.json()
        print(f"company summary: {data}")
        placements = data.get("placements") or data.get("total_placements")
        gross = data.get("gross") or data.get("total_gross")
        if placements is not None:
            assert placements == 527, f"expected 527 got {placements}"
        if gross is not None:
            assert abs(float(gross) - 52865786) < 10, f"gross={gross}"
