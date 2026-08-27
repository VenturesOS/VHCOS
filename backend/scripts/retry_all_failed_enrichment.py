"""
Retry LLM enrichment for candidates stuck with ai_enrichment_source='all_failed'.

These were captured during the 2026-08-25 serverless outage — regex ran, but
every LLM provider failed, so the profile was saved with names/phones/headlines
only, no skills/experience/summary. Semantic search and matching are
degraded for these.

Design:
- Resumable: re-queries by `ai_enrichment_source: "all_failed"` each pass,
  so a partial run auto-picks up on next invocation.
- Sequential per candidate (LLM call is the slow step; concurrency=4 to
  batch RunPod A40 pod).
- Uses the SAME extraction path as the /api/extension/re-enrich/{id} route
  (llm_fallback_service.extract_full_profile_fallback → RunPod Qwen → Emergent Haiku).
- Writes back only fields the LLM returned; preserves everything else.
- Uses whatever source the LLM chain reports (runpod_qwen14b, emergent_haiku_4_5, etc)
  — no more all_failed unless every provider fails again.

Usage:
    cd /app/backend && python -m scripts.retry_all_failed_enrichment [--limit N] [--dry-run]

Progress logs every 50 candidates.
"""
import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
# Silence noisy httpx access logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("retry_failed")

CONCURRENCY = 4  # A40 pod can comfortably serve 4 parallel requests
_CTC_MAX = 50_000_000


def _clean_skills(skills):
    """Same skills sanitiser as extension.py — drop empty/duplicated/oversized."""
    if not isinstance(skills, list):
        return []
    seen = set()
    out = []
    for s in skills:
        if not isinstance(s, str):
            continue
        s = s.strip()
        if not s or len(s) > 50:
            continue
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out[:100]


def _build_updates(ai: Dict, candidate: Dict) -> Dict:
    """Mirror the field mapping from routes/extension.py::re_enrich_candidate."""
    updates: Dict = {}

    # Contact
    if ai.get("candidate_phone"):
        digits = "".join(filter(str.isdigit, str(ai["candidate_phone"])))
        if len(digits) >= 10:
            updates["phone"] = digits[-10:]
            updates["phone_normalized"] = digits[-10:]
    if ai.get("candidate_email"):
        email = ai["candidate_email"].lower().strip()
        blocked = ["@naukri.com", "@vhc.in", "noreply@", "support@"]
        if not any(p in email for p in blocked):
            updates["email"] = email

    # Professional
    for field, target in [
        ("current_employer", "current_employer"),
        ("current_designation", "designation"),
        ("location", "location"),
        ("headline", "headline"),
        ("profile_summary", "summary"),
    ]:
        if ai.get(field):
            updates[target] = ai[field]

    if ai.get("current_department"):
        d = ai["current_department"].strip()
        if len(d) < 80:
            updates["department"] = d
    if ai.get("current_industry"):
        d = ai["current_industry"].strip()
        if len(d) < 80:
            updates["industry"] = d

    if ai.get("experience_years"):
        try:
            e = float(ai["experience_years"])
            if e <= 50:
                updates["experience_years"] = round(e, 2)
        except (ValueError, TypeError):
            pass

    if ai.get("current_ctc"):
        try:
            v = int(ai["current_ctc"])
            if v <= _CTC_MAX:
                updates["current_salary"] = v
        except (ValueError, TypeError):
            pass
    if ai.get("expected_ctc"):
        try:
            v = int(ai["expected_ctc"])
            if v <= _CTC_MAX:
                updates["expected_salary"] = v
        except (ValueError, TypeError):
            pass

    if ai.get("notice_period"):
        updates["notice_period"] = ai["notice_period"]
    if ai.get("notice_period_days"):
        try:
            updates["notice_period_days"] = int(ai["notice_period_days"])
        except (ValueError, TypeError):
            pass

    if ai.get("key_skills"):
        skills = _clean_skills(ai["key_skills"])
        if skills:
            updates["skills"] = skills

    if isinstance(ai.get("work_experience"), list) and ai["work_experience"]:
        updates["experience"] = ai["work_experience"]
    if isinstance(ai.get("education"), list) and ai["education"]:
        updates["education"] = ai["education"]

    if ai.get("certifications"):
        updates["certifications"] = ai["certifications"]
    if ai.get("languages"):
        updates["languages"] = ai["languages"]

    personal = {}
    for k in ("date_of_birth", "gender", "marital_status"):
        if ai.get(k):
            personal[k] = ai[k]
    if personal:
        existing = candidate.get("personal_details") or {}
        updates["personal_details"] = {**existing, **personal}

    return updates


async def retry_one(db, candidate: Dict, dry_run: bool) -> str:
    """Retry enrichment for a single candidate. Returns short status string."""
    from services.llm_fallback_service import extract_full_profile_fallback

    cid = candidate.get("id")
    name = candidate.get("name") or "(unknown)"
    raw_text = (
        candidate.get("raw_text_for_enrichment")
        or candidate.get("raw_page_text")
        or candidate.get("raw_profile_text")
        or ""
    )
    if not raw_text or len(raw_text) < 200:
        # Nothing to feed the LLM — mark separately so we don't retry endlessly
        if not dry_run:
            await db.candidate_bank.update_one(
                {"id": cid},
                {"$set": {"ai_enrichment_source": "no_raw_text",
                          "ai_enriched_at": datetime.now(timezone.utc).isoformat()}},
            )
        return "no_raw_text"

    try:
        ai = await extract_full_profile_fallback(raw_text=raw_text, candidate_name=name)
    except Exception as e:
        logger.warning(f"[Retry] {cid} '{name}': extraction crashed — {e}")
        return "crashed"

    if not ai or ai.get("error"):
        return "still_failed"

    updates = _build_updates(ai, candidate)
    if not updates:
        return "empty_result"

    src = ai.get("source") or ai.get("_extraction_source") or "runpod_qwen14b"
    updates["ai_enriched_at"] = datetime.now(timezone.utc).isoformat()
    updates["ai_enrichment_source"] = src

    if not dry_run:
        await db.candidate_bank.update_one({"id": cid}, {"$set": updates})
    return src


async def main():
    parser = argparse.ArgumentParser(description="Retry all_failed enrichments through the LLM chain")
    parser.add_argument("--limit", type=int, default=None, help="Cap docs processed")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without writing")
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    query = {"ai_enrichment_source": "all_failed"}
    total = await db.candidate_bank.count_documents(query)
    logger.info(f"Found {total:,} candidates with ai_enrichment_source='all_failed'")
    if args.limit:
        total = min(total, args.limit)
        logger.info(f"Limited to {args.limit:,}")

    if args.dry_run:
        logger.info("DRY RUN — no writes will be made")

    if total == 0:
        logger.info("Nothing to do. Exiting.")
        return 0

    started = time.monotonic()
    counts: Dict[str, int] = {}
    processed = 0

    cursor = db.candidate_bank.find(query, {"_id": 0}).limit(args.limit or 0)

    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def run_one(cand):
        async with semaphore:
            return await retry_one(db, cand, args.dry_run)

    tasks = []
    async for cand in cursor:
        tasks.append(asyncio.create_task(run_one(cand)))
        if len(tasks) >= CONCURRENCY * 4:
            for status in await asyncio.gather(*tasks, return_exceptions=True):
                if isinstance(status, Exception):
                    counts["exception"] = counts.get("exception", 0) + 1
                else:
                    counts[status] = counts.get(status, 0) + 1
                processed += 1
            tasks = []
            if processed % 50 == 0 or processed == total:
                elapsed = time.monotonic() - started
                rate = processed / elapsed if elapsed else 0
                logger.info(
                    f"progress: {processed:,}/{total:,} "
                    f"({processed*100/total:.1f}%) | {rate:.1f}/sec | "
                    f"{dict(sorted(counts.items(), key=lambda x: -x[1]))}"
                )

    if tasks:
        for status in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(status, Exception):
                counts["exception"] = counts.get("exception", 0) + 1
            else:
                counts[status] = counts.get(status, 0) + 1
            processed += 1

    elapsed = time.monotonic() - started
    logger.info(
        f"DONE in {elapsed:.1f}s: processed={processed:,}, "
        f"breakdown={dict(sorted(counts.items(), key=lambda x: -x[1]))}"
    )
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
