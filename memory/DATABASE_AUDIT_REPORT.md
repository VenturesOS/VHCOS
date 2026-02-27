# VHC Talent OS — Database Storage Protocol Audit
**Date**: Feb 2026
**Auditor**: E1 (Senior Database Architect)

---

## PHASE 1 — DATA STORAGE ARCHITECTURE

### Databases Detected: 2

```
+--------------------------------------------------------------+
|                   DATA STORAGE ARCHITECTURE                   |
+--------------------------------------------------------------+
|                                                              |
|  [Emergent Container (K8s Pod)]                              |
|  +--------------------------------------------------+       |
|  |  FastAPI Backend (port 8001)                      |       |
|  |                                                   |       |
|  |  config.py                                        |       |
|  |    1. mongo_production_override.py (PRIORITY)--+  |       |
|  |    2. .env MONGO_URL (FALLBACK)            |   |  |       |
|  |    3. os.environ MONGO_URL (FALLBACK)      |   |  |       |
|  |                                            v   v  |       |
|  |                                   [URI RESOLVED]  |       |
|  +--------------------------------------------------+       |
|           |                                    |             |
|           v                                    |             |
|  +--------------------+                        |             |
|  | LOCAL MongoDB      |  NOT USED              |             |
|  | localhost:27017     |  (stale test data)     |             |
|  | DB: vhc_talent_os  |                        |             |
|  | 3.78 MB            |                        |             |
|  | Last write: Jan 31 |                        |             |
|  +--------------------+                        |             |
|                                                v             |
+--------------------------------------------------------------+
                                                 |
                                          [TLS + SRV]
                                                 |
                                                 v
                              +-------------------------------+
                              | ATLAS MongoDB (ACTIVE)        |
                              | cluster0.vuhdiod.mongodb.net  |
                              | DB: vhc_talent_os             |
                              | 60.43 MB                      |
                              | MongoDB 8.0.19 Enterprise     |
                              | Last write: Feb 27            |
                              | User: vhc_admin (atlasAdmin)  |
                              +-------------------------------+
```

### Connection Points Identified

| Source | Variable | Value | Active? |
|--------|----------|-------|---------|
| `mongo_production_override.py` | MONGO_URL | `mongodb+srv://vhc_admin:***@cluster0.vuhdiod.mongodb.net/...` | YES (PRIORITY 1) |
| `backend/.env` | MONGO_URL | Same Atlas URI | YES (FALLBACK) |
| OS environment | MONGO_URL | NOT SET | N/A |
| OS environment | MONGODB_URI | NOT SET | N/A |
| Local mongod | localhost:27017 | Running but NOT used by app | NO |

### Resolution Logic (config.py)
1. First tries `mongo_production_override.py` — checks for `cluster0.vuhdiod.mongodb.net`
2. If import fails, falls back to env vars: `MONGODB_URI` > `MONGODB_URL` > `MONGO_URL`
3. The override file was created because the Emergent platform may overwrite `.env` during deployment

### Active Database: **ATLAS** (cluster0.vuhdiod.mongodb.net)
- Override label: `[EMERGENCY OVERRIDE ACTIVE]`
- DB name: `vhc_talent_os`
- Connection: TLS + SRV + certifi CA bundle

---

## DATA FRAGMENTATION ANALYSIS

### Collection Comparison

| Collection | Local | Atlas | Delta | Authority |
|-----------|-------|-------|-------|-----------|
| users | 11 | 28 | +17 | **ATLAS** |
| candidate_bank | 1,701 | 1,846 | +145 | **ATLAS** |
| applications | 51 | 50 | -1 | LOCAL (test data) |
| jobs | 15 | 1 | -14 | LOCAL (test data) |
| companies | 15 | 22 | +7 | **ATLAS** |
| audit_logs | 173 | 180 | +7 | **ATLAS** |
| match_results | 38 | 61 | +23 | **ATLAS** |
| candidate_profiles | 5 | 13 | +8 | **ATLAS** |
| teams | 10 | 10 | 0 | EQUAL |
| commercials | 4 | 6 | +2 | **ATLAS** |

### Collections ONLY in Atlas (47 collections)
All post-migration features: attendance, blog, compliance, trackers, security, maintenance, notifications, SEO, etc.

### Timestamp Analysis

| Collection | Local Last Write | Atlas Last Write |
|-----------|-----------------|-----------------|
| users | Jan 30, 2026 | Feb 26, 2026 |
| candidate_bank | Jan 31, 2026 | Feb 27, 2026 |
| applications | Jan 31, 2026 | Feb 26, 2026 |
| jobs | Jan 30, 2026 | Feb 25, 2026 |
| companies | Jan 30, 2026 | Feb 25, 2026 |
| audit_logs | Jan 31, 2026 | Feb 26, 2026 |

### Verdict: Data is NOT actively fragmented
- The local DB contains **stale test data** from Jan 28-31, 2026
- The 14 "extra" local jobs are all test jobs (names: "Test Job", "TEST_Job_Approval", etc.)
- The 1 "extra" local application is test data
- **All production writes go to Atlas** since the override was activated (~Feb 1)
- No data loss risk — Atlas has all production data

---

## PHASE 2 — DATA PORTABILITY

### Tool Availability
| Tool | Version | Available |
|------|---------|-----------|
| mongodump | 100.14.1 | YES |
| mongorestore | 100.14.1 | YES |
| mongosh | - | YES |
| pymongo | - | YES |

### Atlas Permissions
- User: `vhc_admin`
- Roles: `atlasAdmin`, `readWriteAnyDatabase`
- Write access: CONFIRMED (tested create/drop)
- Export capability: FULL (mongodump compatible)
- Import capability: FULL (mongorestore compatible)

### Vendor Lock-In Assessment: **NONE**
- Standard MongoDB Atlas (M0/M2/M5 tier)
- No Atlas-specific features used (no Atlas Search, no Data API, no Realm)
- Application uses standard `pymongo`/`motor` drivers
- Full `mongodump`/`mongorestore` compatible
- Can migrate to any MongoDB hosting (self-hosted, DocumentDB, Cosmos DB) with zero code changes

---

## PHASE 3 — MIGRATION FEASIBILITY

### Is Migration Needed? **NO active migration required**

The application is already consolidated on Atlas. The local MongoDB is an unused remnant.

### Risk Assessment

| Risk | Level | Details |
|------|-------|---------|
| Data loss | **NONE** | Atlas has all production data |
| Schema mismatch | **NONE** | Same schema, Atlas has more collections |
| Duplicate IDs | **NONE** | Separate databases, no cross-write |
| Data integrity | **LOW** | Local DB is stale, not being written to |

### What would be needed if you wanted to consolidate TO local:
1. Atlas → Local migration (mongodump/mongorestore)
2. Update config.py to use localhost
3. Remove override file

### What would be needed to consolidate TO Atlas (current state):
1. **Already done** — app already writes exclusively to Atlas
2. Local DB can be safely ignored or cleared

---

## PHASE 4 — CONSOLIDATION PLAN

### Recommended Single Database: **ATLAS** (current active DB)

**Rationale:**
- Already the authoritative source with all production data
- 28 users, 1846 candidates, full feature coverage (56 collections)
- MongoDB 8.0.19 Enterprise with TLS, replicas, automated backups
- User has `atlasAdmin` role — full control
- No migration needed — just cleanup

### Cleanup Steps (Optional)

#### Step 1: Backup Atlas (safety net)
```bash
mongodump --uri="mongodb+srv://vhc_admin:DL4cbb4890@cluster0.vuhdiod.mongodb.net" \
  --db=vhc_talent_os \
  --out=/app/backup_atlas_$(date +%Y%m%d) \
  --tlsCAFile=$(python3 -c "import certifi; print(certifi.where())")
```

#### Step 2: Export local DB (archive before clearing)
```bash
mongodump --host=localhost --port=27017 \
  --db=vhc_talent_os \
  --out=/app/backup_local_$(date +%Y%m%d)
```

#### Step 3: Simplify config.py (remove override complexity)
The `mongo_production_override.py` was a workaround for platform .env overwrites. Once the platform supports external MongoDB config, this can be simplified to just use `.env`.

#### Step 4: Verify (post any changes)
```bash
# Verify login
curl -X POST $API_URL/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@vhc.in","password":"VhcAdmin@2024"}'

# Verify document counts
python3 -c "
from pymongo import MongoClient; import certifi
c = MongoClient('mongodb+srv://vhc_admin:DL4cbb4890@cluster0.vuhdiod.mongodb.net/?retryWrites=true&w=majority', tls=True, tlsCAFile=certifi.where())
db = c['vhc_talent_os']
print(f'users: {db.users.count_documents({})}')  # expect 28
print(f'candidate_bank: {db.candidate_bank.count_documents({})}')  # expect 1846
print(f'applications: {db.applications.count_documents({})}')  # expect 50
"
```

---

## PHASE 5 — VALIDATION SUMMARY

### Current State (validated)
| Check | Status | Details |
|-------|--------|---------|
| Login works | PASS | Both admin@vhc.in and siddharth@vhc.in authenticated |
| Candidate pipeline | PASS | 1846 candidates in bank, 13 profiles |
| Tracker data | PASS | 5 submission trackers, 11 tracker rows, 29 events |
| Attendance data | PASS | 48 records, 1 settings doc, 15 health scores |
| No data loss | PASS | All collections present, counts consistent |
| Document counts | PASS | 28 users, 50 applications, 22 companies |

---

## FINAL SUMMARY

| Item | Value |
|------|-------|
| Databases detected | **2** (Local MongoDB + Atlas MongoDB) |
| Actively used | **Atlas** (cluster0.vuhdiod.mongodb.net / vhc_talent_os) |
| Local DB status | **Stale** (test data from Jan 2026, not written to) |
| Data fragmentation | **NO** (Atlas is complete, local is a subset) |
| Migration needed | **NO** (already consolidated on Atlas) |
| Vendor lock-in | **NONE** (standard MongoDB, fully portable) |
| Risk level | **LOW** (no action required for data integrity) |
| Recommended setup | Keep Atlas as single DB, optionally clear local stale data |
