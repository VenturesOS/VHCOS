"""
Candidate Auto-Merge & Dedup Service
-------------------------------------
Centralized logic for:
1. Recruiter contact filtering (strip recruiter's own email/phone from captures)
2. Fuzzy 2/3 match detection (name + email + phone)
3. Smart merge (keep best data from both profiles)
"""
import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from config import db

logger = logging.getLogger(__name__)

# ── Sanity limits ──
CTC_MAX = 200_000_000  # ₹20 Crore — anything above is a false positive


def normalize_phone(phone: str) -> str:
    """Strip to last 10 digits for comparison."""
    if not phone:
        return ""
    digits = re.sub(r'\D', '', str(phone))
    return digits[-10:] if len(digits) >= 10 else digits


def normalize_name(name: str) -> str:
    """Lowercase, strip extra spaces, remove titles."""
    if not name:
        return ""
    name = re.sub(r'\b(mr|mrs|ms|dr|prof|shri|smt)\.?\s*', '', name.lower().strip(), flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', name).strip()


def names_similar(name1: str, name2: str, threshold: float = 0.75) -> bool:
    """Check if two names are similar enough (SequenceMatcher ratio)."""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    if not n1 or not n2:
        return False
    return SequenceMatcher(None, n1, n2).ratio() >= threshold


def filter_recruiter_contacts(email: str, phone: str, recruiter_email: str, recruiter_phone: str, candidate_name: str) -> tuple:
    """
    Strip captured email/phone if they match the capturing recruiter's own credentials.
    Returns (cleaned_email, cleaned_phone).
    """
    cleaned_email = email
    cleaned_phone = phone

    if email and recruiter_email:
        if email.lower().strip() == recruiter_email.lower().strip():
            logger.warning(f"[Dedup] Stripped recruiter email '{email}' from capture of '{candidate_name}'")
            cleaned_email = None

    if phone and recruiter_phone:
        cap_phone = normalize_phone(phone)
        rec_phone = normalize_phone(recruiter_phone)
        if cap_phone and rec_phone and cap_phone == rec_phone:
            logger.warning(f"[Dedup] Stripped recruiter phone '{phone}' from capture of '{candidate_name}'")
            cleaned_phone = None

    return cleaned_email, cleaned_phone


async def find_merge_candidate(name: str, email: str, phone: str, exclude_id: str = None) -> dict:
    """
    Search for an existing candidate that matches 2/3 of (name, email, phone).
    Returns the best match or None.
    """
    if not name:
        return None

    candidates = []

    # Search by email
    if email:
        email_match = await db.candidate_bank.find_one(
            {"email": email.lower().strip()},
            {"_id": 0}
        )
        if email_match and (not exclude_id or email_match.get("id") != exclude_id):
            candidates.append(("email", email_match))

    # Search by phone
    if phone:
        phone_norm = normalize_phone(phone)
        if phone_norm and len(phone_norm) >= 10:
            phone_match = await db.candidate_bank.find_one(
                {"phone_normalized": phone_norm},
                {"_id": 0}
            )
            if phone_match and (not exclude_id or phone_match.get("id") != exclude_id):
                # Avoid duplicating candidates already found by email
                if not any(c[1].get("id") == phone_match.get("id") for c in candidates):
                    candidates.append(("phone", phone_match))

    # Search by name (fuzzy)
    if not candidates:
        # Only search by name if we have email or phone to cross-validate
        if email or phone:
            name_norm = normalize_name(name)
            if len(name_norm) >= 3:
                # Search with regex for partial name match
                name_parts = name_norm.split()
                if len(name_parts) >= 2:
                    # Use first and last name for search
                    name_regex = re.compile(
                        f".*{re.escape(name_parts[0])}.*{re.escape(name_parts[-1])}.*",
                        re.IGNORECASE
                    )
                    cursor = db.candidate_bank.find(
                        {"name": name_regex},
                        {"_id": 0}
                    ).limit(10)
                    async for doc in cursor:
                        if exclude_id and doc.get("id") == exclude_id:
                            continue
                        candidates.append(("name", doc))

    # Score each candidate: how many of the 3 identifiers match?
    best_match = None
    best_score = 0

    for source, candidate in candidates:
        score = 0

        # Check name similarity
        if names_similar(name, candidate.get("name", "")):
            score += 1

        # Check email match
        if email and candidate.get("email"):
            if email.lower().strip() == candidate["email"].lower().strip():
                score += 1

        # Check phone match
        if phone and candidate.get("phone"):
            if normalize_phone(phone) == normalize_phone(candidate["phone"]):
                score += 1
            elif candidate.get("phone_normalized") and normalize_phone(phone) == candidate["phone_normalized"]:
                score += 1

        if score >= 2 and score > best_score:
            best_score = score
            best_match = candidate

    if best_match:
        logger.warning(
            f"[AutoMerge] Found match: '{name}' → '{best_match.get('name')}' "
            f"(id={best_match.get('id', '?')[:12]}, score={best_score}/3)"
        )

    return best_match


def merge_profiles(existing: dict, incoming: dict) -> dict:
    """
    Merge incoming profile data into existing profile.
    Returns a dict of $set updates for MongoDB.

    Merge rules:
    - CTC: keep higher value IF it passes sanity (≤ ₹20 Cr)
    - Skills: union of both sets
    - Work experience: keep the longer list
    - Education: keep the longer list
    - Other fields: keep non-empty, prefer incoming if both exist
    """
    updates = {}
    now = datetime.now(timezone.utc).isoformat()

    # ── Simple string/number fields: fill gaps, prefer incoming for non-critical ──
    _FILL_FIELDS = [
        "email", "phone", "phone_normalized",
        "current_employer", "designation", "department", "industry",
        "location", "headline", "summary",
        "notice_period", "notice_period_days",
        "gender", "date_of_birth", "marital_status",
        "naukri_profile_id", "naukri_profile_url",
        "source_platform",
    ]
    for field in _FILL_FIELDS:
        existing_val = existing.get(field)
        incoming_val = incoming.get(field)
        if incoming_val and not existing_val:
            updates[field] = incoming_val

    # ── CTC: keep HIGHER value if it passes sanity ──
    for ctc_field in ["current_salary", "expected_salary"]:
        ex_val = existing.get(ctc_field) or 0
        in_val = incoming.get(ctc_field) or 0
        # Only update to higher if it's sane
        if in_val > ex_val and in_val <= CTC_MAX:
            updates[ctc_field] = in_val
        elif ex_val > CTC_MAX:
            # Existing has a bad value — clear it or use incoming
            if in_val > 0 and in_val <= CTC_MAX:
                updates[ctc_field] = in_val
            else:
                updates[ctc_field] = None

    # ── Skills: union ──
    ex_skills = set(existing.get("skills") or [])
    in_skills = set(incoming.get("skills") or [])
    merged_skills = list(ex_skills | in_skills)
    if len(merged_skills) > len(ex_skills):
        updates["skills"] = merged_skills[:50]  # Cap at 50

    # ── Experience years: keep higher ──
    ex_exp = existing.get("total_experience_years") or 0
    in_exp = incoming.get("total_experience_years") or 0
    if in_exp > ex_exp:
        updates["total_experience_years"] = in_exp

    # ── Work experience: keep the longer list ──
    ex_work = existing.get("experience") or []
    in_work = incoming.get("experience") or []
    if len(in_work) > len(ex_work):
        updates["experience"] = in_work

    # ── Education: keep the longer list ──
    ex_edu = existing.get("education") or []
    in_edu = incoming.get("education") or []
    if len(in_edu) > len(ex_edu):
        updates["education"] = in_edu

    # ── Raw text: keep the longer one ──
    ex_raw = existing.get("raw_profile_text") or ""
    in_raw = incoming.get("raw_profile_text") or ""
    if len(in_raw) > len(ex_raw):
        updates["raw_profile_text"] = in_raw

    # ── Metadata ──
    updates["last_merged_at"] = now
    updates["merge_count"] = (existing.get("merge_count") or 0) + 1

    return updates


async def log_merge_audit(existing_id: str, incoming_data: dict, merge_updates: dict, merged_by: str):
    """Log merge event for audit trail."""
    try:
        audit_entry = {
            "type": "auto_merge",
            "candidate_id": existing_id,
            "merged_by": merged_by,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "incoming_name": incoming_data.get("name"),
            "incoming_email": incoming_data.get("email"),
            "incoming_phone": incoming_data.get("phone"),
            "incoming_source": incoming_data.get("source"),
            "fields_updated": list(merge_updates.keys()),
        }
        await db.merge_audit_log.insert_one(audit_entry)
        logger.info(f"[AutoMerge] Audit logged for candidate {existing_id[:12]}")
    except Exception as e:
        logger.warning(f"[AutoMerge] Audit log failed: {e}")
