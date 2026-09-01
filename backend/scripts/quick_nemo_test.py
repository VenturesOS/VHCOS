"""Quick Nemotron vs Qwen sanity check on one hardcoded profile."""
import asyncio, json, os, time, sys
from dotenv import load_dotenv; load_dotenv()
sys.path.insert(0, '/app/backend')
from services.llm_fallback_service import _call_nemotron, _call_runpod_vllm, _extract_json_from_response
import inspect, re
import services.llm_fallback_service as lfs

# Realistic Naukri-style profile
PROFILE = """Rajesh Kumar Sharma
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
Languages: English, Hindi, Kannada"""

# Extract real prompt
src = inspect.getsource(lfs.extract_full_profile_fallback)
m = re.search(r'system_prompt = """(.*?)"""', src, re.DOTALL)
SYSTEM_PROMPT = m.group(1)
USER_PROMPT = f"Extract complete profile:\n\n{PROFILE}"

async def call_and_parse(fn, name):
    t0 = time.monotonic()
    resp = await fn(SYSTEM_PROMPT, USER_PROMPT)
    dt = time.monotonic() - t0
    if not resp:
        return {"error": f"{name} call returned None", "_time": dt}
    content = _extract_json_from_response(resp["content"])
    try:
        r = json.loads(content)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            r = repair_json(content, return_objects=True)
        except Exception as e:
            r = {"error": f"parse fail: {e}", "raw": content[:500]}
    r["_time"] = dt
    r["_content_len"] = len(content)
    return r

async def main():
    print("=== Nemotron call ===")
    nemo = await call_and_parse(_call_nemotron, "Nemotron")
    print(f"time={nemo.get('_time'):.1f}s, content_chars={nemo.get('_content_len')}")

    print("\n=== Qwen (RunPod) call ===")
    qwen = await call_and_parse(_call_runpod_vllm, "Qwen")
    print(f"time={qwen.get('_time'):.1f}s, content_chars={qwen.get('_content_len')}")

    print("\n=== SIDE-BY-SIDE ===")
    fields = ["name","current_employer","current_designation","location",
              "experience_years","current_ctc","expected_ctc","notice_period_days"]
    print(f"{'field':<22} {'Nemotron':<35} {'Qwen':<35} {'match'}")
    print("-"*100)
    for f in fields:
        n, q = nemo.get(f), qwen.get(f)
        match = "✓" if n == q else "✗"
        print(f"{f:<22} {str(n)[:33]:<35} {str(q)[:33]:<35} {match}")
    n_sk = len(nemo.get("key_skills") or [])
    q_sk = len(qwen.get("key_skills") or [])
    n_ex = len(nemo.get("work_experience") or [])
    q_ex = len(qwen.get("work_experience") or [])
    n_ed = len(nemo.get("education") or [])
    q_ed = len(qwen.get("education") or [])
    print(f"{'skills_count':<22} {n_sk:<35} {q_sk:<35}")
    print(f"{'work_exp_count':<22} {n_ex:<35} {q_ex:<35}")
    print(f"{'education_count':<22} {n_ed:<35} {q_ed:<35}")

asyncio.run(main())
