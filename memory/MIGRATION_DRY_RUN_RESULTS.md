================================================================================
DATABASE CONSOLIDATION — DRY-RUN SIMULATION
Timestamp: 2026-02-17T06:39:56.082538Z
Mode: READ-ONLY SIMULATION (no writes)
================================================================================

================================================================================
PHASE 1: USERS
================================================================================

--- 1a. UUID Conflict Resolution (Option A: Keep Production UUIDs) ---
  DELETE Atlas user: admin@vhc.in (Atlas UUID: 842077a8-d9e7-4bca-b89e-dce044e630f6)
  INSERT Prod user: admin@vhc.in (Prod UUID: eb962d6f-ad6f-454a-bd7b-edc68f8b4ff7, role: admin)
  DELETE Atlas user: ajit@vhc.in (Atlas UUID: 09d5c0fa-4c11-4951-bcf8-bd223b0b62e2)
  INSERT Prod user: ajit@vhc.in (Prod UUID: cf36890a-b8fa-47e2-abf3-d4600f04c831, role: employer)
  DELETE Atlas user: jatin@vhc.in (Atlas UUID: 58dc5b71-adb6-4a04-9d19-1c3874907230)
  INSERT Prod user: jatin@vhc.in (Prod UUID: 839f5e28-f97e-4e0d-ae18-091e0636fa60, role: recruiter)
  DELETE Atlas user: siddharth@vhc.in (Atlas UUID: 220bcc65-0f44-4550-b7ef-09bc4ccdb3d7)
  INSERT Prod user: siddharth@vhc.in (Prod UUID: f412d7aa-c3f1-436f-aaea-91600905f486, role overridden to: admin)

--- 1b. Production-Only Users ---
  SKIP test user: employer@vhctalent.com (inactive)
  SKIP test user: recruiter@vhctalent.com (inactive)
  SKIP test user: recruiter2@vhctalent.com (inactive)
  INSERT prod-only user: rohit@vhc.in (a39a318f-a107-4a5b-b6ff-03232a4d2289, role: employer)
  INSERT prod-only user: manorma@vhc.in (10f2023f-1404-4ae6-afea-884384e020fd, role: employer)
  INSERT prod-only user: Rohitjakhmola28@yahoo.com (a8f2f035-8d4b-4c90-ae53-ef64a0fd7c0c, role: candidate)
  INSERT prod-only user: yatharthrao9@gmail.com (67ac3ae1-5b14-4a1c-aedf-0cbbbb58e629, role: candidate)

--- 1c. Remap created_by References ---

================================================================================
PHASE 2: COMPANIES
================================================================================

--- 2a. Update Employer Assignments (remap Atlas UUIDs to Prod UUIDs) ---
  UPDATE company 'Tech M ' (f56968c2-8967-460d-8904-fdc4bc0eb1b4): employer 09d5c0fa-4c11-4951-bcf8-bd223b0b62e2 -> cf36890a-b8fa-47e2-abf3-d4600f04c831

--- 2b. Production-Only Companies ---
  UPDATE company 'JSW' (3908c977-938e-4f47-8c93-3b494e8559aa): set employer to cf36890a-b8fa-47e2-abf3-d4600f04c831 (from prod)
  UPDATE company 'Volvo Commercial Vehicle ' (8066c10f-215b-4ed2-9b2d-8726b609e4fa): set employer to cf36890a-b8fa-47e2-abf3-d4600f04c831 (from prod)
  SKIP duplicate company: Panosonic India (ba188401-91dc-446d-93c0-d9712b84c230) — will merge into 'Panasonic India'
  SKIP test company: TEST_Company_HR_569d4d80 (f5f9d37e-9fd3-44d8-b6c5-69cf7354cab7)
  SKIP test company: TEST_Company_61bb3d68 (0cc83122-c5c9-4d74-afd9-e6930b91a5ac)
  SKIP test company: TEST_Company_HR_77c727c1 (5570a478-4bbd-433e-80e1-d62508bcbf60)
  SKIP test company: TEST_Company_7fd832c3 (0e5da6fb-fce8-4396-8781-730a9d091e9d)
  SKIP test company: TEST_Update_Company_208f9526 (729204e2-4ca3-4d9f-b693-b369e3307047)
  SKIP test company: TEST_Company_26cc4e54 (a33a97f6-d2a1-4027-9a34-d8629c7d7b76)
  SKIP test company: TEST_Update_Company_4e1c5324 (dcad6691-b2be-494d-9083-b172dc657395)
  SKIP test company: TEST_DeleteCompany_e8a4fa42 (0bbc6830-e419-49da-9732-4c1f36edc852)
  SKIP test company: TEST_CascadeCompany_be731843 (4b1f1705-3151-4fde-9834-66d0309c32f1)
  SKIP test company: TEST_UpdatedCompany_cf5561c7 (7f54f4fc-13b8-49b9-b9d3-a9fcd6691974)
  INSERT prod-only company: TVS  (14c1b9aa-9646-4d4c-884c-c985b9ae9198, employer: cf36890a-b8fa-47e2-abf3-d4600f04c831)
  INSERT prod-only company: Panasonic (9c1553d8-4ead-4324-bf79-6a3a6c512d44, employer: 10f2023f-1404-4ae6-afea-884384e020fd)

--- 2c. Company Dedup: Panosonic India -> Panasonic India ---
  RENAME company 9c1553d8-4ead-4324-bf79-6a3a6c512d44: 'Panasonic' -> 'Panasonic India'
  REPOINT all references from ba188401-91dc-446d-93c0-d9712b84c230 to 9c1553d8-4ead-4324-bf79-6a3a6c512d44
  References to duplicate company: jobs=0, apps=0, commercials=0

================================================================================
PHASE 3: TEAMS
================================================================================

--- 3a. Remap Team Employer IDs ---
  UPDATE team 'Ajit Team' (2c488fdd-6bc2-425f-b60a-6ac78eb06d22): employer_id 09d5c0fa-4c11-4951-bcf8-bd223b0b62e2 -> cf36890a-b8fa-47e2-abf3-d4600f04c831

================================================================================
PHASE 4: JOBS
================================================================================

--- 4a. Production-Only Jobs ---
  SKIP test job: Test Job bcd18e32 (191ee9ec-874d-43fb-95d6-3ab1170739d3)
  SKIP test job: Career Page Test Job 4e1892d9 (360a21ce-9adf-4e7b-8d61-0165a2c85400)
  SKIP test job: Non-Live Job 6e59664c (d763de77-ddb4-4471-bc77-96f1e32762e0)
  SKIP test job: Test Job 0dc6d30c (2500f50d-227c-4235-930d-68788c985930)
  SKIP test job: Career Page Test Job 883c4677 (3d217c26-fc3b-4396-8b81-eeb9fbfa2d12)
  SKIP test job: Non-Live Job 35a587f3 (38d122c9-94cc-447e-8318-08932376c21e)
  SKIP test job: Test Job - Infra Wire (3efa09bc-635e-47a3-970c-3849419f0dac)
  INSERT prod-only job: Test Recruiter Job Approval (5203cc0d-851f-4b79-a782-5929c7a39ee7, company: None)
  SKIP test job: TEST_Job_c9c27dc5 (87851d6f-16a1-4222-9f5e-c68dcdc14bd1)
  SKIP test job: TEST_Job_Approval_aeeb1b89 (9fac4328-2b12-4cf0-8f78-b9da27c9587c)
  INSERT prod-only job: AM/DM – Warranty Specialist (afeea144-0b75-4dfd-8d39-88d0cf291745, company: f5f9d37e-9fd3-44d8-b6c5-69cf7354cab7)

================================================================================
PHASE 5: CANDIDATE BANK
================================================================================
  
Total prod-only candidates: 56
  Email duplicates found: 0
  Will INSERT: 56 candidates

================================================================================
PHASE 6: APPLICATIONS
================================================================================

--- 6a. Atlas Orphaned Application Cleanup ---
  DELETE orphaned app: b5b24681-6b4f-4a38-b7ba-5b082ebf2f8b (job_id=ed000817-78ca-496c-a116-7b247e46a2dd not found)
  DELETE orphaned app: eee688b3-94be-43c7-861f-7fc737874107 (job_id=ed000817-78ca-496c-a116-7b247e46a2dd not found)
  DELETE orphaned app: 14bce2df-c130-4fcf-b439-4916174ade00 (job_id=ed000817-78ca-496c-a116-7b247e46a2dd not found)
  DELETE orphaned app: ff5a8a3d-6361-4139-9487-1454f8147ca3 (job_id=ed000817-78ca-496c-a116-7b247e46a2dd not found)
  DELETE orphaned app: d9b2c707-6bf3-4e04-b8b3-3f7def4a899f (job_id=afc73b3c-0218-4a37-b63a-989c33b7ed19 not found)
  DELETE orphaned app: 271ba862-2593-4f82-9cd4-74cc666dca47 (job_id=9fac4328-2b12-4cf0-8f78-b9da27c9587c not found)
  DELETE orphaned app: f1b0cc59-9b45-41cf-801e-707669b9130c (candidate_id=19bbbd7e-8a7e-425d-b6a8-5fdd2a1acd3d not found)
  DELETE orphaned app: 729ff36e-f467-4545-a169-3e1b5316fdfa (job_id=3d217c26-fc3b-4396-8b81-eeb9fbfa2d12 not found, candidate_id=19bbbd7e-8a7e-425d-b6a8-5fdd2a1acd3d not found)
  DELETE orphaned app: c79554a5-87da-4d4a-bfce-420225f8376f (candidate_id=19bbbd7e-8a7e-425d-b6a8-5fdd2a1acd3d not found)

--- 6b. Production-Only Applications ---
    SKIP app c27f1520-0594-40c1-b984-23a914b0cf91: job (1666dad8-80a6-4452-bd3b-6f6764669c49) missing from final DB
    SKIP app 57522565-4fbd-4d18-bcbb-ada87dd4ae2d: job (bfa9f9c1-3e3b-4fee-b5ca-c6e286d23363) missing from final DB
    SKIP app 66112fa7-ecae-434a-995e-ed644848d498: job (b48ad51e-6881-40ad-bb6e-f88c06404932) missing from final DB
    SKIP app 7aa8345c-cd16-495a-a279-66e5a1aee773: job (150cb34f-c005-433c-a5b8-139385464ec8) missing from final DB
  
Prod-only applications: 34
  Will INSERT: 30
  Skipped (test/orphan): 4

================================================================================
PHASE 7: COMMERCIALS
================================================================================
  INSERT prod-only commercial: 7ff9633a-7ae2-4dcb-bf23-006f020fb9a5 (company: 14c1b9aa-9646-4d4c-884c-c985b9ae9198)

================================================================================
DRY-RUN SUMMARY
================================================================================

--- Operations Count ---
Users:       DELETE 4, INSERT 8, UPDATE 0
Companies:   INSERT 2, UPDATE 4, DELETE 0
Teams:       UPDATE 1
Jobs:        INSERT 2
Candidates:  INSERT 56
Applications: INSERT 30, DELETE (orphans) 9
Commercials: INSERT 1

--- Expected Final Document Counts ---
Collection           Before     After      Change    
--------------------------------------------------
users                10         14         +4
companies            5          7          +2
teams                4          4          0 (updates only)
jobs                 6          8          +2
applications         22         43         +21
candidate_bank       1663       1719       +56
commercials          5          6          +1

--- Rollback Commands ---
mongorestore --uri='mongodb+srv://vhc_admin:DL4cbb4890@cluster0.vuhdiod.mongodb.net/vhc_talent_os' \
  --drop --dir='/app/backup/atlas_pre_merge_20260218/vhc_talent_os'
Estimated rollback time: < 5 minutes