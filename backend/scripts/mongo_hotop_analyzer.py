"""
MongoDB Hot Op Analyzer — find what's driving high CPU on Atlas.

Complements the Atlas UI Metrics/Profiler tabs with a shell-friendly view.
Reports:
    - Currently-running ops taking > 1s (likely COLLSCANs, aggregations)
    - Collection sizes so you know which are worth optimising
    - Any missing indexes on the hot fields we filter/sort by

USAGE (prod):
    cd /home/ubuntu/vhc-platform/backend && source venv/bin/activate
    python3 scripts/mongo_hotop_analyzer.py                 # one-shot
    python3 scripts/mongo_hotop_analyzer.py --watch         # refresh every 5s
    python3 scripts/mongo_hotop_analyzer.py --min-secs 5    # only ops > 5s

USAGE (dev container / preview):
    Set MONGO_URL + DB_NAME env vars, then run the same command.

Read-only. Never writes to Mongo. Safe to run against prod at any time.
"""
from __future__ import annotations
import argparse
import os
import sys
import time


def _get_db():
    """Resolve DB handle — prefer production override, fall back to env."""
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
    client = MongoClient(MONGO_URL, tlsAllowInvalidCertificates=True, serverSelectionTimeoutMS=8000)
    return client, client[DB_NAME]


def format_op(op: dict) -> str:
    ns = op.get("ns", "?")
    op_type = op.get("op", "?")
    secs = op.get("secs_running") or (op.get("microsecs_running", 0) / 1e6)
    cmd = op.get("command") or op.get("query") or {}
    cmd_str = str(cmd)[:180].replace("\n", " ")
    plan = op.get("planSummary", "")
    return f"  [{secs:>5.1f}s] {op_type:<8} {ns:<40} {plan:<20} {cmd_str}"


def show_hot_ops(client, min_secs: float) -> None:
    """List server-side operations running longer than min_secs."""
    # `admin.command('currentOp')` is the pymongo-supported entry point for
    # the currentOp diagnostic. NB: the older `db.current_op()` method was
    # removed from the Database class — do not resurrect it.
    micros = int(min_secs * 1e6)
    result = client.admin.command(
        "currentOp",
        {"$or": [
            {"secs_running": {"$gte": int(min_secs)}},
            {"microsecs_running": {"$gte": micros}},
        ]},
    )
    ops = result.get("inprog", []) or []
    # Filter out client/idle sessions AND replica-set heartbeats.
    # `hello`/`isMaster` commands sit for `maxAwaitTimeMS` waiting on the
    # server to detect a topology change — they look like slow ops but are
    # cheap keepalives. Excluding them removes ~90% of the noise.
    def _is_real_op(o: dict) -> bool:
        if not o.get("active", True):
            return False
        if o.get("op") in (None, "none"):
            return False
        cmd = o.get("command") or {}
        if isinstance(cmd, dict) and ("hello" in cmd or "isMaster" in cmd):
            return False
        ns = o.get("ns", "")
        if ns in ("admin.$cmd", "local.oplog.rs"):
            return False
        return True
    ops = [o for o in ops if _is_real_op(o)]

    # Server-side filter passed to `currentOp` as value is NOT honoured by
    # MongoDB (filter fields must be top-level siblings of `currentOp:1`).
    # Rather than rely on server-side filtering, enforce min_secs client-side
    # so `--min-secs 999` reliably shows "nothing long-running right now".
    def _op_secs(o: dict) -> float:
        return float(o.get("secs_running") or (o.get("microsecs_running", 0) / 1e6))
    ops = [o for o in ops if _op_secs(o) >= min_secs]

    print(f"=== In-flight ops running >= {min_secs}s ({len(ops)} found) ===")
    if not ops:
        print("  (nothing long-running right now)")
        return
    for op in sorted(ops, key=lambda o: o.get("secs_running", 0), reverse=True)[:15]:
        print(format_op(op))


def show_collection_sizes(db) -> None:
    """Enumerate the biggest collections + doc counts."""
    print("\n=== Collection sizes ===")
    coll_names = db.list_collection_names()
    rows = []
    for coll in coll_names:
        try:
            s = db.command("collStats", coll)
            rows.append({
                "name":    coll,
                "docs":    s.get("count", 0),
                "size_mb": s.get("storageSize", 0) / 1024 / 1024,
                "idx_mb":  s.get("totalIndexSize", 0) / 1024 / 1024,
            })
        except Exception:
            continue
    rows.sort(key=lambda r: r["size_mb"], reverse=True)
    print(f"  {'collection':<32} {'docs':>10}  {'storage':>10}  {'indexes':>10}")
    for r in rows[:12]:
        print(f"  {r['name']:<32} {r['docs']:>10,}  {r['size_mb']:>8.1f} MB  {r['idx_mb']:>8.1f} MB")


def show_missing_hot_indexes(db) -> None:
    """Warn if hot query paths lack an index."""
    print("\n=== Index sanity on hot filter fields ===")
    hot_fields = {
        "candidate_bank": [
            "email", "phone_normalized", "ai_enrichment_source",
            "enrichment_status", "created_at", "source",
        ],
        "users": ["email"],
        "login_attempts": ["email"],
        "candidate_search_history": ["user_id", "created_at"],
    }
    for coll, fields in hot_fields.items():
        try:
            indexes = list(db[coll].list_indexes())
            indexed = set()
            for idx in indexes:
                # Any prefix of a compound index counts
                keys = list(idx.get("key", {}).keys())
                if keys:
                    indexed.add(keys[0])
            missing = [f for f in fields if f not in indexed]
            if missing:
                print(f"  ⚠️  {coll:<30} missing on: {', '.join(missing)}")
            else:
                print(f"  ✅  {coll:<30} all hot fields indexed")
        except Exception as e:
            print(f"     {coll:<30} error: {e}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--min-secs", type=float, default=1.0,
                    help="Only show ops running at least this long (default 1s)")
    ap.add_argument("--watch", action="store_true",
                    help="Loop every 5s (Ctrl-C to exit) — useful during a CPU spike")
    args = ap.parse_args()

    client, db = _get_db()

    def run_once():
        show_hot_ops(client, args.min_secs)
        show_collection_sizes(db)
        show_missing_hot_indexes(db)

    if not args.watch:
        run_once()
        return

    try:
        while True:
            print("\033[2J\033[H", end="")  # clear screen
            print(f"[{time.strftime('%H:%M:%S')}]")
            run_once()
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
