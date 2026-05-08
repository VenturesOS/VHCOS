#!/usr/bin/env python3
"""
Fix SESHU KUMAR profile - Run this on AWS production
"""
import asyncio
import os
import sys
sys.path.insert(0, '/home/ubuntu/vhc-platform/backend')

from dotenv import load_dotenv
load_dotenv('/home/ubuntu/vhc-platform/backend/.env')

async def fix_seshu():
    from motor.motor_asyncio import AsyncIOMotorClient
    from services.bedrock_service import extract_phone_and_work_experience_only
    from services.naukri_regex_parser import extract_full_profile_regex
    from datetime import datetime, timezone
    
    client = AsyncIOMotorClient(os.getenv('MONGO_URL'))
    db = client[os.getenv('DB_NAME')]
    
    print('🔍 Finding SESHU KUMAR profile...')
    candidate = await db.candidate_bank.find_one({'name': 'SESHU KUMAR. M'})
    if not candidate:
        print('❌ Candidate not found')
        client.close()
        return
    
    raw_text = candidate.get('raw_text_for_enrichment', '')
    if not raw_text:
        print('❌ No raw text available for re-enrichment')
        client.close()
        return
    
    print(f'✅ Found profile (ID: {candidate["id"]})')
    print(f'   Raw text: {len(raw_text)} chars\n')
    
    print('⚙️  Step 1: Running regex extraction...')
    regex_data = extract_full_profile_regex(raw_text, '', '')
    
    print('⚙️  Step 2: Running Claude targeted extraction (phone + work exp)...')
    claude_data = await extract_phone_and_work_experience_only(raw_text, candidate['name'])
    
    # Fix phone number - use the one from Naukri (8801364708)
    phone = '9188013647'  # From Naukri profile
    
    print(f'\n📊 Extraction Results:')
    print(f'   Phone: {phone}')
    print(f'   Work Experiences: {len(claude_data.get("work_experience", []))}')
    print(f'   Skills: {len(regex_data.get("skills", []))}')
    
    # Merge data
    update_data = {
        'candidate_phone': phone,
        'phone': phone,
        'phone_normalized': phone,
        'experience': claude_data.get('work_experience', []),
        'enrichment_status': 'enriched',
        'ai_enrichment_source': 'manual_fix_targeted_claude',
        'ai_enriched_at': datetime.now(timezone.utc).isoformat(),
        # Keep regex-extracted fields
        'current_employer': regex_data.get('current_employer') or candidate.get('current_employer'),
        'designation': regex_data.get('current_designation') or candidate.get('designation'),
        'current_salary': regex_data.get('current_ctc') or candidate.get('current_salary'),
        'expected_salary': regex_data.get('expected_ctc') or candidate.get('expected_salary'),
        'notice_period': regex_data.get('notice_period') or candidate.get('notice_period'),
        'location': regex_data.get('location') or candidate.get('location'),
        'skills': regex_data.get('skills') or candidate.get('skills', []),
        'experience_years': regex_data.get('experience_years') or candidate.get('experience_years'),
    }
    
    print(f'\n💾 Updating database...')
    result = await db.candidate_bank.update_one(
        {'name': 'SESHU KUMAR. M'},
        {'$set': update_data}
    )
    
    if result.modified_count > 0:
        print(f'\n✅ Successfully updated profile!')
        print(f'\n📋 Work Experiences Now Saved:')
        for i, exp in enumerate(claude_data.get('work_experience', [])[:5], 1):
            print(f'   {i}. {exp.get("designation")}')
            print(f'      {exp.get("company")} ({exp.get("from_date")} - {exp.get("to_date")})')
    else:
        print(f'\n⚠️  No changes made (profile may already be correct)')
    
    client.close()
    print('\n✅ Done! Refresh the VHC Candidate Bank to see updated profile.')

if __name__ == '__main__':
    asyncio.run(fix_seshu())
