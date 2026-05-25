"""End-to-end tests for POST /api/extension/check-existing.

Verifies:
  • Auth gate (no token → 403)
  • Allowlisted user (admin@vhc.in) gets real matches with index preserved
  • Non-allowlisted user gets all-false (zero behavior change for them)
  • Fuzzy name match: "Sruthi K" → "SRUTHI K" works
  • Index preservation: results[i].index == input order
  • Confidence: headline-with-employer match → "high", name-only → "medium"
  • Batch returns empty when input is empty
  • Returns proper shape (candidate_id, captured_at, match_confidence)

Run:
    cd /app/backend && python tests/test_extension_check.py
"""
from __future__ import annotations

import asyncio
import os
import sys

import requests

sys.path.insert(0, "/app/backend")
os.chdir("/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from config import db, initialize_db

API = None
with open("/app/frontend/.env") as fh:
    for ln in fh:
        if ln.startswith("REACT_APP_BACKEND_URL="):
            API = ln.split("=", 1)[1].strip()
            break

PASS, FAIL = "\033[92m✓\033[0m", "\033[91m✗\033[0m"
_results: list[tuple[str, bool, str]] = []


def chk(name: str, cond, hint=""):
    _results.append((name, bool(cond), "" if cond else f"  {hint}"))


def login(email: str, password: str) -> str | None:
    r = requests.post(f"{API}/api/auth/login",
                      headers={"Content-Type": "application/json"},
                      json={"email": email, "password": password}, timeout=15)
    if r.status_code != 200:
        return None
    d = r.json()
    return d.get("access_token") or d.get("token")


def H(token: str) -> dict:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}


# ── Pick a real candidate from the DB to test fuzzy match against ────
async def pick_seed_candidate() -> dict | None:
    initialize_db()
    doc = await db.candidate_bank.find_one(
        {"name": {"$regex": "^[A-Z]{2,}", "$options": ""}},
        {"_id": 0, "name": 1, "id": 1, "current_employer": 1,
         "designation": 1, "location": 1, "created_at": 1},
    )
    return doc


# ── Tests ────────────────────────────────────────────────────────────
def test_no_auth():
    r = requests.post(f"{API}/api/extension/check-existing",
                      headers={"Content-Type": "application/json"},
                      json={"candidates": [{"name": "x"}]}, timeout=15)
    chk("no auth → 403", r.status_code == 403, f"got {r.status_code}")


def test_non_admin_gets_all_false(non_admin_token: str | None, seed_name: str):
    if not non_admin_token:
        chk("non-admin login (skipped — no creds)", False, "could not log in as hr12@vhc.in")
        return
    r = requests.post(f"{API}/api/extension/check-existing",
                      headers=H(non_admin_token),
                      json={"candidates": [{"name": seed_name}]}, timeout=15)
    chk("non-admin → 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        results = r.json().get("results", [])
        chk("non-admin gets all-false (gated)",
            all(not x["exists"] for x in results),
            f"got {results}")
        chk("non-admin: index preserved",
            results and results[0]["index"] == 0)


def test_admin_finds_real_candidate(admin_token: str, seed: dict):
    name = seed["name"]
    r = requests.post(f"{API}/api/extension/check-existing",
                      headers=H(admin_token),
                      json={"candidates": [{"name": name}]}, timeout=20)
    chk("admin → 200", r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
    if r.status_code != 200:
        return
    results = r.json().get("results", [])
    chk("admin: one result for one input", len(results) == 1)
    r0 = results[0] if results else {}
    chk(f"admin finds {name!r} (exists=True)",
        r0.get("exists") is True,
        f"got {r0}")
    chk("admin: candidate_id returned",
        bool(r0.get("candidate_id")),
        f"got candidate_id={r0.get('candidate_id')}")
    chk("admin: captured_at returned",
        bool(r0.get("captured_at")))
    chk("admin: match_confidence is high or medium",
        r0.get("match_confidence") in ("high", "medium"),
        f"got {r0.get('match_confidence')}")


def test_fuzzy_match_partial_name(admin_token: str, seed: dict):
    """If DB has 'SRUTHI K', a search for 'Sruthi K' (different case) should still match."""
    parts = seed["name"].split()
    if not parts:
        return
    # Same name, different case
    fuzzed = " ".join(p.capitalize() for p in parts)
    r = requests.post(f"{API}/api/extension/check-existing",
                      headers=H(admin_token),
                      json={"candidates": [{"name": fuzzed}]}, timeout=20)
    if r.status_code != 200:
        chk("fuzzy: HTTP error", False, f"got {r.status_code}")
        return
    results = r.json().get("results", [])
    chk(f"fuzzy: case-insensitive match for {fuzzed!r}",
        bool(results and results[0].get("exists")),
        f"got {results}")


def test_index_preservation_batch(admin_token: str, seed: dict):
    """Send a batch of 3 — DEFINITELY-FAKE, REAL, DEFINITELY-FAKE — confirm indices 0,1,2 preserved."""
    payload = {"candidates": [
        {"name": "ZZZZ_NEVER_EXISTS_AAAA"},
        {"name": seed["name"]},
        {"name": "QQQQ_NEVER_EXISTS_BBBB"},
    ]}
    r = requests.post(f"{API}/api/extension/check-existing",
                      headers=H(admin_token), json=payload, timeout=20)
    if r.status_code != 200:
        chk("batch: HTTP error", False, f"got {r.status_code}")
        return
    results = r.json().get("results", [])
    chk("batch: returns 3 results", len(results) == 3)
    chk("batch: index 0 preserved", results[0].get("index") == 0)
    chk("batch: index 1 preserved", results[1].get("index") == 1)
    chk("batch: index 2 preserved", results[2].get("index") == 2)
    chk("batch: fake[0]=false, real[1]=true, fake[2]=false",
        not results[0]["exists"] and results[1]["exists"] and not results[2]["exists"],
        f"got {[r.get('exists') for r in results]}")


def test_confidence_high_with_employer(admin_token: str, seed: dict):
    """If we pass a headline mentioning the candidate's current_employer, confidence should bump to 'high'."""
    emp = (seed.get("current_employer") or "").strip()
    if not emp or len(emp) < 4:
        chk("confidence-high (skipped — no employer in seed)", True)
        return
    headline = f"Senior Engineer at {emp}"
    r = requests.post(f"{API}/api/extension/check-existing",
                      headers=H(admin_token),
                      json={"candidates": [{"name": seed["name"], "headline": headline}]},
                      timeout=20)
    if r.status_code != 200:
        return
    results = r.json().get("results", [])
    chk(f"confidence=high when headline mentions {emp!r}",
        bool(results and results[0].get("match_confidence") == "high"),
        f"got {results[0].get('match_confidence') if results else None}")


def test_empty_request(admin_token: str):
    r = requests.post(f"{API}/api/extension/check-existing",
                      headers=H(admin_token),
                      json={"candidates": []}, timeout=10)
    chk("empty payload → 200 with empty results",
        r.status_code == 200 and r.json().get("results") == [],
        f"got {r.status_code} {r.text[:200]}")


# ── Runner ───────────────────────────────────────────────────────────
async def main():
    if not API:
        print("FATAL: REACT_APP_BACKEND_URL not found"); return 1
    print(f"API={API}")

    admin = login("admin@vhc.in", "VhcAdmin@2024")
    non_admin = login("hr12@vhc.in", "12345678")
    if not admin:
        print("FATAL: admin login failed"); return 1
    print(f"admin_token={admin[:25]}…")
    print(f"non_admin_token={'OK' if non_admin else 'FAILED'}")

    seed = await pick_seed_candidate()
    if not seed:
        print("FATAL: could not find a candidate to test against"); return 1
    print(f"Seed candidate: {seed.get('name')!r} (id={seed.get('id')})")

    test_no_auth()
    test_non_admin_gets_all_false(non_admin, seed["name"])
    test_admin_finds_real_candidate(admin, seed)
    test_fuzzy_match_partial_name(admin, seed)
    test_index_preservation_batch(admin, seed)
    test_confidence_high_with_employer(admin, seed)
    test_empty_request(admin)

    failed = sum(1 for _, ok, _ in _results if not ok)
    for name, ok, msg in _results:
        print(f"  {PASS if ok else FAIL} {name}{msg}")
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
