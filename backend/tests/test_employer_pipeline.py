"""
Test suite for Employer Pipeline View with Stage Control
Tests: GET /api/employer/pipeline, PUT /api/applications/{id}, POST /api/applications/{id}/notes
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
EMPLOYER_CREDS = {"email": "employer@vhctalent.com", "password": "VhcTalent@2024"}
RECRUITER_CREDS = {"email": "recruiter@vhctalent.com", "password": "VhcTalent@2024"}


class TestAuthentication:
    """Test authentication for all roles"""
    
    def test_admin_login(self, api_client):
        """Admin login should succeed"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "admin"
        print("✅ Admin login successful")
    
    def test_employer_login(self, api_client):
        """Employer login should succeed"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "employer"
        print("✅ Employer login successful")
    
    def test_recruiter_login(self, api_client):
        """Recruiter login should succeed"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json=RECRUITER_CREDS)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "recruiter"
        print("✅ Recruiter login successful")


class TestEmployerPipelineEndpoint:
    """Test GET /api/employer/pipeline endpoint"""
    
    def test_employer_pipeline_returns_correct_structure(self, employer_client):
        """Employer pipeline should return correct data structure"""
        response = employer_client.get(f"{BASE_URL}/api/employer/pipeline")
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "pipeline" in data
        assert "stage_counts" in data
        assert "total_applications" in data
        assert "filters" in data
        
        # Verify pipeline stages exist
        expected_stages = ["applied", "shortlisted", "interview", "offered", "hired", "rejected", "on_hold"]
        for stage in expected_stages:
            assert stage in data["pipeline"], f"Missing stage: {stage}"
            assert stage in data["stage_counts"], f"Missing stage count: {stage}"
        
        # Verify filters structure
        assert "recruiters" in data["filters"]
        assert "jobs" in data["filters"]
        
        print(f"✅ Employer pipeline structure correct - {data['total_applications']} total applications")
    
    def test_employer_pipeline_with_disabled_team_returns_empty(self, employer_client):
        """Employer with disabled team should get empty pipeline (expected behavior)"""
        response = employer_client.get(f"{BASE_URL}/api/employer/pipeline")
        assert response.status_code == 200
        data = response.json()
        
        # Note: employer@vhctalent.com has a DISABLED team, so pipeline is empty
        # This is expected behavior per the agent context
        assert data["total_applications"] == 0
        print("✅ Employer with disabled team returns empty pipeline (expected)")
    
    def test_employer_pipeline_filter_by_recruiter(self, employer_client):
        """Employer pipeline should accept recruiter_id filter"""
        response = employer_client.get(f"{BASE_URL}/api/employer/pipeline", params={"recruiter_id": "test-id"})
        assert response.status_code == 200
        data = response.json()
        assert "pipeline" in data
        print("✅ Employer pipeline accepts recruiter_id filter")
    
    def test_employer_pipeline_filter_by_job(self, employer_client):
        """Employer pipeline should accept job_id filter"""
        response = employer_client.get(f"{BASE_URL}/api/employer/pipeline", params={"job_id": "test-id"})
        assert response.status_code == 200
        data = response.json()
        assert "pipeline" in data
        print("✅ Employer pipeline accepts job_id filter")
    
    def test_employer_pipeline_unauthorized_without_token(self, api_client):
        """Employer pipeline should require authentication"""
        response = api_client.get(f"{BASE_URL}/api/employer/pipeline")
        assert response.status_code in [401, 403]
        print("✅ Employer pipeline requires authentication")


class TestAdminPipelineEndpoint:
    """Test admin pipeline still works (regression)"""
    
    def test_admin_pipeline_returns_data(self, admin_client):
        """Admin pipeline should return applications"""
        response = admin_client.get(f"{BASE_URL}/api/admin/pipeline")
        assert response.status_code == 200
        data = response.json()
        
        assert "pipeline" in data
        assert "stage_counts" in data
        assert "total_applications" in data
        assert data["total_applications"] > 0, "Admin should see applications"
        
        print(f"✅ Admin pipeline returns {data['total_applications']} applications")
    
    def test_admin_pipeline_filter_by_employer(self, admin_client):
        """Admin pipeline should filter by employer_id"""
        response = admin_client.get(f"{BASE_URL}/api/admin/pipeline", params={"employer_id": "096ec385-98a3-4001-9230-dfd79a68353f"})
        assert response.status_code == 200
        data = response.json()
        assert "pipeline" in data
        print(f"✅ Admin pipeline filter by employer returns {data['total_applications']} applications")


class TestApplicationStageTransition:
    """Test PUT /api/applications/{id} for stage transitions"""
    
    def test_stage_transition_applied_to_shortlisted(self, admin_client):
        """Should be able to move application from applied to shortlisted"""
        # Get an application in applied stage
        pipeline_res = admin_client.get(f"{BASE_URL}/api/admin/pipeline")
        assert pipeline_res.status_code == 200
        pipeline_data = pipeline_res.json()
        
        applied_apps = pipeline_data["pipeline"].get("applied", [])
        if not applied_apps:
            pytest.skip("No applications in applied stage to test")
        
        app_id = applied_apps[0]["id"]
        original_stage = "applied"
        
        # Update to shortlisted
        update_res = admin_client.put(f"{BASE_URL}/api/applications/{app_id}", json={"stage": "shortlisted"})
        assert update_res.status_code == 200
        updated_data = update_res.json()
        assert updated_data["stage"] == "shortlisted"
        
        # Revert back to original stage
        revert_res = admin_client.put(f"{BASE_URL}/api/applications/{app_id}", json={"stage": original_stage})
        assert revert_res.status_code == 200
        
        print(f"✅ Stage transition applied → shortlisted works for app {app_id}")
    
    def test_stage_transition_to_interview(self, admin_client):
        """Should be able to move application to interview stage"""
        pipeline_res = admin_client.get(f"{BASE_URL}/api/admin/pipeline")
        pipeline_data = pipeline_res.json()
        
        # Find any application to test
        for stage in ["applied", "shortlisted"]:
            apps = pipeline_data["pipeline"].get(stage, [])
            if apps:
                app_id = apps[0]["id"]
                original_stage = stage
                break
        else:
            pytest.skip("No applications available to test")
        
        # Update to interview
        update_res = admin_client.put(f"{BASE_URL}/api/applications/{app_id}", json={"stage": "interview"})
        assert update_res.status_code == 200
        assert update_res.json()["stage"] == "interview"
        
        # Revert
        admin_client.put(f"{BASE_URL}/api/applications/{app_id}", json={"stage": original_stage})
        print(f"✅ Stage transition to interview works")
    
    def test_stage_transition_invalid_app_id(self, admin_client):
        """Should return 404 for invalid application ID"""
        response = admin_client.put(f"{BASE_URL}/api/applications/invalid-id-12345", json={"stage": "shortlisted"})
        assert response.status_code == 404
        print("✅ Invalid application ID returns 404")


class TestApplicationNotes:
    """Test POST /api/applications/{id}/notes endpoint"""
    
    def test_add_note_to_application(self, admin_client):
        """Should be able to add note to application"""
        # Get an application
        pipeline_res = admin_client.get(f"{BASE_URL}/api/admin/pipeline")
        pipeline_data = pipeline_res.json()
        
        # Find any application
        app_id = None
        for stage, apps in pipeline_data["pipeline"].items():
            if apps:
                app_id = apps[0]["id"]
                break
        
        if not app_id:
            pytest.skip("No applications available to test")
        
        # Add note
        note_content = "TEST_note_from_pytest"
        response = admin_client.post(f"{BASE_URL}/api/applications/{app_id}/notes", json={"content": note_content})
        assert response.status_code == 200
        data = response.json()
        
        assert "note" in data
        assert data["note"]["content"] == note_content
        assert "author_name" in data["note"]
        assert "created_at" in data["note"]
        
        print(f"✅ Note added successfully to application {app_id}")
    
    def test_add_empty_note_fails(self, admin_client):
        """Should fail when adding empty note"""
        pipeline_res = admin_client.get(f"{BASE_URL}/api/admin/pipeline")
        pipeline_data = pipeline_res.json()
        
        app_id = None
        for stage, apps in pipeline_data["pipeline"].items():
            if apps:
                app_id = apps[0]["id"]
                break
        
        if not app_id:
            pytest.skip("No applications available to test")
        
        response = admin_client.post(f"{BASE_URL}/api/applications/{app_id}/notes", json={"content": ""})
        # Should either fail validation or return error
        assert response.status_code in [400, 422] or "error" in response.json().get("detail", "").lower()
        print("✅ Empty note validation works")


class TestDashboardStatsRegression:
    """Regression tests for dashboard stats"""
    
    def test_admin_stats_endpoint(self, admin_client):
        """Admin stats should work"""
        response = admin_client.get(f"{BASE_URL}/api/stats/admin")
        assert response.status_code == 200
        data = response.json()
        assert "total_jobs" in data
        print(f"✅ Admin stats: {data.get('total_jobs')} jobs")
    
    def test_employer_stats_endpoint(self, employer_client):
        """Employer stats should work"""
        response = employer_client.get(f"{BASE_URL}/api/stats/employer")
        assert response.status_code == 200
        print("✅ Employer stats endpoint works")
    
    def test_recruiter_stats_endpoint(self, recruiter_client):
        """Recruiter stats should work"""
        response = recruiter_client.get(f"{BASE_URL}/api/stats/recruiter")
        assert response.status_code == 200
        print("✅ Recruiter stats endpoint works")


class TestRecruiterPipelineRegression:
    """Regression tests for recruiter pipeline (uses applicationAPI.getAll)"""
    
    def test_recruiter_can_get_applications(self, recruiter_client):
        """Recruiter should be able to get applications"""
        response = recruiter_client.get(f"{BASE_URL}/api/applications")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Recruiter can get applications: {len(data)} found")
    
    def test_recruiter_can_update_application_stage(self, recruiter_client, admin_client):
        """Recruiter should be able to update application stage"""
        # Get applications via admin to find one
        pipeline_res = admin_client.get(f"{BASE_URL}/api/admin/pipeline")
        pipeline_data = pipeline_res.json()
        
        app_id = None
        original_stage = None
        for stage, apps in pipeline_data["pipeline"].items():
            if apps:
                app_id = apps[0]["id"]
                original_stage = stage
                break
        
        if not app_id:
            pytest.skip("No applications available to test")
        
        # Recruiter updates stage
        new_stage = "shortlisted" if original_stage != "shortlisted" else "interview"
        response = recruiter_client.put(f"{BASE_URL}/api/applications/{app_id}", json={"stage": new_stage})
        
        # Revert with admin
        admin_client.put(f"{BASE_URL}/api/applications/{app_id}", json={"stage": original_stage})
        
        assert response.status_code == 200
        print("✅ Recruiter can update application stage")


# Fixtures
@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture
def admin_client(api_client):
    """Session with admin auth"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
    if response.status_code == 200:
        token = response.json().get("access_token")
        api_client.headers.update({"Authorization": f"Bearer {token}"})
        return api_client
    pytest.skip("Admin authentication failed")


@pytest.fixture
def employer_client(api_client):
    """Session with employer auth"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
    if response.status_code == 200:
        token = response.json().get("access_token")
        api_client.headers.update({"Authorization": f"Bearer {token}"})
        return api_client
    pytest.skip("Employer authentication failed")


@pytest.fixture
def recruiter_client():
    """Session with recruiter auth"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    response = session.post(f"{BASE_URL}/api/auth/login", json=RECRUITER_CREDS)
    if response.status_code == 200:
        token = response.json().get("access_token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    pytest.skip("Recruiter authentication failed")
