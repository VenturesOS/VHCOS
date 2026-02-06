"""
MongoDB Migration Script: Local → Atlas
Exports all collections from local MongoDB and imports to MongoDB Atlas
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
import certifi
import sys

# Configuration
LOCAL_MONGO_URL = "mongodb://localhost:27017"
ATLAS_MONGO_URL = "mongodb+srv://vhc_app_user:9VcZcHYTtIdGeVY@cluster0.vuhdiod.mongodb.net/?appName=Cluster0&retryWrites=true&w=majority"
DB_NAME = "vhc_talent_os"

# Collections to migrate
COLLECTIONS = [
    'settings',
    'audit_logs', 
    'referrals',
    'companies',
    'bulk_import_batches',
    'commercials',
    'job_sequences',
    'candidate_profiles',
    'candidate_bank',
    'applications',
    'match_results',
    'teams',
    'job_alerts',
    'candidates',
    'notification_logs',
    'jobs',
    'users'
]

def migrate_sync():
    """Synchronous migration using PyMongo"""
    print("=" * 60)
    print("MongoDB Migration: Local → Atlas")
    print("=" * 60)
    
    # Connect to local MongoDB
    print("\n📡 Connecting to local MongoDB...")
    try:
        local_client = MongoClient(LOCAL_MONGO_URL, serverSelectionTimeoutMS=5000)
        local_client.admin.command('ping')
        local_db = local_client[DB_NAME]
        print("✅ Connected to local MongoDB")
    except Exception as e:
        print(f"❌ Failed to connect to local MongoDB: {e}")
        return False
    
    # Connect to Atlas
    print("\n📡 Connecting to MongoDB Atlas...")
    try:
        atlas_client = MongoClient(ATLAS_MONGO_URL, serverSelectionTimeoutMS=10000)
        atlas_client.admin.command('ping')
        atlas_db = atlas_client[DB_NAME]
        print("✅ Connected to MongoDB Atlas")
    except Exception as e:
        print(f"❌ Failed to connect to Atlas: {e}")
        return False
    
    # Migrate each collection
    print("\n" + "=" * 60)
    print("Starting Migration...")
    print("=" * 60)
    
    total_docs = 0
    migrated_docs = 0
    
    for collection_name in COLLECTIONS:
        local_collection = local_db[collection_name]
        atlas_collection = atlas_db[collection_name]
        
        # Count documents in local
        local_count = local_collection.count_documents({})
        total_docs += local_count
        
        if local_count == 0:
            print(f"⏭️  {collection_name}: Empty (skipped)")
            continue
        
        # Check if Atlas collection already has data
        atlas_count = atlas_collection.count_documents({})
        if atlas_count > 0:
            print(f"⚠️  {collection_name}: Atlas already has {atlas_count} docs. Clearing first...")
            atlas_collection.delete_many({})
        
        # Export from local
        print(f"📤 {collection_name}: Exporting {local_count} documents...")
        documents = list(local_collection.find({}))
        
        # Import to Atlas (in batches for large collections)
        batch_size = 500
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            try:
                atlas_collection.insert_many(batch, ordered=False)
            except Exception as e:
                print(f"   ⚠️  Batch insert warning: {e}")
        
        # Verify
        new_atlas_count = atlas_collection.count_documents({})
        if new_atlas_count == local_count:
            print(f"✅ {collection_name}: {new_atlas_count} documents migrated successfully")
            migrated_docs += new_atlas_count
        else:
            print(f"⚠️  {collection_name}: Expected {local_count}, got {new_atlas_count}")
            migrated_docs += new_atlas_count
    
    # Summary
    print("\n" + "=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"Total documents in local: {total_docs}")
    print(f"Documents migrated to Atlas: {migrated_docs}")
    print(f"Success rate: {(migrated_docs/total_docs*100) if total_docs > 0 else 100:.1f}%")
    
    # Close connections
    local_client.close()
    atlas_client.close()
    
    if migrated_docs == total_docs:
        print("\n✅ Migration completed successfully!")
        return True
    else:
        print("\n⚠️  Migration completed with some discrepancies")
        return True

if __name__ == "__main__":
    success = migrate_sync()
    sys.exit(0 if success else 1)
