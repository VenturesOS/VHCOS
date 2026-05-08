"""
Secure user seeding script for VHC Talent OS.
Reads credentials from environment variables only.
Sets requires_password_reset=True for all seeded users.
"""
import os
import sys
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import bcrypt
import uuid
from datetime import datetime, timezone

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

async def seed_users():
    mongo_url = os.environ.get('MONGO_URL')
    if not mongo_url:
        print("ERROR: MONGO_URL environment variable is required.")
        sys.exit(1)
    db_name = os.environ.get('DB_NAME', 'vhc_talent_os')
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # User configs from environment
    users_config = [
        {
            "email_env": "RECRUITER_EMAIL",
            "pass_env": "RECRUITER_PASSWORD",
            "role": "recruiter",
            "name": "Demo Recruiter"
        },
        {
            "email_env": "EMPLOYER_EMAIL", 
            "pass_env": "EMPLOYER_PASSWORD",
            "role": "employer",
            "name": "Demo Employer"
        },
        {
            "email_env": "CANDIDATE_EMAIL",
            "pass_env": "CANDIDATE_PASSWORD", 
            "role": "candidate",
            "name": "Demo Candidate"
        }
    ]
    
    created = []
    
    for config in users_config:
        email = os.environ.get(config["email_env"])
        password = os.environ.get(config["pass_env"])
        
        if not email or not password:
            print(f"SKIP: {config['role']} - missing env vars")
            continue
            
        if len(password) < 8:
            print(f"ERROR: {config['role']} password must be >= 8 chars")
            continue
        
        # Check if exists
        existing = await db.users.find_one({"email": email})
        if existing:
            print(f"EXISTS: {config['role']} ({email})")
            continue
        
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        user_doc = {
            "id": user_id,
            "email": email,
            "name": config["name"],
            "role": config["role"],
            "password": hash_password(password),
            "phone": None,
            "company_id": None,
            "is_active": True,
            "requires_password_reset": True,
            "created_at": now
        }
        
        await db.users.insert_one(user_doc)
        
        # Create candidate profile if candidate
        if config["role"] == "candidate":
            profile_doc = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "name": config["name"],
                "email": email,
                "phone": None,
                "headline": None,
                "summary": None,
                "skills": [],
                "experience": [],
                "education": [],
                "resume_url": None,
                "created_at": now,
                "updated_at": now
            }
            await db.candidate_profiles.insert_one(profile_doc)
        
        created.append({
            "role": config["role"],
            "email": email,
            "route": f"/{config['role']}"
        })
        print(f"CREATED: {config['role']} ({email}) - requires password reset")
    
    client.close()
    return created

if __name__ == "__main__":
    result = asyncio.run(seed_users())
    print(f"\nSeeded {len(result)} users")
