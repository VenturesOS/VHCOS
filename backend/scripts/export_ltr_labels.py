#!/usr/bin/env python3
"""
export_ltr_labels.py — Asha outcomes → LTR training telemetry
=============================================================
Every completed screening is a labeled (candidate, mandate) pair with a
far stronger signal than click behavior: a human-verified conversation.
This script converts them into the platform's ltr_telemetry slate/action
format so the existing XGBoost pipeline consumes them with zero changes.

Mapping (source = "asha_screening"):
  QUALIFIED                  → action "shortlist"
  QUALIFIED + reversed_by    → action "shortlist" (human-endorsed)
  NOT_QUALIFIED              → action "reject"
  PLACED edge on the pair    → extra action "contact"  (strongest label)

Idempotent: sessions are stamped ltr_exported=True; re-runs skip them.

Usage (from backend/, MONGO_URL set):
  python scripts/export_ltr_labels.py            # export new sessions
  python scripts/export_ltr_labels.py --dry-run  # count only
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "vhc_talent_os")
if not MONGO_URL:
    sys.exit("MONGO_URL required")

VERDICT_ACTION = {"QUALIFIED": "shortlist", "NOT_QUALIFIED": "reject"}


async def main(dry: bool):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    try:
        from services.ltr_telemetry import log_slate, log_action  # platform helpers
        use_helpers = True
    except Exception as e:
        print(f"ltr_telemetry helpers unavailable ({e}); exiting without writes")
        return

    q = {"flow": "screening", "state": "completed",
         "verdict": {"$in": list(VERDICT_ACTION)},
         "ltr_exported": {"$ne": True}}
    total = await db.screening_sessions.count_documents(q)
    print(f"Sessions to export: {total}")
    if dry:
        client.close()
        return

    exported = 0
    cursor = db.screening_sessions.find(q)
    async for s in cursor:
        action = VERDICT_ACTION[s["verdict"]]
        try:
            slate_id = await log_slate(
                source="asha_screening",
                query=s["mandate_id"],
                query_meta={"mandate_title": s.get("mandate_title"),
                            "asha_session": s["id"],
                            "verified": s.get("verified") or {}},
                slate=[{"rank": 0, "candidate_id": s["candidate_id"],
                        "score": (s.get("score") or 0) / 100}],
            )
            await log_action(slate_id, candidate_id=s["candidate_id"],
                             action=action, rank=0)
            placed = await db.edges.find_one(
                {"src": f"cand:{s['candidate_id']}", "rel": "PLACED",
                 "dst": f"mandate:{s['mandate_id']}"})
            if placed:
                await log_action(slate_id, candidate_id=s["candidate_id"],
                                 action="contact", rank=0)
            await db.screening_sessions.update_one(
                {"id": s["id"]}, {"$set": {"ltr_exported": True}})
            exported += 1
        except Exception as e:
            print(f"  export failed for session {s['id']}: {e}")
    print(f"Exported {exported}/{total} labeled pairs into ltr_telemetry.")
    client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    asyncio.run(main(ap.parse_args().dry_run))
