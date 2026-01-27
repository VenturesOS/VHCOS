"""
Test Suite: Employer-led Mandate Allocation to Recruiters
Tests the feature allowing Employers to assign job mandates to specific Recruiters.

Key Business Rules:
- Only Employers can assign recruiters to mandates
- Recruiters cannot self-assign
- Recruiters can ONLY see mandates explicitly assigned to them
- Assignment history is tracked for audit
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
EMPLOYER_CREDS = {"email": "employer@vhctalent.com", "password": "VhcTalent@2024"}
RECRUITER1_CREDS = {"email": "recruiter@vhctalent.com", "password": "VhcTalent@2024"}
RECRUITER2_CREDS = {"email": "recruiter2@vhctalent.com", "password": "VhcTalent@2024"}


class TestMandateAssignmentSetup:
    """Setup and authentication tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def employer_token(self):
        """Get employer auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
        assert response.status_code == 200, f"Employer login failed: {response.text}"
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter1_token(self):
        """Get recruiter1 auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER1_CREDS)
        assert response.status_code == 200, f"Recruiter1 login failed: {response.text}"
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter2_token(self):
        """Get recruiter2 auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER2_CREDS)
        assert response.status_code == 200, f"Recruiter2 login failed: {response.text}"
        return response.json()["access_token"]
    
    def test_all_users_can_login(self, admin_token, employer_token, recruiter1_token, recruiter2_token):
        """Verify all test users can authenticate"""
        assert admin_token is not None
        assert employer_token is not None
        assert recruiter1_token is not None
        assert recruiter2_token is not None
        print("✅ All test users authenticated successfully")


class TestTeamRecruitersEndpoint:
    """Tests for GET /api/employer/team-recruiters endpoint"""
    
    @pytest.fixture(scope="class")
    def employer_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter1_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER1_CREDS)
        return response.json()["access_token"]
    
    def test_employer_can_get_team_recruiters(self, employer_token):
        """Employer should see recruiters in their team"""
        response = requests.get(
            f"{BASE_URL}/api/employer/team-recruiters",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "recruiters" in data
        assert isinstance(data["recruiters"], list)
        
        # Verify recruiter structure
        if len(data["recruiters"]) > 0:
            recruiter = data["recruiters"][0]
            assert "id" in recruiter
            assert "name" in recruiter
            assert "email" in recruiter
            assert "active_mandates_count" in recruiter
        
        print(f"✅ Employer sees {len(data['recruiters'])} recruiters in team")
    
    def test_admin_can_get_all_recruiters(self, admin_token):
        """Admin should see all recruiters"""
        response = requests.get(
            f"{BASE_URL}/api/employer/team-recruiters",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "recruiters" in data
        print(f"✅ Admin sees {len(data['recruiters'])} recruiters")
    
    def test_recruiter_cannot_access_team_recruiters(self, recruiter1_token):
        """Recruiters should NOT be able to access team-recruiters endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/employer/team-recruiters",
            headers={"Authorization": f"Bearer {recruiter1_token}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✅ Recruiter correctly denied access to team-recruiters endpoint")


class TestAssignRecruitersEndpoint:
    """Tests for POST /api/jobs/{job_id}/assign-recruiters endpoint"""
    
    @pytest.fixture(scope="class")
    def employer_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter1_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER1_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter1_id(self, employer_token):
        """Get recruiter1's user ID"""
        response = requests.get(
            f"{BASE_URL}/api/employer/team-recruiters",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        data = response.json()
        for rec in data.get("recruiters", []):
            if rec.get("email") == RECRUITER1_CREDS["email"]:
                return rec["id"]
        pytest.skip("Recruiter1 not found in team")
    
    @pytest.fixture(scope="class")
    def active_job_id(self, employer_token):
        """Get an active job ID for testing"""
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        jobs = response.json()
        for job in jobs:
            if job.get("status") in ["active", "pending_approval"]:
                return job["id"]
        pytest.skip("No active jobs found for testing")
    
    def test_employer_can_assign_recruiters(self, employer_token, active_job_id, recruiter1_id):
        """Employer should be able to assign recruiters to a mandate"""
        response = requests.post(
            f"{BASE_URL}/api/jobs/{active_job_id}/assign-recruiters",
            headers={"Authorization": f"Bearer {employer_token}"},
            json=[recruiter1_id]
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert data.get("success") == True
        assert "assigned_recruiters" in data
        assert len(data["assigned_recruiters"]) > 0
        print(f"✅ Employer assigned recruiter to job {active_job_id}")
    
    def test_recruiter_cannot_self_assign(self, recruiter1_token, active_job_id, recruiter1_id):
        """Recruiters should NOT be able to assign themselves"""
        response = requests.post(
            f"{BASE_URL}/api/jobs/{active_job_id}/assign-recruiters",
            headers={"Authorization": f"Bearer {recruiter1_token}"},
            json=[recruiter1_id]
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✅ Recruiter correctly denied self-assignment")
    
    def test_cannot_assign_to_closed_job(self, employer_token, recruiter1_id):
        """Cannot assign recruiters to closed jobs"""
        # First get a closed job if exists
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        jobs = response.json()
        closed_job = None
        for job in jobs:
            if job.get("status") == "closed":
                closed_job = job
                break
        
        if not closed_job:
            pytest.skip("No closed jobs to test")
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/{closed_job['id']}/assign-recruiters",
            headers={"Authorization": f"Bearer {employer_token}"},
            json=[recruiter1_id]
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✅ Cannot assign recruiters to closed jobs")


class TestRemoveRecruiterEndpoint:
    """Tests for DELETE /api/jobs/{job_id}/assign-recruiters/{recruiter_id}"""
    
    @pytest.fixture(scope="class")
    def employer_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter1_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER1_CREDS)
        return response.json()["access_token"]
    
    def test_employer_can_remove_recruiter(self, employer_token):
        """Employer should be able to remove a recruiter from mandate"""
        # First get a job with assigned recruiters
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        jobs = response.json()
        
        job_with_recruiters = None
        for job in jobs:
            if job.get("assigned_recruiters") and len(job["assigned_recruiters"]) > 0:
                job_with_recruiters = job
                break
        
        if not job_with_recruiters:
            pytest.skip("No jobs with assigned recruiters found")
        
        recruiter_to_remove = job_with_recruiters["assigned_recruiters"][0]
        
        response = requests.delete(
            f"{BASE_URL}/api/jobs/{job_with_recruiters['id']}/assign-recruiters/{recruiter_to_remove}",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        print(f"✅ Employer removed recruiter from mandate")
    
    def test_recruiter_cannot_remove_self(self, recruiter1_token, employer_token):
        """Recruiter should NOT be able to remove themselves"""
        # Get recruiter1's ID
        response = requests.get(
            f"{BASE_URL}/api/employer/team-recruiters",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        data = response.json()
        recruiter1_id = None
        for rec in data.get("recruiters", []):
            if rec.get("email") == RECRUITER1_CREDS["email"]:
                recruiter1_id = rec["id"]
                break
        
        if not recruiter1_id:
            pytest.skip("Recruiter1 not found")
        
        # Get a job
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        jobs = response.json()
        if not jobs:
            pytest.skip("No jobs found")
        
        response = requests.delete(
            f"{BASE_URL}/api/jobs/{jobs[0]['id']}/assign-recruiters/{recruiter1_id}",
            headers={"Authorization": f"Bearer {recruiter1_token}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✅ Recruiter correctly denied removing themselves")


class TestAssignmentsEndpoint:
    """Tests for GET /api/jobs/{job_id}/assignments endpoint"""
    
    @pytest.fixture(scope="class")
    def employer_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter1_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER1_CREDS)
        return response.json()["access_token"]
    
    def test_employer_can_get_assignments(self, employer_token):
        """Employer should see assignment details"""
        # Get a job
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        jobs = response.json()
        if not jobs:
            pytest.skip("No jobs found")
        
        job_id = jobs[0]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/jobs/{job_id}/assignments",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "job_id" in data
        assert "assigned_recruiters" in data
        assert "assignment_history" in data
        print(f"✅ Employer can view assignment details")
    
    def test_assignment_history_tracked(self, employer_token):
        """Assignment history should be tracked"""
        # Get a job with assignment history
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        jobs = response.json()
        
        for job in jobs:
            if job.get("assignment_history") and len(job["assignment_history"]) > 0:
                response = requests.get(
                    f"{BASE_URL}/api/jobs/{job['id']}/assignments",
                    headers={"Authorization": f"Bearer {employer_token}"}
                )
                data = response.json()
                
                history = data.get("assignment_history", [])
                if history:
                    entry = history[0]
                    assert "action" in entry
                    assert "timestamp" in entry
                    print(f"✅ Assignment history tracked with {len(history)} entries")
                    return
        
        print("⚠️ No assignment history found (may need to assign first)")


class TestRecruiterVisibility:
    """Tests for recruiter job visibility - CRITICAL BUSINESS RULE"""
    
    @pytest.fixture(scope="class")
    def employer_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter1_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER1_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter2_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER2_CREDS)
        return response.json()["access_token"]
    
    def test_recruiter1_sees_assigned_jobs(self, recruiter1_token, employer_token):
        """Recruiter1 should see jobs assigned to them"""
        # First ensure recruiter1 is assigned to at least one job
        # Get recruiter1's ID
        response = requests.get(
            f"{BASE_URL}/api/employer/team-recruiters",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        data = response.json()
        recruiter1_id = None
        for rec in data.get("recruiters", []):
            if rec.get("email") == RECRUITER1_CREDS["email"]:
                recruiter1_id = rec["id"]
                break
        
        # Get jobs as employer
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        employer_jobs = response.json()
        
        # Assign recruiter1 to first active job if not already assigned
        for job in employer_jobs:
            if job.get("status") in ["active", "pending_approval"]:
                if recruiter1_id not in job.get("assigned_recruiters", []):
                    requests.post(
                        f"{BASE_URL}/api/jobs/{job['id']}/assign-recruiters",
                        headers={"Authorization": f"Bearer {employer_token}"},
                        json=[recruiter1_id]
                    )
                break
        
        # Now check recruiter1's view
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers={"Authorization": f"Bearer {recruiter1_token}"}
        )
        assert response.status_code == 200
        recruiter1_jobs = response.json()
        
        print(f"✅ Recruiter1 sees {len(recruiter1_jobs)} jobs")
        
        # Verify recruiter1 only sees jobs they're assigned to or posted
        for job in recruiter1_jobs:
            is_assigned = recruiter1_id in job.get("assigned_recruiters", [])
            is_poster = job.get("posted_by") == recruiter1_id
            assert is_assigned or is_poster, f"Recruiter1 sees job {job['id']} but is not assigned or poster"
    
    def test_recruiter2_sees_no_jobs_if_unassigned(self, recruiter2_token, employer_token):
        """Recruiter2 (unassigned) should see 0 jobs"""
        # Get recruiter2's ID
        response = requests.get(
            f"{BASE_URL}/api/employer/team-recruiters",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        data = response.json()
        recruiter2_id = None
        for rec in data.get("recruiters", []):
            if rec.get("email") == RECRUITER2_CREDS["email"]:
                recruiter2_id = rec["id"]
                break
        
        # Get jobs as recruiter2
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers={"Authorization": f"Bearer {recruiter2_token}"}
        )
        assert response.status_code == 200
        recruiter2_jobs = response.json()
        
        # Recruiter2 should only see jobs they posted or are assigned to
        for job in recruiter2_jobs:
            is_assigned = recruiter2_id in job.get("assigned_recruiters", [])
            is_poster = job.get("posted_by") == recruiter2_id
            assert is_assigned or is_poster, f"Recruiter2 sees job {job['id']} but is not assigned or poster"
        
        print(f"✅ Recruiter2 sees {len(recruiter2_jobs)} jobs (should be 0 if not assigned to any)")
    
    def test_employer_sees_all_team_jobs(self, employer_token):
        """Employer should see all jobs in their team"""
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 200
        jobs = response.json()
        print(f"✅ Employer sees {len(jobs)} jobs in their team")


class TestEndToEndAssignmentFlow:
    """End-to-end test of the complete assignment workflow"""
    
    @pytest.fixture(scope="class")
    def employer_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter1_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER1_CREDS)
        return response.json()["access_token"]
    
    def test_full_assignment_workflow(self, employer_token, recruiter1_token):
        """Test complete workflow: get recruiters -> assign -> verify visibility -> check history"""
        
        # Step 1: Get team recruiters
        response = requests.get(
            f"{BASE_URL}/api/employer/team-recruiters",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 200
        recruiters = response.json().get("recruiters", [])
        print(f"Step 1: Found {len(recruiters)} recruiters in team")
        
        if not recruiters:
            pytest.skip("No recruiters in team")
        
        recruiter1_id = None
        for rec in recruiters:
            if rec.get("email") == RECRUITER1_CREDS["email"]:
                recruiter1_id = rec["id"]
                break
        
        if not recruiter1_id:
            pytest.skip("Recruiter1 not found in team")
        
        # Step 2: Get an active job
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        jobs = response.json()
        active_job = None
        for job in jobs:
            if job.get("status") in ["active", "pending_approval"]:
                active_job = job
                break
        
        if not active_job:
            pytest.skip("No active jobs found")
        
        print(f"Step 2: Found active job: {active_job.get('title')} ({active_job.get('job_public_id')})")
        
        # Step 3: Assign recruiter
        response = requests.post(
            f"{BASE_URL}/api/jobs/{active_job['id']}/assign-recruiters",
            headers={"Authorization": f"Bearer {employer_token}"},
            json=[recruiter1_id]
        )
        assert response.status_code == 200
        print(f"Step 3: Assigned recruiter to job")
        
        # Step 4: Verify recruiter can see the job
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers={"Authorization": f"Bearer {recruiter1_token}"}
        )
        recruiter_jobs = response.json()
        job_ids = [j["id"] for j in recruiter_jobs]
        assert active_job["id"] in job_ids, "Recruiter should see assigned job"
        print(f"Step 4: Recruiter can see the assigned job")
        
        # Step 5: Check assignment history
        response = requests.get(
            f"{BASE_URL}/api/jobs/{active_job['id']}/assignments",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 200
        assignments = response.json()
        assert len(assignments.get("assignment_history", [])) > 0
        print(f"Step 5: Assignment history has {len(assignments['assignment_history'])} entries")
        
        print("✅ Full assignment workflow completed successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
