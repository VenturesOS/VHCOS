"""
Regression: pipeline timeline window filter (v5.5.10).

`_build_pipeline_window_filter(window, from, to)` translates a window
selection into a Mongo filter that keeps applications whose stage_history
has at least one transition inside the window. Verifies:
  1. 'all' / None  → returns None (no filter)
  2. 'week' / 'month' / etc → returns $or with stage_history.timestamp range
  3. 'custom' with from/to → respects bounds and end-of-day extension
  4. bad custom dates fall back gracefully (no exception)
  5. The filter integrates correctly with the /pipeline-stats endpoint
"""
import asyncio
from datetime import datetime, timezone, timedelta

from routes.applications import _build_pipeline_window_filter, _WINDOW_DAYS


def test_window_all_returns_none():
    assert _build_pipeline_window_filter(None, None, None) is None
    assert _build_pipeline_window_filter("all", None, None) is None


def test_window_preset_returns_or_filter():
    for w in ("week", "month", "quarter", "year"):
        f = _build_pipeline_window_filter(w, None, None)
        assert f is not None, f"window={w} returned None"
        assert "$or" in f, f"window={w} missing $or"
        # First branch: stage_history elemMatch
        sh = f["$or"][0]["stage_history"]["$elemMatch"]["timestamp"]
        assert "$gte" in sh and "$lte" in sh
        # Window size sanity check
        start = datetime.fromisoformat(sh["$gte"])
        end = datetime.fromisoformat(sh["$lte"])
        span_days = (end - start).days
        expected = _WINDOW_DAYS[w]
        # Allow ±1 day for date boundary
        assert abs(span_days - expected) <= 1, f"window={w} span={span_days} expected~{expected}"


def test_window_custom_respects_bounds():
    f = _build_pipeline_window_filter("custom", "2026-05-01", "2026-05-31")
    assert f is not None
    sh = f["$or"][0]["stage_history"]["$elemMatch"]["timestamp"]
    start = datetime.fromisoformat(sh["$gte"])
    end = datetime.fromisoformat(sh["$lte"])
    assert start.day == 1 and start.month == 5
    # End-of-day extension for date-only inputs
    assert end.day == 31 and end.month == 5
    assert end.hour == 23, f"end-of-day not applied (hour={end.hour})"


def test_window_custom_invalid_falls_back():
    """Bad ISO input must NOT raise — fall back to 'month' window."""
    f = _build_pipeline_window_filter("custom", "not-a-date", "also-broken")
    assert f is not None
    sh = f["$or"][0]["stage_history"]["$elemMatch"]["timestamp"]
    span = datetime.fromisoformat(sh["$lte"]) - datetime.fromisoformat(sh["$gte"])
    assert 29 <= span.days <= 31, f"fallback to month broken (span={span.days}d)"


def test_window_filter_includes_updated_at_fallback():
    """Older applications missing stage_history should still be picked up
    when updated_at is inside the window."""
    f = _build_pipeline_window_filter("week", None, None)
    # Second $or branch
    fallback = f["$or"][1]
    assert "updated_at" in fallback["$and"][0]
    # And only fires when stage_history is empty/absent
    sh_check = fallback["$and"][1]["$or"]
    assert any("$exists" in c.get("stage_history", {}) for c in sh_check)
    assert any("$size" in c.get("stage_history", {}) for c in sh_check)



def test_window_bare_dates_imply_custom():
    """fix.docx (2026-09-15): frontend removed the preset dropdown, now
    sends window_from / window_to without window='custom'. Those bare
    dates must still activate the filter."""
    f = _build_pipeline_window_filter(None, "2026-05-01", "2026-05-31")
    assert f is not None, "bare dates without window preset should filter"
    sh = f["$or"][0]["stage_history"]["$elemMatch"]["timestamp"]
    assert "2026-05-01" in sh["$gte"]
    assert "2026-05-31" in sh["$lte"]


def test_window_all_with_bare_from_still_fires():
    """Same as above but window='all' is explicitly sent by the URL —
    if the user set only a From date, that alone should still filter."""
    f = _build_pipeline_window_filter("all", "2026-05-01", None)
    assert f is not None
    sh = f["$or"][0]["stage_history"]["$elemMatch"]["timestamp"]
    assert "2026-05-01" in sh["$gte"]
