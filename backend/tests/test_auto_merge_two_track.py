"""
Regression: candidate auto-merge two-track scorer (v5.5.10).

Bug A: name fuzzy search was gated on `email or phone` — masked Naukri captures
(majority of new captures) were never even searched by name.

Bug B: legacy 2/3 threshold required hits in (name + email + phone) — masked
profiles max out at 1 (just name) and could never auto-merge.

Fix: two-track scorer.
  Track A: ≥2 of (name, email, phone) — legacy preserved.
  Track B: name match + ≥2 of (employer, designation, location, exp ±1).

These tests pin both tracks and the masked-contact case.
"""
import asyncio
import uuid

from config import db, initialize_db

initialize_db()

from services.candidate_merge import find_merge_candidate  # noqa: E402


def _seed(doc):
    doc.setdefault("id", str(uuid.uuid4()))
    return doc


def test_auto_merge_end_to_end():
    async def _run():
        # Cleanup any prior test records
        await db.candidate_bank.delete_many({"_test_automerge": True})

        # Use a unique name to avoid colliding with real production records
        uniq = uuid.uuid4().hex[:6]
        test_name = f"Zarquon Testperson {uniq}"

        ramesh = _seed({
            "_test_automerge": True,
            "name": test_name,
            "name_lower": test_name.lower(),
            "email": f"zarquon_{uniq}@example.com",
            "phone": f"99999{uniq[:5]}",
            "phone_normalized": f"99999{uniq[:5]}",
            "current_employer": "TESTCO AIRWORKS PVT LTD",
            "designation": "Aircraft Maintenance Engineer",
            "location": "Bengaluru",
            "experience_years": 16,
        })
        await db.candidate_bank.insert_one(ramesh.copy())

        # ── Case 1: Track A — full contact, must merge ──
        m = await find_merge_candidate(
            name=test_name,
            email=f"zarquon_{uniq}@example.com",
            phone=f"99999{uniq[:5]}",
        )
        assert m is not None, "Track A: full contact failed"
        assert m["id"] == ramesh["id"]

        # ── Case 2: Track A — email only + name, must merge (2/3) ──
        m = await find_merge_candidate(
            name=test_name,
            email=f"zarquon_{uniq}@example.com",
            phone=None,
        )
        assert m is not None and m["id"] == ramesh["id"], "Track A 2/3 (name+email) failed"

        # ── Case 3: Track B — masked contact, full multi-signal match ──
        m = await find_merge_candidate(
            name=test_name,
            email=None,
            phone=None,
            current_employer="TESTCO AIRWORKS PVT LTD",
            designation="Aircraft Maintenance Engineer",
            location="Bengaluru",
            experience_years=16,
        )
        assert m is not None, "Track B: full multi-signal masked match failed"
        assert m["id"] == ramesh["id"]

        # ── Case 4: Track B — name + employer + designation (2 corroborating) ──
        m = await find_merge_candidate(
            name=test_name,
            email=None,
            phone=None,
            current_employer="TESTCO AIRWORKS PVT LTD",
            designation="Aircraft Maintenance Engineer",
        )
        assert m is not None and m["id"] == ramesh["id"], "Track B 2-signal masked failed"

        # ── Case 5: Track B should NOT match — name only, no corroboration ──
        m = await find_merge_candidate(
            name=test_name,
            email=None, phone=None,
        )
        assert m is None, f"Track B with name-only must NOT auto-merge (got {m})"

        # ── Case 6: Track B should NOT match — name + only 1 weak signal ──
        m = await find_merge_candidate(
            name=test_name,
            email=None, phone=None,
            location="Bengaluru",  # only 1 corroborating signal
        )
        assert m is None, f"Track B with 1 signal must NOT auto-merge (got {m})"

        # ── Case 7: Different person, same name — must not falsely merge ──
        m = await find_merge_candidate(
            name=test_name,
            email=None, phone=None,
            current_employer="Wipro",          # different employer
            designation="Software Engineer",   # different role
            location="Pune",                   # different city
            experience_years=4,                # different exp
        )
        assert m is None, f"Different person must NOT merge into Aircraft Engineer (got {m})"

        # Cleanup
        await db.candidate_bank.delete_many({"_test_automerge": True})

    asyncio.run(_run())
