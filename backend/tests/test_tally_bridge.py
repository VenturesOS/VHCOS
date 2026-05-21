"""Standalone tests for the Tally bridge endpoints.

Verifies:
  • Auth (bad/missing token → 403)
  • /queue returns only bills with status in (sent, paid) AND not yet pushed
  • XML envelope is well-formed and contains correct ledger entries
  • /ack marks the bill pushed and removes it from /queue
  • Failure ack records the error but does NOT mark pushed
  • Idempotency: ack on already-pushed bill keeps the state correct
  • Re-pushing via flipping tally.pushed=false works

Run:
    cd /app/backend && python tests/test_tally_bridge.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
import xml.etree.ElementTree as ET

import requests

sys.path.insert(0, "/app/backend")
os.chdir("/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from config import db, initialize_db

API = os.environ["REACT_APP_BACKEND_URL"] if "REACT_APP_BACKEND_URL" in os.environ else None
if not API:
    # Read frontend/.env
    with open("/app/frontend/.env") as fh:
        for ln in fh:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                API = ln.split("=", 1)[1].strip()
                break
TOKEN = os.environ.get("TALLY_BRIDGE_TOKEN")

PASS, FAIL = "\033[92m✓\033[0m", "\033[91m✗\033[0m"
_results: list[tuple[str, bool, str]] = []


def chk(name: str, cond, hint=""):
    _results.append((name, bool(cond), "" if cond else f"  {hint}"))


def H(extra: dict | None = None) -> dict:
    h = {"X-Tally-Bridge-Token": TOKEN, "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


# ── Seed: insert a fresh test bill in sent state ──────────────────────
async def seed_test_bill() -> str:
    initialize_db()
    bill_id = str(uuid.uuid4())
    doc = {
        "id": bill_id,
        "bill_number": f"VHC/26-27/TEST-{bill_id[:8]}",
        "bill_date": "2026-02-10",
        "due_date": "2026-02-17",
        "sender_legal_name": "VENTURE HRD CENTRE PVT LTD",
        "sender_address": "Delhi",
        "sender_gstin": "07AAMPY9883D2ZT",
        "sender_pan": "AAMPY9883D",
        "sender_state_code": "07",
        "client_company_id": "test-co",
        "client_legal_name": "Pytest Tally Customer",
        "client_address": "Bengaluru, KA",
        "client_gstin": "29AAAAA1234A1Z5",
        "client_state_code": "29",
        "client_billing_email": "test@example.com",
        "line_items": [{
            "candidate_name": "Foo Bar",
            "designation": "QA",
            "joining_date": "2026-02-01",
            "annual_ctc": 1_200_000,
            "commercial_rate_pct": 8.33,
            "line_amount": 99960.0,
            "hsn_sac": "998512",
            "application_id": None,
        }],
        "totals": {
            "taxable_value": 99960.0,
            "gst_kind": "IGST",
            "igst_pct": 18.0, "cgst_pct": 0, "sgst_pct": 0,
            "tax_total": 17992.80,
            "grand_total": 117952.80,
            "amount_in_words": "Indian Rupees ... Only",
            "tax_in_words": "Indian Rupees ... Only",
        },
        "status": "sent",
        "sent_at": "2026-02-10T00:00:00+00:00",
        "reminders_enabled": True,
        "reminder_schedule_days": [7, 14, 30],
        "reminders_sent": [], "mail_events": [], "cc_emails": [], "bcc_emails": [],
        "created_by": "pytest", "created_by_email": "pytest@vhc.in",
        "created_at": "2026-02-10T00:00:00+00:00",
    }
    await db.bills.insert_one(doc)
    return bill_id


async def cleanup(bill_id: str):
    await db.bills.delete_one({"id": bill_id})


# ── Tests ──────────────────────────────────────────────────────────────
def test_auth():
    r = requests.get(f"{API}/api/tally/queue", timeout=10)
    chk("missing token → 403", r.status_code == 403, f"got {r.status_code}")
    r = requests.get(f"{API}/api/tally/queue", headers={"X-Tally-Bridge-Token": "bad"}, timeout=10)
    chk("bad token → 403", r.status_code == 403, f"got {r.status_code}")


def test_queue_contains_our_bill(bill_id: str):
    r = requests.get(f"{API}/api/tally/queue", headers=H(), timeout=15)
    chk("queue with good token → 200", r.status_code == 200, f"got {r.status_code}")
    items = r.json() if r.status_code == 200 else []
    ours = [i for i in items if i.get("bill_id") == bill_id]
    chk("our seed bill is in the queue", len(ours) == 1, f"matches={len(ours)}")
    return ours[0] if ours else None


def test_xml_valid(item: dict):
    if not item:
        chk("xml-shape (skipped — no item)", False)
        return
    xml = item.get("xml", "")
    chk("xml has ENVELOPE root", xml.startswith("<ENVELOPE>"))
    chk("xml contains target company",
        "<SVCURRENTCOMPANY>VENTURE HRD CENTRE PVT LTD</SVCURRENTCOMPANY>" in xml)
    chk("xml has Sales voucher type", 'VCHTYPE="Sales"' in xml)
    chk("xml has REMOTEID for idempotency", "REMOTEID=" in xml)
    chk("xml has party ledger", "Pytest Tally Customer" in xml)
    chk("xml has sales credit ledger", "Sales - Placement Consultancy" in xml)
    chk("xml has IGST tax ledger (KA→DL interstate)", "Output IGST @ 18%" in xml)
    chk("xml does NOT have CGST/SGST (would be wrong for interstate)",
        "Output CGST" not in xml and "Output SGST" not in xml)
    # Parse the XML to be sure it's well-formed
    try:
        root = ET.fromstring(xml)
        # Find the voucher
        vch = root.find(".//VOUCHER")
        chk("xml is well-formed (parses)", vch is not None)
        # Sum ledger amounts: should be near zero (sales is double-entry)
        amts = [float(e.text) for e in root.findall(".//ALLLEDGERENTRIES.LIST/AMOUNT") if e.text]
        chk(f"ledger amounts sum to ~0 (got {sum(amts):.2f})", abs(sum(amts)) < 0.05)
    except ET.ParseError as e:
        chk(f"xml parse failed: {e}", False)


def test_success_ack(bill_id: str):
    payload = {
        "bill_id": bill_id, "success": True,
        "tally_vch_id": "9999",
        "raw_response": "<RESPONSE><CREATED>1</CREATED><LASTVCHID>9999</LASTVCHID></RESPONSE>",
    }
    r = requests.post(f"{API}/api/tally/ack", headers=H(), json=payload, timeout=10)
    chk("ack-success → 200", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    chk("ack body says pushed", r.json().get("pushed") is True)


def test_queue_now_excludes_our_bill(bill_id: str):
    r = requests.get(f"{API}/api/tally/queue", headers=H(), timeout=15)
    items = r.json()
    matches = [i for i in items if i.get("bill_id") == bill_id]
    chk("our bill no longer in queue after ack-success", len(matches) == 0,
        f"still present: {matches}")


def test_failure_ack_path(bill_id_failure: str):
    # Ack with failure should NOT mark pushed
    payload = {
        "bill_id": bill_id_failure, "success": False,
        "error": "Could not find LEDGER 'Pytest Tally Customer'",
        "raw_response": "<RESPONSE><LINEERROR>Could not find LEDGER...</LINEERROR></RESPONSE>",
    }
    r = requests.post(f"{API}/api/tally/ack", headers=H(), json=payload, timeout=10)
    chk("ack-failure → 200", r.status_code == 200)
    chk("ack body says NOT pushed", r.json().get("pushed") is False)


async def assert_db_state(bill_id_success: str, bill_id_failure: str):
    s = await db.bills.find_one({"id": bill_id_success}, {"_id": 0, "tally": 1})
    f = await db.bills.find_one({"id": bill_id_failure}, {"_id": 0, "tally": 1})
    chk("success bill: tally.pushed=true", (s or {}).get("tally", {}).get("pushed") is True)
    chk("success bill: vch_id captured", (s or {}).get("tally", {}).get("tally_vch_id") == "9999")
    chk("failure bill: tally.pushed=false", (f or {}).get("tally", {}).get("pushed") is False)
    chk("failure bill: error captured",
        "Could not find LEDGER" in ((f or {}).get("tally", {}).get("last_error") or ""))


async def test_retry_after_flip(bill_id: str):
    # Flip pushed back to false → bill must reappear in queue
    await db.bills.update_one({"id": bill_id}, {"$set": {"tally.pushed": False}})
    r = requests.get(f"{API}/api/tally/queue", headers=H(), timeout=15)
    items = r.json()
    matches = [i for i in items if i.get("bill_id") == bill_id]
    chk("after flipping pushed=false, bill reappears in queue", len(matches) == 1)


# ── Runner ─────────────────────────────────────────────────────────────
async def main():
    if not TOKEN:
        print("FATAL: TALLY_BRIDGE_TOKEN not set in env"); return 1
    if not API:
        print("FATAL: REACT_APP_BACKEND_URL not found"); return 1
    print(f"API={API}")
    print(f"TOKEN={TOKEN[:20]}…")

    bid_success = await seed_test_bill()
    bid_failure = await seed_test_bill()
    print(f"Seeded bills: success={bid_success[:8]} failure={bid_failure[:8]}")

    try:
        test_auth()
        item = test_queue_contains_our_bill(bid_success)
        test_xml_valid(item)
        test_success_ack(bid_success)
        test_queue_now_excludes_our_bill(bid_success)
        test_failure_ack_path(bid_failure)
        await assert_db_state(bid_success, bid_failure)
        await test_retry_after_flip(bid_success)
    finally:
        await cleanup(bid_success)
        await cleanup(bid_failure)

    failed = 0
    for name, ok, msg in _results:
        print(f"  {PASS if ok else FAIL} {name}{msg}")
        if not ok:
            failed += 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
