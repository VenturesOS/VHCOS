"""
Admin user ops — Phase 55.4 (May 2026)

Single-purpose helper script for the user-lifecycle changes shipped in
`routes/admin.py`:

  1. `--archive-deactivated`
     Backfill: for every already-deactivated user whose email is still
     the original one (no `_deact_` prefix), rename their email to the
     archived form. Frees those emails for re-use.

  2. `--deactivate <email>`
     Soft-deletes an active user (sets is_active=False, archives email,
     bumps token_version, purges refresh tokens).

  3. `--create <email> <name> <password> [--role recruiter]`
     Creates a brand-new user account. Errors if the email is already
     in use by an ACTIVE record (a deactivated record's old email is
     archived so does NOT collide).

  4. `--reset-password <email> <new-password>`
     Resets an existing user's password and re-activates them in one shot.

Usage (on EC2):
    cd /home/ubuntu/vhc-platform/backend && source venv/bin/activate

    # 1. one-time backfill — frees ~30 already-deactivated emails
    python scripts/admin_user_ops.py --archive-deactivated --apply

    # 2. deactivate Ronak so hr6@vhc.in becomes free
    python scripts/admin_user_ops.py --deactivate hr6@vhc.in --apply

    # 3. create Sachin on hr12 (Srishti's hr12 was archived in step 1)
    python scripts/admin_user_ops.py --create hr12@vhc.in 'Sachin' '12345678' --apply

    # 4. create Diya on hr6 (Ronak's hr6 was archived in step 2)
    python scripts/admin_user_ops.py --create hr6@vhc.in  'Diya'   '12345678' --apply

All commands default to DRY-RUN — pass `--apply` to commit.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional


def _bootstrap() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    backend_root = os.path.dirname(here)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)


_bootstrap()

from config import db, initialize_db  # noqa: E402
from utils.auth import hash_password  # noqa: E402


def _archive_email(email: str) -> str:
    """Same archive shape as routes/admin._archive_email — kept in sync."""
    if not email or "@" not in email:
        return email or ""
    local, _, domain = email.partition("@")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"_deact_{ts}_{local}@{domain}"


def _normalize(e: str) -> str:
    return (e or "").strip().lower()


# ─────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────
async def cmd_archive_deactivated(apply: bool) -> int:
    cursor = db.users.find(
        {
            "is_active": False,
            "email": {"$exists": True, "$ne": None, "$not": {"$regex": "^_deact_"}},
        },
        {"_id": 0, "id": 1, "email": 1, "name": 1},
    )
    rows = await cursor.to_list(length=10_000)
    print(f"Found {len(rows)} deactivated user(s) with un-archived emails")
    if not rows:
        return 0
    n = 0
    for r in rows:
        old = r["email"]
        new = _archive_email(old)
        marker = "[APPLY]" if apply else "[DRY]"
        print(f"  {marker} {r.get('name'):<28} {old:<35} → {new}")
        if apply:
            await db.users.update_one(
                {"id": r["id"]},
                {"$set": {"email": new, "original_email": old}},
            )
            n += 1
    if apply:
        print(f"\nArchived {n} email(s).")
    else:
        print("\nDry run — re-run with --apply to commit.")
    return 0


async def cmd_deactivate(email: str, apply: bool) -> int:
    email = _normalize(email)
    user = await db.users.find_one(
        {"email": email}, {"_id": 0, "id": 1, "name": 1, "role": 1, "is_active": 1}
    )
    if not user:
        print(f"ERROR: no user with email {email!r}")
        return 1
    if not user.get("is_active", True):
        print(f"User {email!r} is already inactive — nothing to do.")
        return 0
    archived = _archive_email(email)
    print(f"DEACTIVATE  {user.get('name')!r} ({user.get('role')})  {email}  →  {archived}")
    if not apply:
        print("Dry run — re-run with --apply to commit.")
        return 0
    await db.users.update_one(
        {"id": user["id"]},
        {
            "$set": {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "email": archived,
                "original_email": email,
            },
            "$inc": {"token_version": 1},
        },
    )
    # Invalidate sessions
    try:
        await db.refresh_tokens.delete_many({"user_id": user["id"]})
    except Exception:
        pass
    print(f"OK — {email} is now free for re-use.")
    return 0


async def cmd_create(
    email: str,
    name: str,
    password: str,
    role: str,
    apply: bool,
) -> int:
    email = _normalize(email)
    # Collision check: only ACTIVE original-email records block creation.
    # Archived deactivated emails carry the `_deact_` prefix and are ignored.
    existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "is_active": 1, "name": 1})
    if existing:
        if existing.get("is_active", True):
            print(
                f"ERROR: email {email!r} is currently used by an ACTIVE user "
                f"({existing.get('name')}). Deactivate first."
            )
            return 1
        # Should not happen post-backfill, but guard anyway.
        print(
            f"ERROR: email {email!r} is on a deactivated record but NOT archived. "
            f"Run `--archive-deactivated --apply` first."
        )
        return 1

    now = datetime.now(timezone.utc).isoformat()
    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id,
        "email": email,
        "name": name,
        "role": role,
        "password": hash_password(password),
        "phone": None,
        "company_id": "",
        "is_active": True,
        "requires_password_reset": False,
        "token_version": 0,
        "created_at": now,
        "created_by": "admin_user_ops_script",
    }
    print(f"CREATE  role={role}  name={name!r}  email={email}  id={user_id}")
    if not apply:
        print("Dry run — re-run with --apply to commit.")
        return 0
    await db.users.insert_one(doc)
    print(f"OK — created {role} account {email} ({name}).")
    return 0


async def cmd_reset_password(email: str, new_password: str, apply: bool) -> int:
    email = _normalize(email)
    user = await db.users.find_one(
        {"email": email}, {"_id": 0, "id": 1, "name": 1, "is_active": 1}
    )
    if not user:
        print(f"ERROR: no user with email {email!r}")
        return 1
    print(
        f"RESET password for {user.get('name')!r} ({email}) "
        f"+ reactivate={not user.get('is_active', True)}"
    )
    if not apply:
        print("Dry run — re-run with --apply to commit.")
        return 0
    await db.users.update_one(
        {"id": user["id"]},
        {
            "$set": {
                "password": hash_password(new_password),
                "is_active": True,
                "requires_password_reset": False,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "$inc": {"token_version": 1},
        },
    )
    print(f"OK — password reset and account active for {email}.")
    return 0


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────
async def cmd_migrate_email(old_email: str, new_email: str, apply: bool) -> int:
    """Rename a user's primary email (keeps user_id, role, password, all FK
    records). Useful when shifting an active recruiter onto a different slot.

    Both emails are normalized. If `new_email` is currently held by ANOTHER
    user (active or inactive), the command refuses unless that account is
    deactivated and its email is already archived.
    """
    old_email = _normalize(old_email)
    new_email = _normalize(new_email)
    if old_email == new_email:
        print(f"ERROR: old_email and new_email are identical ({old_email})")
        return 1

    user = await db.users.find_one(
        {"email": old_email},
        {"_id": 0, "id": 1, "name": 1, "role": 1, "is_active": 1},
    )
    if not user:
        print(f"ERROR: no user with email {old_email!r}")
        return 1

    # Block if the destination email is held by anyone else
    collision = await db.users.find_one(
        {"email": new_email, "id": {"$ne": user["id"]}},
        {"_id": 0, "id": 1, "name": 1, "is_active": 1},
    )
    if collision:
        if collision.get("is_active", True):
            print(
                f"ERROR: destination {new_email!r} is held by ACTIVE user "
                f"{collision.get('name')!r}. Deactivate first."
            )
        else:
            print(
                f"ERROR: destination {new_email!r} is held by INACTIVE user "
                f"{collision.get('name')!r} (email not archived yet). "
                f"Run `--archive-deactivated --apply` first."
            )
        return 1

    print(
        f"MIGRATE  {user.get('name')!r} ({user.get('role')})  "
        f"{old_email}  →  {new_email}   "
        f"[active={user.get('is_active', True)}]"
    )
    if not apply:
        print("Dry run — re-run with --apply to commit.")
        return 0

    await db.users.update_one(
        {"id": user["id"]},
        {
            "$set": {
                "email": new_email,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "$push": {
                "email_history": {
                    "from": old_email,
                    "to": new_email,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "by": "admin_user_ops_script",
                }
            },
        },
    )
    print(f"OK — user {user.get('name')!r} now logs in with {new_email}.")
    print(f"  (all {user.get('role')} records stay attached via user_id; no FK rewrites needed)")
    return 0


async def main(args: argparse.Namespace) -> int:
    initialize_db()

    if args.archive_deactivated:
        return await cmd_archive_deactivated(args.apply)
    if args.deactivate:
        return await cmd_deactivate(args.deactivate, args.apply)
    if args.create:
        email, name, password = args.create
        return await cmd_create(email, name, password, args.role, args.apply)
    if args.reset_password:
        email, new_password = args.reset_password
        return await cmd_reset_password(email, new_password, args.apply)
    if args.migrate_email:
        old_email, new_email = args.migrate_email
        return await cmd_migrate_email(old_email, new_email, args.apply)
    print("No command. See --help.")
    return 2


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Admin user ops")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--archive-deactivated",
        action="store_true",
        help="Backfill: archive emails of all already-deactivated users",
    )
    g.add_argument(
        "--deactivate",
        metavar="EMAIL",
        help="Soft-delete an active user and archive their email",
    )
    g.add_argument(
        "--create",
        nargs=3,
        metavar=("EMAIL", "NAME", "PASSWORD"),
        help="Create a new active user account",
    )
    g.add_argument(
        "--reset-password",
        nargs=2,
        metavar=("EMAIL", "NEW_PASSWORD"),
        help="Reset password and reactivate a user",
    )
    g.add_argument(
        "--migrate-email",
        nargs=2,
        metavar=("OLD_EMAIL", "NEW_EMAIL"),
        help="Rename a user's email (keeps user_id and all FK records)",
    )
    p.add_argument(
        "--role",
        default="recruiter",
        choices=["admin", "employer", "recruiter", "candidate"],
        help="Role for --create (default: recruiter)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform the operation (default: dry-run)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main(args)))
