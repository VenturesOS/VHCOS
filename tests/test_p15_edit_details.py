"""
Test Suite for Phase 1.5: Controlled Candidate Detail Preview & Edit
Tests the PUT /api/applications/{app_id}/details and GET /api/applications/{app_id}/edit-history endpoints
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
EMPLOYER_CREDS = {"email": "employer@vhctalent.com", "password": "Demo@2024"}


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
def candidate_token():
    """Get candidate authentication token (for unauthorized access tests)"""
    # Register a new candidate
    unique_email = f"test_candidate_{uuid.uuid4().hex[:8]}@example.com"
    response = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": unique_email,
        "password": "Test@2024",
        "name": "Test Candidate",
        "role": "candidate"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Candidate registration failed")


@pytest.fixture(scope="module")
def test_application_id(employer_token):
    """Get a test application ID from employer's jobs"""
    headers = {"Authorization": f"Bearer {employer_token}"}
    
    # Get employer's jobs
    jobs_response = requests.get(f"{BASE_URL}/api/jobs", headers=headers)
    if jobs_response.status_code != 200 or not jobs_response.json():
        pytest.skip("No jobs found for employer")
    
    job_id = jobs_response.json()[0]["id"]
    
    # Get applicants for the job
    applicants_response = requests.get(f"{BASE_URL}/api/jobs/{job_id}/applicants", headers=headers)
    if applicants_response.status_code != 200:
        pytest.skip("Failed to get applicants")
    
    applicants = applicants_response.json().get("applicants", [])
    if not applicants:
        pytest.skip("No applicants found for testing")
    
    return applicants[0]["id"]


class TestUpdateApplicationDetails:
    """Tests for PUT /api/applications/{app_id}/details endpoint"""
    
    def test_update_current_salary(self, employer_token, test_application_id):
        """Test updating current salary field"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        # Get current salary first
        app_response = requests.get(f"{BASE_URL}/api/applications/{test_application_id}", headers=headers)
        current_salary = app_response.json().get("current_salary", 0) or 0
        new_salary = current_salary + 100000
        
        response = requests.put(
            f"{BASE_URL}/api/applications/{test_application_id}/details",
            headers=headers,
            json={"current_salary": new_salary}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Application details updated successfully"
        assert data["application_id"] == test_application_id
        
        # Verify change was recorded
        changes = data.get("changes", [])
        salary_change = next((c for c in changes if c["field"] == "current_salary"), None)
        assert salary_change is not None
        assert salary_change["new_value"] == new_salary
        
        # Verify application was updated
        assert data["application"]["current_salary"] == new_salary
        assert data["application"]["manually_edited"] == True
    
    def test_update_notice_period(self, employer_token, test_application_id):
        """Test updating notice period field"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        response = requests.put(
            f"{BASE_URL}/api/applications/{test_application_id}/details",
            headers=headers,
            json={"notice_period": "60 days"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify change was recorded
        changes = data.get("changes", [])
        notice_change = next((c for c in changes if c["field"] == "notice_period"), None)
        assert notice_change is not None
        assert notice_change["new_value"] == "60 days"
        
        # Verify application was updated
        assert data["application"]["notice_period"] == "60 days"
    
    def test_update_skills(self, employer_token, test_application_id):
        """Test updating skills array"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        new_skills = ["Python", "JavaScript", "React", "FastAPI"]
        
        response = requests.put(
            f"{BASE_URL}/api/applications/{test_application_id}/details",
            headers=headers,
            json={"skills": new_skills}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify change was recorded
        changes = data.get("changes", [])
        skills_change = next((c for c in changes if c["field"] == "skills"), None)
        assert skills_change is not None
        assert skills_change["new_value"] == new_skills
        
        # Verify application was updated
        assert data["application"]["skills"] == new_skills
    
    def test_update_experience_summary(self, employer_token, test_application_id):
        """Test updating experience summary field"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        new_summary = "Experienced software engineer with 8+ years in full-stack development."
        
        response = requests.put(
            f"{BASE_URL}/api/applications/{test_application_id}/details",
            headers=headers,
            json={"experience_summary": new_summary}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify change was recorded
        changes = data.get("changes", [])
        summary_change = next((c for c in changes if c["field"] == "experience_summary"), None)
        assert summary_change is not None
        assert summary_change["new_value"] == new_summary
        
        # Verify application was updated
        assert data["application"]["experience_summary"] == new_summary
    
    def test_update_multiple_fields(self, employer_token, test_application_id):
        """Test updating multiple fields at once"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        response = requests.put(
            f"{BASE_URL}/api/applications/{test_application_id}/details",
            headers=headers,
            json={
                "current_salary": 2000000,
                "notice_period": "90 days",
                "skills": ["Leadership", "Management", "Strategy"],
                "experience_summary": "Senior leader with 15+ years experience."
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify all changes were recorded
        changes = data.get("changes", [])
        assert len(changes) >= 1  # At least one field should have changed
        
        # Verify updated_by info
        assert data["updated_by"]["role"] == "employer"
    
    def test_no_changes_detected(self, employer_token, test_application_id):
        """Test when no actual changes are made"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        # Get current values
        app_response = requests.get(f"{BASE_URL}/api/applications/{test_application_id}", headers=headers)
        current_salary = app_response.json().get("current_salary")
        
        # Send same value
        response = requests.put(
            f"{BASE_URL}/api/applications/{test_application_id}/details",
            headers=headers,
            json={"current_salary": current_salary}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "No changes detected"
    
    def test_admin_can_update_details(self, admin_token, test_application_id):
        """Test that admin role can update application details"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.put(
            f"{BASE_URL}/api/applications/{test_application_id}/details",
            headers=headers,
            json={"current_salary": 2500000}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["updated_by"]["role"] == "admin"
    
    def test_candidate_cannot_update_details(self, candidate_token, test_application_id):
        """Test that candidate role cannot update application details"""
        headers = {"Authorization": f"Bearer {candidate_token}"}
        
        response = requests.put(
            f"{BASE_URL}/api/applications/{test_application_id}/details",
            headers=headers,
            json={"current_salary": 3000000}
        )
        
        assert response.status_code == 403
        assert response.json()["detail"] == "Insufficient permissions"
    
    def test_update_nonexistent_application(self, employer_token):
        """Test updating a non-existent application"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        fake_id = str(uuid.uuid4())
        response = requests.put(
            f"{BASE_URL}/api/applications/{fake_id}/details",
            headers=headers,
            json={"current_salary": 1000000}
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestAuditTrail:
    """Tests for audit trail functionality"""
    
    def test_audit_entry_created(self, employer_token, test_application_id):
        """Test that audit entries are created for changes"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        # Make a change
        unique_salary = 1234567
        response = requests.put(
            f"{BASE_URL}/api/applications/{test_application_id}/details",
            headers=headers,
            json={"current_salary": unique_salary}
        )
        
        assert response.status_code == 200
        
        # Check edit history
        history_response = requests.get(
            f"{BASE_URL}/api/applications/{test_application_id}/edit-history",
            headers=headers
        )
        
        assert history_response.status_code == 200
        data = history_response.json()
        
        # Find our change in history
        edit_history = data.get("edit_history", [])
        our_change = next(
            (e for e in edit_history if e.get("new_value") == unique_salary),
            None
        )
        
        assert our_change is not None
        assert our_change["field"] == "current_salary"
        assert our_change["updated_by_role"] == "employer"
        assert "timestamp" in our_change
    
    def test_last_edited_by_updated(self, employer_token, test_application_id):
        """Test that last_edited_by is updated after changes"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        # Make a change
        response = requests.put(
            f"{BASE_URL}/api/applications/{test_application_id}/details",
            headers=headers,
            json={"notice_period": "Immediate"}
        )
        
        assert response.status_code == 200
        
        # Check last_edited_by
        app = response.json()["application"]
        assert app["last_edited_by"] is not None
        assert app["last_edited_by"]["role"] == "employer"
        assert "timestamp" in app["last_edited_by"]
        assert "name" in app["last_edited_by"]
    
    def test_manually_edited_flag_set(self, employer_token, test_application_id):
        """Test that manually_edited flag is set after editing"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        response = requests.put(
            f"{BASE_URL}/api/applications/{test_application_id}/details",
            headers=headers,
            json={"skills": ["Test Skill"]}
        )
        
        assert response.status_code == 200
        assert response.json()["application"]["manually_edited"] == True


class TestGetEditHistory:
    """Tests for GET /api/applications/{app_id}/edit-history endpoint"""
    
    def test_get_edit_history(self, employer_token, test_application_id):
        """Test getting edit history for an application"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/applications/{test_application_id}/edit-history",
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "application_id" in data
        assert "edit_history" in data
        assert "last_edited_by" in data
        assert isinstance(data["edit_history"], list)
    
    def test_edit_history_contains_required_fields(self, employer_token, test_application_id):
        """Test that edit history entries contain all required fields"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/applications/{test_application_id}/edit-history",
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        if data["edit_history"]:
            entry = data["edit_history"][0]
            assert "field" in entry
            assert "old_value" in entry
            assert "new_value" in entry
            assert "updated_by_id" in entry
            assert "updated_by_name" in entry
            assert "updated_by_role" in entry
            assert "timestamp" in entry
    
    def test_admin_can_get_edit_history(self, admin_token, test_application_id):
        """Test that admin can get edit history"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/applications/{test_application_id}/edit-history",
            headers=headers
        )
        
        assert response.status_code == 200
    
    def test_candidate_cannot_get_edit_history(self, candidate_token, test_application_id):
        """Test that candidate cannot get edit history"""
        headers = {"Authorization": f"Bearer {candidate_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/applications/{test_application_id}/edit-history",
            headers=headers
        )
        
        assert response.status_code == 403
    
    def test_get_history_nonexistent_application(self, employer_token):
        """Test getting history for non-existent application"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        fake_id = str(uuid.uuid4())
        response = requests.get(
            f"{BASE_URL}/api/applications/{fake_id}/edit-history",
            headers=headers
        )
        
        assert response.status_code == 404


class TestDataPersistence:
    """Tests for data persistence after updates"""
    
    def test_changes_persist_after_update(self, employer_token, test_application_id):
        """Test that changes persist after update"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        # Make a unique change
        unique_salary = 9876543
        
        # Update
        update_response = requests.put(
            f"{BASE_URL}/api/applications/{test_application_id}/details",
            headers=headers,
            json={"current_salary": unique_salary}
        )
        assert update_response.status_code == 200
        
        # Verify by getting the application
        get_response = requests.get(
            f"{BASE_URL}/api/applications/{test_application_id}",
            headers=headers
        )
        assert get_response.status_code == 200
        assert get_response.json()["current_salary"] == unique_salary
    
    def test_changes_visible_in_applicants_list(self, employer_token, test_application_id):
        """Test that changes are visible in job applicants list"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        # Get the application to find job_id
        app_response = requests.get(
            f"{BASE_URL}/api/applications/{test_application_id}",
            headers=headers
        )
        job_id = app_response.json()["job_id"]
        
        # Make a unique change
        unique_notice = "15 days"
        
        # Update
        update_response = requests.put(
            f"{BASE_URL}/api/applications/{test_application_id}/details",
            headers=headers,
            json={"notice_period": unique_notice}
        )
        assert update_response.status_code == 200
        
        # Verify in applicants list
        applicants_response = requests.get(
            f"{BASE_URL}/api/jobs/{job_id}/applicants",
            headers=headers
        )
        assert applicants_response.status_code == 200
        
        applicants = applicants_response.json()["applicants"]
        our_applicant = next(
            (a for a in applicants if a["id"] == test_application_id),
            None
        )
        
        assert our_applicant is not None
        assert our_applicant["notice_period"] == unique_notice
        assert our_applicant["manually_edited"] == True
        assert our_applicant["last_edited_by"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
