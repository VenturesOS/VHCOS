"""End-to-end tests for Bill Generator (Phase 55.6).

Covers:
- ACL (admin vs plain recruiter)
- CRUD: create draft, list, get, update, cancel
- Computed totals (taxable, GST kind, grand_total)
- Bill numbering: sequential within FY
- PDF render
- Mail preview (LLM body)
- Send in test_mode
- Mark-paid lock (subsequent edits return 409)
"""
from __future__ import annotations

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://talent-graph-fix.preview.emergentagent.com").rstrip("/")
ADMIN = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
PLAIN_RECRUITER = {"email": "hr12@vhc.in", "password": "12345678"}


# ──────────────── fixtures ────────────────
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def recruiter_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=PLAIN_RECRUITER, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"Plain recruiter login failed: {r.status_code} {r.text}")
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def recruiter_headers(recruiter_token):
    return {"Authorization": f"Bearer {recruiter_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def candidate_company(admin_headers):
    """Pick a real company with billing_email; fallback to any company."""
    r = requests.get(f"{BASE_URL}/api/companies", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", data)
    chosen = None
    for c in items[:100]:
        if c.get("billing_email") or c.get("primary_email"):
            chosen = c
            break
    if not chosen and items:
        chosen = items[0]
    if not chosen:
        pytest.skip("No companies available")
    return chosen


# ──────────────── ACL ────────────────
class TestACL:
    def test_admin_can_list_bills(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/bills", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "items" in body and "count" in body
        assert isinstance(body["items"], list)

    def test_plain_recruiter_forbidden(self, recruiter_headers):
        r = requests.get(f"{BASE_URL}/api/bills", headers=recruiter_headers, timeout=15)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"


# ──────────────── CRUD + Computations ────────────────
class TestBillCrud:
    bill_id = None
    bill_number = None
    second_bill_id = None
    second_bill_number = None

    def test_create_bill(self, admin_headers, candidate_company):
        payload = {
            "client_company_id": candidate_company["id"],
            "line_items": [
                {
                    "candidate_name": "TEST_Candidate A",
                    "designation": "Engineer",
                    "joining_date": "2026-05-01",
                    "annual_ctc": 1200000,
                    "commercial_rate_pct": 8.33,
                    "line_amount": 0,  # trigger auto-compute
                },
                {
                    "candidate_name": "TEST_Candidate B",
                    "designation": "Senior Engineer",
                    "joining_date": "2026-05-15",
                    "annual_ctc": 2000000,
                    "commercial_rate_pct": 10.0,
                    "line_amount": 0,
                },
            ],
        }
        r = requests.post(f"{BASE_URL}/api/bills", headers=admin_headers, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        b = r.json()
        # Bill number format
        assert "bill_number" in b
        assert b["bill_number"].startswith("VHC/"), b["bill_number"]
        parts = b["bill_number"].split("/")
        assert len(parts) == 3 and parts[0] == "VHC"
        assert "-" in parts[1] and parts[2].isdigit()
        # Status draft
        assert b["status"] == "draft"
        # Line items: auto-compute
        li = b["line_items"]
        assert len(li) == 2
        # CTC 1200000 * 8.33 / 100 = 99960
        assert abs(li[0]["line_amount"] - 99960.0) < 0.01, li[0]
        # CTC 2000000 * 10 / 100 = 200000
        assert abs(li[1]["line_amount"] - 200000.0) < 0.01, li[1]
        # Totals
        t = b["totals"]
        taxable = 99960.0 + 200000.0
        assert abs(t["taxable_value"] - taxable) < 0.01
        assert t["gst_kind"] in ("IGST", "CGST_SGST")
        assert abs(t["grand_total"] - round(taxable * 1.18, 2)) < 0.05
        # Amount in words
        assert isinstance(t["amount_in_words"], str)
        assert t["amount_in_words"].startswith("Indian Rupees"), t["amount_in_words"]
        # store for following tests
        TestBillCrud.bill_id = b["id"]
        TestBillCrud.bill_number = b["bill_number"]

    def test_get_bill(self, admin_headers):
        assert TestBillCrud.bill_id
        r = requests.get(f"{BASE_URL}/api/bills/{TestBillCrud.bill_id}", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        b = r.json()
        assert b["id"] == TestBillCrud.bill_id

    def test_sequential_numbering(self, admin_headers, candidate_company):
        payload = {
            "client_company_id": candidate_company["id"],
            "line_items": [
                {
                    "candidate_name": "TEST_Seq",
                    "joining_date": "2026-06-01",
                    "annual_ctc": 500000,
                    "commercial_rate_pct": 8.33,
                    "line_amount": 0,
                },
            ],
        }
        r = requests.post(f"{BASE_URL}/api/bills", headers=admin_headers, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        b = r.json()
        TestBillCrud.second_bill_id = b["id"]
        TestBillCrud.second_bill_number = b["bill_number"]
        # Should be exactly N+1 vs prior
        first = int(TestBillCrud.bill_number.split("/")[-1])
        second = int(TestBillCrud.second_bill_number.split("/")[-1])
        assert second == first + 1, f"Expected {first+1}, got {second}"
        # Same FY
        assert TestBillCrud.bill_number.split("/")[1] == TestBillCrud.second_bill_number.split("/")[1]

    def test_update_recomputes_totals(self, admin_headers):
        assert TestBillCrud.bill_id
        new_items = [
            {
                "candidate_name": "TEST_Updated",
                "joining_date": "2026-05-01",
                "annual_ctc": 600000,
                "commercial_rate_pct": 8.33,
                "line_amount": 0,
            }
        ]
        r = requests.put(
            f"{BASE_URL}/api/bills/{TestBillCrud.bill_id}",
            headers=admin_headers,
            json={"line_items": new_items},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        b = r.json()
        expected = round(600000 * 8.33 / 100, 2)  # 49980
        assert abs(b["totals"]["taxable_value"] - expected) < 0.01
        assert abs(b["totals"]["grand_total"] - round(expected * 1.18, 2)) < 0.05

    def test_render_pdf(self, admin_headers):
        assert TestBillCrud.bill_id
        r = requests.get(f"{BASE_URL}/api/bills/{TestBillCrud.bill_id}/pdf", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.headers.get("x-vhc-bill-id") == TestBillCrud.bill_id
        assert r.content[:4] == b"%PDF", r.content[:20]
        assert len(r.content) > 2000

    def test_preview_mail(self, admin_headers):
        assert TestBillCrud.bill_id
        r = requests.post(
            f"{BASE_URL}/api/bills/{TestBillCrud.bill_id}/preview-mail",
            headers=admin_headers,
            timeout=90,  # LLM may be slow
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "plain" in body and "html" in body
        assert isinstance(body["plain"], str) and len(body["plain"].strip()) > 10
        assert isinstance(body["html"], str) and len(body["html"].strip()) > 10

    def test_send_test_mode(self, admin_headers):
        assert TestBillCrud.bill_id
        r = requests.post(
            f"{BASE_URL}/api/bills/{TestBillCrud.bill_id}/send",
            headers=admin_headers,
            json={"test_mode": True},
            timeout=120,
        )
        # Accept 200 (success) OR 502 (Resend reject) — both are documented acceptable
        assert r.status_code in (200, 502), f"Unexpected status {r.status_code}: {r.text[:300]}"
        if r.status_code == 200:
            data = r.json()
            assert data.get("to") == ADMIN["email"]
            assert data.get("test_mode") is True
            # verify mail_events appended
            r2 = requests.get(f"{BASE_URL}/api/bills/{TestBillCrud.bill_id}", headers=admin_headers, timeout=15)
            assert r2.status_code == 200
            events = r2.json().get("mail_events", [])
            assert len(events) >= 1
            assert events[-1].get("test_mode") is True
        else:
            # Structured Resend error acceptable per problem spec
            print(f"[WARN] Send returned 502 — Resend likely rejected test inbox: {r.text[:200]}")

    def test_mark_paid_locks_edits(self, admin_headers):
        assert TestBillCrud.second_bill_id
        # Mark paid on the SECOND bill so first stays cancellable for delete test
        r = requests.post(
            f"{BASE_URL}/api/bills/{TestBillCrud.second_bill_id}/mark-paid",
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # Subsequent PUT should 409
        r2 = requests.put(
            f"{BASE_URL}/api/bills/{TestBillCrud.second_bill_id}",
            headers=admin_headers,
            json={"line_items": [{"candidate_name": "X", "joining_date": "2026-05-01", "annual_ctc": 1, "commercial_rate_pct": 1, "line_amount": 0}]},
            timeout=15,
        )
        assert r2.status_code == 409, f"Expected 409, got {r2.status_code}: {r2.text}"

    def test_cancel_draft(self, admin_headers):
        assert TestBillCrud.bill_id
        r = requests.delete(f"{BASE_URL}/api/bills/{TestBillCrud.bill_id}", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        # Verify status == cancelled
        r2 = requests.get(f"{BASE_URL}/api/bills/{TestBillCrud.bill_id}", headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["status"] == "cancelled"
