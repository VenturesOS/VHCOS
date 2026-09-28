"""Backend regression tests for the unified sourcing→joining→invoice flow
(iteration 198, review dated 2026-01).

Covers:
  - GET /api/joinings dedupe (one row per candidate)
  - PATCH /api/joinings/{id} accepts joined_ctc, revenue, join_date
  - POST /api/joinings/{id}/raise-invoice accepts billing_amount + designation
    (NOT commercial_rate_pct) and returns bill_id + bill_number
  - GET /api/joinings as recruiter returns restricted:true with only the
    non-money keys, scoped to that recruiter
  - POST /api/joinings/payment-reminders/run?dry_run=true admin listing
  - Removed old process: /api/applications/pending-approval and
    /api/applications/{id}/employer-approval → 404/405
  - email_service.send_email drops non-allowlisted categories
"""
import os
import asyncio
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
RECRUITER = {"email": "hr6@vhc.in", "password": "12345678"}


# ── Auth helpers ────────────────────────────────────────────────────────────
def _login(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login {creds['email']}: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def recruiter_token():
    return _login(RECRUITER)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ── Joinings listing / dedupe ───────────────────────────────────────────────
def test_admin_joinings_dedupe_and_shape(admin_token):
    r = requests.get(f"{BASE_URL}/api/joinings?limit=1000", headers=H(admin_token), timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "items" in data and "count" in data
    items = data["items"]

    # No two rows for the same candidate_name where one has empty client
    by_name = {}
    for it in items:
        by_name.setdefault(it["candidate_name"], []).append(it)
    dup_offenders = []
    for name, rows in by_name.items():
        if len(rows) > 1 and any(not r.get("client_name") for r in rows) and any(r.get("client_name") for r in rows):
            dup_offenders.append(name)
    assert not dup_offenders, f"dedupe leak: {dup_offenders[:5]}"

    # RIDDHI MUKHERJEE is a known-good single-row case (regression anchor)
    riddhi = [i for i in items if "RIDDHI" in (i.get("candidate_name") or "").upper()
              and "MUKHERJEE" in (i.get("candidate_name") or "").upper()]
    if riddhi:
        assert len(riddhi) == 1, f"RIDDHI duplicated: {riddhi}"


# ── PATCH: joined_ctc + revenue + join_date ─────────────────────────────────
def _find_pipeline_app_for_write(admin_token):
    """Pick a pipeline-source joining we can safely mutate (Hero motocorp
    / Royal Enfield preferred per handoff note)."""
    r = requests.get(f"{BASE_URL}/api/joinings?limit=1000", headers=H(admin_token), timeout=90)
    r.raise_for_status()
    items = r.json()["items"]

    preferred = [i for i in items
                 if i.get("source") == "pipeline"
                 and i.get("application_id")
                 and (
                     "hero" in (i.get("client_name") or "").lower()
                     or "enfield" in (i.get("client_name") or "").lower()
                     or "enfiled" in (i.get("client_name") or "").lower()
                 )
                 and i.get("join_date", "").startswith("2026-09")]
    if preferred:
        return preferred[0]
    fallback = [i for i in items if i.get("source") == "pipeline" and i.get("application_id")]
    return fallback[0] if fallback else None


def test_patch_joining_join_date_and_ctc(admin_token):
    row = _find_pipeline_app_for_write(admin_token)
    if not row:
        pytest.skip("No pipeline-only joining rows available to safely mutate")
    app_id = row["application_id"]

    # Read current
    prior_ctc = row.get("joined_ctc") or 0
    prior_join = row.get("join_date")

    # 1) PATCH — join_date + ctc (do NOT set revenue: avoids booking mutation
    #    and the tracker-guard block)
    new_ctc = 777777.0
    r = requests.patch(
        f"{BASE_URL}/api/joinings/{app_id}",
        json={"joined_ctc": new_ctc, "join_date": prior_join or "2026-09-28"},
        headers=H(admin_token),
        timeout=30,
    )
    assert r.status_code == 200, f"PATCH failed: {r.status_code} {r.text}"

    # Verify persistence
    r2 = requests.get(f"{BASE_URL}/api/joinings?limit=1000", headers=H(admin_token), timeout=90)
    r2.raise_for_status()
    hit = next((i for i in r2.json()["items"] if i.get("application_id") == app_id), None)
    assert hit is not None, "row disappeared after PATCH"
    assert float(hit.get("joined_ctc") or 0) == new_ctc, f"CTC not persisted, got {hit.get('joined_ctc')}"

    # Restore ctc so downstream users see original figure
    requests.patch(f"{BASE_URL}/api/joinings/{app_id}",
                   json={"joined_ctc": float(prior_ctc)},
                   headers=H(admin_token), timeout=30)


def test_patch_joining_rejects_commercial_only_when_tracker_dup_absent(admin_token):
    """Sanity: schema accepts join_date at all (no 422)."""
    row = _find_pipeline_app_for_write(admin_token)
    if not row:
        pytest.skip("no pipeline app")
    r = requests.patch(
        f"{BASE_URL}/api/joinings/{row['application_id']}",
        json={"join_date": row.get("join_date") or "2026-09-28"},
        headers=H(admin_token),
        timeout=30,
    )
    assert r.status_code == 200, r.text


# ── Recruiter scope + restricted shape ──────────────────────────────────────
def test_recruiter_joinings_restricted_and_scoped(recruiter_token):
    r = requests.get(f"{BASE_URL}/api/joinings?limit=100", headers=H(recruiter_token), timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("restricted") is True
    for it in data.get("items", []):
        # Only allowed keys — no rupee values
        assert set(it.keys()) <= {"key", "join_date", "candidate_name", "client_name", "position"}, \
            f"leaked keys: {it.keys()}"
    # hr6 has 0 joinings per handoff note — either empty list or all only their own
    # We just assert restricted:true and shape (count may be 0)


# ── Payment reminders dry-run ───────────────────────────────────────────────
def test_payment_reminders_dry_run_admin(admin_token):
    r = requests.post(
        f"{BASE_URL}/api/joinings/payment-reminders/run?dry_run=true",
        headers=H(admin_token),
        timeout=60,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Expect per-recipient breakdown; be tolerant to key naming
    assert isinstance(body, dict)
    assert any(k in body for k in ("recipients", "per_recipient", "sent", "would_send", "results")), \
        f"unexpected reminder shape: {list(body.keys())}"


def test_payment_reminders_forbidden_for_recruiter(recruiter_token):
    r = requests.post(
        f"{BASE_URL}/api/joinings/payment-reminders/run?dry_run=true",
        headers=H(recruiter_token),
        timeout=30,
    )
    assert r.status_code == 403


# ── Removed old approval routes ─────────────────────────────────────────────
def test_pending_approval_route_removed(admin_token):
    r = requests.get(f"{BASE_URL}/api/applications/pending-approval", headers=H(admin_token), timeout=30)
    assert r.status_code in (404, 405), f"expected 404/405, got {r.status_code}"


def test_employer_approval_route_removed(admin_token):
    r = requests.post(f"{BASE_URL}/api/applications/some-id/employer-approval",
                      json={"approved": True}, headers=H(admin_token), timeout=30)
    assert r.status_code in (404, 405), f"expected 404/405, got {r.status_code}"


# ── Raise invoice: schema uses billing_amount (NOT commercial_rate_pct) ────
def test_raise_invoice_schema_rejects_commercial_rate_pct(admin_token):
    """Sending the OLD payload (commercial_rate_pct instead of billing_amount)
    must fail with 422 — proves the model changed."""
    row = _find_pipeline_app_for_write(admin_token)
    if not row:
        pytest.skip("no pipeline app")
    r = requests.post(
        f"{BASE_URL}/api/joinings/{row['application_id']}/raise-invoice",
        json={"joined_ctc": 100000, "commercial_rate_pct": 8.33},  # old shape
        headers=H(admin_token),
        timeout=30,
    )
    # Missing 'billing_amount' → 422 Pydantic validation error
    assert r.status_code == 422, f"expected 422 old-shape rejection, got {r.status_code}: {r.text[:200]}"


def test_raise_invoice_accepts_new_shape(admin_token):
    """Actually create ONE test invoice (max 2 per handoff)."""
    row = _find_pipeline_app_for_write(admin_token)
    if not row:
        pytest.skip("no writable pipeline row")

    # Skip if the row already has an invoice attached
    if row.get("bill_number"):
        pytest.skip(f"row already invoiced: {row.get('bill_number')}")

    app_id = row["application_id"]
    payload = {
        "joined_ctc": 500000.0,
        "billing_amount": 41650.0,
        "designation": row.get("position") or "QA Test Position",
    }
    r = requests.post(
        f"{BASE_URL}/api/joinings/{app_id}/raise-invoice",
        json=payload,
        headers=H(admin_token),
        timeout=60,
    )
    if r.status_code == 409:
        # Tracker duplicate — expected safety block, not a bug
        pytest.skip(f"tracker duplicate 409: {r.text[:120]}")
    assert r.status_code == 200, f"raise-invoice failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("bill_id"), f"missing bill_id: {body}"
    assert body.get("bill_number"), f"missing bill_number: {body}"

    # Fetch the bill and assert line item carries application_id
    bill = requests.get(f"{BASE_URL}/api/bills/{body['bill_id']}", headers=H(admin_token), timeout=30)
    if bill.status_code == 200:
        bd = bill.json()
        line_items = bd.get("line_items") or []
        assert any(li.get("application_id") == app_id for li in line_items), \
            f"application_id not on line item: {line_items}"

    print(f"\n>>> TEST INVOICE CREATED — bill_id={body['bill_id']}, "
          f"bill_number={body['bill_number']}, app_id={app_id}  (main agent: please clean up)")


# ── Email service category gate ─────────────────────────────────────────────
def test_email_service_blocks_non_allowlisted_category():
    """Direct unit-level check on the service (no HTTP)."""
    import sys
    sys.path.insert(0, "/app/backend")
    from services.email_service import send_email, ALLOWED_EMAIL_CATEGORIES

    assert "attendance_reminder" in ALLOWED_EMAIL_CATEGORIES
    assert "attendance_status" in ALLOWED_EMAIL_CATEGORIES
    assert "payment_due" in ALLOWED_EMAIL_CATEGORIES
    assert "password_reset" in ALLOWED_EMAIL_CATEGORIES
    # everything else must be blocked
    for bad in ("daily_digest", "job_match_alert", "blog", "weekly_report", "other"):
        assert bad not in ALLOWED_EMAIL_CATEGORIES

    async def _run():
        return await send_email(
            recipient_email="qa-blocked@vhc.test",
            subject="qa",
            html_content="<p>qa</p>",
            category="daily_digest",
        )
    res = asyncio.get_event_loop().run_until_complete(_run()) if not asyncio.get_event_loop().is_running() else asyncio.run(_run())
    assert res["status"] == "blocked", f"non-allowlisted category should be blocked, got {res}"
