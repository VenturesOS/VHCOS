#!/usr/bin/env python3
"""
Check if education data exists in raw text
"""
import sys
sys.path.insert(0, '/home/ubuntu/vhc-platform/backend')

from pymongo import MongoClient
from config import mongodb_uri, db_name

# Connect to MongoDB
client = MongoClient(mongodb_uri, tlsAllowInvalidCertificates=True)
db = client[db_name]

# Find profile
profile = db.candidate_bank.find_one(
    {"name": "Deepak Diptiman Nayak"},
    {"_id": 0, "raw_text_for_enrichment": 1}
)

raw_text = profile.get('raw_text_for_enrichment', '').lower()

print("=" * 80)
print("🔍 SEARCHING FOR EDUCATION DATA IN RAW TEXT")
print("=" * 80)

print(f"\nTotal raw text length: {len(raw_text)} characters\n")

# Keywords to search for
education_keywords = [
    'education', 'degree', 'b.tech', 'b.e.', 'mba', 'bachelor', 
    'master', 'college', 'university', 'institute', 'graduation',
    'b tech', 'engineering', 'orissa engineering'
]

print("Searching for education keywords:")
found_any = False
for keyword in education_keywords:
    if keyword in raw_text:
        count = raw_text.count(keyword)
        print(f"  ✅ '{keyword}' - found {count} time(s)")
        found_any = True
        
        # Show context around first occurrence
        pos = raw_text.find(keyword)
        start = max(0, pos - 100)
        end = min(len(raw_text), pos + 100)
        context = raw_text[start:end]
        print(f"     Context: ...{context}...")
        print()

if not found_any:
    print("  ❌ No education keywords found in raw text!")
    print("\n⚠️  The Naukri profile might not have education section,")
    print("    or the extension didn't capture it.")

print("\n" + "=" * 80)
print("💡 RECOMMENDATION")
print("=" * 80)

if found_any:
    print("\n✅ Education data EXISTS in raw text")
    print("   → The issue is with Groq extraction")
    print("   → We need to improve the Groq prompt")
else:
    print("\n❌ Education data NOT FOUND in raw text")
    print("   → The Naukri profile doesn't have visible education")
    print("   → Or the Chrome extension didn't capture it")
    print("\nSolutions:")
    print("  1. Check the actual Naukri profile - does it show education?")
    print("  2. Try capturing a DIFFERENT candidate with visible education")
    print("  3. Or add education manually in VHC UI")

client.close()
