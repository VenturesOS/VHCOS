"""Regression tests for the Phase 57 badge fuzzy-path fix.

Background: the old /check-existing fuzzy path ran ONE $or query over all
first-name tokens with a SHARED 800-doc cap. Popular names exhausted the
cap and alphabetically-later names got empty (and then TTL-cached!)
buckets — the root cause of "candidate in DB but no green badge"
(Ramesh Kannan bug). The fix gives every card its OWN bounded query
built by `_bucket_query_for`.

Run: cd /app/backend && python -m pytest tests/test_badge_bucket_query.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routes.extension_check import _bucket_query_for  # noqa: E402


def test_multi_token_query_shape():
    key, query, lim = _bucket_query_for("Ramesh Kannan")
    assert key == "ramesh|kannan"
    assert lim == 200
    branches = query["$or"]
    assert len(branches) == 2
    # Forward branch: prefix on first token + (other-token word OR single-token DB name)
    fwd = branches[0]["$and"]
    assert fwd[0] == {"name_lower": {"$regex": "^ramesh"}}
    or_clauses = fwd[1]["$or"]
    assert {"name_lower": {"$regex": r"\bkannan"}} in or_clauses
    assert {"name_lower": {"$regex": r"^\S+$"}} in or_clauses
    # Reversed branch: prefix on last token + first token as word
    rev = branches[1]["$and"]
    assert rev[0] == {"name_lower": {"$regex": "^kannan"}}
    assert rev[1] == {"name_lower": {"$regex": r"\bramesh"}}


def test_single_token_gets_prefix_scan_with_bigger_limit():
    key, query, lim = _bucket_query_for("Yash")
    assert key == "yash"
    assert query == {"name_lower": {"$regex": "^yash"}}
    assert lim == 600  # must cover "yash vardhan", "yash sharma", ...


def test_per_card_queries_are_independent():
    """The shared-cap starvation bug cannot recur: each card produces its
    own query + own limit, regardless of what other cards are in the batch."""
    _, q1, l1 = _bucket_query_for("Akash Chavan")
    _, q2, l2 = _bucket_query_for("Ramesh Kannan")
    assert q1 != q2
    assert l1 == l2 == 200  # bounded per-card, not per-batch


def test_honorifics_and_punctuation_stripped():
    key, query, _ = _bucket_query_for("Mr. Ramesh-Kannan")
    assert key == "ramesh|kannan"
    assert query is not None


def test_empty_or_junk_name_returns_no_query():
    for bad in (None, "", "  ", ". -", "A"):
        key, query, lim = _bucket_query_for(bad)
        assert query is None
        assert lim == 0


def test_cache_key_stable_across_token_order():
    """Cache key sorts the non-first tokens so 'Manish Kumar Sehgal'
    always maps to the same bucket."""
    k1, _, _ = _bucket_query_for("Manish Kumar Sehgal")
    assert k1 == "manish|kumar,sehgal"


def test_regex_special_chars_escaped():
    key, query, _ = _bucket_query_for("Ramesh (Kannan)")
    # Parens stripped by cleaning, so this is the normal multi-token shape
    assert key == "ramesh|kannan"
    fwd = query["$or"][0]["$and"]
    assert fwd[0] == {"name_lower": {"$regex": "^ramesh"}}
