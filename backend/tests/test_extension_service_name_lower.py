"""
Regression: every extension capture must populate `name_lower`.

This caught a P0 bug where `build_complete_candidate` and `build_complete_update`
in services/extension_service.py forgot to write `name_lower`, making freshly
captured profiles invisible to the badge-scan endpoint (which queries
`name_lower: {$regex: "^<first-token>"}` for fast prefix bucketing). Net effect:
recruiters re-captured the same profile because no green badge ever appeared.
"""
from datetime import datetime, timezone

from models.extension import CompleteNaukriProfileInput
from services.extension_service import build_complete_candidate, build_complete_update


def _user():
    return {"id": "u1", "email": "admin@vhc.in", "name": "Admin", "role": "admin"}


def _profile(name: str) -> CompleteNaukriProfileInput:
    return CompleteNaukriProfileInput(
        name=name,
        email=None,
        phone=None,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        source_platform="naukri",
        extension_version="5.5.10",
    )


def test_build_complete_candidate_populates_name_lower():
    doc = build_complete_candidate(_profile("Ramesh Kannan"), "id-1", _user(), now="t")
    assert doc["name_lower"] == "ramesh kannan", f"got {doc['name_lower']!r}"


def test_build_complete_candidate_handles_whitespace_and_case():
    doc = build_complete_candidate(_profile("  Vinod Kumar T  "), "id-2", _user(), now="t")
    assert doc["name_lower"] == "vinod kumar t"


def test_build_complete_update_populates_name_lower():
    upd = build_complete_update(_profile("Ramesh Kannan"), _user(), now="t")
    assert upd["name_lower"] == "ramesh kannan"


def test_build_complete_update_skips_name_lower_when_name_missing():
    """If the incoming profile carries no name, name_lower must NOT be in the
    final $set update — otherwise we'd blow away a previously-populated
    name_lower on the existing record. (build_complete_update strips None /
    empty values via _should_overwrite.)"""
    p = CompleteNaukriProfileInput(
        name="",  # empty / missing on this delta
        scraped_at=datetime.now(timezone.utc).isoformat(),
        source_platform="naukri",
    )
    upd = build_complete_update(p, _user(), now="t")
    assert "name_lower" not in upd, f"unexpected name_lower in update: {upd.get('name_lower')!r}"
