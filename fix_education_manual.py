#!/usr/bin/env python3
"""
Manual Education Enrichment Fix
Run this on AWS server to diagnose and fix education extraction for Deepak's profile
"""
import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, '/home/ubuntu/vhc-platform/backend')

from pymongo import MongoClient
from config import mongodb_uri, db_name
from services.groq_service import extract_full_profile_groq
import json
from datetime import datetime, timezone

async def main():
    print("=" * 80)
    print("🔧 EDUCATION FIX - MANUAL ENRICHMENT")
    print("=" * 80)
    
    # Connect to MongoDB
    print("\n[1] Connecting to MongoDB...")
    client = MongoClient(mongodb_uri, tlsAllowInvalidCertificates=True)
    db = client[db_name]
    
    # Find Deepak's profile
    print("[2] Finding Deepak Diptiman Nayak's profile...")
    profile = db.candidate_bank.find_one(
        {"name": "Deepak Diptiman Nayak"},
        {"_id": 0}
    )
    
    if not profile:
        print("❌ Profile not found!")
        return
    
    print(f"✅ Found profile: {profile['id']}")
    
    # Check current education status
    print("\n[3] Current Education Status:")
    current_education = profile.get('education', [])
    print(f"   Education field: {current_education}")
    print(f"   Education count: {len(current_education) if current_education else 0}")
    print(f"   Enrichment status: {profile.get('enrichment_status', 'NOT SET')}")
    print(f"   AI source: {profile.get('ai_enrichment_source', 'NOT SET')}")
    
    # Get raw text for enrichment
    raw_text = profile.get('raw_text_for_enrichment', '')
    if not raw_text:
        print("\n❌ No raw_text_for_enrichment found - cannot re-enrich!")
        print("   The profile needs to be re-captured from Naukri extension.")
        return
    
    print(f"\n[4] Raw text available: {len(raw_text)} characters")
    print(f"   First 500 chars: {raw_text[:500]}...")
    
    # Run Groq extraction
    print("\n[5] Running Groq extraction...")
    try:
        result = await extract_full_profile_groq(
            raw_text=raw_text, 
            candidate_name=profile.get('name')
        )
        
        if result.get('error'):
            print(f"❌ Groq extraction failed: {result['error']}")
            return
        
        print("✅ Groq extraction successful!")
        
        # Show what Groq extracted
        print("\n[6] Groq Extraction Results:")
        education = result.get('education', [])
        print(f"   Education extracted: {len(education)} entries")
        if education:
            print(f"   Education data:")
            print(json.dumps(education, indent=4))
        else:
            print("   ⚠️  No education extracted from raw text!")
            print("\n   Checking if education data exists in raw text:")
            if 'education' in raw_text.lower() or 'degree' in raw_text.lower() or 'b.tech' in raw_text.lower():
                print("   ✅ Education keywords found in raw text")
            else:
                print("   ❌ No education keywords found in raw text")
        
        # Save to database
        if education and len(education) > 0:
            print("\n[7] Saving education to database...")
            updates = {
                "education": education,
                "enrichment_status": "enriched",
                "ai_enrichment_source": "groq_full_llama_3_3_70b_manual_fix",
                "ai_enriched_at": datetime.now(timezone.utc).isoformat(),
            }
            
            # Also update other fields if available
            if result.get('current_ctc'):
                updates["current_salary"] = int(result['current_ctc'])
            if result.get('notice_period'):
                updates["notice_period"] = result['notice_period']
            if result.get('notice_period_days'):
                updates["notice_period_days"] = int(result['notice_period_days'])
            if result.get('profile_summary'):
                updates["summary"] = result['profile_summary']
            
            db.candidate_bank.update_one(
                {"id": profile["id"]},
                {"$set": updates}
            )
            
            print(f"✅ Database updated with {len(updates)} fields:")
            for key in updates.keys():
                if key != 'ai_enriched_at':
                    print(f"      - {key}")
            
            # Verify
            print("\n[8] Verifying database update...")
            updated_profile = db.candidate_bank.find_one(
                {"id": profile["id"]},
                {"_id": 0, "education": 1}
            )
            
            if updated_profile.get('education'):
                print(f"✅ VERIFIED: Education now has {len(updated_profile['education'])} entries")
                print(json.dumps(updated_profile['education'], indent=4))
            else:
                print("❌ FAILED: Education still empty after update!")
        else:
            print("\n⚠️  Cannot save - no education extracted")
            print("\n[DEBUG] Full Groq result:")
            print(json.dumps(result, indent=2))
    
    except Exception as e:
        print(f"\n❌ Error during enrichment: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        client.close()
    
    print("\n" + "=" * 80)
    print("✅ DIAGNOSTIC COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
