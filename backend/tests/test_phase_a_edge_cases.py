"""
Phase A: Backend Foundation - Edge Cases & Permission Boundary Tests

Additional tests for:
1. Job State Machine - All valid/invalid transitions
2. Referral State Machine - All valid/invalid transitions
3. Permission Boundaries - Role-based access control
4. Company-Employer Assignment
5. Team CRUD - Update and Delete operations
6. Audit Trail Verification
"""

import pytest
import httpx
import os
import uuid

# API Configuration
API_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://servermod-dev.preview.emergentagent.com")

# Test credentials
ADMIN_CREDS = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
EMPLOYER_CREDS = {"email": "employer@vhctalent.com", "password": "Demo@2024"}
RECRUITER_CREDS = {"email": "recruiter@vhctalent.com", "password": "Demo@2024"}
CANDIDATE_CREDS = {"email": "candidate@vhctalent.com", "password": "Demo@2024"}


# ============== FIXTURES ==============

@pytest.fixture
def admin_token():
    response = httpx.post(f"{API_URL}/api/auth/login", json=ADMIN_CREDS)
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture
def employer_token():
    response = httpx.post(f"{API_URL}/api/auth/login", json=EMPLOYER_CREDS)
    assert response.status_code == 200, f"Employer login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture
def recruiter_token():
    response = httpx.post(f"{API_URL}/api/auth/login", json=RECRUITER_CREDS)
    assert response.status_code == 200, f"Recruiter login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture
def candidate_token():
    response = httpx.post(f"{API_URL}/api/auth/login", json=CANDIDATE_CREDS)
    assert response.status_code == 200, f"Candidate login failed: {response.text}"
    return response.json()["access_token"]


# ============== JOB STATE MACHINE TESTS ==============

class TestJobStateMachine:
    """Test all job state transitions"""
    
    def test_active_to_on_hold_transition(self, admin_token):
        """Test active -> on_hold transition"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create active job
        job_data = {
            "title": f"State Test Job {uuid.uuid4().hex[:8]}",
            "description": "Testing state transitions",
            "location": "Remote",
            "job_type": "full-time"
        }
        create_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        assert create_response.status_code == 200
        job_id = create_response.json()["id"]
        assert create_response.json()["status"] == "active"
        
        # Transition to on_hold
        transition_data = {"new_status": "on_hold", "reason": "Budget review"}
        response = httpx.post(f"{API_URL}/api/jobs/{job_id}/transition", json=transition_data, headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "on_hold"
    
    def test_on_hold_to_active_transition(self, admin_token):
        """Test on_hold -> active transition"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create and put on hold
        job_data = {
            "title": f"On Hold Test {uuid.uuid4().hex[:8]}",
            "description": "Testing on_hold to active",
            "location": "Remote",
            "job_type": "full-time"
        }
        create_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        job_id = create_response.json()["id"]
        
        # Put on hold
        httpx.post(f"{API_URL}/api/jobs/{job_id}/transition", json={"new_status": "on_hold"}, headers=headers)
        
        # Reactivate
        response = httpx.post(f"{API_URL}/api/jobs/{job_id}/transition", json={"new_status": "active"}, headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "active"
    
    def test_active_to_closed_transition(self, admin_token):
        """Test active -> closed transition"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        job_data = {
            "title": f"Close Test {uuid.uuid4().hex[:8]}",
            "description": "Testing close transition",
            "location": "Remote",
            "job_type": "full-time"
        }
        create_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        job_id = create_response.json()["id"]
        
        response = httpx.post(f"{API_URL}/api/jobs/{job_id}/transition", json={"new_status": "closed"}, headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "closed"
    
    def test_closed_to_archived_transition(self, admin_token):
        """Test closed -> archived transition (admin only)"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        job_data = {
            "title": f"Archive Test {uuid.uuid4().hex[:8]}",
            "description": "Testing archive transition",
            "location": "Remote",
            "job_type": "full-time"
        }
        create_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        job_id = create_response.json()["id"]
        
        # Close first
        httpx.post(f"{API_URL}/api/jobs/{job_id}/transition", json={"new_status": "closed"}, headers=headers)
        
        # Archive
        response = httpx.post(f"{API_URL}/api/jobs/{job_id}/transition", json={"new_status": "archived"}, headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "archived"
    
    def test_archived_cannot_transition(self, admin_token):
        """Test that archived jobs cannot transition to any state"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        job_data = {
            "title": f"Final State Test {uuid.uuid4().hex[:8]}",
            "description": "Testing archived is final",
            "location": "Remote",
            "job_type": "full-time"
        }
        create_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        job_id = create_response.json()["id"]
        
        # Close and archive
        httpx.post(f"{API_URL}/api/jobs/{job_id}/transition", json={"new_status": "closed"}, headers=headers)
        httpx.post(f"{API_URL}/api/jobs/{job_id}/transition", json={"new_status": "archived"}, headers=headers)
        
        # Try to reactivate - should fail
        response = httpx.post(f"{API_URL}/api/jobs/{job_id}/transition", json={"new_status": "active"}, headers=headers)
        assert response.status_code == 400
    
    def test_invalid_direct_to_archived(self, employer_token):
        """Test that non-admin cannot transition directly to archived"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        job_data = {
            "title": f"Invalid Archive Test {uuid.uuid4().hex[:8]}",
            "description": "Testing invalid archive",
            "location": "Remote",
            "job_type": "full-time"
        }
        create_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        job_id = create_response.json()["id"]
        
        # Try to archive directly from active - should fail
        response = httpx.post(f"{API_URL}/api/jobs/{job_id}/transition", json={"new_status": "archived"}, headers=headers)
        assert response.status_code == 400


# ============== REFERRAL STATE MACHINE TESTS ==============

class TestReferralStateMachine:
    """Test all referral state transitions"""
    
    @pytest.fixture
    def active_job_id(self, admin_token):
        """Create an active job for referral tests"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        job_data = {
            "title": f"Referral Job {uuid.uuid4().hex[:8]}",
            "description": "For referral testing",
            "location": "Remote",
            "job_type": "full-time"
        }
        response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        return response.json()["id"]
    
    def test_submitted_to_validated(self, admin_token, recruiter_token, active_job_id):
        """Test submitted -> validated transition"""
        unique_id = uuid.uuid4().hex[:8]
        
        # Create referral as recruiter
        rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
        referral_data = {
            "job_id": active_job_id,
            "candidate_name": f"Test Candidate {unique_id}",
            "candidate_email": f"test.{unique_id}@example.com",
            "candidate_phone": "+91-9876543210"
        }
        create_response = httpx.post(f"{API_URL}/api/referrals", json=referral_data, headers=rec_headers)
        assert create_response.status_code == 200
        referral_id = create_response.json()["id"]
        
        # Validate as admin
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        response = httpx.post(
            f"{API_URL}/api/referrals/{referral_id}/transition",
            json={"new_status": "validated", "reason": "Verified contact info"},
            headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["status"] == "validated"
    
    def test_validated_to_linked(self, admin_token, recruiter_token, active_job_id):
        """Test validated -> linked transition"""
        unique_id = uuid.uuid4().hex[:8]
        
        # Create and validate referral
        rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
        referral_data = {
            "job_id": active_job_id,
            "candidate_name": f"Link Test {unique_id}",
            "candidate_email": f"link.{unique_id}@example.com",
            "candidate_phone": "+91-9876543211"
        }
        create_response = httpx.post(f"{API_URL}/api/referrals", json=referral_data, headers=rec_headers)
        referral_id = create_response.json()["id"]
        
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        httpx.post(f"{API_URL}/api/referrals/{referral_id}/transition", json={"new_status": "validated"}, headers=admin_headers)
        
        # Link
        response = httpx.post(f"{API_URL}/api/referrals/{referral_id}/transition", json={"new_status": "linked"}, headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "linked"
    
    def test_full_referral_lifecycle(self, admin_token, recruiter_token, active_job_id):
        """Test complete referral lifecycle: submitted -> validated -> linked -> in_process -> outcome_reached -> closed"""
        unique_id = uuid.uuid4().hex[:8]
        
        # Create referral
        rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
        referral_data = {
            "job_id": active_job_id,
            "candidate_name": f"Full Lifecycle {unique_id}",
            "candidate_email": f"lifecycle.{unique_id}@example.com",
            "candidate_phone": "+91-9876543212"
        }
        create_response = httpx.post(f"{API_URL}/api/referrals", json=referral_data, headers=rec_headers)
        referral_id = create_response.json()["id"]
        
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Go through all states
        states = ["validated", "linked", "in_process", "outcome_reached", "closed"]
        for state in states:
            response = httpx.post(
                f"{API_URL}/api/referrals/{referral_id}/transition",
                json={"new_status": state},
                headers=admin_headers
            )
            assert response.status_code == 200, f"Failed to transition to {state}: {response.text}"
            assert response.json()["status"] == state
        
        # Verify status_history has all transitions
        final_referral = response.json()
        assert len(final_referral["status_history"]) >= 6  # Initial + 5 transitions
    
    def test_invalid_referral_transition(self, admin_token, recruiter_token, active_job_id):
        """Test that invalid referral transitions are rejected"""
        unique_id = uuid.uuid4().hex[:8]
        
        # Create referral
        rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
        referral_data = {
            "job_id": active_job_id,
            "candidate_name": f"Invalid Trans {unique_id}",
            "candidate_email": f"invalid.{unique_id}@example.com",
            "candidate_phone": "+91-9876543213"
        }
        create_response = httpx.post(f"{API_URL}/api/referrals", json=referral_data, headers=rec_headers)
        referral_id = create_response.json()["id"]
        
        # Try to skip to in_process from submitted - should fail
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        response = httpx.post(
            f"{API_URL}/api/referrals/{referral_id}/transition",
            json={"new_status": "in_process"},
            headers=admin_headers
        )
        assert response.status_code == 400
    
    def test_closed_referral_cannot_transition(self, admin_token, recruiter_token, active_job_id):
        """Test that closed referrals cannot transition"""
        unique_id = uuid.uuid4().hex[:8]
        
        # Create and close referral
        rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
        referral_data = {
            "job_id": active_job_id,
            "candidate_name": f"Closed Test {unique_id}",
            "candidate_email": f"closed.{unique_id}@example.com",
            "candidate_phone": "+91-9876543214"
        }
        create_response = httpx.post(f"{API_URL}/api/referrals", json=referral_data, headers=rec_headers)
        referral_id = create_response.json()["id"]
        
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        httpx.post(f"{API_URL}/api/referrals/{referral_id}/transition", json={"new_status": "closed"}, headers=admin_headers)
        
        # Try to reopen - should fail
        response = httpx.post(
            f"{API_URL}/api/referrals/{referral_id}/transition",
            json={"new_status": "validated"},
            headers=admin_headers
        )
        assert response.status_code == 400


# ============== PERMISSION BOUNDARY TESTS ==============

class TestPermissionBoundaries:
    """Test role-based access control"""
    
    def test_candidate_cannot_create_job(self, candidate_token):
        """Candidates should not be able to create jobs"""
        headers = {"Authorization": f"Bearer {candidate_token}"}
        job_data = {
            "title": "Unauthorized Job",
            "description": "Should fail",
            "location": "Remote",
            "job_type": "full-time"
        }
        response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        assert response.status_code == 403
    
    def test_candidate_cannot_create_referral(self, candidate_token):
        """Candidates should not be able to create referrals"""
        headers = {"Authorization": f"Bearer {candidate_token}"}
        referral_data = {
            "job_id": "some-job-id",
            "candidate_name": "Test",
            "candidate_email": "test@test.com",
            "candidate_phone": "+91-1234567890"
        }
        response = httpx.post(f"{API_URL}/api/referrals", json=referral_data, headers=headers)
        assert response.status_code == 403
    
    def test_recruiter_cannot_transition_job(self, recruiter_token, admin_token):
        """Recruiters should not be able to transition job status"""
        # Create job as admin
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        job_data = {
            "title": f"Recruiter Trans Test {uuid.uuid4().hex[:8]}",
            "description": "Testing recruiter permissions",
            "location": "Remote",
            "job_type": "full-time"
        }
        create_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=admin_headers)
        job_id = create_response.json()["id"]
        
        # Try to transition as recruiter
        rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
        response = httpx.post(
            f"{API_URL}/api/jobs/{job_id}/transition",
            json={"new_status": "on_hold"},
            headers=rec_headers
        )
        assert response.status_code == 403
    
    def test_recruiter_cannot_transition_referral(self, recruiter_token, admin_token):
        """Recruiters should not be able to transition referral status"""
        # Create job and referral
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        job_data = {
            "title": f"Ref Trans Test {uuid.uuid4().hex[:8]}",
            "description": "Testing recruiter referral permissions",
            "location": "Remote",
            "job_type": "full-time"
        }
        job_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=admin_headers)
        job_id = job_response.json()["id"]
        
        unique_id = uuid.uuid4().hex[:8]
        rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
        referral_data = {
            "job_id": job_id,
            "candidate_name": f"Perm Test {unique_id}",
            "candidate_email": f"perm.{unique_id}@example.com",
            "candidate_phone": "+91-9876543215"
        }
        ref_response = httpx.post(f"{API_URL}/api/referrals", json=referral_data, headers=rec_headers)
        referral_id = ref_response.json()["id"]
        
        # Try to transition as recruiter
        response = httpx.post(
            f"{API_URL}/api/referrals/{referral_id}/transition",
            json={"new_status": "validated"},
            headers=rec_headers
        )
        assert response.status_code == 403
    
    def test_employer_cannot_create_team(self, employer_token):
        """Employers should not be able to create teams"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        team_data = {
            "name": "Unauthorized Team",
            "employer_id": "some-id",
            "recruiter_ids": [],
            "company_ids": []
        }
        response = httpx.post(f"{API_URL}/api/teams", json=team_data, headers=headers)
        assert response.status_code == 403


# ============== COMPANY-EMPLOYER ASSIGNMENT TESTS ==============

class TestCompanyEmployerAssignment:
    """Test company-employer assignment functionality"""
    
    def test_admin_can_assign_employer_to_company(self, admin_token):
        """Admin can assign an employer to a company"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get an employer
        emp_response = httpx.get(f"{API_URL}/api/admin/employers", headers=headers)
        employers = emp_response.json()
        if not employers:
            pytest.skip("No employers available")
        employer_id = employers[0]["id"]
        
        # Get or create a company
        comp_response = httpx.get(f"{API_URL}/api/companies", headers=headers)
        companies = comp_response.json()
        
        if companies:
            company_id = companies[0]["id"]
        else:
            # Create a company
            company_data = {
                "name": f"Test Company {uuid.uuid4().hex[:8]}",
                "description": "For assignment testing",
                "industry": "Technology"
            }
            create_response = httpx.post(f"{API_URL}/api/companies", json=company_data, headers=headers)
            company_id = create_response.json()["id"]
        
        # Assign employer
        response = httpx.put(
            f"{API_URL}/api/companies/{company_id}/assign-employer?employer_id={employer_id}",
            headers=headers
        )
        assert response.status_code == 200
        assert response.json()["employer_id"] == employer_id
    
    def test_non_admin_cannot_assign_employer(self, employer_token, admin_token):
        """Non-admin users cannot assign employers to companies"""
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        emp_headers = {"Authorization": f"Bearer {employer_token}"}
        
        # Get a company
        comp_response = httpx.get(f"{API_URL}/api/companies", headers=admin_headers)
        companies = comp_response.json()
        if not companies:
            pytest.skip("No companies available")
        company_id = companies[0]["id"]
        
        # Try to assign as employer
        response = httpx.put(
            f"{API_URL}/api/companies/{company_id}/assign-employer?employer_id=some-id",
            headers=emp_headers
        )
        assert response.status_code == 403


# ============== TEAM CRUD TESTS ==============

class TestTeamCRUD:
    """Test team update and delete operations"""
    
    def test_admin_can_update_team(self, admin_token):
        """Admin can update team details"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get an employer
        emp_response = httpx.get(f"{API_URL}/api/admin/employers", headers=headers)
        employers = emp_response.json()
        if not employers:
            pytest.skip("No employers available")
        employer_id = employers[0]["id"]
        
        # Create a team
        team_data = {
            "name": f"Update Test Team {uuid.uuid4().hex[:8]}",
            "employer_id": employer_id,
            "recruiter_ids": [],
            "company_ids": []
        }
        create_response = httpx.post(f"{API_URL}/api/teams", json=team_data, headers=headers)
        team_id = create_response.json()["id"]
        
        # Update team
        update_data = {"name": f"Updated Team {uuid.uuid4().hex[:8]}"}
        response = httpx.put(f"{API_URL}/api/teams/{team_id}", json=update_data, headers=headers)
        assert response.status_code == 200
        assert "Updated Team" in response.json()["name"]
    
    def test_admin_can_delete_team(self, admin_token):
        """Admin can soft-delete (disable) a team"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get an employer
        emp_response = httpx.get(f"{API_URL}/api/admin/employers", headers=headers)
        employers = emp_response.json()
        if not employers:
            pytest.skip("No employers available")
        employer_id = employers[0]["id"]
        
        # Create a team
        team_data = {
            "name": f"Delete Test Team {uuid.uuid4().hex[:8]}",
            "employer_id": employer_id,
            "recruiter_ids": [],
            "company_ids": []
        }
        create_response = httpx.post(f"{API_URL}/api/teams", json=team_data, headers=headers)
        team_id = create_response.json()["id"]
        
        # Delete team
        response = httpx.delete(f"{API_URL}/api/teams/{team_id}", headers=headers)
        assert response.status_code == 200
        
        # Verify team is disabled
        get_response = httpx.get(f"{API_URL}/api/teams/{team_id}", headers=headers)
        assert get_response.json()["status"] == "disabled"


# ============== PUBLIC JOBS PRIVACY TESTS ==============

class TestPublicJobsPrivacy:
    """Test client privacy in public job listings"""
    
    def test_public_jobs_list_hides_company_id(self):
        """Public jobs list should not expose company_id"""
        response = httpx.get(f"{API_URL}/api/public/jobs")
        assert response.status_code == 200
        jobs = response.json()
        
        for job in jobs:
            assert "company_id" not in job, f"company_id exposed in public job: {job.get('id')}"
    
    def test_public_job_detail_hides_company_id(self, admin_token):
        """Public job detail should not expose company_id"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get an active job
        jobs_response = httpx.get(f"{API_URL}/api/jobs?status=active", headers=headers)
        jobs = jobs_response.json()
        if not jobs:
            pytest.skip("No active jobs available")
        
        job_id = jobs[0]["id"]
        
        # Get public detail
        response = httpx.get(f"{API_URL}/api/public/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        assert "company_id" not in job
    
    def test_public_jobs_show_alias_or_confidential(self):
        """Public jobs should show alias or 'Confidential Client'"""
        response = httpx.get(f"{API_URL}/api/public/jobs")
        assert response.status_code == 200
        jobs = response.json()
        
        for job in jobs:
            assert job.get("company_name") is not None
            # Should be either the alias or "Confidential Client"
            assert len(job["company_name"]) > 0


# ============== AUDIT TRAIL TESTS ==============

class TestAuditTrail:
    """Test audit logging functionality"""
    
    def test_job_transition_creates_audit_entry(self, admin_token):
        """Job state transitions should create audit entries"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create job
        job_data = {
            "title": f"Audit Test Job {uuid.uuid4().hex[:8]}",
            "description": "Testing audit trail",
            "location": "Remote",
            "job_type": "full-time"
        }
        create_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=headers)
        job_id = create_response.json()["id"]
        initial_history_len = len(create_response.json()["approval_history"])
        
        # Transition
        httpx.post(f"{API_URL}/api/jobs/{job_id}/transition", json={"new_status": "on_hold"}, headers=headers)
        
        # Get job and verify audit
        get_response = httpx.get(f"{API_URL}/api/jobs/{job_id}", headers=headers)
        job = get_response.json()
        
        assert len(job["approval_history"]) > initial_history_len
        latest_entry = job["approval_history"][-1]
        assert "changed_by" in latest_entry
        assert "timestamp" in latest_entry
    
    def test_referral_transition_creates_audit_entry(self, admin_token, recruiter_token):
        """Referral state transitions should create audit entries"""
        # Create job
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        job_data = {
            "title": f"Ref Audit Test {uuid.uuid4().hex[:8]}",
            "description": "Testing referral audit",
            "location": "Remote",
            "job_type": "full-time"
        }
        job_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=admin_headers)
        job_id = job_response.json()["id"]
        
        # Create referral
        unique_id = uuid.uuid4().hex[:8]
        rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
        referral_data = {
            "job_id": job_id,
            "candidate_name": f"Audit Test {unique_id}",
            "candidate_email": f"audit.{unique_id}@example.com",
            "candidate_phone": "+91-9876543216"
        }
        ref_response = httpx.post(f"{API_URL}/api/referrals", json=referral_data, headers=rec_headers)
        referral_id = ref_response.json()["id"]
        initial_history_len = len(ref_response.json()["status_history"])
        
        # Transition
        httpx.post(
            f"{API_URL}/api/referrals/{referral_id}/transition",
            json={"new_status": "validated"},
            headers=admin_headers
        )
        
        # Get referral and verify audit
        get_response = httpx.get(f"{API_URL}/api/referrals/{referral_id}", headers=admin_headers)
        referral = get_response.json()
        
        assert len(referral["status_history"]) > initial_history_len
        latest_entry = referral["status_history"][-1]
        assert "changed_by" in latest_entry
        assert "timestamp" in latest_entry


# ============== REFERRAL LINK TO CANDIDATE TESTS ==============

class TestReferralLinkCandidate:
    """Test referral to candidate linking functionality"""
    
    def test_link_referral_creates_candidate(self, admin_token, recruiter_token):
        """Linking a referral should create a candidate bank record"""
        # Create job
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        job_data = {
            "title": f"Link Candidate Test {uuid.uuid4().hex[:8]}",
            "description": "Testing candidate linking",
            "location": "Remote",
            "job_type": "full-time"
        }
        job_response = httpx.post(f"{API_URL}/api/jobs", json=job_data, headers=admin_headers)
        job_id = job_response.json()["id"]
        
        # Create referral
        unique_id = uuid.uuid4().hex[:8]
        rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
        referral_data = {
            "job_id": job_id,
            "candidate_name": f"Link Test {unique_id}",
            "candidate_email": f"linktest.{unique_id}@example.com",
            "candidate_phone": "+91-9876543217"
        }
        ref_response = httpx.post(f"{API_URL}/api/referrals", json=referral_data, headers=rec_headers)
        referral_id = ref_response.json()["id"]
        
        # Validate first
        httpx.post(
            f"{API_URL}/api/referrals/{referral_id}/transition",
            json={"new_status": "validated"},
            headers=admin_headers
        )
        
        # Link to candidate (creates new candidate)
        response = httpx.post(
            f"{API_URL}/api/referrals/{referral_id}/link-candidate",
            headers=admin_headers
        )
        assert response.status_code == 200
        assert "candidate_id" in response.json()
        
        # Verify referral is now linked
        ref_get = httpx.get(f"{API_URL}/api/referrals/{referral_id}", headers=admin_headers)
        assert ref_get.json()["status"] == "linked"
        assert ref_get.json()["linked_candidate_id"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
