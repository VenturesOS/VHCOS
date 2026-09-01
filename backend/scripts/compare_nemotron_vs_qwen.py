"""
Quality A/B test: Nemotron vs Qwen on real candidate profiles.

Picks 3 varied profiles from candidate_bank (well-detailed, sparse, long-CTC),
runs the SAME system+user prompts through both models, prints a field-by-field
diff so we can eyeball quality delta before making Nemotron the default.

Usage:
    cd /app/backend && python -m scripts.compare_nemotron_vs_qwen
"""
import asyncio
import json
import os
import sys
import time

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()


def _summarise(result):
    """Compress a big extraction dict into a diffable summary."""
    if not isinstance(result, dict) or result.get("error"):
        return {"error": result.get("error", "no result") if isinstance(result, dict) else "not a dict"}
    return {
        "name": result.get("name"),
        "email": result.get("email"),
        "phone": result.get("phone") or result.get("candidate_phone"),
        "current_employer": result.get("current_employer"),
        "current_designation": result.get("current_designation"),
        "location": result.get("location"),
        "experience_years": result.get("experience_years"),
        "current_ctc": result.get("current_ctc"),
        "expected_ctc": result.get("expected_ctc"),
        "notice_period": result.get("notice_period"),
        "notice_period_days": result.get("notice_period_days"),
        "skills_count": len(result.get("key_skills") or []),
        "skills_sample": (result.get("key_skills") or [])[:5],
        "work_exp_count": len(result.get("work_experience") or []),
        "education_count": len(result.get("education") or []),
        "profile_summary_len": len(result.get("profile_summary") or ""),
    }


def _field_diff(nemo, qwen):
    """Return list of (field, nemo_val, qwen_val, winner) for user-visible fields."""
    rows = []
    for k in ["name", "current_employer", "current_designation", "location",
              "experience_years", "current_ctc", "expected_ctc", "notice_period",
              "notice_period_days", "skills_count", "work_exp_count",
              "education_count", "profile_summary_len"]:
        n, q = nemo.get(k), qwen.get(k)
        # Determine winner
        if n == q:
            winner = "="
        elif n is None or n == "" or n == 0:
            winner = "Q"
        elif q is None or q == "" or q == 0:
            winner = "N"
        elif k.endswith("_count") or k.endswith("_len") or k.endswith("_days"):
            # numeric — higher is generally better (more data extracted)
            try:
                winner = "N" if float(n) > float(q) else "Q" if float(q) > float(n) else "="
            except (TypeError, ValueError):
                winner = "?"
        else:
            winner = "?"  # different string values — hard to auto-judge
        rows.append((k, n, q, winner))
    return rows


async def main():
    from services.llm_fallback_service import (
        _call_nemotron, _call_runpod_vllm, _extract_json_from_response
    )

    # Build the same system prompt used in production
    # (imported by pulling it from the function scope — cleanest way)
    import services.llm_fallback_service as lfs
    import inspect
    src = inspect.getsource(lfs.extract_full_profile_fallback)
    # Extract the system_prompt string literal — cheaper than reproducing it here
    # We'll just import a small wrapper that gives us the same prompt
    # Actually simplest: call the real function twice, once forcing Nemotron only
    # and once forcing Qwen only. We do this via env toggles.

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # ── Pick 3 varied candidates that have full raw_text ──
    # (a) well-detailed: rich profile with skills, experience, ctc
    # (b) sparse: minimal info
    # (c) long-CTC format: has "Lakhs" or "expects" pattern in raw
    pipe_full = [
        {"$match": {
            "raw_text_for_enrichment": {"$type": "string", "$ne": ""},
            "skills": {"$exists": True, "$type": "array"},
            "$expr": {"$gte": [{"$strLenCP": {"$ifNull": ["$raw_text_for_enrichment", ""]}}, 3000]},
        }},
        {"$sample": {"size": 1}},
        {"$project": {"_id": 0, "id": 1, "name": 1, "raw_text_for_enrichment": 1}},
    ]
    pipe_sparse = [
        {"$match": {
            "raw_text_for_enrichment": {"$type": "string", "$ne": ""},
            "$expr": {
                "$and": [
                    {"$gte": [{"$strLenCP": {"$ifNull": ["$raw_text_for_enrichment", ""]}}, 500]},
                    {"$lte": [{"$strLenCP": {"$ifNull": ["$raw_text_for_enrichment", ""]}}, 2000]},
                ]
            },
        }},
        {"$sample": {"size": 1}},
        {"$project": {"_id": 0, "id": 1, "name": 1, "raw_text_for_enrichment": 1}},
    ]
    pipe_ctc = [
        {"$match": {
            "raw_text_for_enrichment": {"$type": "string", "$regex": "Lakhs|Lacs|expects|LPA", "$options": "i"},
            "$expr": {"$gte": [{"$strLenCP": {"$ifNull": ["$raw_text_for_enrichment", ""]}}, 2500]},
        }},
        {"$sample": {"size": 1}},
        {"$project": {"_id": 0, "id": 1, "name": 1, "raw_text_for_enrichment": 1}},
    ]

    tests = []
    for label, pipe in [("well-detailed", pipe_full), ("sparse", pipe_sparse), ("long-CTC", pipe_ctc)]:
        docs = await db.candidate_bank.aggregate(pipe).to_list(1)
        if docs:
            tests.append((label, docs[0]))
        else:
            print(f"[warn] no candidate matched for '{label}'")

    if not tests:
        print("ERROR: No candidates found for testing.")
        return 1

    # ── Grab the actual system_prompt from the running extract_full_profile_fallback ──
    # by patching _call_nemotron and _call_runpod_vllm temporarily.
    captured_prompts = {}

    orig_nemo = lfs._call_nemotron
    orig_qwen = lfs._call_runpod_vllm

    async def spy_nemo(sp, up, **kw):
        captured_prompts["system"] = sp
        return await orig_nemo(sp, up, **kw)

    async def spy_qwen(sp, up, **kw):
        captured_prompts["system"] = sp
        return await orig_qwen(sp, up, **kw)

    for label, doc in tests:
        raw_text = doc["raw_text_for_enrichment"]
        name = doc.get("name", "unknown")
        raw_len = len(raw_text)
        print(f"\n{'='*70}")
        print(f"TEST: {label} — {name} (raw_text {raw_len} chars)")
        print('='*70)

        # Call each model directly with the same prompt from the running service
        # Trigger once through the wrapper to capture the real prompt
        lfs._call_nemotron = spy_nemo
        lfs._call_runpod_vllm = spy_qwen

        # Run Nemotron (Layer 0) — will short-circuit; then reset and run Qwen separately
        # We'll actually just build prompts here directly by reading from the source
        # since patching mid-flight is finicky. Simpler: extract prompt from source.
        pass

    lfs._call_nemotron = orig_nemo
    lfs._call_runpod_vllm = orig_qwen

    # ── Direct comparison approach: build prompt inline ──
    # This is the exact system_prompt from extract_full_profile_fallback.
    # We import a getter to avoid duplicating it here.
    system_prompt_src = inspect.getsource(lfs.extract_full_profile_fallback)
    # Extract the literal between the first triple-quoted string
    import re
    m = re.search(r'system_prompt = """(.*?)"""', system_prompt_src, re.DOTALL)
    if not m:
        print("ERROR: Could not extract system_prompt from source. Aborting.")
        return 1
    system_prompt = m.group(1)

    for label, doc in tests:
        raw_text = doc["raw_text_for_enrichment"]
        name = doc.get("name", "unknown")
        user_prompt = f"Extract complete profile:\n\n{raw_text[:50000]}"

        print(f"\n{'='*70}")
        print(f"TEST: {label} — {name}")
        print('='*70)

        # Nemotron
        t0 = time.monotonic()
        nemo_resp = await orig_nemo(system_prompt, user_prompt)
        t_nemo = time.monotonic() - t0
        nemo_result = None
        if nemo_resp:
            content = _extract_json_from_response(nemo_resp["content"])
            try:
                nemo_result = json.loads(content)
            except json.JSONDecodeError:
                try:
                    from json_repair import repair_json
                    nemo_result = repair_json(content, return_objects=True)
                except Exception:
                    nemo_result = {"error": "json_parse_failed"}
        else:
            nemo_result = {"error": "nemotron_call_failed"}

        # Qwen (RunPod pod)
        t0 = time.monotonic()
        qwen_resp = await orig_qwen(system_prompt, user_prompt)
        t_qwen = time.monotonic() - t0
        qwen_result = None
        if qwen_resp:
            content = _extract_json_from_response(qwen_resp["content"])
            try:
                qwen_result = json.loads(content)
            except json.JSONDecodeError:
                try:
                    from json_repair import repair_json
                    qwen_result = repair_json(content, return_objects=True)
                except Exception:
                    qwen_result = {"error": "json_parse_failed"}
        else:
            qwen_result = {"error": "qwen_call_failed"}

        # Print diff
        n_sum = _summarise(nemo_result)
        q_sum = _summarise(qwen_result)
        print(f"\nLatency:   Nemotron={t_nemo:.1f}s   Qwen={t_qwen:.1f}s")
        print(f"\n{'field':<25} {'Nemotron':<40} {'Qwen':<40} winner")
        print("-" * 115)
        for field, n, q, w in _field_diff(n_sum, q_sum):
            n_str = str(n)[:38]
            q_str = str(q)[:38]
            print(f"{field:<25} {n_str:<40} {q_str:<40} {w}")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
