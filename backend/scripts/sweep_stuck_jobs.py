"""
Stuck-Job Sweeper — Phase 56.6 (Jun 2026).

Runs on EC2 via cron every 10 minutes. Idempotent + safe to over-run.

What it does
------------
Scans Mongo for `status: "processing"` rows that are stale (age > 5 min)
in known background-job collections, and rewrites them to
`status: "failed"`. This frees the UI from showing "Processing..." forever
when a worker died mid-job (e.g. during the Atlas blip we saw at
05:56-06:00 on 2026-06-02, when 17 rows across `match_jobs`,
`job_suggestions`, and `background_jobs` got orphaned).

Without this cron, the only recovery path was a manual one-shot script
(/tmp/cleanup_real_stuck.py during incident response). Now it's automatic.

What it does NOT do
-------------------
- Does NOT retry the failed jobs. Retry is the user's choice in the UI.
- Does NOT touch `naukri_capture_logs` — those rows are only written on
  completion (success/failed), never as 'processing'. The "Processing"
  state in the extension popup is purely client-side chrome.storage —
  not server-side state.
- Does NOT touch jobs younger than 5 min — they may still be running.

Cron entry (add via `crontab -e` on EC2):
    */10 * * * * cd /home/ubuntu/vhc-platform/backend && \\
        venv/bin/python scripts/sweep_stuck_jobs.py >> /var/log/sweep_stuck.log 2>&1
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pymongo

# ── Load .env (without depending on python-dotenv to keep this script
# self-contained and runnable from any cwd) ──
ENV_PATH = Path("/home/ubuntu/vhc-platform/backend/.env")
if not ENV_PATH.exists():
    # Local-dev fallback
    ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

env: dict[str, str] = {}
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v.strip('"').strip("'")

MONGO_URL = env.get("MONGO_URL") or os.environ.get("MONGO_URL")
DB_NAME = env.get("DB_NAME") or os.environ.get("DB_NAME") or "vhc"

if not MONGO_URL:
    print("[Sweeper] MONGO_URL not set — aborting")
    sys.exit(1)


# Collections we sweep. Each entry:
#   (collection_name, time_field, max_age_minutes)
# `time_field` is the column on which we measure age. Some collections
# use `started_at`, some use `created_at`. Anything older than max_age
# AND still in 'processing' gets marked failed.
SWEEP_TARGETS: list[tuple[str, str, int]] = [
    # Talent-graph batch matchers — usually finish in <2 min
    ("match_jobs", "created_at", 15),
    # Auto job-suggestion runs — usually finish in <1 min
    ("job_suggestions", "started_at", 10),
    # Generic background jobs (clustering, backfill, etc.) — slower
    ("background_jobs", "created_at", 30),
    # Bulk import / enrich jobs
    ("bulk_enrich_jobs", "started_at", 60),
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sweep_one(db, coll_name: str, time_field: str, max_age_minutes: int) -> int:
    coll = db[coll_name]
    cutoff = _utc_now() - timedelta(minutes=max_age_minutes)
    # `processing` is the standard. Some flows use `running` instead.
    q = {
        "status": {"$in": ["processing", "running"]},
        time_field: {"$lt": cutoff},
    }
    n_match = coll.count_documents(q)
    if n_match == 0:
        return 0
    res = coll.update_many(
        q,
        {"$set": {
            "status": "failed",
            "error": f"auto-failed by sweeper — stuck >{max_age_minutes}min in 'processing'",
            "failed_at": _utc_now(),
            "completed_at": _utc_now(),  # some readers look at this field
        }},
    )
    return res.modified_count


def main() -> int:
    client = pymongo.MongoClient(MONGO_URL, serverSelectionTimeoutMS=10_000)
    db = client[DB_NAME]
    total = 0
    for coll, tf, age in SWEEP_TARGETS:
        try:
            n = sweep_one(db, coll, tf, age)
            if n:
                # Only log when something changed — quiet on no-op
                print(f"[{_utc_now().isoformat()}] {coll}: swept {n} stuck → failed (age>{age}min)")
                total += n
        except Exception as e:
            print(f"[{_utc_now().isoformat()}] {coll}: ERROR {e}")
    # Write a single roll-up to cron_job_logs so admins can see history
    if total > 0:
        try:
            db.cron_job_logs.insert_one({
                "id": f"sweep-{_utc_now().isoformat()}",
                "job_name": "sweep_stuck_jobs",
                "status": "success",
                "details": {"total_swept": total},
                "executed_at": _utc_now(),
            })
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
