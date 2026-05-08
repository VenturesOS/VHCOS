"""
Comprehensive side-by-side quality test: RunPod Qwen 14B vs Claude Haiku 4.5
Tests with 5 messy Naukri-style profiles.
"""
import asyncio, os, json, time
os.environ['RUNPOD_VLLM_URL'] = os.environ.get('RUNPOD_VLLM_URL', 'https://d34lxvlivy5s62-8000.proxy.runpod.net')
os.environ['RUNPOD_MODEL_NAME'] = os.environ.get('RUNPOD_MODEL_NAME', 'Qwen/Qwen2.5-14B-Instruct-AWQ')

from services.llm_fallback_service import (
    _call_runpod_vllm, _call_emergent_llm_haiku, _extract_json_from_response,
    extract_full_profile_fallback
)

TEST_PROFILES = [
    {
        "name": "Priya Mehta",
        "text": """Priya Mehta
priya.mehta92@gmail.com | 8899776655
7y 3m Experience | Pune, Maharashtra
Current CTC: 18.5 Lakhs | Expected CTC: 28 Lakhs
Notice Period: 3 Months
Lead Data Engineer at Wipro Technologies
Previous: Senior Data Analyst at Capgemini (2019-2022)
Junior Analyst at Accenture (2017-2019)
Skills: Python, SQL, Apache Spark, Hadoop, AWS Redshift, Tableau, Power BI, ETL, Data Warehousing
Education: M.Tech Data Science - BITS Pilani (2017), B.E. CS - Pune University (2015)""",
        "expected": {"experience": 7.03, "ctc": 1850000, "work_exp": 3, "education": 2}
    },
    {
        "name": "Amit Kumar Singh",
        "text": """Amit Kumar Singh
amit.k.singh@yahoo.com | +91-7766554433
12y 11m | Senior Manager - Operations
Location: Noida, UP
CTC: 32 Lakhs | Expected: 45 Lakhs
Notice: Immediate
Currently at Amazon India since 2020
Operations Manager at Flipkart (2016-2020)
Assistant Manager at Snapdeal (2013-2016)
Trainee at Paytm (2011-2013)
Skills: Supply Chain, Logistics, Warehouse Mgmt, SAP, Excel, Team Management, P&L, Vendor Management
MBA - IIM Lucknow (2011), B.Com - Delhi University (2009)
Languages: English, Hindi""",
        "expected": {"experience": 12.11, "ctc": 3200000, "work_exp": 4, "education": 2}
    },
    {
        "name": "Sneha Reddy",
        "text": """Sneha Reddy
sneha.reddy@outlook.com | 9988776655
2y 5m Experience
UI/UX Designer | Hyderabad
Current Salary: 8 Lakhs | Expected: 14 Lakhs
Notice Period: 30 Days
UI Designer at Zoho Corp (Jun 2023 - Present)
Junior Designer Intern at Freshworks (Jan 2022 - May 2023)
Skills: Figma, Adobe XD, Sketch, HTML, CSS, JavaScript, User Research, Wireframing, Prototyping
B.Des Visual Communication - NID Ahmedabad (2021)""",
        "expected": {"experience": 2.05, "ctc": 800000, "work_exp": 2, "education": 1}
    },
    {
        "name": "Rajesh Patel",
        "text": """Rajesh Patel
rajesh.patel55@gmail.com | 9123456789
0y 8m | Fresher - Software Developer
Ahmedabad, Gujarat
CTC: 4.5 Lakhs | Expected: 6 Lakhs
Notice: 15 Days
Software Developer Trainee at TCS (Aug 2025 - Present)
Intern at Infosys (May 2025 - Jul 2025)
Skills: Java, Spring Boot, MySQL, Git, REST API, HTML, CSS
B.Tech Computer Engineering - Gujarat Technological University (2025)
CGPA: 8.2""",
        "expected": {"experience": 0.08, "ctc": 450000, "work_exp": 2, "education": 1}
    },
    {
        "name": "Kavita Sharma",
        "text": """Kavita Sharma
kavita.sharma@hotmail.com
Phone: 8877665544
10y 0m | Director of Engineering
Bangalore
Current CTC: 55 Lakhs per annum | Expected CTC: 75 Lakhs
Notice Period: 90 Days (3 Months)
Director of Engineering at Swiggy (2022 - Present)
Engineering Manager at Uber India (2019 - 2022)
Senior Software Engineer at Microsoft (2016 - 2019)
Software Engineer at Oracle (2014 - 2016)
Skills: System Design, Microservices, AWS, GCP, Python, Go, Kubernetes, Docker, CI/CD, Team Leadership, Agile, Scrum
Education: M.Tech CS - IIT Bombay (2014), B.Tech IT - NIT Trichy (2012)
Certifications: AWS Solutions Architect Professional""",
        "expected": {"experience": 10.00, "ctc": 5500000, "work_exp": 4, "education": 2}
    }
]

SYSTEM_PROMPT = """Extract candidate data from profile text. Return ONLY valid JSON:
{"name": "string", "experience_years": number, "current_ctc": number_in_rupees, "expected_ctc": number_in_rupees, "notice_period": "string", "notice_period_days": number, "current_employer": "string", "current_designation": "string", "phone": "string", "email": "string", "location": "string", "key_skills": ["skill1"], "work_experience": [{"company": "string", "designation": "string"}], "education": [{"degree": "string", "institution": "string"}], "profile_summary": "2 sentences"}

RULES:
- CTC: Convert lakhs to rupees (1 lakh = 100000, "18.5 Lakhs" = 1850000)
- Experience: DO NOT divide months by 12. Formula: Years + (Months/100). "7y 3m"=7.03, "2y 5m"=2.05, "12y 11m"=12.11
- Notice: Convert to days (Immediate=0, 30 Days=30, 3 Months=90)
- Extract ALL skills mentioned. Return ONLY JSON."""

async def test_single(profile, provider):
    """Test extraction with a specific provider."""
    start = time.time()
    user_prompt = f"Extract:\n{profile['text']}"
    
    if provider == "runpod":
        resp = await _call_runpod_vllm(SYSTEM_PROMPT, user_prompt)
    else:
        resp = await _call_emergent_llm_haiku(SYSTEM_PROMPT, user_prompt)
    
    elapsed = round(time.time() - start, 1)
    
    if not resp:
        return {"error": True, "time": elapsed}
    
    try:
        content = _extract_json_from_response(resp["content"])
        data = json.loads(content)
        data["_time"] = elapsed
        return data
    except:
        return {"error": True, "raw": resp["content"][:200], "time": elapsed}

async def main():
    print("=" * 80)
    print("QUALITY TEST: RunPod Qwen 14B vs Claude Haiku 4.5")
    print("=" * 80)
    
    runpod_score = 0
    haiku_score = 0
    runpod_fails = 0
    total_fields = 0
    
    for profile in TEST_PROFILES:
        print(f"\n{'─' * 60}")
        print(f"PROFILE: {profile['name']}")
        print(f"{'─' * 60}")
        
        # Test both in parallel
        rp, hk = await asyncio.gather(
            test_single(profile, "runpod"),
            test_single(profile, "haiku")
        )
        
        expected = profile["expected"]
        
        if rp.get("error"):
            print(f"  RunPod: FAILED ({rp.get('time', '?')}s)")
            runpod_fails += 1
        else:
            exp_match = rp.get("experience_years") == expected["experience"]
            ctc_match = rp.get("current_ctc") == expected["ctc"]
            we_match = len(rp.get("work_experience", [])) == expected["work_exp"]
            ed_match = len(rp.get("education", [])) == expected["education"]
            skills_count = len(rp.get("key_skills", []))
            
            rp_correct = sum([exp_match, ctc_match, we_match, ed_match])
            runpod_score += rp_correct
            total_fields += 4
            
            print(f"  RunPod ({rp.get('_time', '?')}s):")
            print(f"    Exp: {rp.get('experience_years')} {'OK' if exp_match else 'WRONG (expected ' + str(expected['experience']) + ')'}") 
            print(f"    CTC: {rp.get('current_ctc')} {'OK' if ctc_match else 'WRONG (expected ' + str(expected['ctc']) + ')'}")
            print(f"    Work: {len(rp.get('work_experience', []))} {'OK' if we_match else 'WRONG (expected ' + str(expected['work_exp']) + ')'}")
            print(f"    Edu: {len(rp.get('education', []))} {'OK' if ed_match else 'WRONG (expected ' + str(expected['education']) + ')'}")
            print(f"    Skills: {skills_count} | Summary: {'Yes' if rp.get('profile_summary') else 'No'}")
        
        if hk.get("error"):
            print(f"  Haiku: FAILED ({hk.get('time', '?')}s)")
        else:
            exp_match = hk.get("experience_years") == expected["experience"]
            ctc_match = hk.get("current_ctc") == expected["ctc"]
            we_match = len(hk.get("work_experience", [])) == expected["work_exp"]
            ed_match = len(hk.get("education", [])) == expected["education"]
            skills_count = len(hk.get("key_skills", []))
            
            hk_correct = sum([exp_match, ctc_match, we_match, ed_match])
            haiku_score += hk_correct
            
            print(f"  Haiku ({hk.get('_time', '?')}s):")
            print(f"    Exp: {hk.get('experience_years')} {'OK' if exp_match else 'WRONG (expected ' + str(expected['experience']) + ')'}") 
            print(f"    CTC: {hk.get('current_ctc')} {'OK' if ctc_match else 'WRONG (expected ' + str(expected['ctc']) + ')'}")
            print(f"    Work: {len(hk.get('work_experience', []))} {'OK' if we_match else 'WRONG (expected ' + str(expected['work_exp']) + ')'}")
            print(f"    Edu: {len(hk.get('education', []))} {'OK' if ed_match else 'WRONG (expected ' + str(expected['education']) + ')'}")
            print(f"    Skills: {skills_count} | Summary: {'Yes' if hk.get('profile_summary') else 'No'}")
    
    print(f"\n{'=' * 60}")
    print(f"FINAL SCORES (out of {total_fields} field checks):")
    print(f"  RunPod Qwen 14B: {runpod_score}/{total_fields} ({round(runpod_score/max(total_fields,1)*100)}%) | Failures: {runpod_fails}")
    print(f"  Claude Haiku:    {haiku_score}/{total_fields} ({round(haiku_score/max(total_fields,1)*100)}%)")
    print(f"{'=' * 60}")

asyncio.run(main())
