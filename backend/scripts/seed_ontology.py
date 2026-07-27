#!/usr/bin/env python3
"""
seed_ontology.py — bootstrap the Neural Schema dictionaries
===========================================================

Three passes (run from backend/ so imports resolve):

  python scripts/seed_ontology.py                    # pass 1: export + counts
  python scripts/seed_ontology.py --bootstrap        # pass 2: LLM proposals
  python scripts/seed_ontology.py --promote          # pass 3: approved → live

Pass 1 aggregates distinct raw values from candidate_bank into staging
collections ontology_candidates_{skill|role|company|location} as
{raw_value, count, status:"pending"} — top 5000/2000/2000/500.

Pass 2 sends pending rows in batches of 50 to the agent LLM adapter
(services.screening_llm — Groq env) asking for STRICT JSON proposals
{canonical_name, aliases, category, parent}; writes status:"proposed".
Resumable: only status:"pending" rows are processed; a crash cannot
duplicate. Review + approve via routes in ontology admin (or directly
flip status to "approved" in Mongo for bulk-obvious rows).

Pass 3 upserts approved rows into skills_ontology / roles_ontology /
companies_ontology / locations_ontology using models.neural_schema, and
imports every pair from services.synonym_service as aliases first.
"""
import argparse
import asyncio
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from models.neural_schema import (  # noqa: E402
    SkillEntity, RoleEntity, CompanyEntity, LocationEntity, slug_id, utcnow,
)
from services import screening_llm  # noqa: E402

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "vhc_talent_os")
if not MONGO_URL:
    sys.exit("MONGO_URL required")

SPECS = {
    "skill":    {"fields": ["key_skills", "skills"], "cap": 5000, "list": True},
    "role":     {"fields": ["current_designation", "designation"], "cap": 2000, "list": False},
    "company":  {"fields": ["current_employer", "current_company", "company"], "cap": 2000, "list": False},
    "location": {"fields": ["current_location", "location"], "cap": 500, "list": False},
}
LIVE = {"skill": ("skills_ontology", SkillEntity, "skill"),
        "role": ("roles_ontology", RoleEntity, "role"),
        "company": ("companies_ontology", CompanyEntity, "co"),
        "location": ("locations_ontology", LocationEntity, "loc")}


async def pass_export(db):
    for etype, spec in SPECS.items():
        counter = Counter()
        cursor = db.candidate_bank.find({}, {f: 1 for f in spec["fields"]})
        async for doc in cursor:
            for f in spec["fields"]:
                v = doc.get(f)
                vals = v if isinstance(v, list) else ([v] if isinstance(v, str) else [])
                for raw in vals:
                    raw = (raw or "").strip()
                    if 1 < len(raw) < 80:
                        counter[raw] += 1
        staging = db[f"ontology_candidates_{etype}"]
        new = 0
        for raw, count in counter.most_common(spec["cap"]):
            r = await staging.update_one(
                {"raw_value": raw},
                {"$set": {"count": count, "updated_at": utcnow()},
                 "$setOnInsert": {"status": "pending", "created_at": utcnow()}},
                upsert=True)
            new += 1 if r.upserted_id else 0
        total = await staging.count_documents({})
        print(f"  {etype:9s}: {len(counter):,} distinct → staged {total:,} (new {new:,})")


_PROMPT = (
    "You canonicalize Indian recruitment {etype} names. For each raw value return "
    'JSON: {{"raw": "<input>", "canonical_name": "<clean canonical>", '
    '"aliases": ["<common variants>"], "category": "<one of: {cats}>", '
    '"parent": "<broader parent name or null>"}}. '
    "Respond with ONLY a JSON array covering every input, nothing else."
)
_CATS = {"skill": "technical|functional|tool|certification|soft",
         "role": "role", "company": "company", "location": "location"}


async def pass_bootstrap(db, batch=50):
    for etype in SPECS:
        staging = db[f"ontology_candidates_{etype}"]
        pending = await staging.count_documents({"status": "pending"})
        print(f"  {etype}: {pending:,} pending")
        while True:
            rows = await staging.find({"status": "pending"}).sort("count", -1).limit(batch).to_list(batch)
            if not rows:
                break
            raws = [r["raw_value"] for r in rows]
            out = await screening_llm._chat(
                system=_PROMPT.format(etype=etype, cats=_CATS[etype]),
                user=json.dumps(raws, ensure_ascii=False),
                max_tokens=2500, temperature=0)
            proposals = {}
            if out:
                try:
                    arr = json.loads(out[out.index("["): out.rindex("]") + 1])
                    proposals = {p.get("raw"): p for p in arr if isinstance(p, dict)}
                except Exception as e:
                    print(f"    parse fail ({e}) — batch marked llm_failed")
            for r in rows:
                p = proposals.get(r["raw_value"])
                if p and p.get("canonical_name"):
                    await staging.update_one({"_id": r["_id"]}, {"$set": {
                        "status": "proposed", "proposal": {
                            "canonical_name": p["canonical_name"],
                            "aliases": p.get("aliases") or [],
                            "category": p.get("category"),
                            "parent": p.get("parent"),
                        }, "updated_at": utcnow()}})
                else:
                    await staging.update_one({"_id": r["_id"]},
                        {"$set": {"status": "llm_failed", "updated_at": utcnow()}})
            done = await staging.count_documents({"status": {"$ne": "pending"}})
            print(f"    …{done:,} processed")


def _entity(etype, canonical, aliases, category, parent, count):
    _, model, prefix = LIVE[etype]
    base = dict(id=slug_id(prefix, canonical), canonical_name=canonical,
                aliases=sorted({a for a in aliases if a and a != canonical}),
                usage_count=count)
    if etype == "skill":
        cat = category if category in ("technical", "functional", "tool", "certification", "soft") else "technical"
        return model(**base, category=cat,
                     parent_skill_id=slug_id(prefix, parent) if parent else None)
    if etype == "role":
        return model(**base, function=parent)
    if etype == "company":
        return model(**base, industry=parent)
    return model(**base, state=parent)


async def pass_promote(db):
    # synonym_service import first — existing aliases become first-class
    try:
        from services.synonym_service import SYNONYMS  # type: ignore
        syn_pairs = sum(len(v) for v in SYNONYMS.values()) if isinstance(SYNONYMS, dict) else 0
        print(f"  synonym_service: importing {syn_pairs} alias links into skills")
        if isinstance(SYNONYMS, dict):
            for canonical, aliases in SYNONYMS.items():
                ent = _entity("skill", canonical, list(aliases), "technical", None, 0)
                await db.skills_ontology.update_one(
                    {"id": ent.id},
                    {"$set": ent.model_dump(exclude={"usage_count"}),
                     "$setOnInsert": {"usage_count": 0}}, upsert=True)
    except Exception as e:
        print(f"  synonym import skipped: {e}")

    for etype in SPECS:
        staging = db[f"ontology_candidates_{etype}"]
        live_name, _, _ = LIVE[etype]
        rows = await staging.find({"status": "approved"}).to_list(100000)
        for r in rows:
            p = r.get("proposal") or {"canonical_name": r["raw_value"], "aliases": []}
            ent = _entity(etype, p["canonical_name"],
                          [r["raw_value"], *(p.get("aliases") or [])],
                          p.get("category"), p.get("parent"), r.get("count", 0))
            await db[live_name].update_one(
                {"id": ent.id},
                {"$set": ent.model_dump(), }, upsert=True)
            await staging.update_one({"_id": r["_id"]}, {"$set": {"status": "promoted"}})
        live = await db[live_name].count_documents({})
        print(f"  {etype:9s}: promoted {len(rows):,} → {live_name} now {live:,}")
        await db[live_name].create_index("aliases")
        await db[live_name].create_index("canonical_name")


async def main(args):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    print(f"\nNeural Schema seeder — db={DB_NAME}")
    if args.bootstrap:
        print("PASS 2 — LLM bootstrap")
        await pass_bootstrap(db)
    elif args.promote:
        print("PASS 3 — promote approved")
        await pass_promote(db)
    else:
        print("PASS 1 — export distinct values")
        await pass_export(db)
    client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--promote", action="store_true")
    asyncio.run(main(ap.parse_args()))
