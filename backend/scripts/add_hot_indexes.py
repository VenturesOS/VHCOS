"""
Atlas Hot-Index Backfill — adds missing indexes on `candidate_bank`.

Root cause of the 75% CPU spike (Phase 55.11k): the API filters and dedupe
aggregation constantly touch `ai_enrichment_source` and `enrichment_status`,
neither of which had an index. Every query = full COLLSCAN over 148k docs.

Adds two indexes (background=True so no lock during creation):
    - {ai_enrichment_source: 1}   partial: field exists
    - {enrichment_status:    1}   partial: field exists

Also adds a TTL policy on `api_metrics` (330k+ rows and growing forever).
    - {created_at: 1}  expireAfterSeconds = 30 days

USAGE (prod):
    cd /home/ubuntu/vhc-platform/backend && source venv/bin/activate
    python3 scripts/add_hot_indexes.py --dry-run     # preview
    python3 scripts/add_hot_indexes.py               # apply

SAFETY:
    - --dry-run inspects only, no writes
    - createIndex is idempotent — safe to re-run
    - background=True → no collection lock
    - Atlas will show a "Creating index" spinner in the UI while it runs
"""
from __future__ import annotations
import argparse
import os
import sys


HOT_INDEXES: list[dict] = [
    {
        "collection": "candidate_bank",
        "keys":       [("ai_enrichment_source", 1)],
        "partial":    {"ai_enrichment_source": {"$exists": True}},
        "name":       "ai_enrichment_source_1",
    },
    {
        "collection": "candidate_bank",
        "keys":       [("enrichment_status", 1)],
        "partial":    {"enrichment_status": {"$exists": True}},
        "name":       "enrichment_status_1",
    },
]

TTL_INDEXES: list[dict] = [
    # NOTE: api_metrics already has a TTL on `timestamp` (7 days) created by
    # middleware/api_metrics.py::ensure_indexes(). We intentionally do NOT
    # add another TTL here. If you need a longer/shorter retention window,
    # edit the middleware — that's the single source of truth.
]

# One-off cleanup targets: named indexes that earlier runs of this script
# created but which turned out to be wrong (see TTL note above). Idempotent.
STALE_INDEXES_TO_DROP: list[dict] = [
    {"collection": "api_metrics", "name": "api_metrics_ttl_30d"},
]


def _get_db():
    sys.path.insert(0, "/home/ubuntu/vhc-platform/backend")
    sys.path.insert(0, "/app/backend")
    try:
        from mongo_production_override import MONGO_URL, DB_NAME  # type: ignore
    except ImportError:
        MONGO_URL = os.environ.get("MONGO_URL")
        DB_NAME = os.environ.get("DB_NAME") or "vhc_talent_os"
        if not MONGO_URL:
            print("ERROR: MONGO_URL not resolvable")
            sys.exit(2)
    from pymongo import MongoClient
    return MongoClient(MONGO_URL, tlsAllowInvalidCertificates=True, serverSelectionTimeoutMS=8000)[DB_NAME]


def existing_index_names(db, coll: str) -> set[str]:
    try:
        return {i.get("name") for i in db[coll].list_indexes()}
    except Exception:
        return set()


def apply_hot_indexes(db, dry_run: bool) -> None:
    print("=== Hot-path indexes on candidate_bank ===")
    for spec in HOT_INDEXES:
        coll = spec["collection"]
        existing = existing_index_names(db, coll)
        if spec["name"] in existing:
            print(f"  ✓ SKIP {coll}.{spec['name']} — already exists")
            continue
        if dry_run:
            print(f"  DRY  would create {coll}.{spec['name']} keys={spec['keys']}")
            continue
        db[coll].create_index(
            spec["keys"],
            name=spec["name"],
            background=True,
            partialFilterExpression=spec["partial"],
        )
        print(f"  ✅ CREATED {coll}.{spec['name']}")


def apply_ttl_indexes(db, dry_run: bool) -> None:
    print("\n=== TTL indexes ===")
    if not TTL_INDEXES:
        print("  (none configured — TTL for api_metrics lives in middleware/api_metrics.py)")
    for spec in TTL_INDEXES:
        coll = spec["collection"]
        existing = existing_index_names(db, coll)
        if spec["name"] in existing:
            print(f"  ✓ SKIP {coll}.{spec['name']} — already exists")
            continue
        if dry_run:
            print(f"  DRY  would create {coll}.{spec['name']} expireAfterSeconds={spec['expire_seconds']}")
            continue
        db[coll].create_index(
            spec["keys"],
            name=spec["name"],
            background=True,
            expireAfterSeconds=spec["expire_seconds"],
        )
        print(f"  ✅ CREATED {coll}.{spec['name']} (docs older than {spec['expire_seconds']//86400}d will drop)")


def drop_stale_indexes(db, dry_run: bool) -> None:
    """Drop indexes that older versions of this script created by mistake."""
    print("\n=== Stale index cleanup ===")
    if not STALE_INDEXES_TO_DROP:
        return
    for spec in STALE_INDEXES_TO_DROP:
        coll = spec["collection"]
        name = spec["name"]
        if name not in existing_index_names(db, coll):
            continue
        if dry_run:
            print(f"  DRY  would drop {coll}.{name}")
            continue
        db[coll].drop_index(name)
        print(f"  🗑️  DROPPED {coll}.{name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="Preview without creating")
    args = ap.parse_args()

    db = _get_db()
    apply_hot_indexes(db, args.dry_run)
    apply_ttl_indexes(db, args.dry_run)
    drop_stale_indexes(db, args.dry_run)
    print("\nDone. Atlas CPU should drop within minutes as new queries use the indexes.")


if __name__ == "__main__":
    main()
