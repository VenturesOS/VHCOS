"""Offline write-gate checks using actual field-filtered fake queries."""
import asyncio
import ast
import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))
from identity_capture import CaptureIdentityLookupError, select_capture_candidate, normalized_phone, capture_identity_filter  # noqa: E402


def matches(doc, query):
    if "$and" in query:
        return all(matches(doc, item) for item in query["$and"])
    if "$or" in query:
        return any(matches(doc, item) for item in query["$or"])
    import re
    for key, value in query.items():
        actual = doc.get(key)
        if isinstance(value, dict):
            if "$exists" in value and (key in doc) != value["$exists"]:
                return False
            if "$eq" in value and actual != value["$eq"]:
                return False
            if "$in" in value and actual not in value["$in"]:
                return False
            if "$regex" in value and (not isinstance(actual, str) or not re.search(
                    value["$regex"], actual, re.I if "i" in value.get("$options", "") else 0)):
                return False
        elif actual != value:
            return False
    return True


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def max_time_ms(self, milliseconds):
        assert milliseconds > 0
        return self

    async def to_list(self, count):
        return copy.deepcopy(self.rows[:count])


class Bank:
    def __init__(self, rows, fail=False):
        self.rows, self.fail, self.queries = rows, fail, []

    def find(self, query, projection):
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("offline")
        return Cursor([row for row in self.rows if matches(row, query)])


BASE = {"name": "Rahul Sharma", "email": "rahul@person.test", "phone": "+91 98765 43210"}
SAVED = {**BASE, "id": "saved", "phone_normalized": "9876543210", "location": "Mumbai"}


def choose(profile, rows, fail=False):
    db = SimpleNamespace(candidate_bank=Bank(rows, fail))
    return asyncio.run(select_capture_candidate(db, profile))


def test_unique_contact_pair_and_compatible_name_can_update_after_move_and_url_rotation():
    assert choose({**BASE, "location": "Delhi", "naukri_profile_url": "https://naukri.com/?sid=new"}, [SAVED]) == SAVED


@pytest.mark.parametrize("extra", [
    {}, {"naukri_profile_id": "same-session"}, {"email": BASE["email"]}, {"phone": BASE["phone"]},
    {"naukri_profile_url": "https://naukri.com/?pid=same"},
    {"linkedin_url": "https://linkedin.com/in/rahul-sharma/"},
])
def test_same_name_employer_or_url_without_two_contacts_cannot_select_update(extra):
    profile = {"name": "Rahul Sharma", "current_company": "TCS", "location": "Delhi", **extra}
    rows = [{**SAVED, "current_employer": "TCS", **extra}]
    assert choose(profile, rows) is None


def test_contacts_pointing_to_different_people_cannot_merge():
    rows = [{**SAVED, "phone": "9765432109", "phone_normalized": "9765432109"},
            {**SAVED, "id": "other", "email": "other@person.test"}]
    assert choose(BASE, rows) is None


def test_shared_contact_or_duplicate_rows_cannot_pick_arbitrary_first():
    assert choose(BASE, [SAVED, {**SAVED, "id": "duplicate"}]) is None
    assert choose(BASE, [SAVED, {**SAVED, "id": "other", "phone": "9765432109"}]) is None


def test_name_conflict_or_inconsistent_stored_phone_abstains():
    assert choose(BASE, [{**SAVED, "name": "Rahul Mohan Kumar"}]) is None
    assert choose(BASE, [{**SAVED, "phone": "9765432109"}]) is None


def test_lookup_failure_is_retryable_and_never_a_new_candidate_decision():
    with pytest.raises(CaptureIdentityLookupError):
        choose(BASE, [], fail=True)


def test_concurrent_enrichment_between_contact_reads_is_retryable_not_an_insert():
    class ChangingBank(Bank):
        def find(self, query, projection):
            cursor = super().find(query, projection)
            if len(self.queries) == 2:
                cursor.rows = [{**row, "updated_at": "new"} for row in cursor.rows]
            return cursor
    db = SimpleNamespace(candidate_bank=ChangingBank([SAVED]))
    with pytest.raises(CaptureIdentityLookupError):
        asyncio.run(select_capture_candidate(db, BASE))


def test_foreign_phone_gate_preserves_country_code_and_rejects_legacy_truncation():
    profile = {**BASE, "phone": "+44 7911 123456"}
    saved = {**SAVED, **profile, "phone_normalized": "447911123456"}
    assert choose(profile, [saved]) == saved
    assert choose(profile, [{**saved, "phone_normalized": "7911123456"}]) is None
    assert normalized_phone(profile["phone"]) == "447911123456"


@pytest.mark.parametrize("phone", ["hidden", "98****3210", "0000000000", "123", None])
def test_invalid_contacts_never_supply_identity(phone):
    assert normalized_phone(phone) is None
    assert choose({**BASE, "phone": phone}, [SAVED]) is None


@pytest.mark.parametrize("field", ["name", "email", "phone", "phone_normalized"])
def test_capture_write_rechecks_contact_evidence_after_concurrent_edit(field):
    guard = capture_identity_filter(SAVED)
    assert matches(SAVED, guard)
    assert not matches({**SAVED, field: "changed"}, guard)
    missing = {key: value for key, value in SAVED.items() if key != field}
    assert not matches(missing, guard)
    assert matches(missing, capture_identity_filter(missing))
    assert not matches({**missing, field: None}, capture_identity_filter(missing))


def test_actual_capture_route_only_saves_observations_and_has_no_bank_write_bypass():
    route = Path(__file__).resolve().parents[1] / "routes" / "extension.py"
    tree = ast.parse(route.read_text(encoding="utf-8"))
    capture = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "capture_profile")
    calls = [node for node in ast.walk(capture) if isinstance(node, ast.Call)]
    simple_calls = [node.func.id for node in calls if isinstance(node.func, ast.Name)]
    assert simple_calls.count("record_capture_observation") == 1
    assert "find_merge_candidate" not in simple_calls
    assert "_names_are_similar" not in simple_calls
    assert not any(isinstance(node.func, ast.Attribute) and node.func.attr in {"insert_one", "update_one"}
                   and "candidate_bank" in ast.unparse(node.func) for node in calls)
