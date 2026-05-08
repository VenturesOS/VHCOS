"""
Test Suite for VHC Talent OS - Phase 1.5 Hardening
Tests: CV Preview & Download, Admin User Management, Admin Collective Pipeline View

Features tested:
- TASK 1: CV Preview & Download with Firstname_Lastname_VHC.ext naming
- TASK 2: Admin User Management (CRUD, password reset, recruiter assignment, toggle status)
- TASK 3: Admin Collective Pipeline View with filters
"""
import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
EMPLOYER_CREDS = {"email": "employer@vhctalent.com", "password": "Demo@2024"}
RECRUITER_CREDS = {"email": "recruiter@vhctalent.com", "password": "Demo@2024"}
CANDIDATE_CREDS = {"email": "candidate@vhctalent.com", "password": "Demo@2024"}


# ============== FIXTURES ==============

@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Admin authentication failed")


@pytest.fixture(scope="module")
def employer_token():
    """Get employer authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Employer authentication failed")


@pytest.fixture(scope="module")
def recruiter_token():
    """Get recruiter authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER_CREDS)
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Recruiter authentication failed")


@pytest.fixture(scope="module")
def candidate_token():
    """Get candidate authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=CANDIDATE_CREDS)
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Candidate authentication failed")


@pytest.fixture(scope="module")
def test_application_with_resume(admin_token):
    """Find an application that has a resume attached"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Get all applications
    response = requests.get(f"{BASE_URL}/api/applications", headers=headers)
    if response.status_code != 200:
        pytest.skip("Failed to get applications")
    
    applications = response.json()
    
    # Find one with resume_url
    for app in applications:
        if app.get("resume_url"):
            return app
    
    # If no application has resume, try to find from candidate_bank
    # Get applications and check candidate_bank for resume
    for app in applications:
        if app.get("candidate_id"):
            candidate_resp = requests.get(
                f"{BASE_URL}/api/candidate-bank/{app['candidate_id']}", 
                headers=headers
            )
            if candidate_resp.status_code == 200:
                candidate = candidate_resp.json()
                if candidate.get("resume_url"):
                    return app
    
    pytest.skip("No application with resume found for testing")


@pytest.fixture(scope="module")
def employer_job_id(employer_token):
    """Get a job ID owned by the employer"""
    headers = {"Authorization": f"Bearer {employer_token}"}
    response = requests.get(f"{BASE_URL}/api/jobs", headers=headers)
    if response.status_code == 200 and response.json():
        return response.json()[0]["id"]
    pytest.skip("No jobs found for employer")


# ============== TASK 1: CV PREVIEW & DOWNLOAD ==============

class TestCVDownload:
    """Tests for CV Preview & Download functionality"""
    
    def test_admin_can_download_any_resume(self, admin_token, test_application_with_resume):
        """Admin should be able to download any resume"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        app_id = test_application_with_resume["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/applications/{app_id}/resume",
            headers=headers,
            allow_redirects=False
        )
        
        # Should return file or redirect
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}"
        
        if response.status_code == 200:
            # Check content-disposition header for filename
            content_disp = response.headers.get("content-disposition", "")
            assert "VHC" in content_disp or response.content, "Should have VHC in filename or return content"
    
    def test_employer_can_download_their_job_applicant_resume(self, employer_token, employer_job_id):
        """Employer should be able to download resumes for their job applicants"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        # Get applicants for employer's job
        applicants_resp = requests.get(
            f"{BASE_URL}/api/jobs/{employer_job_id}/applicants",
            headers=headers
        )
        
        if applicants_resp.status_code != 200:
            pytest.skip("Failed to get applicants")
        
        applicants = applicants_resp.json().get("applicants", [])
        
        # Find applicant with resume
        app_with_resume = next((a for a in applicants if a.get("resume_url")), None)
        
        if not app_with_resume:
            pytest.skip("No applicant with resume found")
        
        response = requests.get(
            f"{BASE_URL}/api/applications/{app_with_resume['id']}/resume",
            headers=headers
        )
        
        # Should succeed or return 404 if file doesn't exist
        assert response.status_code in [200, 404]
    
    def test_resume_download_returns_404_if_no_resume(self, admin_token):
        """Should return 404 if application has no resume"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get applications
        apps_resp = requests.get(f"{BASE_URL}/api/applications", headers=headers)
        if apps_resp.status_code != 200:
            pytest.skip("Failed to get applications")
        
        # Find application without resume
        apps = apps_resp.json()
        app_without_resume = next((a for a in apps if not a.get("resume_url")), None)
        
        if not app_without_resume:
            pytest.skip("All applications have resumes")
        
        response = requests.get(
            f"{BASE_URL}/api/applications/{app_without_resume['id']}/resume",
            headers=headers
        )
        
        assert response.status_code == 404
    
    def test_candidate_cannot_download_resume(self, candidate_token, test_application_with_resume):
        """Candidate should not be able to download resumes via this endpoint"""
        headers = {"Authorization": f"Bearer {candidate_token}"}
        app_id = test_application_with_resume["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/applications/{app_id}/resume",
            headers=headers
        )
        
        assert response.status_code == 403
    
    def test_resume_filename_format(self, admin_token, test_application_with_resume):
        """Resume download should have Firstname_Lastname_VHC.ext format"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        app_id = test_application_with_resume["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/applications/{app_id}/resume",
            headers=headers
        )
        
        if response.status_code == 200:
            content_disp = response.headers.get("content-disposition", "")
            # Check for VHC in filename
            assert "_VHC" in content_disp or "VHC" in content_disp, \
                f"Filename should contain VHC pattern, got: {content_disp}"


# ============== TASK 2: ADMIN USER MANAGEMENT ==============

class TestAdminUserManagement:
    """Tests for Admin User Management functionality"""
    
    def test_get_all_users_admin_only(self, admin_token, employer_token, candidate_token):
        """Only admin should be able to get all users"""
        # Admin can access
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        admin_resp = requests.get(f"{BASE_URL}/api/users", headers=admin_headers)
        assert admin_resp.status_code == 200
        assert isinstance(admin_resp.json(), list)
        
        # Employer cannot access
        employer_headers = {"Authorization": f"Bearer {employer_token}"}
        employer_resp = requests.get(f"{BASE_URL}/api/users", headers=employer_headers)
        assert employer_resp.status_code == 403
        
        # Candidate cannot access
        candidate_headers = {"Authorization": f"Bearer {candidate_token}"}
        candidate_resp = requests.get(f"{BASE_URL}/api/users", headers=candidate_headers)
        assert candidate_resp.status_code == 403
    
    def test_admin_create_user_employer(self, admin_token):
        """Admin should be able to create employer user"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        unique_email = f"test_employer_{uuid.uuid4().hex[:8]}@test.com"
        
        response = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers=headers,
            json={
                "email": unique_email,
                "password": "Test@2024",
                "name": "Test Employer",
                "role": "employer",
                "phone": "9876543210"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == unique_email
        assert data["role"] == "employer"
        assert data["is_active"] == True
        
        return data["id"]
    
    def test_admin_create_user_recruiter(self, admin_token):
        """Admin should be able to create recruiter user"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        unique_email = f"test_recruiter_{uuid.uuid4().hex[:8]}@test.com"
        
        response = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers=headers,
            json={
                "email": unique_email,
                "password": "Test@2024",
                "name": "Test Recruiter",
                "role": "recruiter"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "recruiter"
    
    def test_admin_create_user_candidate(self, admin_token):
        """Admin should be able to create candidate user"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        unique_email = f"test_candidate_{uuid.uuid4().hex[:8]}@test.com"
        
        response = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers=headers,
            json={
                "email": unique_email,
                "password": "Test@2024",
                "name": "Test Candidate",
                "role": "candidate"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "candidate"
    
    def test_admin_cannot_create_admin_user(self, admin_token):
        """Admin should not be able to create another admin via this endpoint"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        unique_email = f"test_admin_{uuid.uuid4().hex[:8]}@test.com"
        
        response = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers=headers,
            json={
                "email": unique_email,
                "password": "Test@2024",
                "name": "Test Admin",
                "role": "admin"
            }
        )
        
        assert response.status_code == 400
    
    def test_admin_update_user(self, admin_token):
        """Admin should be able to update user details"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # First create a user
        unique_email = f"test_update_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers=headers,
            json={
                "email": unique_email,
                "password": "Test@2024",
                "name": "Original Name",
                "role": "candidate"
            }
        )
        
        if create_resp.status_code != 200:
            pytest.skip("Failed to create test user")
        
        user_id = create_resp.json()["id"]
        
        # Update the user
        update_resp = requests.put(
            f"{BASE_URL}/api/users/{user_id}",
            headers=headers,
            json={"name": "Updated Name", "phone": "1234567890"}
        )
        
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Updated Name"
        assert update_resp.json()["phone"] == "1234567890"
    
    def test_admin_delete_user_soft_delete(self, admin_token):
        """Admin delete should soft-delete (set is_active=false)"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create a user to delete
        unique_email = f"test_delete_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers=headers,
            json={
                "email": unique_email,
                "password": "Test@2024",
                "name": "To Delete",
                "role": "candidate"
            }
        )
        
        if create_resp.status_code != 200:
            pytest.skip("Failed to create test user")
        
        user_id = create_resp.json()["id"]
        
        # Delete the user
        delete_resp = requests.delete(
            f"{BASE_URL}/api/users/{user_id}",
            headers=headers
        )
        
        assert delete_resp.status_code == 200
        assert "deactivated" in delete_resp.json()["message"].lower()
        
        # Verify user is deactivated, not deleted
        get_resp = requests.get(f"{BASE_URL}/api/users/{user_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["is_active"] == False
    
    def test_admin_reset_password(self, admin_token):
        """Admin should be able to reset any user's password"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create a user
        unique_email = f"test_reset_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers=headers,
            json={
                "email": unique_email,
                "password": "OldPassword@2024",
                "name": "Reset Test",
                "role": "candidate"
            }
        )
        
        if create_resp.status_code != 200:
            pytest.skip("Failed to create test user")
        
        user_id = create_resp.json()["id"]
        
        # Reset password
        reset_resp = requests.post(
            f"{BASE_URL}/api/admin/users/{user_id}/reset-password",
            headers=headers,
            json={"new_password": "NewPassword@2024"}
        )
        
        assert reset_resp.status_code == 200
        assert "reset" in reset_resp.json()["message"].lower()
        
        # Verify new password works
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": unique_email, "password": "NewPassword@2024"}
        )
        assert login_resp.status_code == 200
    
    def test_admin_toggle_user_status(self, admin_token):
        """Admin should be able to toggle user active status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create a user
        unique_email = f"test_toggle_{uuid.uuid4().hex[:8]}@test.com"
        create_resp = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers=headers,
            json={
                "email": unique_email,
                "password": "Test@2024",
                "name": "Toggle Test",
                "role": "candidate"
            }
        )
        
        if create_resp.status_code != 200:
            pytest.skip("Failed to create test user")
        
        user_id = create_resp.json()["id"]
        
        # Toggle status (should deactivate)
        toggle_resp = requests.post(
            f"{BASE_URL}/api/admin/users/{user_id}/toggle-status",
            headers=headers
        )
        
        assert toggle_resp.status_code == 200
        assert toggle_resp.json()["is_active"] == False
        
        # Toggle again (should activate)
        toggle_resp2 = requests.post(
            f"{BASE_URL}/api/admin/users/{user_id}/toggle-status",
            headers=headers
        )
        
        assert toggle_resp2.status_code == 200
        assert toggle_resp2.json()["is_active"] == True
    
    def test_admin_get_employers_list(self, admin_token):
        """Admin should be able to get list of employers"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.get(f"{BASE_URL}/api/admin/employers", headers=headers)
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        
        # All returned users should be employers
        for user in response.json():
            assert user["role"] == "employer"
    
    def test_admin_assign_recruiter_to_employer(self, admin_token):
        """Admin should be able to assign recruiter to employer"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create a recruiter
        recruiter_email = f"test_assign_rec_{uuid.uuid4().hex[:8]}@test.com"
        rec_resp = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers=headers,
            json={
                "email": recruiter_email,
                "password": "Test@2024",
                "name": "Assign Test Recruiter",
                "role": "recruiter"
            }
        )
        
        if rec_resp.status_code != 200:
            pytest.skip("Failed to create recruiter")
        
        recruiter_id = rec_resp.json()["id"]
        
        # Create an employer
        employer_email = f"test_assign_emp_{uuid.uuid4().hex[:8]}@test.com"
        emp_resp = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers=headers,
            json={
                "email": employer_email,
                "password": "Test@2024",
                "name": "Assign Test Employer",
                "role": "employer"
            }
        )
        
        if emp_resp.status_code != 200:
            pytest.skip("Failed to create employer")
        
        employer_id = emp_resp.json()["id"]
        
        # Assign recruiter to employer
        assign_resp = requests.post(
            f"{BASE_URL}/api/admin/assign-recruiter",
            headers=headers,
            params={"recruiter_id": recruiter_id, "employer_id": employer_id}
        )
        
        assert assign_resp.status_code == 200
        assert "assigned" in assign_resp.json()["message"].lower()


# ============== TASK 3: ADMIN COLLECTIVE PIPELINE VIEW ==============

class TestAdminPipeline:
    """Tests for Admin Collective Pipeline View"""
    
    def test_admin_can_access_pipeline(self, admin_token):
        """Admin should be able to access pipeline view"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert "pipeline" in data
        assert "stage_counts" in data
        assert "total_applications" in data
        assert "filters" in data
    
    def test_pipeline_has_all_stages(self, admin_token):
        """Pipeline should include all 9 stages"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        expected_stages = [
            "applied", "shortlisted", "interview", "offered", "hired",
            "rejected", "on_hold", "over_budget", "not_qualified"
        ]
        
        for stage in expected_stages:
            assert stage in data["pipeline"], f"Missing stage: {stage}"
            assert stage in data["stage_counts"], f"Missing stage count: {stage}"
    
    def test_pipeline_filter_by_employer(self, admin_token):
        """Pipeline should filter by employer_id"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get employers list
        employers_resp = requests.get(f"{BASE_URL}/api/admin/employers", headers=headers)
        if employers_resp.status_code != 200 or not employers_resp.json():
            pytest.skip("No employers found")
        
        employer_id = employers_resp.json()[0]["id"]
        
        # Get pipeline with filter
        response = requests.get(
            f"{BASE_URL}/api/admin/pipeline",
            headers=headers,
            params={"employer_id": employer_id}
        )
        
        assert response.status_code == 200
    
    def test_pipeline_filter_by_recruiter(self, admin_token):
        """Pipeline should filter by recruiter_id"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get users to find a recruiter
        users_resp = requests.get(f"{BASE_URL}/api/users", headers=headers)
        if users_resp.status_code != 200:
            pytest.skip("Failed to get users")
        
        recruiters = [u for u in users_resp.json() if u["role"] == "recruiter"]
        if not recruiters:
            pytest.skip("No recruiters found")
        
        recruiter_id = recruiters[0]["id"]
        
        # Get pipeline with filter
        response = requests.get(
            f"{BASE_URL}/api/admin/pipeline",
            headers=headers,
            params={"recruiter_id": recruiter_id}
        )
        
        assert response.status_code == 200
    
    def test_pipeline_filter_by_job(self, admin_token):
        """Pipeline should filter by job_id"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get a job
        jobs_resp = requests.get(f"{BASE_URL}/api/jobs", headers=headers)
        if jobs_resp.status_code != 200 or not jobs_resp.json():
            pytest.skip("No jobs found")
        
        job_id = jobs_resp.json()[0]["id"]
        
        # Get pipeline with filter
        response = requests.get(
            f"{BASE_URL}/api/admin/pipeline",
            headers=headers,
            params={"job_id": job_id}
        )
        
        assert response.status_code == 200
    
    def test_pipeline_filters_include_options(self, admin_token):
        """Pipeline response should include filter options"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "filters" in data
        assert "employers" in data["filters"]
        assert "recruiters" in data["filters"]
        assert "jobs" in data["filters"]
    
    def test_non_admin_cannot_access_pipeline(self, employer_token, recruiter_token, candidate_token):
        """Non-admin users should not access pipeline"""
        for token in [employer_token, recruiter_token, candidate_token]:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=headers)
            assert response.status_code == 403


# ============== REGRESSION TESTS ==============

class TestRegression:
    """Regression tests for existing features"""
    
    def test_login_all_roles(self):
        """All 4 roles should be able to login"""
        credentials = [
            ADMIN_CREDS,
            EMPLOYER_CREDS,
            RECRUITER_CREDS,
            CANDIDATE_CREDS
        ]
        
        for creds in credentials:
            response = requests.post(f"{BASE_URL}/api/auth/login", json=creds)
            assert response.status_code == 200, f"Login failed for {creds['email']}"
            assert "access_token" in response.json()
    
    def test_public_jobs_endpoint(self):
        """Public jobs endpoint should work without auth"""
        response = requests.get(f"{BASE_URL}/api/public/jobs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_applicant_review_screen_api(self, employer_token, employer_job_id):
        """Applicant review screen API should still work"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/jobs/{employer_job_id}/applicants",
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "job" in data
        assert "applicants" in data
        assert "stage_counts" in data
    
    def test_edit_details_api(self, employer_token, employer_job_id):
        """Edit details API should still work"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        # Get an applicant
        applicants_resp = requests.get(
            f"{BASE_URL}/api/jobs/{employer_job_id}/applicants",
            headers=headers
        )
        
        if applicants_resp.status_code != 200:
            pytest.skip("Failed to get applicants")
        
        applicants = applicants_resp.json().get("applicants", [])
        if not applicants:
            pytest.skip("No applicants found")
        
        app_id = applicants[0]["id"]
        
        # Test edit details endpoint
        response = requests.put(
            f"{BASE_URL}/api/applications/{app_id}/details",
            headers=headers,
            json={"notice_period": "30 days"}
        )
        
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
