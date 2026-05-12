"""
SEC-04 one-time cleanup — Feb 2026.

Bumps token_version + purges refresh tokens for every user whose
`is_active` is False. This force-logs-out any deactivated user that
was relying on a cached JWT / refresh token (e.g. Sarita whose
extension kept capturing under her name after offboarding).

Run from EC2:
    cd /home/ubuntu/vhc-platform/backend
    source venv/bin/activate
    python scripts/sec04_purge_deactivated_sessions.py

Safe to re-run — idempotent.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone


async def main() -> None:
    # Make backend/ importable when run from /app/backend/scripts/
    here = os.path.dirname(os.path.abspath(__file__))
    backend_root = os.path.dirname(here)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    from config import db, initialize_db  # noqa: WPS433 (lazy import — needs sys.path tweak first)
    initialize_db()

    deactivated_cursor = db.users.find(
        {"is_active": False},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "token_version": 1},
    )
    bumped = 0
    refresh_deleted = 0
    rows = []
    async for u in deactivated_cursor:
        uid = u["id"]
        await db.users.update_one(
            {"id": uid},
            {"$inc": {"token_version": 1},
             "$set": {"sec04_purged_at": datetime.now(timezone.utc).isoformat()}},
        )
        res = await db.refresh_tokens.delete_many({"user_id": uid})
        bumped += 1
        refresh_deleted += res.deleted_count
        rows.append(
            f"  - {u.get('name') or u.get('email') or uid:<35} "
            f"tv:{u.get('token_version', 0)}→{u.get('token_version', 0) + 1}  "
            f"refresh_tokens_removed:{res.deleted_count}"
        )

    print("SEC-04 cleanup complete")
    print(f"  users force-logged-out : {bumped}")
    print(f"  refresh tokens purged  : {refresh_deleted}")
    if rows:
        print("\nAffected users:")
        for r in rows:
            print(r)
    else:
        print("\nNo deactivated users found — nothing to do.")


if __name__ == "__main__":
    asyncio.run(main())
