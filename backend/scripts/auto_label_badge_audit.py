#!/usr/bin/env python3
"""Auto-label badge_audit cards — field-based adjudication (Phase 57.2 v2).

Naukri search-card ids and capture-time profile ids live in DIFFERENT
namespaces (cards: 10-digit numeric; captures: `naukri_<128-hex>`), so id
equality can NOT be used as ground truth (this is also why
`n_via_naukri_id == 0` on every audit — the fast path never fires).

Instead we adjudicate the way a human labeler would — strict name-token
comparison plus independent field corroboration:

  exists=true:
    * every given-name token must have a counterpart (ratio ≥ 0.84 or
      initial-match) on the other side → tokens AGREE
    * any token whose best counterpart scores < 0.70 → tokens CONTRADICT
    * AGREE                         → label 'correct'
    * CONTRADICT                    → label 'incorrect'  (wrong person)
    * in-between                    → left unlabeled (needs human eyes)
  exists=false:
    * bank has a candidate with the SAME normalized full name AND same
      city or employer → label 'incorrect' (missed badge)
    * else → label 'correct' (true negative)

Usage:
  python scripts/auto_label_badge_audit.py                      # dry-run
  python scripts/auto_label_badge_audit.py --write              # persist labels
  python scripts/auto_label_badge_audit.py --since 2026-06-12   # fresh audits only
                                                                # (post-fix recall re-benchmark)
"""
import asyncio
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

WRITE = "--write" in sys.argv
SINCE = None
if "--since" in sys.argv:
    _i = sys.argv.index("--since")
    if _i + 1 < len(sys.argv):
        SINCE = sys.argv[_i + 1]  # ISO date prefix, e.g. 2026-06-12

_HONORIFICS = {"mr", "mrs", "ms", "dr", "prof", "shri", "smt"}


def _toks(name: str) -> list:
    s = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    return [t for t in s.split() if t and t not in _HONORIFICS]


def _tok_match(a: str, b: str) -> float:
    """1.0 initial-match, else SequenceMatcher ratio."""
    if a == b:
        return 1.0
    if len(a) == 1 or len(b) == 1:
        return 1.0 if a[0] == b[0] else 0.0
    return SequenceMatcher(None, a, b).ratio()


def adjudicate_names(card_name: str, cand_name: str) -> str:
    """'agree' | 'contradict' | 'uncertain' via token-level comparison."""
    ta, tb = _toks(card_name), _toks(cand_name)
    if not ta or not tb:
        return "uncertain"
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    worst = 1.0
    for t in short:
        best = max(_tok_match(t, u) for u in long_)
        worst = min(worst, best)
    if worst >= 0.84:
        return "agree"
    if worst < 0.70:
        return "contradict"
    return "uncertain"


def _norm(s) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", str(s or "").lower())).strip()


async def main() -> None:
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]

    if SINCE:
        since_dt = datetime.fromisoformat(SINCE).replace(tzinfo=timezone.utc)
        query = {"ts": {"$gte": since_dt}}
    else:
        query = {}
    audits = await db.badge_audit.find(query).to_list(5000)
    print(f"Analyzing {len(audits)} audits" + (f" since {SINCE}" if SINCE else " (all time)"))

    # Batch-prefetch bank docs for ALL miss-check names (one $in query —
    # per-name find_one round-trips timed out cross-region)
    miss_names = {
        _norm(c.get("card_name"))
        for a in audits for c in (a.get("cards") or [])
        if not c.get("exists") and _norm(c.get("card_name"))
    }
    miss_cache: dict = {n: None for n in miss_names}
    if miss_names:
        async for d in db.candidate_bank.find(
            {"name_lower": {"$in": list(miss_names)}},
            {"_id": 0, "id": 1, "name": 1, "name_lower": 1, "location": 1, "current_employer": 1},
        ):
            miss_cache.setdefault(d.get("name_lower"), None)
            if miss_cache.get(d.get("name_lower")) is None:
                miss_cache[d.get("name_lower")] = d

    stats = Counter()
    fp_examples, miss_examples, uncertain_examples = [], [], []
    seen_dedupe: dict = {}
    now_iso = datetime.now(timezone.utc).isoformat()
    bulk_updates = 0

    for a in audits:
        cards = a.get("cards") or []
        changed = False
        for c in cards:
            exists = bool(c.get("exists"))
            card_name = c.get("card_name") or ""
            key = _norm(card_name)
            if not key:
                stats["no_name"] += 1
                continue
            label = notes = None

            if exists:
                verdict = adjudicate_names(card_name, c.get("matched_candidate_name") or "")
                # Independent corroboration for the borderline zone
                loc_eq = _norm(c.get("card_location")) and _norm(c.get("card_location")) == _norm(c.get("matched_candidate_location"))
                emp_eq = _norm(c.get("card_employer")) and _norm(c.get("card_employer")) == _norm(c.get("matched_candidate_employer"))
                if verdict == "agree":
                    label, notes = "correct", "auto: name tokens agree"
                    stats["TP"] += 1
                elif verdict == "contradict":
                    label, notes = "incorrect", "auto: name token contradiction (wrong person)"
                    stats["FP"] += 1
                    if len(fp_examples) < 10:
                        fp_examples.append(c)
                elif loc_eq or emp_eq:
                    label, notes = "correct", "auto: borderline name + matching location/employer"
                    stats["TP_borderline"] += 1
                else:
                    stats["uncertain"] += 1
                    if len(uncertain_examples) < 8:
                        uncertain_examples.append(c)
            else:
                # Missed-badge check: exact-name candidate with same city/employer
                bank = miss_cache.get(key)
                if bank and (
                    (_norm(c.get("card_location")) and _norm(c.get("card_location")) == _norm(bank.get("location")))
                    or (_norm(c.get("card_employer")) and _norm(c.get("card_employer")) == _norm(bank.get("current_employer")))
                ):
                    label, notes = "incorrect", f"auto: missed — bank candidate {bank['id'][:8]} has same name+city/employer"
                    stats["FN"] += 1
                    if len(miss_examples) < 10:
                        miss_examples.append({**c, "_bank": bank})
                else:
                    label, notes = "correct", "auto: no same-name candidate corroborated in bank"
                    stats["TN"] += 1

            if label:
                seen_dedupe[key] = label if seen_dedupe.get(key) != "incorrect" else "incorrect"
                if WRITE and not c.get("label"):
                    c["label"] = label
                    c["label_notes"] = notes
                    c["labeled_by"] = "auto-groundtruth"
                    c["labeled_at"] = now_iso
                    changed = True

        if WRITE and changed:
            await db.badge_audit.update_one({"_id": a["_id"]}, {"$set": {"cards": cards}})
            bulk_updates += 1

    tp = stats["TP"] + stats["TP_borderline"]
    fp, fn = stats["FP"], stats["FN"]
    print("=== CARD-LEVEL COUNTS (page rescans included) ===")
    for k in ("TP", "TP_borderline", "FP", "FN", "TN", "uncertain", "no_name"):
        print(f"  {k:15s} {stats[k]}")
    if tp + fp:
        print(f"\n  PRECISION: {tp/(tp+fp):.3f}   (badge shown → right person)")
    if tp + fn:
        print(f"  RECALL:    {tp/(tp+fn):.3f}   (known-in-bank → badge shown)")

    dd = Counter(seen_dedupe.values())
    print(f"\n=== DEDUPED BY NAME ({len(seen_dedupe)} unique) === correct: {dd['correct']}  incorrect: {dd['incorrect']}")

    print("\n=== FALSE POSITIVES (wrong person badged) ===")
    for c in fp_examples:
        print(f"  '{c.get('card_name')}' ({c.get('card_location')}) → '{c.get('matched_candidate_name')}' "
              f"({c.get('matched_candidate_location')}) score={c.get('match_score')} sig={c.get('matched_signals')}")
    print("\n=== MISSED BADGES (should have badged) ===")
    for c in miss_examples:
        print(f"  '{c.get('card_name')}' ({c.get('card_location')}) — in bank as '{c['_bank'].get('name')}' ({c['_bank'].get('location')})")
    print("\n=== UNCERTAIN (left for human) ===")
    for c in uncertain_examples:
        print(f"  '{c.get('card_name')}' → '{c.get('matched_candidate_name')}' score={c.get('match_score')}")

    print(f"\n{'Labels persisted to ' + str(bulk_updates) + ' audit documents.' if WRITE else 'DRY RUN — re-run with --write to persist labels.'}")
    cli.close()


if __name__ == "__main__":
    asyncio.run(main())
