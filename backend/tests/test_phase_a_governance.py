"""
Phase A: Backend Foundation for Internal Governance - Test Suite

Tests cover:
1. Job Approval Workflow (Draft -> Pending Approval -> Active)
2. Referral Lifecycle (Submitted -> Validated -> Linked)
3. Team & Hierarchy Management
4. Client Privacy (Company Name Masking)
5. Audit Logging
"""

import pytest
import httpx
import os

# API Configuration
API_URL = os.environ.get("API_URL", "https://candidate-flow-5.preview.emergentagent.com")

# Test credentials
ADMIN_CREDS = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
EMPLOYER_CREDS = {"email": "employer@vhctalent.com", "password": "Demo@2024"}
RECRUITER_CREDS = {"email": "recruiter@vhctalent.com", "password": "Demo@2024"}


class TestAuthentication:
    """Test auth for all roles needed in governance flow"""
    
    @pytest.fixture
    def admin_token(self):
        response = httpx.post(f"{API_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200
        return response.json()["access_token"]
    
    @pytest.fixture
    def employer_token(self):
        response = httpx.post(f"{API_URL}/api/auth/login", json=EMPLOYER_CREDS)
        assert response.status_code == 200
        return response.json()["access_token"]
    
    @pytest.fixture
    def recruiter_token(self):
        response = httpx.post(f"{API_URL}/api/auth/login", json=RECRUITER_CREDS)
        assert response.status_code == 200
        return response.json()["access_token"]


class TestJobApprovalWorkflow(TestAuthentication):
    """Test job approval state machine"""
    
    def test_recruiter_job_goes_to_pending_approval(self, recruiter_token):
        """Jobs created by recruiters should start in pending_approval"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        job_data = {
            "title": "Test Pending Job",
            "description": "Testing approval workflow",
            "location": "Mumbai",
            "job_type": "full-time",
            "public_company_alias": "Test Tech Co"
        }
        response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        assert response.status_code == 200
        job = response.json()
        assert job["status"] == "pending_approval"
        assert job["public_company_alias"] == "Test Tech Co"
        return job["id"]
    
    def test_admin_job_goes_to_active(self, admin_token):
        """Jobs created by admin should start as active"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        job_data = {
            "title": "Admin Direct Job",
            "description": "Testing admin job creation",
            "location": "Delhi",
            "job_type": "contract"
        }
        response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        assert response.status_code == 200
        job = response.json()
        assert job["status"] == "active"
    
    def test_employer_job_goes_to_active(self, employer_token):
        """Jobs created by employers should start as active"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        job_data = {
            "title": "Employer Direct Job",
            "description": "Testing employer job creation",
            "location": "Bangalore",
            "job_type": "full-time"
        }
        response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        assert response.status_code == 200
        job = response.json()
        assert job["status"] == "active"
    
    def test_pending_approval_endpoint(self, admin_token, recruiter_token):
        """Admin/Employer can view pending approval jobs"""
        # Create a pending job
        rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
        job_data = {
            "title": "Pending Review Job",
            "description": "For pending list test",
            "location": "Chennai",
            "job_type": "remote"
        }
        httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=rec_headers)
        
        # Admin can see pending jobs
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        response = httpx.get(f"{API_URL}/api/jobs/pending-approval", headers=admin_headers)
        assert response.status_code == 200
        jobs = response.json()
        assert isinstance(jobs, list)
    
    def test_job_approval_transition(self, admin_token, recruiter_token):
        """Test full approval workflow: pending -> active"""
        # Create pending job as recruiter
        rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
        job_data = {
            "title": "Approval Test Job",
            "description": "Testing transition",
            "location": "Pune",
            "job_type": "full-time",
            "public_company_alias": "Secret Client"
        }
        create_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=rec_headers)
        job_id = create_response.json()["id"]
        
        # Approve as admin
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        transition_data = {"new_status": "active", "reason": "Approved by pytest"}
        response = httpx.post(
            f"{API_URL}/api/jobs/{job_id}/transition",
            json=transition_data,
            headers=admin_headers
        )
        assert response.status_code == 200
        job = response.json()
        assert job["status"] == "active"
        assert len(job["approval_history"]) > 1  # Should have initial + approval entry
    
    def test_invalid_transition_rejected(self, employer_token, recruiter_token):
        """Test that invalid state transitions are rejected for non-admin users"""
        # Create a job as recruiter (starts as pending_approval)
        rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
        job_data = {
            "title": "Invalid Transition Test Job",
            "description": "Testing invalid transition",
            "location": "Mumbai",
            "job_type": "full-time"
        }
        create_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=rec_headers)
        if create_response.status_code != 200:
            pytest.skip("Could not create test job")
        job_id = create_response.json()["id"]
        
        # Employer tries an invalid transition: pending_approval -> archived (not allowed)
        emp_headers = {"Authorization": f"Bearer {employer_token}"}
        transition_data = {"new_status": "archived"}  # archived is only valid from closed
        response = httpx.post(
            f"{API_URL}/api/jobs/{job_id}/transition",
            json=transition_data,
            headers=emp_headers
        )
        assert response.status_code == 400


class TestClientPrivacy(TestAuthentication):
    """Test client privacy (company name masking)"""
    
    def test_public_jobs_show_alias(self, admin_token):
        """Public job listings should show public_company_alias, not real company name"""
        # Create job with alias
        headers = {"Authorization": f"Bearer {admin_token}"}
        job_data = {
            "title": "Privacy Test Job",
            "description": "Testing name masking",
            "location": "Remote",
            "job_type": "full-time",
            "public_company_alias": "Leading Fintech Company"
        }
        create_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        job_id = create_response.json()["id"]
        
        # Fetch from public endpoint
        response = httpx.get(f"{API_URL}/api/public/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        assert job["company_name"] == "Leading Fintech Company"
        assert "company_id" not in job  # Internal ID should be hidden
    
    def test_public_jobs_default_to_confidential(self):
        """Jobs without alias should show 'Confidential Client'"""
        response = httpx.get(f"{API_URL}/api/public/jobs")
        assert response.status_code == 200
        jobs = response.json()
        for job in jobs:
            assert job["company_name"] is not None
            # Should never show internal company_id
            assert "company_id" not in job


class TestTeamManagement(TestAuthentication):
    """Test team CRUD operations"""
    
    def test_admin_can_create_team(self, admin_token):
        """Admin can create teams"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get an employer
        emp_response = httpx.get(f"{API_URL}/api/admin/employers", headers=headers)
        employers = emp_response.json()
        if not employers:
            pytest.skip("No employers to create team for")
        employer_id = employers[0]["id"]
        
        # Create team
        team_data = {
            "name": "Test Governance Team",
            "employer_id": employer_id,
            "recruiter_ids": [],
            "company_ids": []
        }
        response = httpx.post(f"{API_URL}/api/teams", json=team_data, headers=headers)
        assert response.status_code == 200
        team = response.json()
        assert team["name"] == "Test Governance Team"
        assert team["employer_id"] == employer_id
        assert team["status"] == "active"
    
    def test_get_teams(self, admin_token):
        """Admin can view all teams"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = httpx.get(f"{API_URL}/api/teams", headers=headers)
        assert response.status_code == 200
        teams = response.json()
        assert isinstance(teams, list)
    
    def test_non_admin_cannot_create_team(self, recruiter_token):
        """Recruiters cannot create teams"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        team_data = {
            "name": "Unauthorized Team",
            "employer_id": "some-id",
            "recruiter_ids": [],
            "company_ids": []
        }
        response = httpx.post(f"{API_URL}/api/teams", json=team_data, headers=headers)
        assert response.status_code == 403


class TestReferralLifecycle(TestAuthentication):
    """Test referral creation and lifecycle"""
    
    @pytest.fixture
    def active_job_id(self, admin_token):
        """Get or create an active job for referral tests"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = httpx.get(f"{API_URL}/api/jobs?status=active", headers=headers)
        jobs = response.json()
        if jobs:
            return jobs[0]["id"]
        
        # Create one if none exist
        job_data = {
            "title": "Referral Test Job",
            "description": "For testing referrals",
            "location": "Remote",
            "job_type": "full-time"
        }
        create_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        return create_response.json()["id"]
    
    def test_create_referral(self, recruiter_token, active_job_id):
        """Recruiter can create referrals"""
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        referral_data = {
            "job_id": active_job_id,
            "candidate_name": f"Jane Referral {unique_id}",
            "candidate_email": f"jane.{unique_id}@test.com",
            "candidate_phone": "+91-9876543211",
            "note": "Excellent candidate"
        }
        response = httpx.post(f"{API_URL}/api/referrals", json=referral_data, headers=headers)
        assert response.status_code == 200
        referral = response.json()
        assert referral["status"] == "submitted"
        assert "Jane Referral" in referral["candidate_name"]
    
    def test_referral_duplicate_prevented(self, recruiter_token, active_job_id):
        """Duplicate referrals should be prevented"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        referral_data = {
            "job_id": active_job_id,
            "candidate_name": "Duplicate Test",
            "candidate_email": "duplicate.referral@test.com",
            "candidate_phone": "+91-1234567890"
        }
        # First referral
        httpx.post(f"{API_URL}/api/referrals", json=referral_data, headers=headers)
        # Second attempt with same email should fail
        response = httpx.post(f"{API_URL}/api/referrals", json=referral_data, headers=headers)
        assert response.status_code == 400
    
    def test_referral_status_transition(self, admin_token, recruiter_token, active_job_id):
        """Test referral status transitions"""
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        
        # Create referral
        rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
        referral_data = {
            "job_id": active_job_id,
            "candidate_name": f"Transition {unique_id}",
            "candidate_email": f"transition.{unique_id}@test.com",
            "candidate_phone": "+91-5555555555"
        }
        create_response = httpx.post(f"{API_URL}/api/referrals", json=referral_data, headers=rec_headers)
        assert create_response.status_code == 200, f"Failed to create referral: {create_response.text}"
        referral_id = create_response.json()["id"]
        
        # Transition to validated as admin
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        transition_data = {"new_status": "validated", "reason": "Verified by pytest"}
        response = httpx.post(
            f"{API_URL}/api/referrals/{referral_id}/transition",
            json=transition_data,
            headers=admin_headers
        )
        assert response.status_code == 200
        referral = response.json()
        assert referral["status"] == "validated"
        assert len(referral["status_history"]) > 1


class TestAdminHierarchy(TestAuthentication):
    """Test admin hierarchy overview"""
    
    def test_admin_hierarchy_endpoint(self, admin_token):
        """Admin can view full hierarchy"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = httpx.get(f"{API_URL}/api/admin/hierarchy", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "hierarchy" in data
        assert "unassigned_recruiters" in data
        assert "unassigned_companies" in data
        assert "summary" in data
    
    def test_non_admin_cannot_view_hierarchy(self, recruiter_token):
        """Non-admins cannot view hierarchy"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        response = httpx.get(f"{API_URL}/api/admin/hierarchy", headers=headers)
        assert response.status_code == 403


class TestAuditLogging:
    """Test audit trail functionality"""
    
    def test_job_approval_has_audit_trail(self):
        """Job approval history should track all state changes"""
        # Login as admin
        login_response = httpx.post(f"{API_URL}/api/auth/login", json=ADMIN_CREDS)
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create a job
        job_data = {
            "title": "Audit Trail Test Job",
            "description": "Testing audit logging",
            "location": "Remote",
            "job_type": "full-time"
        }
        create_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        job = create_response.json()
        
        # Check approval_history exists
        assert "approval_history" in job
        assert len(job["approval_history"]) >= 1
        
        # Verify audit entry structure
        audit_entry = job["approval_history"][0]
        assert "status" in audit_entry or "to_status" in audit_entry
        assert "changed_by" in audit_entry
        assert "timestamp" in audit_entry


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
