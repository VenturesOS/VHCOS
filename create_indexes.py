#!/usr/bin/env python3
"""
MongoDB Index Creation Script
Run this to optimize aggregation queries and prevent memory errors
"""
import sys
import os
sys.path.insert(0, '/app/backend')

from pymongo import MongoClient, ASCENDING, DESCENDING
from config import mongodb_uri, db_name

def create_indexes():
    """Create indexes to optimize aggregations and prevent memory errors"""
    print("=" * 80)
    print("Creating MongoDB Indexes for Performance Optimization")
    print("=" * 80)
    
    client = MongoClient(mongodb_uri, tlsAllowInvalidCertificates=True)
    db = client[db_name]
    
    indexes_created = []
    
    try:
        # 1. Candidate Bank - Optimize extension capture aggregations
        print("\n[1] candidate_bank indexes...")
        try:
            db.candidate_bank.create_index([("source", ASCENDING)], name="idx_source")
            indexes_created.append("candidate_bank.idx_source")
        except Exception as e:
            if "already exists" in str(e):
                print(f"   ⚠️  idx_source already exists (OK)")
            else:
                raise
        
        try:
            db.candidate_bank.create_index(
                [("source_details.captured_by_name", ASCENDING)],
                name="idx_captured_by_name"
            )
            indexes_created.append("candidate_bank.idx_captured_by_name")
        except Exception as e:
            if "already exists" in str(e):
                print(f"   ⚠️  idx_captured_by_name already exists (OK)")
            else:
                raise
        
        # 2. API Metrics - Optimize aggregations
        print("[2] api_metrics indexes...")
        try:
            db.api_metrics.create_index([("timestamp", DESCENDING)], name="idx_timestamp")
            indexes_created.append("api_metrics.idx_timestamp")
        except Exception as e:
            if "already exists" in str(e):
                print(f"   ⚠️  idx_timestamp already exists (OK)")
            else:
                raise
        
        try:
            db.api_metrics.create_index([("endpoint", ASCENDING)], name="idx_endpoint")
            indexes_created.append("api_metrics.idx_endpoint")
        except Exception as e:
            if "already exists" in str(e):
                print(f"   ⚠️  idx_endpoint already exists (OK)")
            else:
                raise
        
        try:
            db.api_metrics.create_index([("is_error", ASCENDING)], name="idx_is_error")
            indexes_created.append("api_metrics.idx_is_error")
        except Exception as e:
            if "already exists" in str(e):
                print(f"   ⚠️  idx_is_error already exists (OK)")
            else:
                raise
        
        try:
            db.api_metrics.create_index(
                [("timestamp", DESCENDING), ("endpoint", ASCENDING)],
                name="idx_timestamp_endpoint"
            )
            indexes_created.append("api_metrics.idx_timestamp_endpoint")
        except Exception as e:
            if "already exists" in str(e):
                print(f"   ⚠️  idx_timestamp_endpoint already exists (OK)")
            else:
                raise
        
        # 3. Notifications - Optimize unread count queries
        print("[3] notifications indexes...")
        try:
            db.notifications.create_index(
                [("user_id", ASCENDING), ("is_read", ASCENDING)],
                name="idx_user_unread"
            )
            indexes_created.append("notifications.idx_user_unread")
        except Exception as e:
            if "already exists" in str(e):
                print(f"   ⚠️  idx_user_unread already exists (OK)")
            else:
                raise
        
        try:
            db.notifications.create_index([("created_at", DESCENDING)], name="idx_created_at")
            indexes_created.append("notifications.idx_created_at")
        except Exception as e:
            if "already exists" in str(e):
                print(f"   ⚠️  idx_created_at already exists (OK)")
            else:
                raise
        
        print("\n" + "=" * 80)
        print(f"✅ Successfully created {len(indexes_created)} indexes:")
        for idx in indexes_created:
            print(f"   - {idx}")
        
        print("\n📊 Index Statistics:")
        for collection_name in ['candidate_bank', 'api_metrics', 'notifications']:
            indexes = db[collection_name].list_indexes()
            idx_list = list(indexes)
            print(f"\n   {collection_name}: {len(idx_list)} total indexes")
            for idx in idx_list:
                print(f"      - {idx['name']}: {idx.get('key', {})}")
        
        print("\n" + "=" * 80)
        print("✅ INDEX CREATION COMPLETE")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error creating indexes: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()

if __name__ == "__main__":
    create_indexes()
