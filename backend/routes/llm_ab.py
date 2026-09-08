"""
LLM Extraction A/B — Nemotron vs Nemotron Super 120B quality comparison.

Runs the first N candidates captured through the Chrome extension through
BOTH extraction models in parallel and produces an extensive quality
report. Admin-only. Report data is stored so it can be re-visited.

Endpoints:
    POST /api/admin/llm-ab/run            — start a new run (async background)
    GET  /api/admin/llm-ab/runs           — list past runs
    GET  /api/admin/llm-ab/status/{id}    — progress + full report
    POST /api/admin/llm-ab/cancel/{id}    — cancel an in-flight run

Storage:
    Collection: llm_ab_runs
        {
          id, status: pending|running|completed|failed|cancelled,
          created_at, completed_at, started_by,
          sample_size, candidate_ids, source_filter,
          progress: {done, total},
          results: [ per_candidate_result, ... ],
          report:  {compiled metrics}
        }
"""
import os
import asyncio
import logging
import uuid
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from config import db
from utils import require_role
from services.llm_fallback_service import (
    _call_nemotron,
    _call_nvidia_fallback,
    _extract_json_from_response,
)

logger = logging.getLogger(__name__)

llm_ab_router = APIRouter(prefix="/api/admin/llm-ab", tags=["LLM A/B Testing"])

# System prompt kept identical to production `extract_full_profile_fallback`
# so results reflect real extraction quality (not a stripped-down test prompt).
AB_SYSTEM_PROMPT = """You are an expert data-extraction agent for recruitment profiles (Naukri, LinkedIn, resumes).
Extract candidate data from profile text and return ONLY valid JSON (no markdown fences, no commentary).

Required top-level keys:
  name, email, phone, location, experience_years, current_employer, current_designation,
  current_ctc, expected_ctc, notice_period, notice_period_days, profile_summary, headline,
  key_skills (array), work_experience (array of {company, designation, from_date, to_date, is_current, duration, description}),
  education (array of {degree, institution, specialization, year_of_passing, score}),
  certifications (array), languages (array), highest_qualification, current_department, current_industry

Rules:
- CTC: convert "Lacs"/"Lakhs"/"LPA" → rupees (× 100000). "60 Lacs" = 6000000. "Cr" = × 10000000.
- Experience: use formula years + (months/100). "7y 3m" = 7.03, "22y" = 22.00.
- Notice: convert to days (Immediate=0, 15 Days=15, 1 Month=30, 3 Months=90).
- Never leave fields visible in top card as null.
- Return ONLY JSON."""

# ── Fields the report evaluates ──────────────────────────────────────────
CRITICAL_SCALAR_FIELDS = [
    "name", "email", "phone", "location",
    "current_employer", "current_designation",
    "experience_years", "current_ctc", "expected_ctc",
    "notice_period", "notice_period_days",
    "highest_qualification", "current_industry",
    "profile_summary", "headline",
]

ARRAY_FIELDS = ["key_skills", "work_experience", "education", "certifications", "languages"]

AGREEMENT_FIELDS = [
    "name", "email", "phone",
    "current_employer", "current_designation",
    "experience_years", "current_ctc", "expected_ctc",
    "notice_period_days", "location", "highest_qualification",
]


def _is_populated(v: Any) -> bool:
    """A field counts as populated when it is not None, not empty string,
    not the number 0, not an empty list/dict."""
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return v != 0


def _normalise_for_agreement(v: Any) -> Any:
    """Loose equality: strip/lowercase strings, coerce numerics to same type."""
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip().lower()
    if isinstance(v, (int, float)):
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return v
    return v


async def _extract_one(raw_text: str, candidate_name: str) -> Dict[str, Any]:
    """
    Run Nemotron + Nemotron Super 120B on the same raw_text in parallel.
    Returns a dict with per-model output, elapsed_ms, and error info.
    """
    import time
    user_prompt = f"Extract complete profile:\n\n{raw_text[:50000]}"

    async def _nemo():
        t0 = time.time()
        try:
            r = await _call_nemotron(AB_SYSTEM_PROMPT, user_prompt)
            elapsed = int((time.time() - t0) * 1000)
            if not r:
                return {"ok": False, "error": "no response", "elapsed_ms": elapsed, "output": None}
            import json
            content = _extract_json_from_response(r["content"])
            try:
                data = json.loads(content)
                return {"ok": True, "output": data, "elapsed_ms": elapsed, "raw_chars": len(r["content"])}
            except json.JSONDecodeError as e:
                # Try json_repair
                try:
                    from json_repair import repair_json
                    data = repair_json(content, return_objects=True)
                    if isinstance(data, dict):
                        return {"ok": True, "output": data, "elapsed_ms": elapsed,
                                "raw_chars": len(r["content"]), "json_repaired": True}
                except Exception:
                    pass
                return {"ok": False, "error": f"json decode: {e}", "elapsed_ms": elapsed,
                        "output": None, "raw_chars": len(r["content"])}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "elapsed_ms": int((time.time() - t0) * 1000), "output": None}

    async def _nemotron_super():
        t0 = time.time()
        try:
            r = await _call_nvidia_fallback(AB_SYSTEM_PROMPT, user_prompt)
            elapsed = int((time.time() - t0) * 1000)
            if not r:
                return {"ok": False, "error": "no response", "elapsed_ms": elapsed, "output": None}
            import json
            content = _extract_json_from_response(r["content"])
            try:
                data = json.loads(content)
                return {"ok": True, "output": data, "elapsed_ms": elapsed, "raw_chars": len(r["content"])}
            except json.JSONDecodeError as e:
                try:
                    from json_repair import repair_json
                    data = repair_json(content, return_objects=True)
                    if isinstance(data, dict):
                        return {"ok": True, "output": data, "elapsed_ms": elapsed,
                                "raw_chars": len(r["content"]), "json_repaired": True}
                except Exception:
                    pass
                return {"ok": False, "error": f"json decode: {e}", "elapsed_ms": elapsed,
                        "output": None, "raw_chars": len(r["content"])}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "elapsed_ms": int((time.time() - t0) * 1000), "output": None}

    nemo, nemotron_super = await asyncio.gather(_nemo(), _nemotron_super())
    return {"candidate_name": candidate_name, "nemotron": nemo, "nemotron_super": nemotron_super}


def _compile_report(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compile an extensive quality report from per-candidate results."""
    n = len(results)
    if n == 0:
        return {"error": "no results"}

    # Successes
    nemo_ok = [r["nemotron"] for r in results if r["nemotron"].get("ok")]
    nemotron_super_ok = [r["nemotron_super"] for r in results if r["nemotron_super"].get("ok")]
    nemo_repaired = sum(1 for r in results if r["nemotron"].get("json_repaired"))
    nemotron_super_repaired = sum(1 for r in results if r["nemotron_super"].get("json_repaired"))

    # Latency stats
    def _lat_stats(lst):
        vals = [x.get("elapsed_ms", 0) for x in lst if x.get("elapsed_ms")]
        if not vals:
            return {"count": 0, "avg_ms": 0, "p50_ms": 0, "p95_ms": 0, "min_ms": 0, "max_ms": 0}
        vals_sorted = sorted(vals)
        p95_idx = int(len(vals_sorted) * 0.95)
        return {
            "count": len(vals),
            "avg_ms": int(statistics.mean(vals)),
            "p50_ms": int(statistics.median(vals)),
            "p95_ms": int(vals_sorted[min(p95_idx, len(vals_sorted) - 1)]),
            "min_ms": int(min(vals)),
            "max_ms": int(max(vals)),
        }

    nemo_latency = _lat_stats([r["nemotron"] for r in results])
    nemotron_super_latency = _lat_stats([r["nemotron_super"] for r in results])

    # Field-fill rate per critical scalar field
    field_fill: Dict[str, Dict[str, float]] = {}
    for f in CRITICAL_SCALAR_FIELDS:
        nemo_hits = sum(1 for r in nemo_ok if _is_populated((r.get("output") or {}).get(f)))
        nemotron_super_hits = sum(1 for r in nemotron_super_ok if _is_populated((r.get("output") or {}).get(f)))
        field_fill[f] = {
            "nemotron_pct": round(100 * nemo_hits / max(len(nemo_ok), 1), 1),
            "nemotron_super_pct": round(100 * nemotron_super_hits / max(len(nemotron_super_ok), 1), 1),
            "nemotron_count": nemo_hits,
            "nemotron_super_count": nemotron_super_hits,
        }

    # Array richness — count populated items per array field
    array_richness: Dict[str, Dict[str, float]] = {}
    for f in ARRAY_FIELDS:
        def _counts(oks):
            return [len(x.get("output", {}).get(f) or []) for x in oks
                    if isinstance(x.get("output", {}).get(f), list)]
        n_cnts = _counts(nemo_ok)
        q_cnts = _counts(nemotron_super_ok)
        array_richness[f] = {
            "nemotron_avg": round(statistics.mean(n_cnts), 2) if n_cnts else 0.0,
            "nemotron_median": statistics.median(n_cnts) if n_cnts else 0,
            "nemotron_super_avg": round(statistics.mean(q_cnts), 2) if q_cnts else 0.0,
            "nemotron_super_median": statistics.median(q_cnts) if q_cnts else 0,
            "nemotron_zero_pct": round(100 * sum(1 for c in n_cnts if c == 0) / max(len(n_cnts), 1), 1),
            "nemotron_super_zero_pct": round(100 * sum(1 for c in q_cnts if c == 0) / max(len(q_cnts), 1), 1),
        }

    # Agreement rate — % of candidates where both models return same value on a field
    agreement: Dict[str, Dict[str, float]] = {}
    for f in AGREEMENT_FIELDS:
        both = 0
        agree = 0
        for r in results:
            if not (r["nemotron"].get("ok") and r["nemotron_super"].get("ok")):
                continue
            n_val = _normalise_for_agreement((r["nemotron"].get("output") or {}).get(f))
            q_val = _normalise_for_agreement((r["nemotron_super"].get("output") or {}).get(f))
            if n_val is None and q_val is None:
                continue
            both += 1
            if n_val == q_val:
                agree += 1
        agreement[f] = {
            "agree_pct": round(100 * agree / max(both, 1), 1),
            "compared": both,
            "agreed": agree,
        }

    # Winner per candidate: side with more populated critical scalars + more skills
    winner = {"nemotron": 0, "nemotron_super": 0, "tie": 0, "both_failed": 0}
    for r in results:
        n_ok = r["nemotron"].get("ok")
        q_ok = r["nemotron_super"].get("ok")
        if not n_ok and not q_ok:
            winner["both_failed"] += 1
            continue
        if not n_ok:
            winner["nemotron_super"] += 1
            continue
        if not q_ok:
            winner["nemotron"] += 1
            continue
        n_score = sum(1 for f in CRITICAL_SCALAR_FIELDS if _is_populated((r["nemotron"].get("output") or {}).get(f)))
        n_score += len(r["nemotron"].get("output", {}).get("key_skills") or []) * 0.1
        q_score = sum(1 for f in CRITICAL_SCALAR_FIELDS if _is_populated((r["nemotron_super"].get("output") or {}).get(f)))
        q_score += len(r["nemotron_super"].get("output", {}).get("key_skills") or []) * 0.1
        if abs(n_score - q_score) < 0.05:
            winner["tie"] += 1
        elif n_score > q_score:
            winner["nemotron"] += 1
        else:
            winner["nemotron_super"] += 1

    # Empty critical field rate — how often a name/employer/exp is missing on a successful call
    critical_missing = {"nemotron": 0, "nemotron_super": 0}
    for r in nemo_ok:
        out = r.get("output") or {}
        if not (out.get("name") and out.get("current_employer") and out.get("experience_years") is not None):
            critical_missing["nemotron"] += 1
    for r in nemotron_super_ok:
        out = r.get("output") or {}
        if not (out.get("name") and out.get("current_employer") and out.get("experience_years") is not None):
            critical_missing["nemotron_super"] += 1

    # Response-size stats
    def _size_stats(lst):
        vals = [x.get("raw_chars", 0) for x in lst if x.get("raw_chars")]
        if not vals:
            return {"avg": 0, "p50": 0}
        return {"avg": int(statistics.mean(vals)), "p50": int(statistics.median(vals))}

    return {
        "sample_size": n,
        "success": {
            "nemotron_ok": len(nemo_ok),
            "nemotron_super_ok": len(nemotron_super_ok),
            "nemotron_success_pct": round(100 * len(nemo_ok) / n, 1),
            "nemotron_super_success_pct": round(100 * len(nemotron_super_ok) / n, 1),
            "nemotron_json_repaired": nemo_repaired,
            "nemotron_super_json_repaired": nemotron_super_repaired,
        },
        "latency": {
            "nemotron": nemo_latency,
            "nemotron_super": nemotron_super_latency,
        },
        "response_size": {
            "nemotron": _size_stats([r["nemotron"] for r in results]),
            "nemotron_super": _size_stats([r["nemotron_super"] for r in results]),
        },
        "field_fill_rate": field_fill,
        "array_richness": array_richness,
        "agreement": agreement,
        "winner_per_candidate": winner,
        "critical_missing": {
            "nemotron_pct": round(100 * critical_missing["nemotron"] / max(len(nemo_ok), 1), 1),
            "nemotron_super_pct": round(100 * critical_missing["nemotron_super"] / max(len(nemotron_super_ok), 1), 1),
            **critical_missing,
        },
        "verdict": _verdict(winner, len(nemo_ok), len(nemotron_super_ok), n),
    }


def _verdict(winner: Dict, nemo_ok: int, nemotron_super_ok: int, n: int) -> str:
    if nemo_ok == 0 and nemotron_super_ok == 0:
        return "Both models failed — check API keys and pod status."
    if winner["nemotron"] > winner["nemotron_super"] * 1.5:
        return f"Nemotron wins clearly ({winner['nemotron']} vs {winner['nemotron_super']} — {round(100 * winner['nemotron'] / n, 1)}%)"
    if winner["nemotron_super"] > winner["nemotron"] * 1.5:
        return f"Nemotron Super 120B wins clearly ({winner['nemotron_super']} vs {winner['nemotron']} — {round(100 * winner['nemotron_super'] / n, 1)}%)"
    return f"Effectively tied (Nemotron {winner['nemotron']} / Nemotron Super 120B {winner['nemotron_super']} / Tie {winner['tie']})"


async def _run_ab_job(run_id: str, sample_size: int, source_filter: str) -> None:
    """Background task — fetches candidates, runs A/B, writes progress + final report."""
    try:
        await db.llm_ab_runs.update_one(
            {"id": run_id},
            {"$set": {"status": "running", "started_at": datetime.now(timezone.utc).isoformat()}},
        )

        # Fetch first N extension-captured candidates that have raw_text_for_enrichment
        query = {
            "source": {"$regex": source_filter, "$options": "i"},
            "raw_text_for_enrichment": {"$exists": True, "$ne": ""},
        }
        cursor = db.candidate_bank.find(
            query,
            {"_id": 0, "id": 1, "name": 1, "raw_text_for_enrichment": 1, "created_at": 1},
        ).sort("created_at", 1).limit(sample_size)

        candidates = []
        async for c in cursor:
            candidates.append(c)

        if len(candidates) < 1:
            await db.llm_ab_runs.update_one(
                {"id": run_id},
                {"$set": {
                    "status": "failed",
                    "error": f"No extension-captured candidates with raw_text_for_enrichment found (filter='{source_filter}')",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            return

        await db.llm_ab_runs.update_one(
            {"id": run_id},
            {"$set": {
                "candidate_ids": [c["id"] for c in candidates],
                "progress": {"done": 0, "total": len(candidates)},
            }},
        )

        # Concurrency 5 keeps us under Nemotron's 40 rpm free tier + Nemotron Super 120B pod concurrency
        sem = asyncio.Semaphore(2)
        results: List[Dict[str, Any]] = []

        async def _one(idx: int, c: Dict):
            async with sem:
                # Re-check cancel flag
                run = await db.llm_ab_runs.find_one({"id": run_id}, {"status": 1})
                if run and run.get("status") == "cancelled":
                    return None
                raw = c.get("raw_text_for_enrichment") or ""
                if len(raw) < 100:
                    return {"candidate_id": c["id"], "candidate_name": c.get("name"),
                            "skipped": True, "reason": "raw_text too short"}
                out = await _extract_one(raw, c.get("name") or "Unknown")
                out["candidate_id"] = c["id"]
                await db.llm_ab_runs.update_one(
                    {"id": run_id},
                    {"$inc": {"progress.done": 1},
                     "$push": {"results": out}},
                )
                return out

        tasks = [_one(i, c) for i, c in enumerate(candidates)]
        await asyncio.gather(*tasks)

        # Re-read final results and compile report
        final = await db.llm_ab_runs.find_one({"id": run_id}, {"results": 1, "status": 1})
        if final and final.get("status") == "cancelled":
            return
        report = _compile_report([r for r in (final.get("results") or []) if not r.get("skipped")])

        await db.llm_ab_runs.update_one(
            {"id": run_id},
            {"$set": {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "report": report,
            }},
        )

    except Exception as e:
        logger.exception(f"[LLM-AB] Run {run_id} crashed")
        await db.llm_ab_runs.update_one(
            {"id": run_id},
            {"$set": {
                "status": "failed",
                "error": f"{type(e).__name__}: {e}",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }},
        )


@llm_ab_router.post("/run")
async def start_ab_run(
    sample_size: int = 100,
    source_filter: str = "extension",
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(require_role(["admin"])),
):
    """Kick off an A/B extraction run against the first N extension-captured candidates."""
    if not (1 <= sample_size <= 500):
        raise HTTPException(status_code=400, detail="sample_size must be 1-500")

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.llm_ab_runs.insert_one({
        "id": run_id,
        "status": "pending",
        "created_at": now,
        "started_by_id": current_user["id"],
        "started_by_name": current_user.get("name") or current_user.get("email"),
        "sample_size": sample_size,
        "source_filter": source_filter,
        "comparison_model": "nemotron_super",
        "progress": {"done": 0, "total": sample_size},
        "results": [],
        "report": None,
    })

    background_tasks.add_task(_run_ab_job, run_id, sample_size, source_filter)
    return {"run_id": run_id, "status": "pending"}


@llm_ab_router.get("/runs")
async def list_ab_runs(current_user: dict = Depends(require_role(["admin"]))):
    """List past A/B runs, newest first. Trimmed payload (no per-candidate details)."""
    cursor = db.llm_ab_runs.find(
        {},
        {"_id": 0, "id": 1, "status": 1, "created_at": 1, "completed_at": 1,
         "sample_size": 1, "source_filter": 1, "comparison_model": 1, "progress": 1,
         "started_by_name": 1, "report.verdict": 1, "error": 1},
    ).sort("created_at", -1).limit(20)
    return [r async for r in cursor]


@llm_ab_router.get("/status/{run_id}")
async def get_ab_status(
    run_id: str,
    include_results: bool = False,
    current_user: dict = Depends(require_role(["admin"])),
):
    """Return progress + full report + optionally per-candidate results."""
    projection = {"_id": 0}
    if not include_results:
        projection["results"] = 0  # exclude heavy per-candidate details
    run = await db.llm_ab_runs.find_one({"id": run_id}, projection)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@llm_ab_router.post("/cancel/{run_id}")
async def cancel_ab_run(
    run_id: str,
    current_user: dict = Depends(require_role(["admin"])),
):
    """Mark an in-flight run as cancelled — background task exits at next candidate."""
    run = await db.llm_ab_runs.find_one({"id": run_id}, {"status": 1})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.get("status") not in ("pending", "running"):
        return {"ok": False, "message": f"Cannot cancel — status is {run.get('status')}"}
    await db.llm_ab_runs.update_one(
        {"id": run_id},
        {"$set": {"status": "cancelled",
                  "completed_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}
