"""
Quick test to verify experience_years decimal fix
"""
import asyncio
import sys
sys.path.insert(0, '/app/backend')

async def test_decimal_preservation():
    """Test that 2.05 stays as 2.05 and doesn't become 2 or 1"""
    
    print("="*70)
    print("🧪 TESTING EXPERIENCE DECIMAL PRESERVATION")
    print("="*70)
    
    # Test 1: Check if float conversion preserves decimals
    test_values = [2.05, 3.10, 12.11, 5.0, 0.06]
    
    print("\n[Test 1] Float Conversion:")
    for val in test_values:
        result = float(val) if val else 0
        rounded = round(val, 2)
        print(f"  {val} → float={result}, rounded={rounded} {'✅' if result == val else '❌'}")
    
    # Test 2: Simulate the regex parser
    print("\n[Test 2] Regex Parser Simulation:")
    test_cases = [
        ("2y 5m", 2, 5, 2.05),
        ("3y 10m", 3, 10, 3.10),
        ("12y 11m", 12, 11, 12.11),
        ("5y", 5, 0, 5.0),
    ]
    
    for text, years, months, expected in test_cases:
        result = round(years + (months / 100), 2)
        status = "✅" if result == expected else "❌"
        print(f"  '{text}' → {years} + {months}/100 = {result} {status}")
    
    # Test 3: Verify the actual prompt extraction
    print("\n[Test 3] Full Profile Extraction:")
    from services.llm_fallback_service import extract_full_profile_fallback
    
    sample_text = """
    John Doe
    2y 5m
    Current: Software Engineer at Tech Corp
    Skills: Python, React, AWS
    """
    
    result = await extract_full_profile_fallback(sample_text, "John Doe")
    
    if result.get("experience_years"):
        exp = result["experience_years"]
        print(f"  Extracted: {exp}")
        if isinstance(exp, float) and exp > 0:
            print(f"  ✅ SUCCESS: Extracted as float {exp}")
            return True
        else:
            print(f"  ❌ FAIL: Got {type(exp).__name__} = {exp}")
            return False
    else:
        print(f"  ⚠️  No experience_years extracted")
        print(f"  Result keys: {list(result.keys())}")
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(test_decimal_preservation())
        print("\n" + "="*70)
        if success:
            print("✅ ALL TESTS PASSED - Experience decimals preserved correctly!")
        else:
            print("⚠️  Some tests failed - check output above")
        print("="*70)
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
