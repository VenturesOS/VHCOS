"""Conservative write gate for extension recapture. No config import or writes.

Search suggestions are not permission to merge records. Only a compatible name
and two agreeing, unique contact identifiers may select an automatic update.
Rotating URLs, raw provider IDs and employment similarity are never write keys.
"""
from __future__ import annotations

import asyncio
import re

if __package__:
    from .identity_resolution import names_are_compatible
else:
    from identity_resolution import names_are_compatible


class CaptureIdentityLookupError(RuntimeError):
    """A failed identity lookup must be retried rather than treated as new."""


def capture_identity_filter(candidate: dict) -> dict:
    """Recheck the evidence at write time so a concurrent contact edit abstains."""
    return {"$and": [
        {"id": candidate["id"]},
        *[{field: {"$eq": candidate[field], "$exists": True}} if field in candidate else {field: {"$exists": False}}
          for field in ("name", "email", "phone", "phone_normalized")],
    ]}


def normalized_email(value):
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    if (len(value) > 254 or not re.fullmatch(r"[^\s@*]+@[^\s@*]+\.[^\s@*]+", value)
            or value.startswith(("noreply@", "support@", "donotreply@"))
            or value.endswith(("@naukri.com", "@example.com", "@test.com"))):
        return None
    return value


def normalized_phone(value):
    if not isinstance(value, str) or not re.fullmatch(r"[+()\d.\s-]+", value):
        return None
    digits = re.sub(r"\D", "", value)
    if digits.startswith("0091") and len(digits) == 14:
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if not 10 <= len(digits) <= 15 or len(set(digits)) < 3:
        return None
    # Other country codes retain their full digits; never match foreign
    # contacts by blindly taking the last ten digits.
    return digits


async def select_capture_candidate(db, profile: dict) -> dict | None:
    email, phone = normalized_email(profile.get("email")), normalized_phone(profile.get("phone"))
    if not email or not phone:
        return None
    phone_forms = {phone}
    if len(phone) == 10:
        phone_forms.update({"91" + phone, "0091" + phone})
    separator = r"[\s()+.\-]*"
    phone_pattern = r"^" + separator + "(?:" + "|".join(
        separator.join(re.escape(char) for char in item) for item in sorted(phone_forms)
    ) + ")" + separator + r"$"
    queries = [
        {"email": {"$regex": r"^\s*" + re.escape(email) + r"\s*$", "$options": "i"}},
        {"$or": [
            {"phone_normalized": {"$in": sorted(phone_forms)}},
            {"phone": {"$regex": phone_pattern}},
        ]},
    ]
    selected = []
    for query in queries:
        try:
            cursor = db.candidate_bank.find(query, {"_id": 0}).limit(2).max_time_ms(1500)
            rows = await asyncio.wait_for(cursor.to_list(2), timeout=2)
        except Exception:
            raise CaptureIdentityLookupError("Contact identity lookup unavailable") from None
        if len(rows) != 1 or not isinstance(rows[0].get("id"), str) or not rows[0]["id"]:
            return None
        selected.append(rows[0])
    # Both identifiers must point to the very same observed snapshot. A race
    # or shared/recycled identifier cannot choose an arbitrary first record.
    left, right = selected
    if left.get("id") != right.get("id"):
        return None
    if left != right:
        raise CaptureIdentityLookupError("Candidate changed during identity lookup")
    if (normalized_email(left.get("email")) != email
            or normalized_phone(left.get("phone_normalized") or left.get("phone")) != phone
            or (left.get("phone") and normalized_phone(left["phone"]) != phone)
            or not names_are_compatible(profile.get("name"), left.get("name"), require_multiple_tokens=True)):
        return None
    return left
