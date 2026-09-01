"""Solo Nemotron test — show extraction quality on a realistic profile."""
import asyncio, json, os, sys, time
from dotenv import load_dotenv; load_dotenv()
sys.path.insert(0, '/app/backend')
from services.llm_fallback_service import _call_nemotron, _extract_json_from_response
import inspect, re
import services.llm_fallback_service as lfs

PROFILES = [
    ("Rich profile (Naukri-style)", """Rajesh Kumar Sharma
Senior Software Engineer at Tata Consultancy Services
Bengaluru | 8y 3m experience | ₹18 Lacs (expects: ₹28 Lacs) | Notice: 60 days

Skills: Python, Django, FastAPI, PostgreSQL, Redis, Kubernetes, AWS, Docker, Microservices, REST APIs, GraphQL, Kafka, MongoDB, CI/CD, Terraform

Experience:
- Senior Software Engineer, Tata Consultancy Services (Jun 2021 - Present)
  Led migration of monolith to microservices architecture. Built async job processing pipeline handling 2M events/day. Mentored 5 junior engineers.

- Software Engineer, Wipro Ltd (Aug 2018 - May 2021)
  Developed customer analytics dashboard in Django + React. Reduced API response times by 60%.

- Junior Developer, Infosys (Aug 2016 - Jul 2018)
  Full-stack development on client projects in Java Spring Boot and Angular.

Education:
- B.Tech Computer Science, VIT University, 2016, 8.4 CGPA
- Higher Secondary, DPS Delhi, 2012, 92%

Certifications: AWS Solutions Architect (2022), Kubernetes CKA (2023)
Languages: English, Hindi, Kannada
Phone: 9876543210 | Email: rajesh.sharma@example.com"""),
    ("Sparse profile (minimal data)", """Priya Nair
QA Analyst | Chennai | 3 years exp
Skills: Selenium, JIRA
priya.n@yahoo.com | 9812345678"""),
    ("Complex CTC (Lakhs + expects)", """Amit Verma
Head of Manufacturing
Mahindra & Mahindra Ltd, Pune | 22y | ₹60 Lacs (expects: ₹80 Lacs) | Immediate

22 years in automotive manufacturing operations. Led plant transformation with ₹200 Cr capex. B.E. Mechanical from IIT Bombay (1999).

Current: Head Mfg at Mahindra since 2019.
Previous: Sr. GM at Tata Motors (2010-2019), Manager at Bajaj Auto (2001-2010).
Notice: Immediate (serving)"""),
]

src = inspect.getsource(lfs.extract_full_profile_fallback)
m = re.search(r'system_prompt = """(.*?)"""', src, re.DOTALL)
SYSTEM_PROMPT = m.group(1)

async def main():
    for label, profile in PROFILES:
        print(f"\n{'='*70}\nPROFILE: {label}\n{'='*70}")
        t0 = time.monotonic()
        resp = await _call_nemotron(SYSTEM_PROMPT, f"Extract complete profile:\n\n{profile}")
        dt = time.monotonic() - t0
        if not resp:
            print(f"  ✗ FAILED (took {dt:.1f}s) — likely 503; retry with delay in production")
            await asyncio.sleep(20)
            continue
        content = _extract_json_from_response(resp["content"])
        try:
            r = json.loads(content)
        except json.JSONDecodeError:
            from json_repair import repair_json
            r = repair_json(content, return_objects=True)
        print(f"  latency: {dt:.1f}s   content: {len(content)} chars   finish: {resp.get('finish_reason')}")
        print(f"  name: {r.get('name')!r}")
        print(f"  current_employer: {r.get('current_employer')!r}")
        print(f"  current_designation: {r.get('current_designation')!r}")
        print(f"  location: {r.get('location')!r}")
        print(f"  experience_years: {r.get('experience_years')}")
        print(f"  current_ctc: {r.get('current_ctc')}   expected_ctc: {r.get('expected_ctc')}")
        print(f"  notice_period: {r.get('notice_period')!r}  notice_days: {r.get('notice_period_days')}")
        print(f"  skills ({len(r.get('key_skills') or [])}): {(r.get('key_skills') or [])[:8]}")
        print(f"  work_exp ({len(r.get('work_experience') or [])}):")
        for we in (r.get("work_experience") or [])[:3]:
            print(f"    - {we.get('designation')} @ {we.get('company')} ({we.get('from_date')} → {we.get('to_date')})")
        print(f"  education ({len(r.get('education') or [])}):")
        for ed in (r.get("education") or [])[:2]:
            print(f"    - {ed.get('degree')} {ed.get('specialization','')} @ {ed.get('institution')} ({ed.get('year_of_passing')})")
        print(f"  summary: {(r.get('profile_summary') or '')[:180]}...")
        await asyncio.sleep(20)  # avoid Nemotron burst rate limit

asyncio.run(main())
