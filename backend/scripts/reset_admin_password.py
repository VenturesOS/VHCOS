"""
Admin Password Reset — Emergency Login Restoration
===================================================

Sets `password_hash` on a target user record to a fresh bcrypt hash. Handles
two failure modes we hit in prod (Phase 55.11j, 2026-07-10):

    1. Admin user's password_hash is empty ('' or missing) — no valid bcrypt
       verify possible → login endpoint returns 500 / 401.
    2. Admin's password was changed via a broken flow that never wrote the
       hash back.

Safety:
    - Requires --email AND either --password OR $ADMIN_RESET_PASSWORD env var
    - Refuses to run against an email that doesn't exist (won't accidentally
      create a new admin)
    - Prints ONLY the user's role + hash-prefix, never the plaintext
    - Idempotent — re-running produces a NEW bcrypt hash (they're salted)
      but the login outcome is stable

Usage (prod):
    cd /home/ubuntu/vhc-platform/backend && source venv/bin/activate
    python3 scripts/reset_admin_password.py --email admin@vhc.in --password 'VhcAdmin@2024'
    sudo systemctl restart vhc-backend

Or non-interactive:
    ADMIN_RESET_PASSWORD='...' python3 scripts/reset_admin_password.py --email admin@vhc.in
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime, timezone


def _get_db():
    """Resolve the DB handle using the production override module."""
    sys.path.insert(0, "/home/ubuntu/vhc-platform/backend")
    sys.path.insert(0, "/app/backend")
    try:
        from mongo_production_override import MONGO_URL, DB_NAME
    except ImportError:
        MONGO_URL = os.environ.get("MONGO_URL")
        DB_NAME = os.environ.get("DB_NAME") or "vhc_talent_os"
        if not MONGO_URL:
            print("ERROR: no MONGO_URL (checked override module + env)")
            sys.exit(2)
    from pymongo import MongoClient
    return MongoClient(MONGO_URL, tlsAllowInvalidCertificates=True, serverSelectionTimeoutMS=8000)[DB_NAME]


def reset_password(db, email: str, password: str) -> dict:
    """Reset password_hash for the target user. Returns a status dict.

    Never writes a new user record — if the email isn't found we bail out
    so a typo doesn't spawn a rogue admin.
    """
    import bcrypt

    user = db.users.find_one({"email": email})
    if not user:
        return {"ok": False, "reason": "user_not_found", "email": email}

    salt = bcrypt.gensalt(rounds=12)
    new_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    # Write to both field names the codebase has used historically so any
    # login route wins regardless of which field it consults.
    update = {
        "password_hash":   new_hash,
        "hashed_password": new_hash,
        "updated_at":      datetime.now(timezone.utc).isoformat(),
        "is_active":       True,   # unlock in case it was disabled
    }
    res = db.users.update_one({"email": email}, {"$set": update})

    verify = bcrypt.checkpw(password.encode("utf-8"), new_hash.encode("utf-8"))

    return {
        "ok":            True,
        "email":         email,
        "role":          user.get("role"),
        "hash_prefix":   new_hash[:7],
        "hash_len":      len(new_hash),
        "modified":      res.modified_count,
        "bcrypt_verify": verify,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--email", required=True, help="Target user email (must already exist)")
    ap.add_argument("--password", default=os.environ.get("ADMIN_RESET_PASSWORD"),
                    help="New plaintext password (or set $ADMIN_RESET_PASSWORD)")
    args = ap.parse_args()

    if not args.password:
        print("ERROR: pass --password 'value' or set $ADMIN_RESET_PASSWORD")
        sys.exit(1)

    db = _get_db()
    result = reset_password(db, args.email, args.password)

    if not result["ok"]:
        print(f"❌ {result['reason']}: {result['email']}")
        sys.exit(3)

    print(f"✅ Password reset for {result['email']}")
    print(f"   role         : {result['role']}")
    print(f"   hash_prefix  : {result['hash_prefix']}... ({result['hash_len']} chars)")
    print(f"   modified     : {result['modified']}")
    print(f"   bcrypt_verify: {result['bcrypt_verify']}")
    print("\nNow restart the backend so it picks up the update:")
    print("   sudo systemctl restart vhc-backend")


if __name__ == "__main__":
    main()
