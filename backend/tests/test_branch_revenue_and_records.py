"""Branch Revenue + Performance Records e2e API tests."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://badge-audit-v2.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
HR6_EMAIL = "hr6@vhc.in"
HR6_PASSWORD = "12345678"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def hr6_token():
    return _login(HR6_EMAIL, HR6_PASSWORD)


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def hr6_headers(hr6_token):
    return {"Authorization": f"Bearer {hr6_token}"}


# ---------- Branch Revenue KPI (annual 2026) ----------

@pytest.fixture(scope="module")
def dashboard_2026(admin_headers):
    r = requests.get(
        f"{BASE_URL}/api/branch-revenue/dashboard",
        params={"period_type": "year", "period": "2026"},
        headers=admin_headers, timeout=60,
    )
    assert r.status_code == 200, r.text[:400]
    return r.json()


def test_kpis_annual_2026(dashboard_2026):
    k = dashboard_2026["kpis"]
    # placements 527, 54 recruiter groups after merging
    assert k["placements"] == 527, k
    # 54 merged recruiter groups
    assert k["recruiter_groups"] == 54
    assert len(dashboard_2026["recruiters"]) == 54
    # money
    assert 53126000 <= k["gross"] <= 53127000, k  # ~5.31 Cr
    # active revenue ~5.29 Cr
    assert 5.28e7 <= k["active"] <= 5.30e7, k
    # realization ~66.7%
    real = float(k.get("realization_pct") or k.get("realization") or 0)
    assert 66.0 <= real <= 67.5, real
    # records to review 29
    assert k["records_needing_review"] == 29


def test_branch_summary_totals(dashboard_2026):
    branches = {b["branch"]: b for b in dashboard_2026["branches"]}
    expected = {
        "Gurgaon": (17745379, 166),
        "Delhi": (17693388, 180),
        "Faridabad": (9074939, 127),
        "Bangalore": (7611882, 47),
        "Hyderabad": (1001168, 7),
    }
    for name, (gross, placements) in expected.items():
        assert name in branches, f"branch {name} missing. Got: {list(branches.keys())}"
        b = branches[name]
        assert round(b["gross"]) == gross, f"{name} gross: got {b['gross']} expected {gross}"
        assert b["placements"] == placements, f"{name} placements: got {b['placements']} expected {placements}"


def test_priyanka_split_two_people(dashboard_2026):
    """Priyanka (hr64) and Priyanka yadav (hr9) are TWO different people."""
    priyankas = [r for r in dashboard_2026["recruiters"] if "priyanka" in (r.get("recruiter") or "").lower()]
    ids = {r.get("recruiter_id") for r in priyankas if r.get("recruiter_id")}
    assert len(ids) >= 2, f"expected at least 2 Priyanka recruiter_ids, got {ids}"


# ---------- Placements filters ----------

def test_placements_filter_royal_enfield(admin_headers):
    r = requests.get(
        f"{BASE_URL}/api/branch-revenue/placements",
        params={"period_type": "year", "period": "2026", "q": "Royal Enfield"},
        headers=admin_headers, timeout=60,
    )
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert d["count"] > 0
    for row in d["items"][:10]:
        s = " ".join(str(row.get(k) or "") for k in ("organization", "candidate_name")).lower()
        assert "royal enfield" in s or "royal" in s, row


def test_placements_filter_payment_status(admin_headers):
    for status in ("Payment Received", "IP"):
        r = requests.get(
            f"{BASE_URL}/api/branch-revenue/placements",
            params={"period_type": "year", "period": "2026", "payment_status": status},
            headers=admin_headers, timeout=60,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["count"] >= 1, f"no rows for status={status}"
        for row in d["items"]:
            assert row.get("payment_status") == status


# ---------- Performance Records report ----------

@pytest.fixture(scope="module")
def report_2026_annual(admin_headers):
    r = requests.get(
        f"{BASE_URL}/api/performance-records/report",
        params={"period_type": "year", "period": "2026"},
        headers=admin_headers, timeout=120,
    )
    assert r.status_code == 200, r.text[:400]
    return r.json()


def test_report_has_branch_revenue_block(report_2026_annual):
    assert "branch_revenue" in report_2026_annual
    br = report_2026_annual["branch_revenue"]
    assert br["kpis"]["placements"] == 527
    assert report_2026_annual["total_joinings"] == 527


def test_report_teams_have_names_not_uuids(report_2026_annual):
    """Members must display names, not raw UUIDs."""
    for team in report_2026_annual["teams"]:
        for m in team["members"]:
            # A UUID-only 'name' means the fallback fired
            assert m["name"] != m["user_id"], f"team {team['team_name']} member {m['user_id']} has UUID as name"
            assert m["name"], f"empty name for {m['user_id']}"


def test_report_faridabad_ex_members(report_2026_annual):
    """Faridabad team's ex-member list must include Nidhi Singh, Parul Mangla, Lalit kumar (by name)."""
    fbd = None
    for t in report_2026_annual["teams"]:
        if "faridabad" in (t["team_name"] or "").lower():
            fbd = t
            break
    if not fbd:
        pytest.skip("No Faridabad team present")
    ex_names = " ".join((p.get("name") or "").lower() for p in (fbd.get("ex_members") or []))
    for expected in ("nidhi singh", "parul mangla", "lalit kumar"):
        assert expected in ex_names, f"missing {expected!r} in Faridabad ex_members: {ex_names!r}"


# ---------- Snapshot / archive round-trip (idempotent + cleanup) ----------

def test_snapshot_and_delete(admin_headers):
    # Create a snapshot for an old, safe period (2024) to not disturb client data
    r = requests.post(
        f"{BASE_URL}/api/performance-records/snapshot",
        params={"period_type": "year", "period": "2024"},
        headers=admin_headers, timeout=120,
    )
    assert r.status_code == 200, r.text[:400]

    # list archive → find 2024
    r2 = requests.get(f"{BASE_URL}/api/performance-records/archive", headers=admin_headers, timeout=60)
    assert r2.status_code == 200
    items = r2.json()["items"]
    match = next((i for i in items if i["period"] == "2024" and i["period_type"] == "year"), None)
    assert match, "snapshot not visible in archive"

    # delete cleanup
    r3 = requests.delete(f"{BASE_URL}/api/performance-records/archive/{match['id']}", headers=admin_headers, timeout=30)
    assert r3.status_code == 200


# ---------- Role guard: recruiter must be blocked ----------

def test_recruiter_blocked_from_branch_revenue(hr6_headers):
    r = requests.get(f"{BASE_URL}/api/branch-revenue/dashboard", headers=hr6_headers, timeout=30)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"


def test_recruiter_blocked_from_performance_records(hr6_headers):
    r = requests.get(f"{BASE_URL}/api/performance-records/report", headers=hr6_headers, timeout=30)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"


# ---------- Monthly / Quarterly period switch works (smaller numbers, no error) ----------

def test_monthly_smaller_than_annual(admin_headers, dashboard_2026):
    r = requests.get(
        f"{BASE_URL}/api/branch-revenue/dashboard",
        params={"period_type": "month", "period": "2026-01"},
        headers=admin_headers, timeout=60,
    )
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert d["kpis"]["placements"] <= dashboard_2026["kpis"]["placements"]


def test_quarterly_ok(admin_headers):
    r = requests.get(
        f"{BASE_URL}/api/branch-revenue/dashboard",
        params={"period_type": "quarter", "period": "2026-Q1"},
        headers=admin_headers, timeout=60,
    )
    assert r.status_code == 200


# ---------- Branch filter narrows results ----------

def test_branch_filter_narrows(admin_headers, dashboard_2026):
    r = requests.get(
        f"{BASE_URL}/api/branch-revenue/dashboard",
        params={"period_type": "year", "period": "2026", "branch": "Delhi"},
        headers=admin_headers, timeout=60,
    )
    assert r.status_code == 200
    d = r.json()
    assert d["kpis"]["placements"] <= dashboard_2026["kpis"]["placements"]
    # only Delhi in branches
    branches = {b["branch"] for b in d["branches"]}
    assert branches == {"Delhi"} or (len(branches) == 1 and "Delhi" in branches), branches
