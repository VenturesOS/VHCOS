"""
Regression: "Auto-merge all duplicates" bulk endpoint helper.

Verifies the new `_merge_candidate_group` helper that powers both the
single-group `/merge-duplicates` and the bulk `/merge-all-duplicates`
endpoints:
  - merges donors that pass the 2-of-3 safety gate
  - flags donors that fail the safety gate (not merged)
  - raises ValueError when <2 ids supplied
  - raises ValueError when supplied ids don't exist in DB

Run-style mirrors `test_auto_merge_two_track.py`: a single asyncio.run
so Motor's client stays bound to one event loop.
"""
import asyncio
import uuid

from config import db, initialize_db

initialize_db()

from routes.candidates import _merge_candidate_group  # noqa: E402


def _seed(doc):
    doc.setdefault("id", str(uuid.uuid4()))
    return doc


async def _case_strong_match():
    uniq = uuid.uuid4().hex[:6]
    name = f"Bulk Merge Master {uniq}"
    email = f"bulkmerge_{uniq}@example.com"
    phone = f"98765{uniq[:5]}"

    master = _seed({
        "_test_mergeall": True,
        "name": name, "name_lower": name.lower(),
        "email": email, "phone": phone, "phone_normalized": phone,
    })
    donor = _seed({
        "_test_mergeall": True,
        "name": name, "name_lower": name.lower(),
        "email": email, "phone": phone, "phone_normalized": phone,
    })
    await db.candidate_bank.insert_many([dict(master), dict(donor)])

    result = await _merge_candidate_group(
        db, [master["id"], donor["id"]], "tester@vhc.in"
    )
    assert result["merged_count"] == 1, result
    assert result["master_id"] in (master["id"], donor["id"])
    survivors = await db.candidate_bank.count_documents({
        "id": {"$in": [master["id"], donor["id"]]}
    })
    assert survivors == 1


async def _case_weak_match_skipped():
    uniq = uuid.uuid4().hex[:6]
    uniq_b = uuid.uuid4().hex[:6]
    email = f"sharedemail_{uniq}@example.com"
    a = _seed({
        "_test_mergeall": True,
        "name": f"Alice Alpha {uniq}", "name_lower": f"alice alpha {uniq}",
        "email": email, "phone": f"11111{uniq[:5]}",
        "phone_normalized": f"11111{uniq[:5]}",
    })
    b = _seed({
        "_test_mergeall": True,
        "name": f"Bob Beta {uniq_b}", "name_lower": f"bob beta {uniq_b}",
        "email": email, "phone": f"22222{uniq[:5]}",
        "phone_normalized": f"22222{uniq[:5]}",
    })
    await db.candidate_bank.insert_many([dict(a), dict(b)])

    result = await _merge_candidate_group(
        db, [a["id"], b["id"]], "tester@vhc.in"
    )
    assert result["merged_count"] == 0, result
    assert len(result["skipped"]) == 1
    survivors = await db.candidate_bank.count_documents({
        "id": {"$in": [a["id"], b["id"]]}
    })
    assert survivors == 2


async def _case_too_few_ids():
    try:
        await _merge_candidate_group(db, ["only-one"], "tester@vhc.in")
        raise AssertionError("Expected ValueError")
    except ValueError as e:
        assert "at least 2" in str(e).lower()


async def _case_unknown_ids():
    try:
        await _merge_candidate_group(
            db,
            [f"missing-{uuid.uuid4().hex}", f"missing-{uuid.uuid4().hex}"],
            "tester@vhc.in",
        )
        raise AssertionError("Expected ValueError")
    except ValueError as e:
        assert "could not find" in str(e).lower()


def test_merge_all_duplicates_helper():
    async def _run():
        # Cleanup any prior test records
        await db.candidate_bank.delete_many({"_test_mergeall": True})
        try:
            await _case_strong_match()
            await _case_weak_match_skipped()
            await _case_too_few_ids()
            await _case_unknown_ids()
        finally:
            await db.candidate_bank.delete_many({"_test_mergeall": True})

    asyncio.run(_run())


if __name__ == "__main__":
    test_merge_all_duplicates_helper()
    print("PASS: all 4 merge-all-duplicates helper cases")
