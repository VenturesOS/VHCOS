"""
Test suite for POST /api/matching/shortlist endpoint
Tests the bug fix: Shortlist Candidate button functionality from AI screening
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestShortlistCandidate:
    """Tests for shortlisting candidates from AI screening to job pipeline"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        self.admin_email = "admin@vhc.in"
        self.admin_password = "VhcAdmin@2024"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": self.admin_email,
            "password": self.admin_password
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token = login_res.json()["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        print(f"✅ Logged in as admin")
    
    def test_shortlist_endpoint_exists(self):
        """Test that POST /api/matching/shortlist endpoint exists"""
        # Send request with invalid data to check endpoint exists (should return 422 not 404)
        response = self.session.post(f"{BASE_URL}/api/matching/shortlist", json={})
        assert response.status_code != 404, "Endpoint /api/matching/shortlist not found"
        print(f"✅ Endpoint exists, status: {response.status_code}")
    
    def test_shortlist_requires_candidate_id(self):
        """Test that candidate_id is required"""
        response = self.session.post(f"{BASE_URL}/api/matching/shortlist", json={
            "job_id": "some-job-id"
        })
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print(f"✅ Validation works - candidate_id required")
    
    def test_shortlist_requires_job_id(self):
        """Test that job_id is required"""
        response = self.session.post(f"{BASE_URL}/api/matching/shortlist", json={
            "candidate_id": "some-candidate-id"
        })
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print(f"✅ Validation works - job_id required")
    
    def test_shortlist_invalid_job_returns_404(self):
        """Test that invalid job_id returns 404"""
        response = self.session.post(f"{BASE_URL}/api/matching/shortlist", json={
            "candidate_id": "some-candidate-id",
            "job_id": "invalid-job-id-12345"
        })
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        assert "Job not found" in response.json().get("detail", "")
        print(f"✅ Invalid job returns 404")
    
    def test_shortlist_invalid_candidate_returns_404(self):
        """Test that invalid candidate_id returns 404"""
        # First get a valid job
        jobs_res = self.session.get(f"{BASE_URL}/api/jobs")
        assert jobs_res.status_code == 200
        jobs = jobs_res.json()
        assert len(jobs) > 0, "No jobs found for testing"
        job_id = jobs[0]["id"]
        
        response = self.session.post(f"{BASE_URL}/api/matching/shortlist", json={
            "candidate_id": "invalid-candidate-id-12345",
            "job_id": job_id
        })
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        assert "Candidate not found" in response.json().get("detail", "")
        print(f"✅ Invalid candidate returns 404")
    
    def test_shortlist_creates_application_record(self):
        """Test that shortlisting creates an application record with correct stage and source"""
        # Get a valid job
        jobs_res = self.session.get(f"{BASE_URL}/api/jobs")
        assert jobs_res.status_code == 200
        jobs = jobs_res.json()
        assert len(jobs) > 0, "No jobs found for testing"
        job_id = jobs[0]["id"]
        job_title = jobs[0]["title"]
        
        # Get a candidate from candidate bank
        candidates_res = self.session.get(f"{BASE_URL}/api/candidate-bank?limit=50")
        assert candidates_res.status_code == 200
        candidates = candidates_res.json()
        assert len(candidates) > 0, "No candidates found for testing"
        
        # Find a candidate not already in this job's pipeline
        candidate = None
        for c in candidates:
            # Check if candidate already has application for this job
            apps_res = self.session.get(f"{BASE_URL}/api/jobs/{job_id}/applicants")
            if apps_res.status_code == 200:
                applicants = apps_res.json().get("applicants", [])
                existing_ids = [a.get("candidate_id") for a in applicants]
                if c["id"] not in existing_ids:
                    candidate = c
                    break
        
        if not candidate:
            pytest.skip("All candidates already in pipeline for test job")
        
        candidate_id = candidate["id"]
        candidate_name = candidate.get("name", "")
        
        # Shortlist the candidate
        response = self.session.post(f"{BASE_URL}/api/matching/shortlist", json={
            "candidate_id": candidate_id,
            "job_id": job_id,
            "notes": "TEST_SHORTLIST - Testing shortlist functionality"
        })
        
        assert response.status_code == 200, f"Shortlist failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "application_id" in data, "Response missing application_id"
        assert "candidate_name" in data, "Response missing candidate_name"
        assert "job_title" in data, "Response missing job_title"
        assert data["stage"] == "shortlisted", f"Expected stage 'shortlisted', got {data['stage']}"
        
        application_id = data["application_id"]
        print(f"✅ Shortlist created application: {application_id}")
        
        # Verify application was created with correct data
        app_res = self.session.get(f"{BASE_URL}/api/applications/{application_id}")
        assert app_res.status_code == 200, f"Failed to get application: {app_res.text}"
        app_data = app_res.json()
        
        assert app_data["stage"] == "shortlisted", f"Application stage should be 'shortlisted', got {app_data['stage']}"
        assert app_data["source"] == "ai_screening", f"Application source should be 'ai_screening', got {app_data.get('source')}"
        assert app_data["candidate_id"] == candidate_id
        assert app_data["job_id"] == job_id
        
        print(f"✅ Application has correct stage='shortlisted' and source='ai_screening'")
        
        # Verify candidate appears in job pipeline
        pipeline_res = self.session.get(f"{BASE_URL}/api/jobs/{job_id}/applicants")
        assert pipeline_res.status_code == 200
        pipeline_data = pipeline_res.json()
        applicants = pipeline_data.get("applicants", [])
        
        found = False
        for applicant in applicants:
            if applicant.get("candidate_id") == candidate_id:
                found = True
                assert applicant.get("stage") == "shortlisted"
                break
        
        assert found, f"Candidate {candidate_id} not found in job pipeline"
        print(f"✅ Candidate appears in job pipeline with stage='shortlisted'")
        
        return application_id, candidate_id, job_id
    
    def test_duplicate_shortlist_returns_400(self):
        """Test that shortlisting same candidate to same job twice returns 400"""
        # Get a valid job
        jobs_res = self.session.get(f"{BASE_URL}/api/jobs")
        jobs = jobs_res.json()
        job_id = jobs[0]["id"]
        
        # Get a candidate
        candidates_res = self.session.get(f"{BASE_URL}/api/candidate-bank?limit=50")
        candidates = candidates_res.json()
        
        # Find a candidate not already in pipeline
        candidate = None
        for c in candidates:
            apps_res = self.session.get(f"{BASE_URL}/api/jobs/{job_id}/applicants")
            if apps_res.status_code == 200:
                applicants = apps_res.json().get("applicants", [])
                existing_ids = [a.get("candidate_id") for a in applicants]
                if c["id"] not in existing_ids:
                    candidate = c
                    break
        
        if not candidate:
            pytest.skip("All candidates already in pipeline")
        
        candidate_id = candidate["id"]
        
        # First shortlist should succeed
        response1 = self.session.post(f"{BASE_URL}/api/matching/shortlist", json={
            "candidate_id": candidate_id,
            "job_id": job_id
        })
        assert response1.status_code == 200, f"First shortlist failed: {response1.text}"
        print(f"✅ First shortlist succeeded")
        
        # Second shortlist should fail with 400
        response2 = self.session.post(f"{BASE_URL}/api/matching/shortlist", json={
            "candidate_id": candidate_id,
            "job_id": job_id
        })
        assert response2.status_code == 400, f"Expected 400 for duplicate, got {response2.status_code}"
        assert "already in pipeline" in response2.json().get("detail", "").lower()
        print(f"✅ Duplicate shortlist correctly returns 400: {response2.json().get('detail')}")
    
    def test_shortlist_with_notes(self):
        """Test that notes are saved when shortlisting"""
        # Get a valid job
        jobs_res = self.session.get(f"{BASE_URL}/api/jobs")
        jobs = jobs_res.json()
        job_id = jobs[1]["id"] if len(jobs) > 1 else jobs[0]["id"]  # Use different job
        
        # Get a candidate not in this job's pipeline
        candidates_res = self.session.get(f"{BASE_URL}/api/candidate-bank?limit=50")
        candidates = candidates_res.json()
        
        candidate = None
        for c in candidates:
            apps_res = self.session.get(f"{BASE_URL}/api/jobs/{job_id}/applicants")
            if apps_res.status_code == 200:
                applicants = apps_res.json().get("applicants", [])
                existing_ids = [a.get("candidate_id") for a in applicants]
                if c["id"] not in existing_ids:
                    candidate = c
                    break
        
        if not candidate:
            pytest.skip("All candidates already in pipeline for this job")
        
        test_notes = "TEST_NOTES - Excellent candidate from AI screening"
        
        response = self.session.post(f"{BASE_URL}/api/matching/shortlist", json={
            "candidate_id": candidate["id"],
            "job_id": job_id,
            "notes": test_notes
        })
        
        assert response.status_code == 200, f"Shortlist with notes failed: {response.text}"
        application_id = response.json()["application_id"]
        
        # Verify notes were saved
        app_res = self.session.get(f"{BASE_URL}/api/applications/{application_id}")
        assert app_res.status_code == 200
        app_data = app_res.json()
        
        notes = app_data.get("notes", [])
        assert len(notes) > 0, "Notes not saved"
        assert test_notes in str(notes), f"Notes content not found. Got: {notes}"
        print(f"✅ Notes saved correctly: {notes}")
    
    def test_shortlist_unauthorized_role(self):
        """Test that candidate role cannot shortlist"""
        # Create a new session without auth
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        # Try to shortlist without auth
        response = session.post(f"{BASE_URL}/api/matching/shortlist", json={
            "candidate_id": "some-id",
            "job_id": "some-job"
        })
        
        # Should return 401 (unauthorized) or 403 (forbidden)
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"✅ Unauthorized access correctly blocked: {response.status_code}")


class TestShortlistFrontendAPI:
    """Test the frontend API function matchingAPI.shortlistCandidate"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    def test_api_matches_frontend_call_format(self):
        """Test that API accepts the format used by frontend matchingAPI.shortlistCandidate"""
        # Frontend sends: { candidate_id, job_id, notes }
        # This matches the ShortlistRequest model
        
        jobs_res = self.session.get(f"{BASE_URL}/api/jobs")
        jobs = jobs_res.json()
        job_id = jobs[2]["id"] if len(jobs) > 2 else jobs[0]["id"]
        
        candidates_res = self.session.get(f"{BASE_URL}/api/candidate-bank?limit=50")
        candidates = candidates_res.json()
        
        candidate = None
        for c in candidates:
            apps_res = self.session.get(f"{BASE_URL}/api/jobs/{job_id}/applicants")
            if apps_res.status_code == 200:
                applicants = apps_res.json().get("applicants", [])
                existing_ids = [a.get("candidate_id") for a in applicants]
                if c["id"] not in existing_ids:
                    candidate = c
                    break
        
        if not candidate:
            pytest.skip("All candidates already in pipeline")
        
        # Simulate frontend call format
        response = self.session.post(f"{BASE_URL}/api/matching/shortlist", json={
            "candidate_id": candidate["id"],
            "job_id": job_id,
            "notes": None  # Frontend may send null
        })
        
        assert response.status_code == 200, f"API call failed: {response.text}"
        data = response.json()
        
        # Verify response has fields frontend expects
        assert "candidate_name" in data
        assert "job_title" in data
        assert "application_id" in data
        print(f"✅ API response matches frontend expectations: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
