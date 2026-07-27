"""
screening_analytics.py — drop-off funnel over screening sessions
================================================================
Pure functions over session documents so everything is unit-testable;
the route just fetches and delegates.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List


def funnel(sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-block asked/answered/dropped counts, language split, verdict
    mix, and average completion turns. 'Dropped at' = the current block
    of sessions that ended without completing (stalled/opted_out)."""
    blocks: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    by_language = defaultdict(int)
    verdicts = defaultdict(int)
    completed_turns: List[int] = []

    for s in sessions:
        by_language[s.get("language") or "en"] += 1
        if s.get("verdict"):
            verdicts[s["verdict"]] += 1
        s_blocks = s.get("blocks") or []
        answers = s.get("answers") or {}
        idx = s.get("idx", 0)
        for i, b in enumerate(s_blocks):
            bid = b["id"]
            if bid not in blocks:
                blocks[bid] = {"id": bid, "kind": b["kind"], "asked": 0,
                               "answered": 0, "dropped_here": 0, "unclear": 0}
                order.append(bid)
            entry = blocks[bid]
            if i < idx or bid in answers:
                entry["asked"] += 1
            a = answers.get(bid)
            if a is not None:
                if a.get("value") is not None:
                    entry["answered"] += 1
                elif a.get("asks", 0) >= 2:
                    entry["unclear"] += 1
        if s.get("state") in ("stalled", "opted_out") and idx < len(s_blocks):
            bid = s_blocks[idx]["id"]
            blocks.setdefault(bid, {"id": bid, "kind": s_blocks[idx]["kind"],
                                    "asked": 0, "answered": 0,
                                    "dropped_here": 0, "unclear": 0})
            blocks[bid]["dropped_here"] += 1
        if s.get("state") == "completed":
            completed_turns.append(sum(1 for t in (s.get("transcript") or [])
                                       if t.get("dir") == "in"))

    total = len(sessions)
    completed = sum(1 for s in sessions if s.get("state") == "completed")
    return {
        "total_sessions": total,
        "completed": completed,
        "completion_rate": round(completed / total * 100, 1) if total else 0.0,
        "avg_candidate_turns": round(sum(completed_turns) / len(completed_turns), 1)
        if completed_turns else None,
        "by_language": dict(by_language),
        "verdicts": dict(verdicts),
        "blocks": [blocks[b] for b in order],
    }
