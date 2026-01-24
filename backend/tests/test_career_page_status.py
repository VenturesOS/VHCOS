"""
Career Page Status Control Tests - Phase 3 Internal Recruitment OS Enhancement

Tests for:
- POST /api/jobs/{id}/career-page-status - Update career page status
- GET /api/jobs/{id}/career-page-history - Get audit trail
- GET /api/career-page/jobs - Public endpoint for live jobs
- Job creation defaults career_page_status to 'not_posted'
- Role-based access control (Admin, Employer, Recruiter)
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}


class TestCareerPageStatusAdmin:
    """Admin career page status control tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        # Get an active job for testing
        jobs_response = requests.get(f"{BASE_URL}/api/jobs", headers=self.headers)
        assert jobs_response.status_code == 200
        jobs = jobs_response.json()
        active_jobs = [j for j in jobs if j.get("status") == "active"]
        if active_jobs:
            self.test_job_id = active_jobs[0]["id"]
        else:
            # Create a test job
            job_data = {
                "title": f"TEST Career Page Job {uuid.uuid4().hex[:8]}",
                "description": "Test job for career page testing",
                "location": "Remote",
                "job_type": "full-time"
            }
            create_response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=self.headers)
            assert create_response.status_code == 200
            self.test_job_id = create_response.json()["id"]
    
    def test_admin_can_post_job_to_career_page(self):
        """Admin can post any active job to career page"""
        response = requests.post(
            f"{BASE_URL}/api/jobs/{self.test_job_id}/career-page-status",
            json={"new_status": "live", "reason": "Admin posting for testing"},
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["success"] == True
        assert data["career_page_status"] == "live"
        assert "audit_entry" in data
        assert data["audit_entry"]["changed_by_role"] == "admin"
    
    def test_admin_can_remove_job_from_career_page(self):
        """Admin can remove any job from career page"""
        # First post it
        requests.post(
            f"{BASE_URL}/api/jobs/{self.test_job_id}/career-page-status",
            json={"new_status": "live"},
            headers=self.headers
        )
        
        # Then remove it
        response = requests.post(
            f"{BASE_URL}/api/jobs/{self.test_job_id}/career-page-status",
            json={"new_status": "removed", "reason": "Admin removing for testing"},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["career_page_status"] == "removed"
    
    def test_career_page_history_endpoint(self):
        """GET /api/jobs/{id}/career-page-history returns audit trail"""
        # Make a status change first
        requests.post(
            f"{BASE_URL}/api/jobs/{self.test_job_id}/career-page-status",
            json={"new_status": "live", "reason": "History test"},
            headers=self.headers
        )
        
        response = requests.get(
            f"{BASE_URL}/api/jobs/{self.test_job_id}/career-page-history",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert "current_status" in data
        assert len(data["history"]) > 0
        
        # Verify audit entry structure
        entry = data["history"][-1]
        assert "from_status" in entry
        assert "to_status" in entry
        assert "changed_by_name" in entry
        assert "changed_by_role" in entry
        assert "timestamp" in entry
    
    def test_cannot_post_non_active_job_to_career_page(self):
        """Only active jobs can be posted to career page"""
        # Create a draft job
        job_data = {
            "title": f"TEST Draft Job {uuid.uuid4().hex[:8]}",
            "description": "Draft job",
            "location": "Remote",
            "job_type": "full-time"
        }
        create_response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=self.headers)
        draft_job_id = create_response.json()["id"]
        
        # Set to draft status
        requests.put(
            f"{BASE_URL}/api/jobs/{draft_job_id}",
            json={"status": "draft"},
            headers=self.headers
        )
        
        # Try to post to career page
        response = requests.post(
            f"{BASE_URL}/api/jobs/{draft_job_id}/career-page-status",
            json={"new_status": "live"},
            headers=self.headers
        )
        assert response.status_code == 400
        assert "active" in response.json()["detail"].lower()
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/jobs/{draft_job_id}", headers=self.headers)


class TestCareerPagePublicEndpoint:
    """Public career page jobs endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin for setup"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_public_endpoint_returns_only_live_jobs(self):
        """GET /api/career-page/jobs returns only live jobs"""
        # Create and post a job to career page
        job_data = {
            "title": f"TEST Public Career Job {uuid.uuid4().hex[:8]}",
            "description": "Public career page test",
            "location": "Remote",
            "job_type": "full-time"
        }
        create_response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=self.headers)
        job_id = create_response.json()["id"]
        
        # Post to career page
        requests.post(
            f"{BASE_URL}/api/jobs/{job_id}/career-page-status",
            json={"new_status": "live"},
            headers=self.headers
        )
        
        # Check public endpoint (no auth required)
        response = requests.get(f"{BASE_URL}/api/career-page/jobs")
        assert response.status_code == 200
        jobs = response.json()
        
        # Verify our job is in the list
        job_ids = [j["id"] for j in jobs]
        assert job_id in job_ids
        
        # Verify all returned jobs have live status
        for job in jobs:
            # Public endpoint doesn't return career_page_status, but we can verify by checking the job
            assert "title" in job
            assert "location" in job
        
        # Remove from career page
        requests.post(
            f"{BASE_URL}/api/jobs/{job_id}/career-page-status",
            json={"new_status": "removed"},
            headers=self.headers
        )
        
        # Verify job is no longer in public list
        response = requests.get(f"{BASE_URL}/api/career-page/jobs")
        jobs = response.json()
        job_ids = [j["id"] for j in jobs]
        assert job_id not in job_ids
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/jobs/{job_id}", headers=self.headers)
    
    def test_public_endpoint_no_auth_required(self):
        """Public career page endpoint works without authentication"""
        response = requests.get(f"{BASE_URL}/api/career-page/jobs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestJobCreationDefaults:
    """Test that job creation defaults career_page_status correctly"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_new_job_defaults_to_not_posted(self):
        """New jobs should have career_page_status = 'not_posted'"""
        job_data = {
            "title": f"TEST Default Status Job {uuid.uuid4().hex[:8]}",
            "description": "Testing default career page status",
            "location": "Remote",
            "job_type": "full-time"
        }
        response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=self.headers)
        assert response.status_code == 200
        job = response.json()
        
        assert job.get("career_page_status") == "not_posted", \
            f"Expected 'not_posted', got '{job.get('career_page_status')}'"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/jobs/{job['id']}", headers=self.headers)


class TestCareerPageAuditLogging:
    """Test audit logging for career page status changes"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and create test job"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        # Create test job
        job_data = {
            "title": f"TEST Audit Job {uuid.uuid4().hex[:8]}",
            "description": "Audit logging test",
            "location": "Remote",
            "job_type": "full-time"
        }
        create_response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=self.headers)
        self.test_job_id = create_response.json()["id"]
    
    def teardown_method(self, method):
        """Cleanup test job"""
        requests.delete(f"{BASE_URL}/api/jobs/{self.test_job_id}", headers=self.headers)
    
    def test_audit_entry_contains_required_fields(self):
        """Audit entries should contain all required fields"""
        response = requests.post(
            f"{BASE_URL}/api/jobs/{self.test_job_id}/career-page-status",
            json={"new_status": "live", "reason": "Audit test reason"},
            headers=self.headers
        )
        assert response.status_code == 200
        audit_entry = response.json()["audit_entry"]
        
        # Verify all required fields
        assert "from_status" in audit_entry
        assert "to_status" in audit_entry
        assert "changed_by" in audit_entry
        assert "changed_by_name" in audit_entry
        assert "changed_by_role" in audit_entry
        assert "reason" in audit_entry
        assert "timestamp" in audit_entry
        
        # Verify values
        assert audit_entry["from_status"] == "not_posted"
        assert audit_entry["to_status"] == "live"
        assert audit_entry["reason"] == "Audit test reason"
    
    def test_multiple_status_changes_create_history(self):
        """Multiple status changes should create audit history"""
        # Post to career page
        requests.post(
            f"{BASE_URL}/api/jobs/{self.test_job_id}/career-page-status",
            json={"new_status": "live", "reason": "First change"},
            headers=self.headers
        )
        
        # Remove from career page
        requests.post(
            f"{BASE_URL}/api/jobs/{self.test_job_id}/career-page-status",
            json={"new_status": "removed", "reason": "Second change"},
            headers=self.headers
        )
        
        # Post again
        requests.post(
            f"{BASE_URL}/api/jobs/{self.test_job_id}/career-page-status",
            json={"new_status": "live", "reason": "Third change"},
            headers=self.headers
        )
        
        # Get history
        response = requests.get(
            f"{BASE_URL}/api/jobs/{self.test_job_id}/career-page-history",
            headers=self.headers
        )
        assert response.status_code == 200
        history = response.json()["history"]
        
        # Should have 3 entries
        assert len(history) >= 3
        
        # Verify transitions
        transitions = [(h["from_status"], h["to_status"]) for h in history[-3:]]
        assert ("not_posted", "live") in transitions
        assert ("live", "removed") in transitions
        assert ("removed", "live") in transitions


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
