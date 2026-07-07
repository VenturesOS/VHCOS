"""
Content Sprint Kickstart — Batch-generate all 5 pillars + 15 clusters as drafts.

Reads the pillar/cluster spec from docs/CONTENT_SPRINT_STRATEGY.md structure
and fires POST /api/blog/generate for each. Each call takes ~30-60s (Qwen)
so the whole script runs ~15-25 min. Runs sequentially to respect LLM rate
limits.

Output: 20 draft blog posts sitting in the admin queue at
`/admin/blog-engine`. Human editors then review, tweak, and publish 1
pillar + 3 clusters per week (5 weeks) per the strategy doc.

Usage (prod):
    cd /home/ubuntu/vhc-platform/backend
    ADMIN_TOKEN="$(cat /tmp/admin-jwt)"  # get from browser DevTools
    BASE_URL="https://ventureshrd.com"    # or preview URL
    python3 scripts/content_sprint_kickstart.py \\
        --base-url "$BASE_URL" --token "$ADMIN_TOKEN"

Optional flags:
    --only-pillars      Generate only the 5 pillar articles (skip 15 clusters)
    --pillar N          Generate only pillar N (1-5) and its 3 clusters
    --dry-run           Print what would be sent without calling the API
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from typing import Any

try:
    import httpx
except ImportError:
    print("ERROR: `httpx` not installed. Run: pip install httpx")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Content plan — mirrors docs/CONTENT_SPRINT_STRATEGY.md
# ---------------------------------------------------------------------------

SPRINT_PLAN: list[dict[str, Any]] = [
    {
        "pillar": {
            "blog_type": "employer",
            "topic": "Manufacturing Recruitment Agency in Pune — Complete Hiring Guide 2026",
            "industry": "Manufacturing / Automotive OEM",
            "region": "india",
            "keywords": "manufacturing recruitment agency pune, plant hiring pune, "
                        "industrial recruitment pune, shopfloor engineer hiring pune, "
                        "chakan MIDC recruitment, talegaon plant hiring",
        },
        "clusters": [
            {
                "blog_type": "employer",
                "topic": "Plant Head jobs in Pune — Salary benchmarks 2026",
                "industry": "Manufacturing",
                "region": "india",
                "keywords": "plant head jobs pune salary, plant head compensation pune, "
                            "plant head hiring pune 2026",
            },
            {
                "blog_type": "employer",
                "topic": "How Chakan MIDC plants are hiring shopfloor engineers in 2026",
                "industry": "Manufacturing",
                "region": "india",
                "keywords": "chakan MIDC shopfloor engineer hiring, chakan plant hiring, "
                            "shopfloor engineer jobs pune",
            },
            {
                "blog_type": "employer",
                "topic": "Automotive Tier-1 supplier hiring in Talegaon — 2026 outlook",
                "industry": "Automotive",
                "region": "india",
                "keywords": "automotive tier 1 hiring talegaon, tier 1 supplier hiring pune, "
                            "automotive plant recruitment talegaon",
            },
        ],
    },
    {
        "pillar": {
            "blog_type": "employer",
            "topic": "Plant Head Hiring in India — Salary, Skills, Sourcing",
            "industry": "Manufacturing",
            "region": "india",
            "keywords": "plant head hiring india, plant head salary india, "
                        "plant head skills, plant head recruitment strategy, "
                        "senior manufacturing hiring india",
        },
        "clusters": [
            {
                "blog_type": "employer",
                "topic": "Plant Head vs Operations Head — Roles, KPIs and Compensation",
                "industry": "Manufacturing",
                "region": "india",
                "keywords": "plant head vs operations head, plant head kpi, "
                            "operations head compensation india",
            },
            {
                "blog_type": "candidate",
                "topic": "How to move from Production Manager to Plant Head in 3 years",
                "industry": "Manufacturing",
                "category": "career-growth",
                "keywords": "production manager to plant head, plant head career path, "
                            "manufacturing leadership career",
            },
            {
                "blog_type": "employer",
                "topic": "5 red flags when hiring a Plant Head in India",
                "industry": "Manufacturing",
                "region": "india",
                "keywords": "plant head hiring mistakes, plant head interview red flags, "
                            "senior manufacturing hiring pitfalls",
            },
        ],
    },
    {
        "pillar": {
            "blog_type": "employer",
            "topic": "Industrial Recruitment Trends 2026 — What Manufacturing HR Leaders Need to Know",
            "industry": "Manufacturing",
            "region": "india",
            "keywords": "industrial recruitment trends 2026, manufacturing hiring trends india, "
                        "shopfloor hiring 2026, industrial HR trends, plant hiring benchmarks",
        },
        "clusters": [
            {
                "blog_type": "employer",
                "topic": "Attrition in Indian manufacturing plants — 2026 benchmarks",
                "industry": "Manufacturing",
                "region": "india",
                "keywords": "manufacturing attrition india 2026, shopfloor attrition benchmarks, "
                            "plant retention strategy",
            },
            {
                "blog_type": "employer",
                "topic": "Notice-period trends across Indian OEMs in 2026",
                "industry": "Manufacturing",
                "region": "india",
                "keywords": "notice period trends india manufacturing, OEM notice period 2026, "
                            "manufacturing hiring speed",
            },
            {
                "blog_type": "employer",
                "topic": "Cost-per-hire benchmarks for Indian manufacturing (2026 data)",
                "industry": "Manufacturing",
                "region": "india",
                "keywords": "cost per hire manufacturing india, plant hiring cost, "
                            "shopfloor recruiting spend benchmark",
            },
        ],
    },
    {
        "pillar": {
            "blog_type": "employer",
            "topic": "Executive Search for Manufacturing — When to Use a Retained Firm vs In-House",
            "industry": "Manufacturing",
            "region": "india",
            "keywords": "executive search manufacturing india, retained executive search plant, "
                        "manufacturing CXO hiring, industrial executive recruitment",
        },
        "clusters": [
            {
                "blog_type": "employer",
                "topic": "Retained vs Contingent search — cost, speed, quality (2026)",
                "industry": "Manufacturing",
                "region": "india",
                "keywords": "retained vs contingent search, executive search pricing india, "
                            "retained search ROI",
            },
            {
                "blog_type": "employer",
                "topic": "How to shortlist an executive search firm for your plant",
                "industry": "Manufacturing",
                "region": "india",
                "keywords": "executive search firm shortlist, retained search vendor evaluation, "
                            "manufacturing search partner",
            },
            {
                "blog_type": "employer",
                "topic": "Confidential replacements — hiring a Plant Head without alerting the incumbent",
                "industry": "Manufacturing",
                "region": "india",
                "keywords": "confidential executive search, silent replacement plant head, "
                            "discreet CXO hiring india",
            },
        ],
    },
    {
        "pillar": {
            "blog_type": "candidate",
            "topic": "Manufacturing Career Path in India 2026 — Junior Engineer to Plant Head",
            "industry": "Manufacturing",
            "category": "career-growth",
            "keywords": "manufacturing career path india, plant engineer career growth, "
                        "manufacturing leadership career, shopfloor to CXO india",
        },
        "clusters": [
            {
                "blog_type": "candidate",
                "topic": "Best certifications for a Manufacturing Engineer in India (2026)",
                "industry": "Manufacturing",
                "category": "skills",
                "keywords": "manufacturing engineer certifications india, six sigma manufacturing, "
                            "TPM certification, lean manufacturing certification",
            },
            {
                "blog_type": "candidate",
                "topic": "Salary negotiation guide for mid-career manufacturing professionals",
                "industry": "Manufacturing",
                "category": "salary",
                "keywords": "salary negotiation manufacturing india, plant engineer salary hike, "
                            "manufacturing counter-offer strategy",
            },
            {
                "blog_type": "candidate",
                "topic": "How to switch from an IT-services company to a manufacturing plant role",
                "industry": "Manufacturing",
                "category": "career-change",
                "keywords": "IT to manufacturing career switch, manufacturing career change india, "
                            "software to plant engineer transition",
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def fire_generate(client: httpx.Client, base_url: str, token: str, payload: dict) -> tuple[bool, str]:
    """Call POST /api/blog/generate. Returns (ok, message)."""
    url = f"{base_url.rstrip('/')}/api/blog/generate"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r = client.post(url, headers=headers, json=payload, timeout=180.0)
    except httpx.TimeoutException:
        return False, "timeout (LLM took >180s — try re-running for this topic)"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    if r.status_code == 200:
        data = r.json()
        title = (data or {}).get("blog", {}).get("title") or (data or {}).get("title") or "(untitled)"
        return True, f"draft saved: {title[:80]}"
    return False, f"HTTP {r.status_code}: {r.text[:200]}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base-url", required=True, help="e.g. https://ventureshrd.com")
    ap.add_argument("--token", required=True, help="Admin JWT from browser DevTools")
    ap.add_argument("--only-pillars", action="store_true", help="Generate only the 5 pillar articles")
    ap.add_argument("--pillar", type=int, choices=range(1, 6), help="Generate only pillar N and its clusters")
    ap.add_argument("--dry-run", action="store_true", help="Print without calling the API")
    ap.add_argument("--sleep-between", type=float, default=3.0, help="Seconds between calls (LLM cooldown)")
    args = ap.parse_args()

    # Filter plan
    plan = SPRINT_PLAN
    if args.pillar:
        plan = [SPRINT_PLAN[args.pillar - 1]]

    # Flatten to a job list
    jobs = []
    for idx, block in enumerate(plan, 1):
        jobs.append(("PILLAR", idx, block["pillar"]))
        if not args.only_pillars:
            for cid, cluster in enumerate(block["clusters"], 1):
                jobs.append((f"CLUSTER-{cid}", idx, cluster))

    print("\n=== Content Sprint Kickstart ===")
    print(f"Base URL:  {args.base_url}")
    print(f"Jobs:      {len(jobs)}  ({sum(1 for j in jobs if j[0]=='PILLAR')} pillars, "
          f"{sum(1 for j in jobs if j[0].startswith('CLUSTER'))} clusters)")
    print(f"Est. time: ~{len(jobs) * 45 // 60}m at ~45s/article (Qwen)\n")

    with httpx.Client() as client:
        ok = 0
        fail = 0
        for i, (label, p_idx, payload) in enumerate(jobs, 1):
            print(f"[{i}/{len(jobs)}] P{p_idx} {label}: {payload['topic'][:70]}")
            if args.dry_run:
                print(f"    DRY-RUN payload={json.dumps(payload)[:120]}...")
                ok += 1
                continue
            success, msg = fire_generate(client, args.base_url, args.token, payload)
            if success:
                ok += 1
                print(f"    ✅ {msg}")
            else:
                fail += 1
                print(f"    ❌ {msg}")
            if i < len(jobs):
                time.sleep(args.sleep_between)

    print(f"\n=== Done. Success: {ok}  Failed: {fail} ===")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
