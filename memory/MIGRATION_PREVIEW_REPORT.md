# Database Consolidation Preview Report
## VHC Talent OS — Atlas vs Production Local MongoDB

**Generated:** 2026-02-18
**Status:** DRAFT — Awaiting user approval before any execution
**Master DB:** MongoDB Atlas (cluster0.vuhdiod.mongodb.net) / `vhc_talent_os`
**Secondary DB:** Production pod-local MongoDB / `vhc_talent_os`

---

## 1. Collection-Level Document Counts

| Collection | Atlas | Production | Delta | Notes |
|---|---|---|---|---|
| **users** | 10 | 15 | +5 prod | 4 UUID conflicts, 7 prod-only, 2 atlas-only |
| **companies** | 5 | 17 | +12 prod | 3 real prod-only, 8 test artifacts, 1 atlas-only |
| **teams** | 4 | ERROR (500) | N/A | Production teams collection corrupted |
| **jobs** | 6 | 16 | +10 prod | 1 real prod-only, 10 test artifacts, 1 atlas-only |
| **applications** | 22 | 51 | +29 prod | 17 common, 34 prod-only, 5 atlas-only |
| **candidate_bank** | 1663 | 1708 | +45 prod | 1652 common, 56 prod-only, 11 atlas-only |
| **commercials** | 5 | 5 | 0 | 4 common, 1 prod-only, 1 atlas-only |
| **blog_posts** | 2 | 0 | -2 | Atlas-only (created post-split) |
| **candidate_profiles** | 7 | N/A | — | No production API endpoint available |
| **match_results** | 60 | N/A | — | No production API endpoint available |
| **contact_submissions** | 5 | 0 | -5 | Atlas-only |
| **bug_reports** | 5 | 0 | -5 | Atlas-only |
| **audit_logs** | 145 | N/A | — | No production API endpoint available |
| **seo_settings** | 2 | N/A | — | Atlas-only (created by SEO implementation) |
| **blog_schedule_config** | 1 | N/A | — | Atlas-only |
| **blog_analytics** | 23 | N/A | — | Atlas-only |
| **blog_digest_log** | 1 | N/A | — | Atlas-only |
| **match_jobs** | 5 | N/A | — | No production API endpoint available |
| **background_jobs** | 5 | N/A | — | Atlas-only |
| **bulk_import_batches** | 34 | N/A | — | No production API endpoint available |
| **system_errors** | 8 | N/A | — | Atlas-only |
| **job_alerts** | 1 | N/A | — | Atlas-only |
| **ai_search_logs** | 15 | N/A | — | Atlas-only |
| **job_sequences** | 1 | N/A | — | Atlas-only |
| **password_reset_tokens** | 1 | N/A | — | Atlas-only |

---

## 2. Production-Only Users (7)

| Email | UUID | Role | Active | Notes |
|---|---|---|---|---|
| `rohit@vhc.in` | a39a318f-a107-4a5b-b6ff-03232a4d2289 | employer | Yes | **Real user — MUST migrate** |
| `manorma@vhc.in` | 10f2023f-1404-4ae6-afea-884384e020fd | employer | Yes | **Real user — MUST migrate** |
| `Rohitjakhmola28@yahoo.com` | a8f2f035-8d4b-4c90-ae53-ef64a0fd7c0c | candidate | Yes | **Real user — MUST migrate** |
| `yatharthrao9@gmail.com` | 67ac3ae1-5b14-4a1c-aedf-0cbbbb58e629 | candidate | Yes | **Real user — MUST migrate** |
| `employer@vhctalent.com` | 096ec385-98a3-4001-9230-dfd79a68353f | employer | No | Test account (inactive) — SKIP |
| `recruiter@vhctalent.com` | f501f248-57c4-4d38-ae9b-febcbe43c133 | recruiter | No | Test account (inactive) — SKIP |
| `recruiter2@vhctalent.com` | 0e82b2aa-9c30-4a06-ab62-6b4336fccf76 | recruiter | No | Test account (inactive) — SKIP |

---

## 3. Atlas-Only Users (2)

| Email | UUID | Role | Active | Notes |
|---|---|---|---|---|
| `admin@ventureshrd.com` | a792bb92-84dc-4fd3-be03-ec1940296dfc | admin | Yes | Created on Atlas — KEEP |
| `yatharth@vhc.in` | 3bee4bf4-02cb-4b81-8e40-7d8224f1fc94 | candidate | No | Created on Atlas — KEEP |

---

## 4. UUID Conflict Mapping Table (4 conflicts)

These users exist in both databases with the **same email** but **different UUIDs**:

| Email | Production UUID | Atlas UUID | Role | Conflict Type |
|---|---|---|---|---|
| `admin@vhc.in` | `eb962d6f-ad6f-454a-bd7b-edc68f8b4ff7` | `842077a8-d9e7-4bca-b89e-dce044e630f6` | Both admin | UUID mismatch |
| `ajit@vhc.in` | `cf36890a-b8fa-47e2-abf3-d4600f04c831` | `09d5c0fa-4c11-4951-bcf8-bd223b0b62e2` | Both employer | UUID mismatch |
| `jatin@vhc.in` | `839f5e28-f97e-4e0d-ae18-091e0636fa60` | `58dc5b71-adb6-4a04-9d19-1c3874907230` | Both recruiter | UUID mismatch |
| `siddharth@vhc.in` | `f412d7aa-c3f1-436f-aaea-91600905f486` | `220bcc65-0f44-4550-b7ef-09bc4ccdb3d7` | **PROD: employer, ATLAS: admin** | UUID + Role mismatch |

### Identical Users (4 — no conflict, same UUID in both):
- `maneet@vhc.in` — `f2a32556-f910-453a-8a2d-961211a17c46`
- `bikash@vhc.in` — `8dc5f7b9-be24-4e65-81d7-7af78fd07c18`
- `avinash@vhc.in` — `e9e33bd0-db62-4db2-86ea-495a6230e222`
- `yamini@vhc.in` — `06b70e35-bb06-41b9-a5f1-d9111112ae78`

### Cascade Impact of UUID Conflicts
Production data referencing **production UUIDs** that will break if we keep Atlas UUIDs:

**`admin@vhc.in` (prod: `eb962d6f`):**
- `users.created_by` field in 4+ Atlas user records references this ID
- Referenced as creator/admin across audit_logs

**`ajit@vhc.in` (prod: `cf36890a`):**
- 4 companies assigned to this employer ID (Tech M, JSW, Volvo, TVS)
- 1 commercial references TVS (which references this employer)
- Teams in production reference this employer

**`jatin@vhc.in` (prod: `839f5e28`):**
- Jobs created by this recruiter
- Applications and pipeline activity

**`siddharth@vhc.in` (prod: `f412d7aa`):**
- Role conflict: employer in production vs admin in Atlas

---

## 5. Password Hash Format Comparison

| Property | Atlas | Production | Compatible? |
|---|---|---|---|
| Algorithm | bcrypt | bcrypt | YES |
| Prefix | `$2b$12$` | `$2b$12$` | YES |
| Hash length | 60 chars | 60 chars | YES |
| Cost factor | 12 rounds | 12 rounds | YES |
| Login test (admin@vhc.in) | OK with `VhcAdmin@2024` | OK with `VhcAdmin@2024` | YES |
| Login test (ajit@vhc.in) | OK with `12345678` | OK with `12345678` | YES |

**Conclusion:** Password hashes are fully compatible. Both environments use identical bcrypt configuration. Users can authenticate with the same passwords regardless of which database record is kept.

---

## 6. Relationship Integrity Check

### Atlas Relationships (Current State)
| Relationship | Status | Issues |
|---|---|---|
| Companies → Users (employer) | CLEAN | All `assigned_employer_id` values reference valid Atlas users |
| Teams → Users (employer) | CLEAN | All `employer_id` values reference valid Atlas users |
| Teams → Companies | CLEAN | All `company_ids` reference valid Atlas companies |
| Jobs → Companies | CLEAN | Valid or empty company references |
| Applications → Jobs | **BROKEN** | 7 of 22 apps reference job_ids NOT in Atlas jobs |
| Applications → Candidates | **BROKEN** | 13 of 22 apps reference candidate_ids NOT in Atlas candidate_bank |
| Commercials → Companies | CLEAN | All reference valid Atlas companies |

### Production Relationships (Current State)
| Relationship | Status | Issues |
|---|---|---|
| Companies → Users (employer) | CLEAN | All employer IDs reference valid production users |
| Teams | **BROKEN** | GET /api/teams returns 500 (data corruption) |
| Jobs → Companies | MIXED | Most test jobs have no company; real jobs OK |
| Applications → Jobs | MIXED | Some reference jobs that only exist in production |
| Commercials → Companies | CLEAN | All reference valid production companies |

### Cross-Database Relationship Issues
Companies with **employer assignment conflicts** (same company ID, different employer):

| Company | Prod Employer | Atlas Employer | Resolution Needed |
|---|---|---|---|
| Tech M (`f56968c2`) | `cf36890a` (Ajit-prod) | `09d5c0fa` (Ajit-atlas) | Remap to Atlas Ajit UUID |
| JSW (`3908c977`) | `cf36890a` (Ajit-prod) | None | Need to assign to Atlas Ajit UUID |
| Volvo (`8066c10f`) | `cf36890a` (Ajit-prod) | None | Need to assign to Atlas Ajit UUID |

---

## 7. Expected Final Document Counts After Merge

### Strategy: Atlas is master. Merge production-only REAL data in. Discard test artifacts.

| Collection | Current Atlas | Add from Prod | Remove | Final Expected | Notes |
|---|---|---|---|---|---|
| **users** | 10 | +4 (rohit, manorma, 2 candidates) | 0 | **14** | Skip 3 inactive test accounts |
| **companies** | 5 | +3 (TVS, Panasonic, Panosonic India) | 0 | **8** | Skip 8 test companies |
| **teams** | 4 | 0 | 0 | **4** | Production teams corrupted; keep Atlas teams, re-link |
| **jobs** | 6 | +1 (AM/DM Warranty Specialist) | 0 | **7** | Skip 10 test jobs |
| **applications** | 22 | +29 (prod-only real apps) | 0 | **~51** | Requires job/candidate ID remapping for some |
| **candidate_bank** | 1663 | +56 (prod-only candidates) | 0 | **~1719** | Check for email duplicates |
| **commercials** | 5 | +1 (TVS commercial) | 0 | **6** | |
| **blog_posts** | 2 | 0 | 0 | **2** | Production has none |
| **All other collections** | Keep as-is | 0 | 0 | Same | Atlas-only collections preserved |

---

## 8. Conflict Resolution Strategy Per Collection

### `users` Collection
1. **Keep all Atlas users as-is** (they are the master copy)
2. **UUID Conflict Resolution (4 users):**
   - **Option A (Recommended): Keep Production UUIDs for the 4 conflicting users**
     - Rationale: Production has been the live system. All production data (companies, jobs, applications) references production UUIDs. Keeping production UUIDs means zero remapping of downstream data.
     - Action: Delete the 4 Atlas duplicate records, insert the 4 production records (with production UUIDs and production password hashes)
     - Risk: Atlas-only data referencing Atlas UUIDs (like `users.created_by` on some Atlas records and team `employer_id`) needs remapping
   - **Option B: Keep Atlas UUIDs**
     - Rationale: Atlas is declared master
     - Action: Remap ALL production foreign keys (companies, applications, teams) from production UUIDs to Atlas UUIDs
     - Risk: Higher complexity, more remapping required across more collections
   - **Recommendation: Option A** — Less disruption since production has more active foreign key references
3. **For `siddharth@vhc.in`:** User decision required — should role be `employer` (production) or `admin` (Atlas)?
4. **Insert 4 production-only real users** (rohit, manorma, 2 candidates)
5. **Skip 3 inactive test accounts** (employer@vhctalent.com, recruiter@vhctalent.com, recruiter2@vhctalent.com)

### `companies` Collection
1. **Keep all 5 Atlas companies**
2. **Insert 3 production-only REAL companies:** TVS, Panasonic, Panosonic India
3. **Update employer assignments on companies in both DBs:**
   - If Option A (keep prod UUIDs): JSW and Volvo get `assigned_employer_id` set to prod Ajit UUID (`cf36890a`)
   - Tech M already has employer assignment in both (just different UUID for same person)
4. **Skip 8 test companies** (all prefixed with TEST_)

### `teams` Collection
1. **Keep all 4 Atlas teams** (production teams are corrupted/500 error)
2. **Remap employer_id references** in Atlas teams if UUID conflict users change
3. **Add new companies** (TVS, Panasonic, Panosonic India) to relevant teams

### `jobs` Collection
1. **Keep all 6 Atlas jobs**
2. **Insert 1 production-only REAL job:** AM/DM Warranty Specialist (`afeea144`)
3. **Skip 10 test jobs**

### `applications` Collection
1. **Keep all 22 Atlas applications**
2. **Evaluate 34 production-only applications:**
   - Applications referencing valid jobs and candidates: INSERT
   - Applications referencing test jobs or test data: SKIP
   - Applications with candidate/job IDs needing remapping: REMAP then INSERT

### `candidate_bank` Collection
1. **Keep all 1663 Atlas candidates**
2. **Insert 56 production-only candidates** (check for email duplicates first)
3. **11 Atlas-only candidates** already preserved

### `commercials` Collection
1. **Keep all 5 Atlas commercials** (includes 4 common + 1 atlas-only)
2. **Insert 1 production-only commercial** (TVS: `7ff9633a`)

### All Other Collections
- **blog_posts, blog_analytics, blog_schedule_config, blog_digest_log:** Atlas-only, preserved
- **contact_submissions, bug_reports:** Atlas-only, preserved
- **seo_settings:** Atlas-only, preserved
- **audit_logs, match_results, match_jobs, candidate_profiles:** Atlas-only, preserved

---

## 9. Rollback Plan

### Pre-Migration Safety Measures
1. **Full Atlas Backup:** Export ALL Atlas collections using `mongodump` before any write operation
2. **Backup Location:** Store dump at `/app/backup/atlas_pre_merge_YYYYMMDD/`
3. **Verification:** Count documents in backup vs live to confirm complete dump

### Rollback Procedure (< 10 minutes)
1. **Stop application** (prevent new writes during restore)
2. **Drop affected collections** in Atlas that were modified
3. **Restore from backup** using `mongorestore` from the pre-migration dump
4. **Verify document counts** match pre-migration snapshot
5. **Restart application**

### Estimated Rollback Time
| Step | Duration |
|---|---|
| Stop application | 10 seconds |
| Drop & restore collections | 3-5 minutes (small dataset ~2000 docs total) |
| Verify counts | 1 minute |
| Restart application | 30 seconds |
| **Total** | **~5-7 minutes** |

---

## 10. Proposed Migration Order

1. **Phase 0: Backup** — Full mongodump of Atlas
2. **Phase 1: Users** — Resolve UUID conflicts, insert production-only users
3. **Phase 2: Companies** — Insert production-only companies, update employer assignments
4. **Phase 3: Teams** — Remap employer/company references
5. **Phase 4: Jobs** — Insert production-only real job
6. **Phase 5: Candidate Bank** — Insert production-only candidates (dedup by email)
7. **Phase 6: Applications** — Insert production-only applications (remap IDs as needed)
8. **Phase 7: Commercials** — Insert production-only commercial
9. **Phase 8: Verify** — Full integrity check on merged Atlas
10. **Phase 9: Switchover** — Update production .env to point to Atlas, redeploy

---

## Open Questions for User Decision

1. **UUID Conflict Strategy:** Option A (keep production UUIDs) or Option B (keep Atlas UUIDs)?
   - Recommendation: Option A
2. **siddharth@vhc.in role:** Should final role be `employer` (production) or `admin` (Atlas)?
3. **Test data cleanup:** Should test companies/jobs be cleaned from production before merge, or simply not migrated?
4. **Panosonic India vs Panasonic:** Production has both `ba188401` (Panosonic India) and `9c1553d8` (Panasonic) assigned to manorma@vhc.in. Are these intended as separate companies or a typo/duplicate?
5. **Atlas broken applications:** 7 applications reference non-existent jobs, 13 reference non-existent candidates. Should these orphaned records be cleaned up during the merge?
