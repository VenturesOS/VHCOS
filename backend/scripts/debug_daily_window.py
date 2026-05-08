"""Quick debug: show what today's Daily Report window sees in MongoDB.

Usage (from /home/ubuntu/vhc-platform/backend):
    ./venv/bin/python3 scripts/debug_daily_window.py

Connects to the SAME MongoDB the live FastAPI app uses. Priority:
  1. mongo_production_override.py  (what gunicorn uses in production)
  2. MONGO_URL env var / .env      (fallback)

This mirrors config.py so we never hit an AtlasError 'bad auth' again.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

# ── Resolve MongoDB URL exactly the way config.py does ─────────────────────
from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND_DIR, ".env"), override=False)

_REQUIRED_CLUSTER = "cluster0.vuhdiod.mongodb.net"
_REQUIRED_DB = "vhc_talent_os"

mongo_url = None
db_name = None
source = None
try:
    from mongo_production_override import MONGO_URL as _ov_url, DB_NAME as _ov_db  # type: ignore
    if _ov_url and _REQUIRED_CLUSTER in _ov_url:
        mongo_url = _ov_url
        db_name = _ov_db or _REQUIRED_DB
        source = "mongo_production_override.py"
except Exception as e:
    print(f"[warn] mongo_production_override.py not usable: {e}")

if not mongo_url:
    mongo_url = os.environ.get("MONGO_URL") or os.environ.get("MONGODB_URI") or os.environ.get("MONGODB_URL")
    db_name = os.environ.get("DB_NAME") or _REQUIRED_DB
    source = ".env MONGO_URL"

if not mongo_url:
    print("FATAL: no MONGO_URL available from override or .env")
    sys.exit(1)

# Mask password for safe logging
_safe = mongo_url
if "@" in _safe and "://" in _safe:
    proto, rest = _safe.split("://", 1)
    creds, host = rest.split("@", 1)
    if ":" in creds:
        user = creds.split(":", 1)[0]
        _safe = f"{proto}://{user}:***@{host}"
print(f"[debug] Using Mongo via {source}: {_safe}")
print(f"[debug] DB: {db_name}\n")

from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # Daily window = previous 18:30 IST → today 18:30 IST  (UTC: 13:00 → 13:00)
    IST_OFFSET = timedelta(hours=5, minutes=30)
    now_ist = datetime.now(timezone.utc) + IST_OFFSET
    end_ist = now_ist.replace(hour=18, minute=30, second=0, microsecond=0)
    start_ist = end_ist - timedelta(days=1)
    start_iso = (start_ist - IST_OFFSET).replace(tzinfo=timezone.utc).isoformat()
    end_iso = (end_ist - IST_OFFSET).replace(tzinfo=timezone.utc).isoformat()

    print(f"Now (UTC):     {datetime.now(timezone.utc).isoformat()}")
    print(f"Now (IST):     {now_ist.isoformat()}")
    print(f"Window start:  {start_iso}")
    print(f"Window end:    {end_iso}\n")

    # ── Overall window sanity ────────────────────────────────────────────
    q_all = {"created_at": {"$gte": start_iso, "$lt": end_iso}}
    count_all = await db.candidate_bank.count_documents(q_all)
    print(f"ALL candidate_bank docs in window: {count_all}")

    # Sample latest docs in window so we can eyeball created_at / created_by
    print("\n--- Latest 5 captures in window ---")
    async for doc in db.candidate_bank.find(
        q_all,
        {"_id": 0, "name": 1, "created_at": 1, "created_by": 1, "captured_by": 1, "linked_mandates": 1},
    ).sort("created_at", -1).limit(5):
        print(" ", doc)

    # ── Per-team breakdown (matches reports_service.aggregate_daily) ─────
    print("\n--- Per-team captures in window ---")
    teams = await db.teams.find(
        {"status": "active"},
        {"_id": 0, "id": 1, "name": 1, "recruiter_ids": 1, "employer_id": 1},
    ).to_list(length=None)
    print(f"Active teams: {len(teams)}\n")
    for t in teams:
        rids = t.get("recruiter_ids") or []
        if not rids:
            print(f"  {t.get('name'):<30s}  (no recruiters)")
            continue
        q = {
            "$and": [
                {"created_at": {"$gte": start_iso, "$lt": end_iso}},
                {"$or": [
                    {"captured_by": {"$in": rids}},
                    {"created_by": {"$in": rids}},
                ]},
            ]
        }
        cnt = await db.candidate_bank.count_documents(q)
        # Also count how many have neither captured_by nor created_by in rids
        # (sanity — catches the case where 'captured_by' is stored but using
        # a different id format)
        print(f"  {t.get('name'):<30s}  recruiters={len(rids):<3}  captures={cnt}")

    # ── Tracker events (profile shared) in window ────────────────────────
    print("\n--- Tracker events in window (submitted_to_client) ---")
    cnt_events = await db.tracker_events.count_documents({
        "new_stage": "submitted_to_client",
        "timestamp": {"$gte": start_iso, "$lt": end_iso},
    })
    print(f"  total submitted_to_client events: {cnt_events}")

    # ── Diagnostic: any captures today-only (last 24h) that are OUTSIDE
    # ── the window? Helps detect timezone mismatches. ────────────────────
    last24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    outside = await db.candidate_bank.count_documents({
        "created_at": {"$gte": last24h},
        "$nor": [{"created_at": {"$gte": start_iso, "$lt": end_iso}}],
    })
    print(f"\nCaptures in past rolling-24h but OUTSIDE daily window: {outside}")
    print("(these would roll into tomorrow's daily report)")

    client.close()


asyncio.run(main())
