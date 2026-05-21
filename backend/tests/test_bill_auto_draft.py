"""Standalone async runner for bill_auto_draft tests.

Avoids pytest-asyncio plugin dependency by driving each test via
`asyncio.run`. Run with:

    cd /app/backend && python tests/test_bill_auto_draft.py

Verifies the auto-draft service:
  • Skips when stage is not hired/joined
  • Skips when offered_ctc missing
  • Creates a draft bill with correct totals on hired
  • Is idempotent (a 2nd call doesn't double-draft)
  • Uses CGST_SGST when client state matches sender (Delhi=07)
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

sys.path.insert(0, "/app/backend")
os.chdir("/app/backend")

from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from config import db, initialize_db
from services.bill_auto_draft import maybe_auto_draft_bill


# ── Test harness ──────────────────────────────────────────────────────
PASS, FAIL = "\033[92m✓\033[0m", "\033[91m✗\033[0m"
_results: list[tuple[str, bool, str]] = []


def assert_eq(name: str, got, want):
    ok = got == want
    msg = "" if ok else f"  expected {want!r}, got {got!r}"
    _results.append((name, ok, msg))


def assert_close(name: str, got, want, tol=0.01):
    ok = abs(float(got) - float(want)) < tol
    msg = "" if ok else f"  |{got} - {want}| > {tol}"
    _results.append((name, ok, msg))


def assert_true(name: str, cond, hint=""):
    _results.append((name, bool(cond), "" if cond else f"  {hint}"))


async def seed():
    cid, jid = str(uuid.uuid4()), str(uuid.uuid4())
    await db.companies.insert_one({
        "id": cid, "name": "PYTEST Throwaway Co",
        "legal_name": "PYTEST Throwaway Co Pvt Ltd",
        "gstin": "29ABCDE1234F1Z5",
        "billing_email": "pytest@example.com",
        "billing_address": "1 Test Street, Bengaluru, KA 560001",
    })
    await db.jobs.insert_one({
        "id": jid, "title": "QA Engineer",
        "company_id": cid, "company_name": "PYTEST Throwaway Co Pvt Ltd",
    })
    return cid, jid


async def cleanup(cid: str, jid: str):
    await db.companies.delete_one({"id": cid})
    await db.jobs.delete_one({"id": jid})
    await db.bills.delete_many({"line_items.application_id": {"$regex": "^PYTEST_"}})


# ── Test cases ────────────────────────────────────────────────────────
async def case_skip_when_not_hired(cid: str, jid: str):
    app_id = f"PYTEST_{uuid.uuid4()}"
    res = await maybe_auto_draft_bill(app_id, {
        "id": app_id, "job_id": jid, "stage": "interview",
        "offered_ctc": 1_200_000, "candidate_name": "T1",
    })
    assert_eq("skip when stage != hired/joined", res, None)


async def case_skip_when_no_ctc(cid: str, jid: str):
    app_id = f"PYTEST_{uuid.uuid4()}"
    res = await maybe_auto_draft_bill(app_id, {
        "id": app_id, "job_id": jid, "stage": "hired",
        "candidate_name": "T2",
    })
    assert_eq("skip when no offered_ctc", res, None)


async def case_creates_draft_igst(cid: str, jid: str):
    app_id = f"PYTEST_{uuid.uuid4()}"
    res = await maybe_auto_draft_bill(app_id, {
        "id": app_id, "job_id": jid, "stage": "hired",
        "offered_ctc": 1_200_000, "candidate_name": "T3",
        "designation": "Senior QA", "join_date": "2026-03-01",
    }, {"id": "tester", "email": "tester@vhc.in"})
    assert_true("creates_draft returns bill number", res and res.startswith("VHC/"),
                hint=f"got {res!r}")
    bill = await db.bills.find_one({"line_items.application_id": app_id}, {"_id": 0})
    assert_true("draft bill exists in db", bill is not None)
    if not bill:
        return
    assert_eq("status=draft", bill.get("status"), "draft")
    assert_eq("auto_drafted=True", bill.get("auto_drafted"), True)
    assert_eq("gst_kind=IGST (KA→DL)", bill["totals"]["gst_kind"], "IGST")
    # 1.2M × 8.33% = 99960
    assert_close("taxable_value=99960", bill["totals"]["taxable_value"], 99960.0)
    assert_close("tax_total=17992.80", bill["totals"]["tax_total"], round(99960 * 0.18, 2))
    assert_close("grand_total=117952.80", bill["totals"]["grand_total"], round(99960 * 1.18, 2))
    li = bill["line_items"][0]
    assert_eq("line_item.application_id linked", li.get("application_id"), app_id)
    assert_eq("line_item.candidate_name", li.get("candidate_name"), "T3")
    assert_eq("line_item.joining_date", li.get("joining_date"), "2026-03-01")


async def case_idempotent(cid: str, jid: str):
    app_id = f"PYTEST_{uuid.uuid4()}"
    payload = {
        "id": app_id, "job_id": jid, "stage": "joined",
        "offered_ctc": 1_000_000, "candidate_name": "T4",
    }
    first = await maybe_auto_draft_bill(app_id, payload)
    second = await maybe_auto_draft_bill(app_id, payload)
    assert_true("first call creates", bool(first))
    assert_eq("second call is no-op (returns None)", second, None)
    n = await db.bills.count_documents({"line_items.application_id": app_id})
    assert_eq("only one bill exists", n, 1)


async def case_intrastate_cgst_sgst(cid: str, jid: str):
    # Patch client gstin to Delhi (07) → same as sender → CGST_SGST
    await db.companies.update_one({"id": cid}, {"$set": {"gstin": "07AABCD1234E1Z9"}})
    try:
        app_id = f"PYTEST_{uuid.uuid4()}"
        await maybe_auto_draft_bill(app_id, {
            "id": app_id, "job_id": jid, "stage": "hired",
            "offered_ctc": 600_000, "candidate_name": "T5",
        })
        bill = await db.bills.find_one({"line_items.application_id": app_id}, {"_id": 0})
        assert_true("intrastate bill exists", bill is not None)
        if bill:
            assert_eq("gst_kind=CGST_SGST (DL=DL)", bill["totals"]["gst_kind"], "CGST_SGST")
            assert_eq("cgst_pct=9", bill["totals"]["cgst_pct"], 9.0)
            assert_eq("sgst_pct=9", bill["totals"]["sgst_pct"], 9.0)
    finally:
        await db.companies.update_one({"id": cid}, {"$set": {"gstin": "29ABCDE1234F1Z5"}})


# ── Runner ────────────────────────────────────────────────────────────
async def main():
    initialize_db()
    cid, jid = await seed()
    try:
        await case_skip_when_not_hired(cid, jid)
        await case_skip_when_no_ctc(cid, jid)
        await case_creates_draft_igst(cid, jid)
        await case_idempotent(cid, jid)
        await case_intrastate_cgst_sgst(cid, jid)
    finally:
        await cleanup(cid, jid)

    failed = 0
    for name, ok, msg in _results:
        print(f"  {PASS if ok else FAIL} {name}{msg}")
        if not ok:
            failed += 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
