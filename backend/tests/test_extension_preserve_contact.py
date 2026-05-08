"""
Phase 54.6 regression test — recapture must NOT wipe existing contact data.

Bug history: when a recruiter recaptured a candidate WITHOUT clicking
"View Contact" on Naukri, the extension sent phone="" (empty string).
The old `build_complete_update` used `if value is not None` so the empty
string passed the guard and MongoDB `$set: {phone: ""}` wiped the
previously-saved phone. This test pins that behaviour.

Run from /app/backend:
    python -m pytest tests/test_extension_preserve_contact.py -v
"""
from __future__ import annotations
from datetime import datetime, timezone

from models.extension import (
    CompleteNaukriProfileInput,
    PersonalDetailsInput,
    CareerPreferencesInput,
)
from services.extension_service import (
    build_complete_update,
    _should_overwrite,
)

NOW = datetime.now(timezone.utc).isoformat()
USER = {"id": "u1", "name": "Test", "email": "t@v.in", "role": "recruiter"}


def _make_profile(**overrides) -> CompleteNaukriProfileInput:
    base = dict(
        name="Palak",
        naukri_profile_id="78520827",
        naukri_profile_url="https://www.naukri.com/candidate/preview/78520827:abc",
        scraped_at=NOW,
    )
    base.update(overrides)
    return CompleteNaukriProfileInput(**base)


# ── _should_overwrite primitive contract ──────────────────────────────
def test_skips_none():
    assert _should_overwrite(None) is False


def test_skips_empty_string():
    assert _should_overwrite("") is False
    assert _should_overwrite("   ") is False


def test_skips_empty_list_and_dict():
    assert _should_overwrite([]) is False
    assert _should_overwrite({}) is False


def test_keeps_false_and_zero():
    # False booleans and 0 numerics ARE valid captured values
    assert _should_overwrite(False) is True
    assert _should_overwrite(0) is True
    assert _should_overwrite(0.0) is True


def test_keeps_real_values():
    assert _should_overwrite("9876543210") is True
    assert _should_overwrite(["python", "fastapi"]) is True


# ── build_complete_update: contact-hidden recapture must preserve ─────
def test_recapture_with_hidden_contact_does_not_emit_phone():
    """phone='' must NOT appear in the update dict (so MongoDB $set
    leaves the existing DB value intact)."""
    profile = _make_profile(phone="", email="")
    update = build_complete_update(profile, USER, NOW)

    assert "phone" not in update, (
        "phone='' must be filtered out so existing DB phone is preserved"
    )
    assert "email" not in update
    assert "phone_normalized" not in update


def test_recapture_with_real_contact_emits_phone():
    profile = _make_profile(phone="9876543210", email="palak@example.com")
    update = build_complete_update(profile, USER, NOW)
    assert update["phone"] == "9876543210"
    assert update["email"] == "palak@example.com"
    assert update["phone_normalized"] == "9876543210"


def test_personal_block_skips_empty_strings():
    profile = _make_profile(
        personal_details=PersonalDetailsInput(
            current_address="",
            current_city="",
            gender="Female",
        ),
    )
    update = build_complete_update(profile, USER, NOW)
    # empty strings filtered, real value retained
    assert "current_address" not in update
    assert "current_city" not in update
    assert update["gender"] == "Female"


def test_career_block_skips_empty_strings_keeps_zero():
    profile = _make_profile(
        career_preferences=CareerPreferencesInput(
            notice_period="",            # empty -> skip
            current_salary=0,            # zero  -> KEEP (fresher)
            expected_salary=1500000,
        ),
    )
    update = build_complete_update(profile, USER, NOW)
    assert "notice_period" not in update
    # Note: build_complete_update only emits career_keys directly listed.
    # current_salary=0 should pass the guard since 0 is a meaningful value.
    assert update.get("current_salary") == 0
    assert update["expected_salary"] == 1500000


def test_has_resume_false_is_kept():
    """has_resume=False is a meaningful capture (resume removed),
    must not be silently dropped."""
    profile = _make_profile(has_resume=False)
    update = build_complete_update(profile, USER, NOW)
    assert update.get("has_resume") is False
