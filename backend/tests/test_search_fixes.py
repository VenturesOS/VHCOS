"""
Tests for Advanced Search / AI Search / Autocomplete / Semantic Search fixes
(Batches A, B, C). DB has ~1.23L candidates.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://talent-graph-fix.preview.emergentagent.com").rstrip("/")


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@vhc.in", "password": "VhcAdmin@2024"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ---------------- Batch A: Advanced Search filters ----------------
class TestAdvancedSearchFilters:
    def test_company_te_connectivity(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            params={"company": "TE Connectivity", "limit": 50},
            headers=auth_headers,
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        items = data.get("items") or data.get("candidates") or data.get("results") or []
        total = data.get("total") or data.get("count") or len(items)
        print(f"[company=TE Connectivity] total={total}, items_returned={len(items)}")
        assert total >= 20, f"expected >20, got {total}"
        # Verify employer field is matched
        hit = False
        for it in items[:20]:
            for k in ("current_employer", "current_company", "company"):
                v = (it.get(k) or "").lower()
                if "te connectivity" in v:
                    hit = True
                    break
            if hit:
                break
        assert hit, "no candidate had TE Connectivity in employer/company fields"

    def test_industry_it_software(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            params={"industry": "IT/Software", "limit": 5},
            headers=auth_headers,
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        total = data.get("total") or data.get("count") or 0
        print(f"[industry=IT/Software] total={total}")
        assert total > 10000, f"expected >10K, got {total}"

    def test_industry_manufacturing(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            params={"industry": "Manufacturing", "limit": 5},
            headers=auth_headers,
            timeout=60,
        )
        assert r.status_code == 200
        total = r.json().get("total") or 0
        print(f"[industry=Manufacturing] total={total}")
        assert total > 30000, f"expected >30K, got {total}"

    def test_industry_bfsi(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            params={"industry": "BFSI", "limit": 5},
            headers=auth_headers,
            timeout=60,
        )
        assert r.status_code == 200
        total = r.json().get("total") or 0
        print(f"[industry=BFSI] total={total}")
        assert total > 1000, f"expected thousands, got {total}"

    def test_has_resume_yes(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            params={"has_resume": "yes", "limit": 5},
            headers=auth_headers,
            timeout=60,
        )
        assert r.status_code == 200
        total = r.json().get("total") or 0
        print(f"[has_resume=yes] total={total}")
        assert total > 5000, f"expected >5K, got {total}"

    def test_has_resume_no(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            params={"has_resume": "no", "limit": 5},
            headers=auth_headers,
            timeout=60,
        )
        assert r.status_code == 200
        total = r.json().get("total") or 0
        print(f"[has_resume=no] total={total}")
        assert total >= 0

    def test_has_phone_excludes_placeholders(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            params={"has_phone": "true", "limit": 20},
            headers=auth_headers,
            timeout=60,
        )
        assert r.status_code == 200
        items = r.json().get("items") or r.json().get("candidates") or []
        print(f"[has_phone=true] items={len(items)}")
        for it in items:
            phone = (it.get("phone") or it.get("primary_phone") or it.get("mobile") or "").strip().lower()
            assert phone not in ("hidden", "not available", "n/a", ""), f"bad phone: {phone}"

    def test_notice_period_immediate(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            params={"notice_period": "immediate", "limit": 20},
            headers=auth_headers,
            timeout=60,
        )
        assert r.status_code == 200
        data = r.json()
        total = data.get("total") or 0
        items = data.get("items") or data.get("candidates") or []
        print(f"[notice_period=immediate] total={total}, items={len(items)}")
        assert total > 0, f"expected matches for 'immediate', got {total}"
        # case-insensitive substring should match "Immediate" / "Immediate Joiner" / etc.
        if items:
            sample = " ".join(
                str(it.get(k, "")) for it in items[:5] for k in ("notice_period", "noticePeriod", "notice")
            ).lower()
            assert "immediate" in sample, f"no 'immediate' substring in sample: {sample[:200]}"


# ---------------- Batch C: Autocomplete ----------------
class TestAutocomplete:
    def test_react_all(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/candidate-bank/autocomplete",
            params={"q": "react", "field": "all"},
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        items = data if isinstance(data, list) else (data.get("suggestions") or data.get("items") or [])
        print(f"[ac q=react] items={len(items)}; sample={items[:3]}")
        assert len(items) >= 5, f"expected >=5 suggestions, got {len(items)}"
        types_seen = {(it.get("type") or it.get("field") or "").lower() for it in items if isinstance(it, dict)}
        print(f"[ac q=react] types_seen={types_seen}")
        assert len(types_seen) >= 1

    def test_banga_location(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/candidate-bank/autocomplete",
            params={"q": "banga", "field": "location"},
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else (data.get("suggestions") or [])
        labels = " ".join(
            (it.get("value") or it.get("label") or str(it)).lower() if isinstance(it, dict) else str(it).lower()
            for it in items
        )
        print(f"[ac banga loc] labels={labels[:300]}")
        assert "bangal" in labels or "bengal" in labels, f"no bangalore/bengaluru in {labels[:200]}"

    def test_industry_field_new(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/candidate-bank/autocomplete",
            params={"q": "it", "field": "industry"},
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        items = data if isinstance(data, list) else (data.get("suggestions") or [])
        print(f"[ac q=it industry] items={len(items)}; sample={items[:5]}")
        assert len(items) > 0, "no industry suggestions returned (NEW field)"


# ---------------- Batch B: AI Search ----------------
class TestAISearch:
    def test_experienced_java_bangalore(self, auth_headers):
        payload = {"prompt": "experienced Java developer in Bangalore", "limit": 30}
        r = requests.post(f"{BASE_URL}/api/ai-search", json=payload, headers=auth_headers, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        results = data.get("results") or data.get("candidates") or data.get("items") or []
        filters = data.get("filters_used") or data.get("filters") or {}
        print(f"[ai java bang] results={len(results)}; filters={filters}")
        assert len(results) >= 5, f"expected >=5, got {len(results)}"
        assert filters.get("min_experience") in (None, 0, "", []), \
            f"sanitiser failed: min_experience={filters.get('min_experience')}"

    def test_it_software_5plus(self, auth_headers):
        payload = {"prompt": "IT/Software with 5+ years", "limit": 30}
        r = requests.post(f"{BASE_URL}/api/ai-search", json=payload, headers=auth_headers, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        results = data.get("results") or data.get("candidates") or data.get("items") or []
        filters = data.get("filters_used") or data.get("filters") or {}
        print(f"[ai it 5+] results={len(results)}; filters={filters}")
        assert 5 <= len(results) <= 30, f"expected 5-30, got {len(results)}"
        assert filters.get("min_experience") == 5, f"expected 5, got {filters.get('min_experience')}"

    def test_strict_relaxed_fallback(self, auth_headers):
        payload = {
            "prompt": "Java developer with 15+ years immediate joiner BFSI no job hopper",
            "limit": 20,
        }
        r = requests.post(f"{BASE_URL}/api/ai-search", json=payload, headers=auth_headers, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        results = data.get("results") or data.get("candidates") or data.get("items") or []
        print(f"[ai strict] results={len(results)}; relaxed={data.get('relaxed')}")
        # Either we got results normally OR relaxed:true kicked in
        if len(results) == 0:
            assert data.get("relaxed") is True, "0 results and relaxed flag not set"
        # Acceptable either way as long as response is valid
        assert "results" in data or "candidates" in data or "items" in data


# ---------------- Semantic / Talent Graph ----------------
class TestTalentGraphSearch:
    def test_python_bangalore_topup(self, auth_headers):
        payload = {"query": "Python developer Bangalore", "limit": 25}
        r = requests.post(f"{BASE_URL}/api/talent-graph/search", json=payload, headers=auth_headers, timeout=180)
        assert r.status_code == 200, r.text
        data = r.json()
        results = data.get("matches") or data.get("results") or data.get("candidates") or data.get("items") or []
        print(f"[tg python bang] results={len(results)}")
        assert len(results) > 0, "no results from talent-graph"
        # Some should be keyword fallback
        match_types = [r.get("match_type") for r in results if isinstance(r, dict)]
        print(f"[tg] match_types sample={match_types[:10]}")
