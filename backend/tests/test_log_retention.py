"""Log retention pruner — cutoff shape and per-collection targeting."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone


class _FakeColl:
    def __init__(self):
        self.calls = []

    async def delete_many(self, filt, **kw):
        self.calls.append((filt, kw))
        class _R:  # noqa: N801
            deleted_count = 3
        return _R()


class _FakeDB:
    def __init__(self):
        self.by_name = {n: _FakeColl() for n in ("api_metrics", "activity_logs", "extraction_traces")}
    def __getitem__(self, name):
        return self.by_name[name]


def test_prune_once_uses_epoch_for_api_metrics_and_iso_for_others():
    from services.log_retention import prune_once
    db = _FakeDB()
    now = datetime.now(timezone.utc)
    out = asyncio.run(prune_once(db))

    # api_metrics uses float epoch
    api_filter, _ = db.by_name["api_metrics"].calls[0]
    api_cutoff = api_filter["timestamp"]["$lt"]
    assert isinstance(api_cutoff, float), api_cutoff
    # Should be roughly (now - 30 days) in seconds since epoch
    expected = (now - timedelta(days=30)).timestamp()
    assert abs(api_cutoff - expected) < 5, (api_cutoff, expected)

    # activity_logs uses ISO string, 90-day window
    act_filter, _ = db.by_name["activity_logs"].calls[0]
    act_cutoff = act_filter["timestamp"]["$lt"]
    assert isinstance(act_cutoff, str) and act_cutoff.endswith("+00:00"), act_cutoff
    days_ago = (now - datetime.fromisoformat(act_cutoff)).total_seconds() / 86400
    assert 89.99 < days_ago < 90.01, days_ago

    # extraction_traces uses ISO string, 30-day window on `created_at`
    ext_filter, _ = db.by_name["extraction_traces"].calls[0]
    assert "created_at" in ext_filter, ext_filter
    ext_cutoff = ext_filter["created_at"]["$lt"]
    assert isinstance(ext_cutoff, str)
    days_ago = (now - datetime.fromisoformat(ext_cutoff)).total_seconds() / 86400
    assert 29.99 < days_ago < 30.01, days_ago

    assert out["api_metrics"]["deleted"] == 3
    assert out["activity_logs"]["deleted"] == 3
    assert out["extraction_traces"]["deleted"] == 3


def test_prune_once_survives_collection_failure(monkeypatch):
    from services.log_retention import prune_once
    db = _FakeDB()

    async def _boom(_filt, **_kw):
        raise RuntimeError("simulated mongo down")

    db.by_name["api_metrics"].delete_many = _boom  # type: ignore[method-assign]

    out = asyncio.run(prune_once(db))
    # Failing collection reports the error, the rest still get pruned
    assert "error" in out["api_metrics"]
    assert out["activity_logs"]["deleted"] == 3
    assert out["extraction_traces"]["deleted"] == 3


def test_pruner_start_disabled_by_env(monkeypatch):
    monkeypatch.setenv("RETENTION_PRUNER_ENABLED", "false")
    # Reload to pick up new env
    import importlib
    import services.log_retention as mod
    importlib.reload(mod)
    task = mod.start_retention_pruner(_FakeDB())
    assert task is None


def test_delete_many_tagged_with_comment_for_atlas_profiler():
    from services.log_retention import prune_once
    db = _FakeDB()
    asyncio.run(prune_once(db))
    for coll_name in ("api_metrics", "activity_logs", "extraction_traces"):
        _, kwargs = db.by_name[coll_name].calls[0]
        assert kwargs.get("comment") == "log_retention_prune", (coll_name, kwargs)
