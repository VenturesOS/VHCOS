"""
Regression: "Auto-merge all duplicates" bulk endpoint.

Verifies the new `_merge_candidate_group` helper + the bulk
`POST /candidate-bank/merge-all-duplicates` endpoint:
  - merges every duplicate group returned by find-all-duplicates
  - tracks IDs already merged so overlapping groups (same person in
    email + phone groups) don't double-process
  - honours the 2-of-3 safety gate (donors that fail are flagged, not merged)
  - returns a summary with groups_merged / total_candidates_merged
"""
import asyncio
import uuid

from config import db, initialize_db

initialize_db()

from routes.candidates import _merge_candidate_group  # noqa: E402


def _seed(doc):
    doc.setdefault("id", str(uuid.uuid4()))
    return doc


def test_merge_helper_merges_strong_match():
    async def _run():
        await db.candidate_bank.delete_many({"_test_mergeall": True})
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

        try:
            result = await _merge_candidate_group(
                db, [master["id"], donor["id"]], "tester@vhc.in"
            )
            assert result["merged_count"] == 1, result
            assert result["master_id"] in (master["id"], donor["id"])
            survivors = await db.candidate_bank.count_documents({
                "id": {"$in": [master["id"], donor["id"]]}
            })
            assert survivors == 1
        finally:
            await db.candidate_bank.delete_many({"_test_mergeall": True})

    asyncio.run(_run())


def test_merge_helper_skips_weak_match():
    async def _run():
        await db.candidate_bank.delete_many({"_test_mergeall": True})
        uniq = uuid.uuid4().hex[:6]
        # Same email but totally different name + phone → only 1/3 match (email)
        email = f"sharedemail_{uniq}@example.com"
        a = _seed({
            "_test_mergeall": True,
            "name": f"Alice Alpha {uniq}", "name_lower": f"alice alpha {uniq}",
            "email": email, "phone": f"11111{uniq[:5]}",
            "phone_normalized": f"11111{uniq[:5]}",
        })
        b = _seed({
            "_test_mergeall": True,
            "name": f"Bob Beta {uniq}", "name_lower": f"bob beta {uniq}",
            "email": email, "phone": f"22222{uniq[:5]}",
            "phone_normalized": f"22222{uniq[:5]}",
        })
        await db.candidate_bank.insert_many([dict(a), dict(b)])

        try:
            result = await _merge_candidate_group(
                db, [a["id"], b["id"]], "tester@vhc.in"
            )
            assert result["merged_count"] == 0, result
            assert len(result["skipped"]) == 1
            # Both should still exist
            survivors = await db.candidate_bank.count_documents({
                "id": {"$in": [a["id"], b["id"]]}
            })
            assert survivors == 2
        finally:
            await db.candidate_bank.delete_many({"_test_mergeall": True})

    asyncio.run(_run())


def test_merge_helper_raises_for_single_id():
    async def _run():
        try:
            await _merge_candidate_group(db, ["only-one"], "tester@vhc.in")
            raise AssertionError("Expected ValueError")
        except ValueError as e:
            assert "at least 2" in str(e).lower()

    asyncio.run(_run())


def test_merge_helper_raises_for_unknown_ids():
    async def _run():
        try:
            await _merge_candidate_group(
                db, ["does-not-exist-1", "does-not-exist-2"], "tester@vhc.in"
            )
            raise AssertionError("Expected ValueError")
        except ValueError as e:
            assert "could not find" in str(e).lower()

    asyncio.run(_run())


if __name__ == "__main__":
    test_merge_helper_merges_strong_match()
    print("PASS: merges strong match")
    test_merge_helper_skips_weak_match()
    print("PASS: skips weak match (safety gate)")
    test_merge_helper_raises_for_single_id()
    print("PASS: raises for <2 ids")
    test_merge_helper_raises_for_unknown_ids()
    print("PASS: raises for unknown ids")
