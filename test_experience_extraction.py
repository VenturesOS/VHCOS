"""
Test script to verify experience_years extraction from Naukri "2y 5m" format.
"""
import asyncio
import sys
sys.path.insert(0, '/app/backend')

async def test_experience_extraction():
    """Test that experience_years is extracted correctly from Naukri profiles."""
    
    print("=" * 70)
    print("🧪 TESTING EXPERIENCE EXTRACTION FIX")
    print("=" * 70)
    
    from services.llm_fallback_service import extract_full_profile_fallback
    
    # Simulate Naukri profile text with "2y 5m" format
    test_profile = """
    Aman Thakur
    2y 5m
    ₹ 4.50 Lacs (expects: ₹ 7.50 Lacs)
    Bhopal
    Current: Executive at JBM Auto Components since Jun '25
    15 Days or less notice period
    
    Work Experience:
    Jun '25 till date - Executive at JBM Auto Components
    May 2024 – May 2025 - Apprenticeship at JK Tyre Industries Ltd.
    May 2022 – Nov 2022 - DET at Johndeere India Pvt.Ltd.
    
    Education:
    B.Tech, Mechanical Engineering, 2025
    Madhav Institute of Technology and Science, Gwalior
    
    Skills:
    AutoCAD, Excel, Production Planning, Preventive Maintenance, 5S, Leadership
    """
    
    print("\n[1/3] Testing with '2y 5m' format...")
    result = await extract_full_profile_fallback(
        raw_text=test_profile,
        candidate_name="Aman Thakur"
    )
    
    if result.get("success"):
        data = result["data"]
        exp_years = data.get("experience_years", 0)
        
        print(f"\n✅ Extraction successful via: {result['source']}")
        print(f"   Name: {data.get('name')}")
        print(f"   Experience Years: {exp_years}")
        print(f"   Work Experience Entries: {len(data.get('work_experience', []))}")
        print(f"   Skills: {len(data.get('key_skills', []))}")
        
        if exp_years == 2:
            print("\n✅ PASS: experience_years extracted correctly (2 years)")
            return True
        elif exp_years == 0:
            print("\n❌ FAIL: experience_years still extracting as 0")
            print(f"   Full data: {data}")
            return False
        else:
            print(f"\n⚠️  WARNING: experience_years = {exp_years} (expected 2)")
            return False
    else:
        print(f"\n❌ FAIL: Extraction failed - {result.get('error')}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_experience_extraction())
    sys.exit(0 if success else 1)
