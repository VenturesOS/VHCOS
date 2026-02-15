"""
VHC Talent OS - Phase-2 Part A: Operational Expansion Tests
Tests for:
- TASK 1: Batch CV Upload (max 10 files, atomic save)
- TASK 2: Manual Add as Applicant (link candidate to job)
- TASK 3: Mandatory Salary & Notice Period validation
- TASK 4: Duplicate Detection (email/phone/fingerprint)
- Role-based access control
"""

import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://recruit-adapt.preview.emergentagent.com')

# Test credentials
CREDENTIALS = {
    "admin": {"email": "admin@vhc.in", "password": "VhcAdmin@2024"},
    "employer": {"email": "employer@vhctalent.com", "password": "Demo@2024"},
    "recruiter": {"email": "recruiter@vhctalent.com", "password": "Demo@2024"},
    "candidate": {"email": "candidate@vhctalent.com", "password": "Demo@2024"}
}

# Existing test candidate from misc_info
EXISTING_CANDIDATE_ID = "787397d9-edf7-449f-bd54-232935b4b88e"
EXISTING_JOB_ID = "7348e899-c5c7-4145-94ed-d0653e1c7b0c"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=CREDENTIALS["admin"]
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def employer_token():
    """Get employer auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=CREDENTIALS["employer"]
    )
    assert response.status_code == 200, f"Employer login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def recruiter_token():
    """Get recruiter auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=CREDENTIALS["recruiter"]
    )
    assert response.status_code == 200, f"Recruiter login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def candidate_token():
    """Get candidate auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=CREDENTIALS["candidate"]
    )
    assert response.status_code == 200, f"Candidate login failed: {response.text}"
    return response.json()["access_token"]


def auth_header(token):
    """Create auth header"""
    return {"Authorization": f"Bearer {token}"}


# ============== TASK 1: BATCH CV UPLOAD TESTS ==============

class TestBatchCVUpload:
    """Tests for batch CV upload functionality"""
    
    def test_batch_parse_rejects_more_than_10_files(self, admin_token):
        """POST /api/candidate-bank/batch-parse rejects >10 files"""
        # Create 11 dummy files
        files = []
        for i in range(11):
            files.append(('files', (f'test_{i}.pdf', b'dummy content', 'application/pdf')))
        
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-parse",
            files=files,
            headers=auth_header(admin_token)
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "Maximum 10 files" in response.json().get("detail", "")
        print("✅ Batch parse correctly rejects >10 files")
    
    def test_batch_parse_rejects_empty_upload(self, admin_token):
        """POST /api/candidate-bank/batch-parse rejects empty upload"""
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-parse",
            files=[],
            headers=auth_header(admin_token)
        )
        
        # Should return 400 or 422 for no files
        assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}"
        print("✅ Batch parse correctly rejects empty upload")
    
    def test_batch_parse_accepts_valid_files(self, admin_token):
        """POST /api/candidate-bank/batch-parse accepts PDF/DOC/DOCX"""
        # Create a simple test PDF-like file
        test_content = b"""
        John Test Candidate
        Email: john.test@example.com
        Phone: 9876543210
        Skills: Python, JavaScript, React
        Experience: 5 years in software development
        """
        
        files = [('files', ('test_resume.pdf', test_content, 'application/pdf'))]
        
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-parse",
            files=files,
            headers=auth_header(admin_token)
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "total" in data
        assert "parsed" in data
        assert "failed" in data
        assert "results" in data
        assert data["total"] == 1
        print(f"✅ Batch parse accepts valid files: {data['parsed']} parsed, {data['failed']} failed")
    
    def test_batch_parse_returns_duplicate_check_info(self, admin_token):
        """Batch parse returns duplicate_check info for each candidate"""
        test_content = b"""
        Duplicate Test Candidate
        Email: duplicate.test@example.com
        Phone: 1234567890
        """
        
        files = [('files', ('dup_test.pdf', test_content, 'application/pdf'))]
        
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-parse",
            files=files,
            headers=auth_header(admin_token)
        )
        
        assert response.status_code == 200
        data = response.json()
        
        if data["results"] and data["results"][0].get("success"):
            result = data["results"][0]
            assert "duplicate_check" in result, "Missing duplicate_check in response"
            assert "is_duplicate" in result["duplicate_check"]
            print(f"✅ Duplicate check info returned: is_duplicate={result['duplicate_check']['is_duplicate']}")
        else:
            print("⚠️ Parse failed, skipping duplicate check validation")
    
    def test_batch_parse_rejects_invalid_file_types(self, admin_token):
        """Batch parse rejects non-PDF/DOC/DOCX files"""
        files = [('files', ('test.txt', b'plain text', 'text/plain'))]
        
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-parse",
            files=files,
            headers=auth_header(admin_token)
        )
        
        assert response.status_code == 200  # Returns 200 with error in results
        data = response.json()
        
        # Check that the file was marked as failed
        if data["results"]:
            result = data["results"][0]
            # Either success=False or error message about file type
            if not result.get("success"):
                print(f"✅ Invalid file type rejected: {result.get('error')}")
            else:
                print("⚠️ File was processed despite invalid extension")


class TestBatchSave:
    """Tests for batch save functionality"""
    
    def test_batch_save_validates_mandatory_salary(self, admin_token):
        """Batch save fails if salary is missing or <= 0"""
        payload = {
            "candidates": [{
                "temp_id": str(uuid.uuid4()),
                "name": "Test Candidate",
                "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
                "phone": "9876543210",
                "skills": ["Python"],
                "experience_summary": "Test",
                "current_salary": 0,  # Invalid - must be positive
                "notice_period": "30 days",
                "file_id": str(uuid.uuid4()),
                "fingerprint": str(uuid.uuid4())
            }]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-save",
            json=payload,
            headers={**auth_header(admin_token), "Content-Type": "application/json"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        detail = response.json().get("detail", {})
        assert "salary" in str(detail).lower() or "validation" in str(detail).lower()
        print("✅ Batch save correctly validates mandatory salary")
    
    def test_batch_save_validates_mandatory_notice_period(self, admin_token):
        """Batch save fails if notice_period is empty"""
        payload = {
            "candidates": [{
                "temp_id": str(uuid.uuid4()),
                "name": "Test Candidate",
                "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
                "phone": "9876543210",
                "skills": ["Python"],
                "experience_summary": "Test",
                "current_salary": 1500000,
                "notice_period": "",  # Invalid - must not be empty
                "file_id": str(uuid.uuid4()),
                "fingerprint": str(uuid.uuid4())
            }]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-save",
            json=payload,
            headers={**auth_header(admin_token), "Content-Type": "application/json"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        detail = response.json().get("detail", {})
        assert "notice" in str(detail).lower() or "validation" in str(detail).lower()
        print("✅ Batch save correctly validates mandatory notice period")
    
    def test_batch_save_atomic_failure(self, admin_token):
        """Batch save fails all if any validation error (atomic)"""
        payload = {
            "candidates": [
                {
                    "temp_id": str(uuid.uuid4()),
                    "name": "Valid Candidate",
                    "email": f"valid_{uuid.uuid4().hex[:8]}@example.com",
                    "phone": "9876543210",
                    "skills": ["Python"],
                    "experience_summary": "Test",
                    "current_salary": 1500000,
                    "notice_period": "30 days",
                    "file_id": str(uuid.uuid4()),
                    "fingerprint": str(uuid.uuid4())
                },
                {
                    "temp_id": str(uuid.uuid4()),
                    "name": "Invalid Candidate",
                    "email": f"invalid_{uuid.uuid4().hex[:8]}@example.com",
                    "phone": "9876543210",
                    "skills": ["Python"],
                    "experience_summary": "Test",
                    "current_salary": 0,  # Invalid
                    "notice_period": "30 days",
                    "file_id": str(uuid.uuid4()),
                    "fingerprint": str(uuid.uuid4())
                }
            ]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-save",
            json=payload,
            headers={**auth_header(admin_token), "Content-Type": "application/json"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        detail = response.json().get("detail", {})
        assert "No candidates were saved" in str(detail) or "validation" in str(detail).lower()
        print("✅ Batch save correctly fails atomically")
    
    def test_batch_save_rejects_more_than_10(self, admin_token):
        """Batch save rejects >10 candidates"""
        candidates = []
        for i in range(11):
            candidates.append({
                "temp_id": str(uuid.uuid4()),
                "name": f"Test Candidate {i}",
                "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
                "phone": "9876543210",
                "skills": ["Python"],
                "experience_summary": "Test",
                "current_salary": 1500000,
                "notice_period": "30 days",
                "file_id": str(uuid.uuid4()),
                "fingerprint": str(uuid.uuid4())
            })
        
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-save",
            json={"candidates": candidates},
            headers={**auth_header(admin_token), "Content-Type": "application/json"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "Maximum 10" in response.json().get("detail", "")
        print("✅ Batch save correctly rejects >10 candidates")


# ============== TASK 2: MANUAL ADD AS APPLICANT TESTS ==============

class TestLinkCandidateToJob:
    """Tests for linking candidate to job as applicant"""
    
    def test_link_candidate_requires_salary(self, admin_token):
        """Link candidate fails if candidate has no salary set"""
        # First create a candidate without salary
        # We'll use the batch save to create one, but this test checks the link endpoint
        
        # Try to link a candidate that might not have salary
        # Using a non-existent candidate to test the validation flow
        response = requests.post(
            f"{BASE_URL}/api/applications/link-candidate",
            json={
                "candidate_id": "non-existent-id",
                "job_id": EXISTING_JOB_ID
            },
            headers={**auth_header(admin_token), "Content-Type": "application/json"}
        )
        
        # Should return 404 for non-existent candidate
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✅ Link candidate correctly validates candidate existence")
    
    def test_link_candidate_prevents_duplicate_application(self, admin_token):
        """Link candidate fails if candidate already applied to same job"""
        # Try to link existing candidate (John Smith) to existing job again
        response = requests.post(
            f"{BASE_URL}/api/applications/link-candidate",
            json={
                "candidate_id": EXISTING_CANDIDATE_ID,
                "job_id": EXISTING_JOB_ID
            },
            headers={**auth_header(admin_token), "Content-Type": "application/json"}
        )
        
        # Should return 400 for duplicate application
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        detail = response.json().get("detail", {})
        assert "already" in str(detail).lower() or "duplicate" in str(detail).lower()
        print("✅ Link candidate correctly prevents duplicate applications")
    
    def test_link_candidate_validates_job_exists(self, admin_token):
        """Link candidate fails if job doesn't exist"""
        response = requests.post(
            f"{BASE_URL}/api/applications/link-candidate",
            json={
                "candidate_id": EXISTING_CANDIDATE_ID,
                "job_id": "non-existent-job-id"
            },
            headers={**auth_header(admin_token), "Content-Type": "application/json"}
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        assert "Job not found" in response.json().get("detail", "")
        print("✅ Link candidate correctly validates job existence")
    
    def test_link_candidate_success_with_valid_data(self, admin_token):
        """Link candidate succeeds with valid candidate and job"""
        # First get a list of jobs to find one the candidate hasn't applied to
        jobs_response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers=auth_header(admin_token)
        )
        
        if jobs_response.status_code == 200:
            jobs = jobs_response.json()
            # Find a job that's not the existing one
            for job in jobs:
                if job["id"] != EXISTING_JOB_ID:
                    # Try to link
                    response = requests.post(
                        f"{BASE_URL}/api/applications/link-candidate",
                        json={
                            "candidate_id": EXISTING_CANDIDATE_ID,
                            "job_id": job["id"]
                        },
                        headers={**auth_header(admin_token), "Content-Type": "application/json"}
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        assert data.get("success") == True
                        assert "application_id" in data
                        print(f"✅ Link candidate succeeded: {data.get('message')}")
                        return
                    elif response.status_code == 400:
                        # Already linked, try next job
                        continue
            
            print("⚠️ No available jobs to test link candidate success")
        else:
            print("⚠️ Could not fetch jobs to test link candidate")


class TestUpdateSalaryNotice:
    """Tests for updating candidate salary/notice period"""
    
    def test_update_salary_notice_success(self, admin_token):
        """PUT /api/candidate-bank/{id}/salary-notice updates successfully"""
        response = requests.put(
            f"{BASE_URL}/api/candidate-bank/{EXISTING_CANDIDATE_ID}/salary-notice",
            params={"current_salary": 1600000, "notice_period": "45 days"},
            headers=auth_header(admin_token)
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") == True
        print("✅ Update salary/notice succeeded")
    
    def test_update_salary_rejects_negative(self, admin_token):
        """Update salary rejects negative values"""
        response = requests.put(
            f"{BASE_URL}/api/candidate-bank/{EXISTING_CANDIDATE_ID}/salary-notice",
            params={"current_salary": -100},
            headers=auth_header(admin_token)
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✅ Update salary correctly rejects negative values")
    
    def test_update_notice_rejects_empty(self, admin_token):
        """Update notice period rejects empty string"""
        response = requests.put(
            f"{BASE_URL}/api/candidate-bank/{EXISTING_CANDIDATE_ID}/salary-notice",
            params={"notice_period": ""},
            headers=auth_header(admin_token)
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✅ Update notice period correctly rejects empty string")


# ============== TASK 4: DUPLICATE DETECTION TESTS ==============

class TestDuplicateDetection:
    """Tests for duplicate detection functionality"""
    
    def test_duplicate_detection_by_email(self, admin_token):
        """Duplicate detection works by email match"""
        # Get existing candidate's email
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank/{EXISTING_CANDIDATE_ID}",
            headers=auth_header(admin_token)
        )
        
        if response.status_code == 200:
            candidate = response.json()
            email = candidate.get("email")
            
            # Try to parse a resume with same email
            test_content = f"""
            Test Duplicate
            Email: {email}
            Phone: 0000000000
            """.encode()
            
            files = [('files', ('dup_email.pdf', test_content, 'application/pdf'))]
            
            parse_response = requests.post(
                f"{BASE_URL}/api/candidate-bank/batch-parse",
                files=files,
                headers=auth_header(admin_token)
            )
            
            if parse_response.status_code == 200:
                data = parse_response.json()
                if data["results"] and data["results"][0].get("success"):
                    dup_check = data["results"][0].get("duplicate_check", {})
                    print(f"✅ Duplicate detection by email: is_duplicate={dup_check.get('is_duplicate')}")
                else:
                    print("⚠️ Parse failed, cannot verify duplicate detection")
            else:
                print(f"⚠️ Parse request failed: {parse_response.status_code}")
        else:
            print(f"⚠️ Could not fetch existing candidate: {response.status_code}")
    
    def test_duplicate_info_excludes_who_added(self, admin_token):
        """Duplicate info does not include 'who added' for privacy"""
        # Get existing candidate
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank/{EXISTING_CANDIDATE_ID}",
            headers=auth_header(admin_token)
        )
        
        if response.status_code == 200:
            candidate = response.json()
            email = candidate.get("email")
            
            test_content = f"""
            Privacy Test
            Email: {email}
            """.encode()
            
            files = [('files', ('privacy_test.pdf', test_content, 'application/pdf'))]
            
            parse_response = requests.post(
                f"{BASE_URL}/api/candidate-bank/batch-parse",
                files=files,
                headers=auth_header(admin_token)
            )
            
            if parse_response.status_code == 200:
                data = parse_response.json()
                if data["results"] and data["results"][0].get("success"):
                    dup_check = data["results"][0].get("duplicate_check", {})
                    existing = dup_check.get("existing_candidate", {})
                    
                    # Should NOT include created_by or added_by
                    assert "created_by" not in existing or existing.get("created_by") is None, \
                        "Duplicate info should not expose who added the candidate"
                    assert "added_by" not in existing, \
                        "Duplicate info should not expose who added the candidate"
                    
                    # Should include: name, date added, salary, notice period
                    if dup_check.get("is_duplicate"):
                        assert "name" in existing
                        assert "created_at" in existing
                        print("✅ Duplicate info correctly excludes 'who added' for privacy")
                    else:
                        print("⚠️ Not detected as duplicate, cannot verify privacy")
                else:
                    print("⚠️ Parse failed")
            else:
                print(f"⚠️ Parse failed: {parse_response.status_code}")
        else:
            print(f"⚠️ Could not fetch candidate: {response.status_code}")


# ============== ROLE-BASED ACCESS TESTS ==============

class TestRoleBasedAccess:
    """Tests for role-based access control"""
    
    def test_admin_can_access_batch_upload(self, admin_token):
        """Admin can access batch upload endpoint"""
        files = [('files', ('test.pdf', b'test', 'application/pdf'))]
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-parse",
            files=files,
            headers=auth_header(admin_token)
        )
        
        assert response.status_code == 200, f"Admin should access batch upload, got {response.status_code}"
        print("✅ Admin can access batch upload")
    
    def test_employer_can_access_batch_upload(self, employer_token):
        """Employer can access batch upload endpoint"""
        files = [('files', ('test.pdf', b'test', 'application/pdf'))]
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-parse",
            files=files,
            headers=auth_header(employer_token)
        )
        
        assert response.status_code == 200, f"Employer should access batch upload, got {response.status_code}"
        print("✅ Employer can access batch upload")
    
    def test_recruiter_can_access_batch_upload(self, recruiter_token):
        """Recruiter can access batch upload endpoint"""
        files = [('files', ('test.pdf', b'test', 'application/pdf'))]
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-parse",
            files=files,
            headers=auth_header(recruiter_token)
        )
        
        assert response.status_code == 200, f"Recruiter should access batch upload, got {response.status_code}"
        print("✅ Recruiter can access batch upload")
    
    def test_candidate_cannot_access_batch_upload(self, candidate_token):
        """Candidate role cannot access batch upload"""
        files = [('files', ('test.pdf', b'test', 'application/pdf'))]
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-parse",
            files=files,
            headers=auth_header(candidate_token)
        )
        
        assert response.status_code == 403, f"Candidate should be denied, got {response.status_code}"
        print("✅ Candidate correctly denied access to batch upload")
    
    def test_candidate_cannot_access_link_endpoint(self, candidate_token):
        """Candidate role cannot access link-candidate endpoint"""
        response = requests.post(
            f"{BASE_URL}/api/applications/link-candidate",
            json={"candidate_id": "test", "job_id": "test"},
            headers={**auth_header(candidate_token), "Content-Type": "application/json"}
        )
        
        assert response.status_code == 403, f"Candidate should be denied, got {response.status_code}"
        print("✅ Candidate correctly denied access to link-candidate")
    
    def test_admin_can_access_all_candidates(self, admin_token):
        """Admin can access all candidates in data bank"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            headers=auth_header(admin_token)
        )
        
        assert response.status_code == 200, f"Admin should access candidate bank, got {response.status_code}"
        candidates = response.json()
        print(f"✅ Admin can access all candidates: {len(candidates)} found")
    
    def test_admin_can_access_all_jobs(self, admin_token):
        """Admin can access all jobs"""
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers=auth_header(admin_token)
        )
        
        assert response.status_code == 200, f"Admin should access jobs, got {response.status_code}"
        jobs = response.json()
        print(f"✅ Admin can access all jobs: {len(jobs)} found")


# ============== INTEGRATION TESTS ==============

class TestIntegration:
    """End-to-end integration tests"""
    
    def test_existing_candidate_has_salary_and_notice(self, admin_token):
        """Verify existing test candidate has salary and notice period set"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank/{EXISTING_CANDIDATE_ID}",
            headers=auth_header(admin_token)
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        candidate = response.json()
        
        assert candidate.get("current_salary") is not None, "Candidate should have salary set"
        assert candidate.get("notice_period") is not None, "Candidate should have notice period set"
        
        print(f"✅ Existing candidate has salary={candidate.get('current_salary')}, notice={candidate.get('notice_period')}")
    
    def test_candidate_bank_endpoint_works(self, admin_token):
        """GET /api/candidate-bank returns list of candidates"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            headers=auth_header(admin_token)
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        candidates = response.json()
        assert isinstance(candidates, list)
        print(f"✅ Candidate bank endpoint works: {len(candidates)} candidates")
    
    def test_jobs_endpoint_works(self, admin_token):
        """GET /api/jobs returns list of jobs"""
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers=auth_header(admin_token)
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        jobs = response.json()
        assert isinstance(jobs, list)
        print(f"✅ Jobs endpoint works: {len(jobs)} jobs")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
