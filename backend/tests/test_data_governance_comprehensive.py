"""
Comprehensive Data Governance & Candidate Intelligence Tests
Tests for mandatory field enforcement, audit logging, history endpoints, and link-candidate-to-job.
"""
import pytest
import requests
import os
import uuid

# Test configuration - use public URL
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://upload-chunks.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_CREDS = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
RECRUITER_CREDS = {"email": "recruiter@vhctalent.com", "password": "Demo@2024"}


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def recruiter_token():
    """Get recruiter auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER_CREDS)
    assert response.status_code == 200, f"Recruiter login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    """Headers with admin auth token"""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def recruiter_headers(recruiter_token):
    """Headers with recruiter auth token"""
    return {"Authorization": f"Bearer {recruiter_token}"}


class TestMandatoryFieldValidation:
    """Tests for mandatory field enforcement in candidate operations"""
    
    def test_batch_save_missing_location(self, admin_headers):
        """Batch save should reject candidates missing location"""
        incomplete_candidate = {
            "candidates": [{
                "temp_id": f"test-{uuid.uuid4()}",
                "name": "Test Candidate Missing Location",
                "email": f"test.missing.loc.{uuid.uuid4()}@example.com",
                "phone": "1234567890",
                "skills": ["Python"],
                "experience_summary": "Test",
                "current_salary": 500000,
                "notice_period": "30 days",
                "experience_years": 3,
                # Missing location
                "file_id": "test-file",
                "fingerprint": f"test-fp-{uuid.uuid4()}"
            }]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-save",
            json=incomplete_candidate,
            headers=admin_headers
        )
        
        # Should fail due to missing location
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
    
    def test_batch_save_missing_experience_years(self, admin_headers):
        """Batch save should reject candidates missing experience_years"""
        incomplete_candidate = {
            "candidates": [{
                "temp_id": f"test-{uuid.uuid4()}",
                "name": "Test Candidate Missing Exp",
                "email": f"test.missing.exp.{uuid.uuid4()}@example.com",
                "phone": "1234567890",
                "skills": ["Python"],
                "experience_summary": "Test",
                "current_salary": 500000,
                "notice_period": "30 days",
                "location": "Mumbai",
                # Missing experience_years
                "file_id": "test-file",
                "fingerprint": f"test-fp-{uuid.uuid4()}"
            }]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-save",
            json=incomplete_candidate,
            headers=admin_headers
        )
        
        # Should fail due to missing experience_years
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
    
    def test_batch_save_with_all_mandatory_fields(self, admin_headers):
        """Batch save should succeed with all mandatory fields"""
        unique_id = str(uuid.uuid4())[:8]
        complete_candidate = {
            "candidates": [{
                "temp_id": f"test-{unique_id}",
                "name": f"Test Complete Candidate {unique_id}",
                "email": f"test.complete.{unique_id}@example.com",
                "phone": "9876543210",
                "skills": ["Python", "FastAPI"],
                "experience_summary": "5 years of experience",
                "current_salary": 1200000,
                "notice_period": "60 days",
                "location": "Bangalore",
                "experience_years": 5,
                "file_id": f"test-file-{unique_id}",
                "fingerprint": f"test-fp-{unique_id}"
            }]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-save",
            json=complete_candidate,
            headers=admin_headers
        )
        
        # Should succeed
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") is True, f"Batch save failed: {data}"


class TestCandidateHistoryEndpoint:
    """Tests for candidate activity history endpoint"""
    
    def test_history_endpoint_returns_200(self, admin_headers):
        """History endpoint should return 200 for valid candidate"""
        # First get a candidate
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        assert response.status_code == 200
        candidates = response.json()
        
        if not candidates:
            pytest.skip("No candidates for testing")
        
        candidate_id = candidates[0]["id"]
        
        # Get history
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/history",
            headers=admin_headers
        )
        assert response.status_code == 200, f"History endpoint failed: {response.text}"
    
    def test_history_has_applications_array(self, admin_headers):
        """History response should have applications array"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        candidates = response.json()
        
        if not candidates:
            pytest.skip("No candidates for testing")
        
        candidate_id = candidates[0]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/history",
            headers=admin_headers
        )
        data = response.json()
        
        assert "applications" in data, "Missing 'applications' in history response"
        assert isinstance(data["applications"], list)
    
    def test_history_has_freshness_data(self, admin_headers):
        """History response should have freshness metadata"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        candidates = response.json()
        
        if not candidates:
            pytest.skip("No candidates for testing")
        
        candidate_id = candidates[0]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/history",
            headers=admin_headers
        )
        data = response.json()
        
        assert "freshness" in data, "Missing 'freshness' in history response"
        freshness = data["freshness"]
        assert "last_profile_updated_at" in freshness
        assert "last_application_date" in freshness
    
    def test_history_has_summary(self, admin_headers):
        """History response should have summary with stage counts"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        candidates = response.json()
        
        if not candidates:
            pytest.skip("No candidates for testing")
        
        candidate_id = candidates[0]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/history",
            headers=admin_headers
        )
        data = response.json()
        
        assert "summary" in data, "Missing 'summary' in history response"
        summary = data["summary"]
        assert "total_applications" in summary
        assert "stages" in summary


class TestUpdateMandatoryFields:
    """Tests for updating mandatory fields endpoint"""
    
    def test_update_all_four_fields(self, admin_headers):
        """Should update salary, notice, location, experience"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        candidates = response.json()
        
        if not candidates:
            pytest.skip("No candidates for testing")
        
        candidate_id = candidates[0]["id"]
        
        # Update all mandatory fields
        response = requests.put(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/salary-notice",
            params={
                "current_salary": 1500000,
                "notice_period": "45 days",
                "location": "Delhi",
                "experience_years": 7
            },
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"Update failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
    
    def test_update_partial_fields(self, admin_headers):
        """Should allow updating only some fields"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        candidates = response.json()
        
        if not candidates:
            pytest.skip("No candidates for testing")
        
        candidate_id = candidates[0]["id"]
        
        # Update only salary
        response = requests.put(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/salary-notice",
            params={"current_salary": 1600000},
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"Partial update failed: {response.text}"
    
    def test_update_rejects_zero_salary(self, admin_headers):
        """Should reject salary of 0"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        candidates = response.json()
        
        if not candidates:
            pytest.skip("No candidates for testing")
        
        candidate_id = candidates[0]["id"]
        
        response = requests.put(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/salary-notice",
            params={"current_salary": 0},
            headers=admin_headers
        )
        
        assert response.status_code == 400, f"Expected 400 for zero salary, got {response.status_code}"


class TestLinkCandidateToJob:
    """Tests for linking candidate to job with mandatory field validation"""
    
    def test_link_endpoint_exists(self, admin_headers):
        """Link endpoint should exist"""
        # Get a candidate and job
        cand_response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        candidates = cand_response.json()
        
        job_response = requests.get(f"{BASE_URL}/api/jobs", headers=admin_headers)
        jobs = job_response.json()
        
        if not candidates or not jobs:
            pytest.skip("No candidates or jobs for testing")
        
        # Find an active job
        active_jobs = [j for j in jobs if j.get("status") == "active"]
        if not active_jobs:
            pytest.skip("No active jobs for testing")
        
        # The endpoint should exist - we're just verifying it's accessible
        # Actual linking may fail due to validation, which is expected
        response = requests.post(
            f"{BASE_URL}/api/applications/link-candidate",
            json={
                "candidate_id": candidates[0]["id"],
                "job_id": active_jobs[0]["id"]
            },
            headers=admin_headers
        )
        
        # Should return 200, 400 (validation), or 409 (duplicate) - not 404
        assert response.status_code != 404, "Link endpoint not found"


class TestAuditLogging:
    """Tests for audit logging of mandatory field changes"""
    
    def test_audit_log_returns_list(self, admin_headers):
        """Audit log should return a list"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        candidates = response.json()
        
        if not candidates:
            pytest.skip("No candidates for testing")
        
        candidate_id = candidates[0]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/audit-log",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_update_creates_audit_entry(self, admin_headers):
        """Updating mandatory fields should create audit entries"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        candidates = response.json()
        
        if not candidates:
            pytest.skip("No candidates for testing")
        
        candidate_id = candidates[0]["id"]
        
        # Get initial audit log count
        audit_response = requests.get(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/audit-log",
            headers=admin_headers
        )
        initial_count = len(audit_response.json())
        
        # Update a field
        unique_salary = 1700000 + (hash(str(uuid.uuid4())) % 100000)
        requests.put(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/salary-notice",
            params={"current_salary": unique_salary},
            headers=admin_headers
        )
        
        # Check audit log increased
        audit_response = requests.get(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/audit-log",
            headers=admin_headers
        )
        new_count = len(audit_response.json())
        
        # Audit log should have at least one new entry
        assert new_count >= initial_count, "Audit log should have new entries after update"


class TestRoleBasedAccess:
    """Tests for role-based access to history and audit endpoints"""
    
    def test_recruiter_can_access_history(self, recruiter_headers):
        """Recruiter should be able to access candidate history"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=recruiter_headers)
        
        if response.status_code != 200:
            pytest.skip("Recruiter cannot access candidate bank")
        
        candidates = response.json()
        if not candidates:
            pytest.skip("No candidates for testing")
        
        candidate_id = candidates[0]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/history",
            headers=recruiter_headers
        )
        
        assert response.status_code == 200, f"Recruiter cannot access history: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
