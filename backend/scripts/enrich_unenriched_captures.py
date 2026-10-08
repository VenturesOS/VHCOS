"""AI-enrich extension captures that never got enriched.

The 9.2k captures parked as identity observations were replayed into the bank
from their snapshot, which is pre-enrichment — so they landed with
enrichment_status unset. This runs the same chain a live capture uses
(Nemotron Super 120B → Nemotron 550B → Mistral Nemotron) over those rows.

    python3 -m scripts.enrich_unenriched_captures --count
    python3 -m scripts.enrich_unenriched_captures --apply [--limit=500] [--workers=4]
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

QUERY = {
    "source": {"$regex": "_extension$"},
    "enrichment_status": {"$in": [None, "", "pending"]},
}
if "--recovered-only" in sys.argv:
    QUERY["recovered_from_observation"] = True
FIELDS = {"_id": 0, "id": 1, "name": 1, "raw_text_for_enrichment": 1, "email": 1, "phone": 1,
          "headline": 1, "summary": 1, "current_employer": 1, "designation": 1,
          "experience": 1, "skills": 1, "recruiter_phone": 1, "recruiter_email": 1}


def build_text(row: dict) -> str:
    """Same shape the capture path composes when the extension sent no raw text."""
    parts = []
    for label, key in (("Name", "name"), ("Email", "email"), ("Phone", "phone"),
                       ("Headline", "headline"), ("Summary", "summary"),
                       ("Current Company", "current_employer"),
                       ("Current Designation", "designation")):
        if row.get(key):
            parts.append(f"{label}: {str(row[key])[:1500]}")
    exp = row.get("experience") or []
    if exp:
        parts.append("\nWork Experience:")
        for e in exp[:5]:
            if isinstance(e, dict) and e.get("designation") and e.get("company"):
                parts.append(f"- {e['designation']} at {e['company']}")
    skills = [s for s in (row.get("skills") or []) if isinstance(s, str)]
    if skills:
        parts.append("\nSkills: " + ", ".join(skills[:10]))
    return "\n".join(parts)


async def worker(db, q: asyncio.Queue, done: list):
    from routes.extension import _background_full_groq_enrich
    while True:
        row = await q.get()
        if row is None:
            q.task_done()
            return
        try:
            text = row.get("raw_text_for_enrichment") or build_text(row)
            if len(text) < 60:
                done.append(0)
            else:
                # The enrichment write is guarded on this field, so it has to be
                # on the row before the chain runs.
                if not row.get("raw_text_for_enrichment"):
                    await db.candidate_bank.update_one(
                        {"id": row["id"]}, {"$set": {"raw_text_for_enrichment": text}})
                await _background_full_groq_enrich(
                    row["id"], row.get("name") or "", text,
                    row.get("recruiter_phone") or "", row.get("recruiter_email") or "",
                )
                done.append(1)
        except Exception as e:
            print(f"  !! {row.get('name')}: {str(e)[:120]}", flush=True)
        finally:
            q.task_done()
        if len(done) % 200 == 0:
            print(f"  …{len(done)} processed ({sum(done)} enriched)", flush=True)


async def main(apply: bool, limit: int, workers: int):
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    total = await db.candidate_bank.count_documents(QUERY)
    print(f"unenriched extension captures: {total}")
    if not apply:
        c.close()
        return

    cur = db.candidate_bank.find(QUERY, FIELDS)
    if limit:
        cur = cur.limit(limit)
    q: asyncio.Queue = asyncio.Queue(maxsize=workers * 4)
    done: list = []
    tasks = [asyncio.create_task(worker(db, q, done)) for _ in range(workers)]
    async for row in cur:
        await q.put(row)
    for _ in tasks:
        await q.put(None)
    await asyncio.gather(*tasks)
    print(f"processed {len(done)}, enriched {sum(done)}")
    c.close()


asyncio.run(main(
    "--apply" in sys.argv,
    int(next((a.split("=")[1] for a in sys.argv if a.startswith("--limit=")), 0)),
    int(next((a.split("=")[1] for a in sys.argv if a.startswith("--workers=")), 4)),
))
