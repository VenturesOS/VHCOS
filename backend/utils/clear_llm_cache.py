"""
Cache Cleanup Utility for LLM Enrichment Cache

This script safely clears the llm_enrichment_cache collection to prevent
legacy bad data (from Claude) from polluting new Groq extractions.

Usage:
    python -m utils.clear_llm_cache [--dry-run]
"""
import asyncio
import sys
import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone

# Add parent directory to path for config imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import mongodb_uri, db_name

async def clear_cache(dry_run=False):
    """Clear the llm_enrichment_cache collection"""
    client = AsyncIOMotorClient(mongodb_uri, tlsAllowInvalidCertificates=True)
    db = client[db_name]
    
    # Count existing cache entries
    cache_count = await db.llm_enrichment_cache.count_documents({})
    
    print(f"\n{'='*60}")
    print("LLM Cache Cleanup Utility")
    print(f"{'='*60}")
    print(f"Database: {db_name}")
    print("Collection: llm_enrichment_cache")
    print(f"Current cache entries: {cache_count}")
    print(f"Mode: {'DRY RUN (no changes will be made)' if dry_run else 'LIVE (cache will be cleared)'}")
    print(f"{'='*60}\n")
    
    if cache_count == 0:
        print("✅ Cache is already empty. Nothing to do.")
        client.close()
        return
    
    if dry_run:
        print(f"[DRY RUN] Would delete {cache_count} cache entries")
        print("\nTo actually clear the cache, run:")
        print("  python -m utils.clear_llm_cache")
    else:
        # Show sample entries before deletion
        print("Sample cache entries (first 3):")
        cursor = db.llm_enrichment_cache.find({}, {"_id": 0, "text_hash": 1, "cached_at": 1, "model": 1}).limit(3)
        async for entry in cursor:
            model = entry.get("model", "unknown")
            cached_at = entry.get("cached_at", "unknown")
            text_hash = entry.get("text_hash", "")[:16] + "..."
            print(f"  - Hash: {text_hash} | Model: {model} | Cached: {cached_at}")
        
        print(f"\n⚠️  WARNING: This will permanently delete all {cache_count} cache entries!")
        confirm = input("Type 'DELETE' to confirm: ")
        
        if confirm != "DELETE":
            print("\n❌ Cancelled. No changes made.")
            client.close()
            return
        
        print("\n🔄 Deleting cache entries...")
        result = await db.llm_enrichment_cache.delete_many({})
        
        print(f"✅ Successfully deleted {result.deleted_count} cache entries")
        print(f"   Timestamp: {datetime.now(timezone.utc).isoformat()}")
        
        # Verify deletion
        remaining = await db.llm_enrichment_cache.count_documents({})
        if remaining == 0:
            print("✅ Cache cleared successfully. All entries removed.")
        else:
            print(f"⚠️  Warning: {remaining} entries still remain in cache")
    
    client.close()
    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(clear_cache(dry_run))
