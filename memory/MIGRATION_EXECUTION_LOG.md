================================================================================
DATABASE CONSOLIDATION — LIVE EXECUTION
Timestamp: 2026-02-17T06:43:25.930580+00:00
================================================================================

--- PRE-MERGE DOCUMENT COUNTS ---
  users: 10
  companies: 5
  teams: 4
  jobs: 6
  applications: 22
  candidate_bank: 1663
  commercials: 5

================================================================================
PHASE 1: USERS
================================================================================
  DELETED Atlas user: admin@vhc.in (842077a8-d9e7-4bca-b89e-dce044e630f6) [matched: 1]
  INSERTED Prod user: admin@vhc.in (eb962d6f-ad6f-454a-bd7b-edc68f8b4ff7, role: admin)
  DELETED Atlas user: ajit@vhc.in (09d5c0fa-4c11-4951-bcf8-bd223b0b62e2) [matched: 1]
  INSERTED Prod user: ajit@vhc.in (cf36890a-b8fa-47e2-abf3-d4600f04c831, role: employer)
  DELETED Atlas user: jatin@vhc.in (58dc5b71-adb6-4a04-9d19-1c3874907230) [matched: 1]
  INSERTED Prod user: jatin@vhc.in (839f5e28-f97e-4e0d-ae18-091e0636fa60, role: recruiter)
  DELETED Atlas user: siddharth@vhc.in (220bcc65-0f44-4550-b7ef-09bc4ccdb3d7) [matched: 1]
  Role override: siddharth@vhc.in -> admin
  INSERTED Prod user: siddharth@vhc.in (f412d7aa-c3f1-436f-aaea-91600905f486, role: admin)
  NOTE: Set default password for rohit@vhc.in (user should reset)
  INSERTED prod-only user: rohit@vhc.in (a39a318f-a107-4a5b-b6ff-03232a4d2289, role: employer)
  NOTE: Set default password for manorma@vhc.in (user should reset)
  INSERTED prod-only user: manorma@vhc.in (10f2023f-1404-4ae6-afea-884384e020fd, role: employer)
  NOTE: Set default password for Rohitjakhmola28@yahoo.com (user should reset)
  INSERTED prod-only user: Rohitjakhmola28@yahoo.com (a8f2f035-8d4b-4c90-ae53-ef64a0fd7c0c, role: candidate)
  NOTE: Set default password for yatharthrao9@gmail.com (user should reset)
  INSERTED prod-only user: yatharthrao9@gmail.com (67ac3ae1-5b14-4a1c-aedf-0cbbbb58e629, role: candidate)

================================================================================
PHASE 2: COMPANIES
================================================================================
  UPDATED company 'Tech M ': employer -> cf36890a-b8fa-47e2-abf3-d4600f04c831
  UPDATED company 'JSW': employer set to cf36890a-b8fa-47e2-abf3-d4600f04c831 (from prod)
  UPDATED company 'Volvo Commercial Vehicle ': employer set to cf36890a-b8fa-47e2-abf3-d4600f04c831 (from prod)
  INSERTED company: TVS  (14c1b9aa-9646-4d4c-884c-c985b9ae9198, employer: cf36890a-b8fa-47e2-abf3-d4600f04c831)
  INSERTED company: Panasonic (9c1553d8-4ead-4324-bf79-6a3a6c512d44, employer: 10f2023f-1404-4ae6-afea-884384e020fd)
  RENAMED company 9c1553d8-4ead-4324-bf79-6a3a6c512d44 -> 'Panasonic India'

================================================================================
PHASE 3: TEAMS
================================================================================
  UPDATED team 'Ajit Team': employer_id -> cf36890a-b8fa-47e2-abf3-d4600f04c831

================================================================================
PHASE 4: JOBS
================================================================================
  SKIP (user decision): Test Recruiter Job Approval (5203cc0d-851f-4b79-a782-5929c7a39ee7)
  SKIP (user decision): AM/DM – Warranty Specialist (afeea144-0b75-4dfd-8d39-88d0cf291745)

================================================================================
PHASE 5: CANDIDATE BANK
================================================================================
  INSERTED 56 production-only candidates

================================================================================
PHASE 6: APPLICATIONS
================================================================================
  DELETED orphan app: b5b24681-6b4f-4a38-b7ba-5b082ebf2f8b
  DELETED orphan app: eee688b3-94be-43c7-861f-7fc737874107
  DELETED orphan app: 14bce2df-c130-4fcf-b439-4916174ade00
  DELETED orphan app: ff5a8a3d-6361-4139-9487-1454f8147ca3
  DELETED orphan app: d9b2c707-6bf3-4e04-b8b3-3f7def4a899f
  DELETED orphan app: 271ba862-2593-4f82-9cd4-74cc666dca47
  DELETED orphan app: f1b0cc59-9b45-41cf-801e-707669b9130c
  DELETED orphan app: 729ff36e-f467-4545-a169-3e1b5316fdfa
  DELETED orphan app: c79554a5-87da-4d4a-bfce-420225f8376f
  Total orphaned apps cleaned: 9
  INSERTED 30 production-only applications
  Skipped 4 (orphan/test references)

================================================================================
PHASE 7: COMMERCIALS
================================================================================
  INSERTED commercial: 7ff9633a-7ae2-4dcb-bf23-006f020fb9a5 (company: 14c1b9aa-9646-4d4c-884c-c985b9ae9198)

================================================================================
POST-MERGE DOCUMENT COUNTS
================================================================================
  users                10       -> 14       (delta: +4) [OK]
  companies            5        -> 7        (delta: +2) [OK]
  teams                4        -> 4        (delta: +0) [OK]
  jobs                 6        -> 6        (delta: +0) [OK]
  applications         22       -> 43       (delta: +21) [OK]
  candidate_bank       1663     -> 1719     (delta: +56) [OK]
  commercials          5        -> 6        (delta: +1) [OK]

--- Operations Executed ---
  user_delete: 4
  user_insert: 8
  user_update: 0
  company_insert: 2
  company_update: 4
  team_update: 1
  job_insert: 0
  cb_insert: 56
  app_insert: 30
  app_delete: 9
  comm_insert: 1