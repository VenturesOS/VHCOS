"""Revenue must add up the same way from every direction.

These are the invariants that stop a future change from quietly
double-counting someone's revenue or dropping a branch.
"""
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://badge-audit-v2.preview.emergentagent.com").rstrip("/")
ADMIN = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
RECRUITER = {"email": "hr6@vhc.in", "password": "12345678"}
YEAR = 2026


def _tok(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, r.text[:200]
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin():
    return {"Authorization": f"Bearer {_tok(ADMIN)}"}


@pytest.fixture(scope="module")
def report(admin):
    r = requests.get(f"{BASE_URL}/api/branch-revenue/reconcile", params={"year": YEAR},
                     headers=admin, timeout=180)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def test_every_check_agrees(report):
    failed = [c for c in report["checks"] if not c["ok"]]
    assert not failed, f"reconciliation failed: {failed}"


def test_all_nine_invariants_are_run(report):
    assert len(report["checks"]) == 9


def test_company_equals_tracker_plus_platform(report):
    t = report["totals"]
    assert abs(t["company_achieved"] - (t["tracker_active"] + t["platform_revenue"])) <= 1


def test_active_is_gross_minus_write_offs(admin):
    r = requests.get(f"{BASE_URL}/api/branch-revenue/dashboard",
                     params={"period_type": "year", "period": str(YEAR)}, headers=admin, timeout=120)
    k = r.json()["kpis"]
    assert abs(k["active"] - (k["gross"] - k["backout"] - k["credit_note"] - k["other"])) <= 1
    assert abs(k["pending"] - (k["pp"] + k["ip"])) <= 1


def test_branch_and_recruiter_tables_match_the_kpis(admin):
    d = requests.get(f"{BASE_URL}/api/branch-revenue/dashboard",
                     params={"period_type": "year", "period": str(YEAR)}, headers=admin, timeout=120).json()
    assert abs(sum(b["gross"] for b in d["branches"]) - d["kpis"]["gross"]) <= 1
    assert abs(sum(r["gross"] for r in d["recruiters"]) - d["kpis"]["gross"]) <= 1
    assert sum(b["placements"] for b in d["branches"]) == d["kpis"]["placements"]


def test_a_tracker_hire_cannot_be_billed_twice(admin):
    """Booking revenue on a hire the tracker already bills must be refused."""
    rows = requests.get(f"{BASE_URL}/api/joinings",
                        params={"date_from": f"{YEAR}-01-01", "date_to": f"{YEAR}-12-31",
                                "source": "both", "limit": 1},
                        headers=admin, timeout=120).json()["items"]
    if not rows:
        pytest.skip("no hire exists in both systems")
    app_id = rows[0]["application_id"]
    patch = requests.patch(f"{BASE_URL}/api/joinings/{app_id}", json={"revenue": 1}, headers=admin, timeout=60)
    assert patch.status_code == 409, patch.text[:200]
    invoice = requests.post(f"{BASE_URL}/api/joinings/{app_id}/raise-invoice",
                            json={"joined_ctc": 100000, "commercial_rate_pct": 8.33},
                            headers=admin, timeout=60)
    assert invoice.status_code == 409, invoice.text[:200]


def test_matched_rows_are_not_editable(admin):
    d = requests.get(f"{BASE_URL}/api/joinings",
                     params={"date_from": f"{YEAR}-01-01", "date_to": f"{YEAR}-12-31", "limit": 1000},
                     headers=admin, timeout=120).json()
    editable = [r for r in d["items"] if r["editable"]]
    assert all(r["source"] == "pipeline" for r in editable), "a tracker-backed row was left editable"


def test_recruiters_never_see_a_rupee_value():
    tok = {"Authorization": f"Bearer {_tok(RECRUITER)}"}
    for path in ("/api/joinings", "/api/branch-revenue/dashboard", "/api/branch-revenue/reconcile",
                 "/api/performance-records/report", "/api/targets/team-summary",
                 "/api/targets/company-summary"):
        assert requests.get(f"{BASE_URL}{path}", headers=tok, timeout=60).status_code == 403, path
    me = requests.get(f"{BASE_URL}/api/targets/me", headers=tok, timeout=60).json()
    assert "achievement_pct" in me
    for money in ("target_amount", "achieved", "revenue"):
        assert money not in me, f"{money} leaked to a recruiter"
