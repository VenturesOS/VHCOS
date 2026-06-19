"""Badge Threshold Phase B — auto-labeler.

Reads accumulated `badge_feedback` rows (the "Wrong match?" telemetry shipped
in Phase A) plus the source `match_results` audit, and produces:

  1. A per-signal precision report — which match signals (naukri_id, email,
     phone, name+location, etc.) correlate with `wrong_match` flags.
  2. A recommended threshold change for the V2 medium-confidence band
     (currently 0.85..1.20). The goal is to push the band closer to 0.95
     once we have enough disagreement signal.
  3. A `confidence_distribution.csv` for the admin to eyeball.

Usage:
    python -m scripts.badge_threshold_autolabeler              # report only
    python -m scripts.badge_threshold_autolabeler --apply      # write the
        # recommended threshold to the `match_thresholds` collection so
        # the next /api/extension/check-existing call picks it up.

PRE-REQUISITE: at least 200 `badge_feedback` rows AND at least 5,000
`match_results` rows. The script will refuse to run below those floors
so we don't tune on noise.
"""
from __future__ import annotations
import argparse
import asyncio
import csv
import logging
import os
import statistics
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
log = logging.getLogger("badge_autolabeler")

MIN_FEEDBACK = int(os.environ.get("AUTOLABELER_MIN_FEEDBACK", "200"))
MIN_AUDIT    = int(os.environ.get("AUTOLABELER_MIN_AUDIT",    "5000"))


async def _get_db():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return cli[os.environ["DB_NAME"]]


async def _check_sample_size(db) -> Dict[str, int]:
    n_fb = await db.badge_feedback.count_documents({"kind": "wrong_match"})
    n_au = await db.match_results.count_documents({})
    log.info("Sample sizes: badge_feedback.wrong_match=%d, match_results=%d", n_fb, n_au)
    return {"feedback": n_fb, "audit": n_au}


async def _load_wrong_match_pairs(db) -> List[Dict[str, Any]]:
    """For each wrong-match feedback row, fetch the underlying match_results
    record so we know which SIGNAL fired and what SCORE the engine assigned.
    Output rows are denormalised + ready for analysis.
    """
    out: List[Dict[str, Any]] = []
    cur = db.badge_feedback.find({"kind": "wrong_match"})
    async for fb in cur:
        audit_id   = fb.get("audit_id")
        card_idx   = fb.get("card_idx")
        badge_cid  = fb.get("badge_candidate_id")
        # Try the audit-id + card-idx lookup first (precise).
        match_doc = None
        if audit_id and card_idx is not None:
            match_doc = await db.match_results.find_one(
                {"audit_id": audit_id, "card_idx": card_idx}
            )
        # Fallback: any match_results row pointing at the same candidate.
        if not match_doc and badge_cid:
            match_doc = await db.match_results.find_one(
                {"candidate_id": badge_cid},
                sort=[("ts", -1)],
            )
        if not match_doc:
            continue
        out.append({
            "feedback_id":   fb.get("id"),
            "candidate_id":  badge_cid,
            "card_name":     fb.get("card_name"),
            "score":         match_doc.get("score"),
            "matched_signals": match_doc.get("matched_signals") or [],
            "match_type":    match_doc.get("match_type"),
        })
    return out


async def _load_positives(db, limit: int = 5000) -> List[Dict[str, Any]]:
    """Sample N recent match_results that have NO wrong-match flag — assumed
    correct (recruiter would have flagged if not). Used as the negative class
    for the auto-labeler.
    """
    # IDs we know are wrong:
    bad = set()
    async for d in db.badge_feedback.find({"kind": "wrong_match"}, {"badge_candidate_id": 1}):
        if d.get("badge_candidate_id"):
            bad.add(d["badge_candidate_id"])
    cur = db.match_results.find({"candidate_id": {"$nin": list(bad)}}).limit(limit)
    return [d async for d in cur]


def _signal_precision(pos: List[Dict[str, Any]], neg: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """For each signal, return precision = TP / (TP+FP)."""
    out: Dict[str, Dict[str, int]] = {}
    for r in pos:
        for s in r.get("matched_signals") or []:
            out.setdefault(s, {"tp": 0, "fp": 0})["tp"] += 1
    for r in neg:
        for s in r.get("matched_signals") or []:
            out.setdefault(s, {"tp": 0, "fp": 0})["fp"] += 1
    result = {}
    for sig, d in out.items():
        total = d["tp"] + d["fp"]
        result[sig] = {
            **d,
            "precision": round(d["tp"] / total, 4) if total else None,
            "n": total,
        }
    return result


def _recommend_threshold(pos: List[Dict[str, Any]]) -> Optional[float]:
    """Find the score below which 80% of `pos` (wrong matches) fall.
    Raising the medium-band floor TO this value would have culled those FPs.
    """
    scores = [float(r.get("score") or 0.0) for r in pos if r.get("score") is not None]
    if len(scores) < 30:
        return None
    scores.sort()
    p80 = scores[int(0.80 * len(scores))]
    # Cap at 1.30 so we don't push the band higher than the existing top.
    return round(min(p80, 1.30), 3)


async def _write_csv(rows: List[Dict[str, Any]], path: str) -> None:
    if not rows:
        return
    keys = sorted({k for r in rows for k in r.keys()})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in keys})
    log.info("Wrote %s (%d rows)", path, len(rows))


async def main(apply_change: bool = False) -> None:
    db = await _get_db()
    sizes = await _check_sample_size(db)
    if sizes["feedback"] < MIN_FEEDBACK or sizes["audit"] < MIN_AUDIT:
        log.warning(
            "Sample below floor (need feedback>=%d, audit>=%d). Refusing to tune.",
            MIN_FEEDBACK, MIN_AUDIT,
        )
        return

    log.info("Loading wrong-match audit pairs …")
    wrong = await _load_wrong_match_pairs(db)
    log.info("Loaded %d wrong-match pairs", len(wrong))

    log.info("Sampling clean positives …")
    clean = await _load_positives(db, limit=5000)
    log.info("Loaded %d clean positives", len(clean))

    sig_report = _signal_precision(clean, wrong)
    log.info("=== Signal precision (TP/(TP+FP)) ===")
    for sig in sorted(sig_report, key=lambda s: -(sig_report[s].get("precision") or 0)):
        d = sig_report[sig]
        log.info("  %-26s precision=%6s  TP=%4d  FP=%4d  n=%4d",
                 sig, d.get("precision"), d["tp"], d["fp"], d["n"])

    rec = _recommend_threshold(wrong)
    log.info("Recommended NEW medium-band floor: %s (was 0.85)", rec)

    await _write_csv(
        [
            {
                "candidate_id": r["candidate_id"],
                "score":        r.get("score"),
                "signals":      ",".join(r.get("matched_signals") or []),
                "match_type":   r.get("match_type"),
            }
            for r in wrong
        ],
        "/tmp/badge_threshold_wrong_matches.csv",
    )

    if apply_change and rec:
        await db.match_thresholds.update_one(
            {"key": "v2_medium_floor"},
            {
                "$set": {
                    "value": rec,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "source": "badge_threshold_autolabeler",
                    "sample_feedback": sizes["feedback"],
                    "sample_audit":    sizes["audit"],
                },
                "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()},
            },
            upsert=True,
        )
        log.info("Applied new threshold %s to match_thresholds.v2_medium_floor", rec)
    elif apply_change:
        log.warning("No recommendation produced — not applying anything.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write recommendation to match_thresholds")
    args = ap.parse_args()
    asyncio.run(main(apply_change=args.apply))
