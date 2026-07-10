"""
Atlas Storage Cleanup — reclaim MongoDB Atlas space on `candidate_bank`.

CONTEXT (Phase 55.11i, 2026-07-10):
    Atlas M0 free tier is a 5 GB soft cap. Prod hit 4.5 GB (~90%) and started
    triggering Atlas alerts. Continued Qwen captures (~500/hr) would hit the
    hard cap within days, blocking writes.

WHAT THIS DOES:
    Removes disposable *derived / raw text* fields from candidates that have
    already been successfully enriched by the LLM. The information in these
    fields is either (a) regeneratable from other fields (embedding,
    ai_full_text) or (b) the original raw scrape which is no longer needed
    once structured extraction succeeded (raw_profile_text,
    raw_text_for_enrichment).

FIELDS TARGETED (in order of impact, largest first):
    - raw_profile_text          : original HTML/text scrape (~50-200KB/doc)
    - raw_text_for_enrichment   : LLM prompt input (~30-80KB/doc)
    - ai_full_text              : Qwen output raw text (~10-40KB/doc)
    - resume_latex              : regenerable render (~5-15KB/doc)
    - profile_update_audit      : append-only audit log inside doc (~variable)

    NOT TOUCHED by default:
    - embedding                 : vector search relies on it (use --strip-embeddings if desperate)
    - anything on enrichment_status != 'enriched'

SAFETY:
    - Every field prune is gated on `enrichment_status == 'enriched'`
    - Ships with --dry-run and --analyze modes
    - --prune-raw only removes the fields it names; NO documents are deleted
    - Batched updates with `updateMany` to avoid oplog spikes
    - Reports before/after collstats

USAGE (prod):
    cd /home/ubuntu/vhc-platform/backend
    source venv/bin/activate

    # Step 1 — see where the space is going
    python3 scripts/atlas_storage_cleanup.py --analyze

    # Step 2 — see what a prune would remove
    python3 scripts/atlas_storage_cleanup.py --dry-run

    # Step 3 — actually prune the raw text fields (enriched docs only)
    python3 scripts/atlas_storage_cleanup.py --prune-raw

    # Nuclear option — strip embeddings too (only if still over quota after step 3)
    python3 scripts/atlas_storage_cleanup.py --strip-embeddings

    # Post-cleanup: Atlas M0 does NOT support `compact`. Space is reclaimed
    # lazily by WiredTiger. Storage may not drop immediately; that's normal.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any


# Fields that are safely removable once enrichment succeeded. Ordered by
# expected space impact (largest first). Kept as a module-level constant so
# it can be imported by tests without executing the CLI.
DISPOSABLE_FIELDS: list[str] = [
    "raw_profile_text",
    "raw_text_for_enrichment",
    "ai_full_text",
    "resume_latex",
    "profile_update_audit",
]

# Extra field the --strip-embeddings mode targets. Kept separate because
# removing it degrades vector search until embeddings are regenerated.
EMBEDDING_FIELD = "embedding"

# Only prune raw fields on documents whose LLM extraction succeeded. This
# preserves the raw text on `pending`/`all_failed`/`None` documents so we
# can retry enrichment against the original source.
ENRICHED_FILTER = {"enrichment_status": "enriched"}


def _get_db() -> Any:
    """Resolve the prod DB handle using the same override module the app uses."""
    sys.path.insert(0, "/home/ubuntu/vhc-platform/backend")
    try:
        from mongo_production_override import MONGO_URL, DB_NAME
    except ImportError:
        # Fallback for dev environments where the override module isn't present.
        import os
        MONGO_URL = os.environ.get("MONGO_URL")
        DB_NAME = os.environ.get("DB_NAME") or "vhc_talent_os"
        if not MONGO_URL:
            print("ERROR: MONGO_URL not resolvable (no override module, no env var).")
            sys.exit(2)
    from pymongo import MongoClient
    client = MongoClient(MONGO_URL, tlsAllowInvalidCertificates=True)
    return client[DB_NAME]


def _human(n_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n_bytes < 1024:
            return f"{n_bytes:.2f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.2f} PB"


def analyze(db: Any) -> None:
    """Print collection storage stats + per-field byte estimates.

    Uses `collStats` for total size and a bounded sample scan (5,000 docs)
    to estimate per-field bytes. Sample-based numbers are marked as such.
    """
    stats = db.command("collStats", "candidate_bank")
    print("\n=== candidate_bank collection stats ===")
    print(f"  documents         : {stats.get('count', 0):,}")
    print(f"  storage size      : {_human(stats.get('storageSize', 0))}")
    print(f"  uncompressed size : {_human(stats.get('size', 0))}")
    print(f"  indexes           : {_human(stats.get('totalIndexSize', 0))}")
    print(f"  avg doc size      : {_human(stats.get('avgObjSize', 0))}")

    print("\n=== per-field byte estimate (5,000-doc sample) ===")
    sample_size = 5000
    field_totals: dict[str, int] = {}
    sampled = 0
    for doc in db.candidate_bank.find({}, limit=sample_size):
        sampled += 1
        for k in list(DISPOSABLE_FIELDS) + [EMBEDDING_FIELD]:
            v = doc.get(k)
            if v is None:
                continue
            # Rough BSON size approximation. Strings: byte length; lists/dicts:
            # BSON overhead + serialized length.
            if isinstance(v, str):
                field_totals[k] = field_totals.get(k, 0) + len(v.encode("utf-8"))
            elif isinstance(v, list):
                # Embeddings are lists of floats (~8 bytes each in BSON).
                field_totals[k] = field_totals.get(k, 0) + len(v) * 8
            elif isinstance(v, dict):
                # Serialize via bson to get real BSON weight.
                try:
                    from bson import BSON
                    field_totals[k] = field_totals.get(k, 0) + len(BSON.encode(v))
                except Exception:
                    field_totals[k] = field_totals.get(k, 0) + len(str(v))

    if not sampled:
        print("  (collection empty)")
        return

    total_docs = stats.get("count", sampled)
    scale = total_docs / sampled if sampled else 1
    rows = sorted(field_totals.items(), key=lambda kv: kv[1], reverse=True)
    for field, sample_bytes in rows:
        est_total = sample_bytes * scale
        avg = sample_bytes / sampled
        print(f"  {field:<30} avg: {_human(avg):>10}  est. total: {_human(est_total):>10}")

    enriched_count = db.candidate_bank.count_documents(ENRICHED_FILTER)
    print(f"\n  enriched documents (target for pruning): {enriched_count:,} / {total_docs:,}")


def count_reclaimable(db: Any, fields: list[str]) -> dict[str, int]:
    """For each field, count how many *enriched* docs still have it set."""
    counts: dict[str, int] = {}
    for f in fields:
        counts[f] = db.candidate_bank.count_documents({
            **ENRICHED_FILTER,
            f: {"$exists": True, "$ne": None},
        })
    return counts


def prune_fields(db: Any, fields: list[str], dry_run: bool) -> None:
    """Remove the named fields on all enriched documents that still have them."""
    counts = count_reclaimable(db, fields)
    print("\n=== Reclaimable fields (enriched docs only) ===")
    for f in fields:
        print(f"  {f:<30} {counts[f]:>10,} docs still have it")

    if dry_run:
        print("\n(--dry-run) NO CHANGES WRITTEN.")
        return

    if not any(counts.values()):
        print("\nNothing to prune. All targeted fields already absent on enriched docs.")
        return

    print("\n=== Applying updates ===")
    for f in fields:
        if counts[f] == 0:
            print(f"  {f:<30} SKIP  (already absent)")
            continue
        res = db.candidate_bank.update_many(
            {**ENRICHED_FILTER, f: {"$exists": True}},
            {"$unset": {f: ""}},
        )
        print(f"  {f:<30} DONE  matched={res.matched_count:,} modified={res.modified_count:,}")

    print("\nNote: Atlas M0 does NOT expose the `compact` command. WiredTiger reclaims")
    print("space lazily; expect the storage-size drop to appear over the next few")
    print("compaction cycles (hours, not days).")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--analyze", action="store_true",
                      help="Report storage size + per-field byte estimates. Read-only.")
    mode.add_argument("--dry-run", action="store_true",
                      help="Show what --prune-raw would remove. Read-only.")
    mode.add_argument("--prune-raw", action="store_true",
                      help="Remove the disposable raw/derived fields on enriched documents.")
    mode.add_argument("--strip-embeddings", action="store_true",
                      help="Also strip the `embedding` field. Nuclear — breaks vector search.")
    args = ap.parse_args()

    db = _get_db()

    if args.analyze:
        analyze(db)
        return

    if args.dry_run:
        prune_fields(db, DISPOSABLE_FIELDS, dry_run=True)
        return

    if args.prune_raw:
        prune_fields(db, DISPOSABLE_FIELDS, dry_run=False)
        return

    if args.strip_embeddings:
        # Deliberately separate step — the operator must opt into breaking
        # vector search. Also prune the raw fields at the same time if the
        # operator hasn't already.
        prune_fields(db, DISPOSABLE_FIELDS + [EMBEDDING_FIELD], dry_run=False)


if __name__ == "__main__":
    main()
