"""
P1 Applicant Review Screen Tests
Tests for GET /api/jobs/{job_id}/applicants endpoint and related functionality
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://talent-graph-fix.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
EMPLOYER_EMAIL = "employer@vhctalent.com"
EMPLOYER_PASSWORD = "Demo@2024"
TEST_JOB_ID = "7348e899-c5c7-4145-94ed-d0653e1c7b0c"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def employer_token():
    """Get employer authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMPLOYER_EMAIL, "password": EMPLOYER_PASSWORD}
    )
    assert response.status_code == 200, f"Employer login failed: {response.text}"
    return response.json()["access_token"]


class TestJobApplicantsEndpoint:
    """Tests for GET /api/jobs/{job_id}/applicants endpoint"""
    
    def test_admin_can_access_applicants(self, admin_token):
        """Admin should be able to access any job's applicants"""
        response = requests.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "job" in data
        assert "applicants" in data
        assert "stage_counts" in data
        
    def test_job_info_in_response(self, admin_token):
        """Job info should include title, location, type, salary range"""
        response = requests.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        job = response.json()["job"]
        
        # Verify job fields
        assert "id" in job
        assert "title" in job
        assert "location" in job
        assert "job_type" in job
        assert "salary_min" in job
        assert "salary_max" in job
        assert "requirements" in job
        assert "applicant_count" in job
        
        # Verify actual values
        assert job["title"] == "Test Software Engineer"
        assert job["location"] == "Remote"
        assert job["job_type"] == "full-time"
        
    def test_applicant_enriched_data(self, admin_token):
        """Applicants should have enriched data with match_score, must_haves, etc."""
        response = requests.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        applicants = response.json()["applicants"]
        
        assert len(applicants) > 0, "Should have at least one applicant"
        
        # Check first applicant has all required fields
        applicant = applicants[0]
        required_fields = [
            "id", "job_id", "candidate_id", "candidate_name", "candidate_email",
            "headline", "skills", "experience_years", "location",
            "current_salary", "notice_period", "stage", "match_score",
            "must_haves_met", "career_stability", "applied_at"
        ]
        
        for field in required_fields:
            assert field in applicant, f"Missing field: {field}"
            
    def test_match_score_calculation(self, admin_token):
        """Match score should be calculated based on requirements"""
        response = requests.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        applicants = response.json()["applicants"]
        
        for applicant in applicants:
            match_score = applicant.get("match_score")
            assert match_score is not None
            assert isinstance(match_score, int)
            assert 0 <= match_score <= 100
            
    def test_must_haves_met_structure(self, admin_token):
        """Must-haves should be list of {requirement, met} objects"""
        response = requests.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        applicants = response.json()["applicants"]
        
        for applicant in applicants:
            must_haves = applicant.get("must_haves_met", [])
            for mh in must_haves:
                assert "requirement" in mh
                assert "met" in mh
                assert isinstance(mh["met"], bool)
                
    def test_career_stability_indicator(self, admin_token):
        """Career stability should have score (green/yellow/red) and quick_changes"""
        response = requests.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        applicants = response.json()["applicants"]
        
        for applicant in applicants:
            stability = applicant.get("career_stability")
            if stability:  # Some may be null if no experience data
                assert "score" in stability
                assert stability["score"] in ["green", "yellow", "red"]
                assert "quick_changes" in stability
                assert isinstance(stability["quick_changes"], int)
                
    def test_stage_counts(self, admin_token):
        """Stage counts should include all stages"""
        response = requests.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        stage_counts = response.json()["stage_counts"]
        
        expected_stages = [
            "applied", "shortlisted", "interview", "offered", "hired",
            "rejected", "on_hold", "over_budget", "not_qualified"
        ]
        
        for stage in expected_stages:
            assert stage in stage_counts, f"Missing stage count: {stage}"
            assert isinstance(stage_counts[stage], int)
            
    def test_filter_by_stage(self, admin_token):
        """Should be able to filter applicants by stage"""
        response = requests.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants?stage=applied",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        applicants = response.json()["applicants"]
        
        for applicant in applicants:
            assert applicant["stage"] == "applied"
            
    def test_applicants_sorted_by_match_score(self, admin_token):
        """Applicants should be sorted by match score (highest first)"""
        response = requests.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        applicants = response.json()["applicants"]
        
        if len(applicants) > 1:
            scores = [a.get("match_score", 0) for a in applicants]
            # Check if sorted in descending order
            assert scores == sorted(scores, reverse=True), "Applicants should be sorted by match score"
            
    def test_unauthorized_access(self):
        """Should return 401 without auth token"""
        response = requests.get(f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants")
        assert response.status_code in [401, 403]
        
    def test_job_not_found(self, admin_token):
        """Should return 404 for non-existent job"""
        response = requests.get(
            f"{BASE_URL}/api/jobs/non-existent-job-id/applicants",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 404


class TestApplicationStageUpdate:
    """Tests for updating application stage (action buttons)"""
    
    def test_update_to_shortlisted(self, admin_token):
        """Should be able to shortlist an applicant"""
        # First get an applicant
        response = requests.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        applicants = response.json()["applicants"]
        
        # Find one in 'applied' stage
        applied_applicant = next((a for a in applicants if a["stage"] == "applied"), None)
        if applied_applicant:
            app_id = applied_applicant["id"]
            
            # Update to shortlisted
            update_response = requests.put(
                f"{BASE_URL}/api/applications/{app_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"stage": "shortlisted"}
            )
            assert update_response.status_code == 200
            
            # Verify update
            updated = update_response.json()
            assert updated["stage"] == "shortlisted"
            
            # Revert back to applied for other tests
            requests.put(
                f"{BASE_URL}/api/applications/{app_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"stage": "applied"}
            )
            
    def test_update_to_rejected(self, admin_token):
        """Should be able to reject an applicant"""
        response = requests.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        applicants = response.json()["applicants"]
        
        applied_applicant = next((a for a in applicants if a["stage"] == "applied"), None)
        if applied_applicant:
            app_id = applied_applicant["id"]
            
            update_response = requests.put(
                f"{BASE_URL}/api/applications/{app_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"stage": "rejected"}
            )
            assert update_response.status_code == 200
            assert update_response.json()["stage"] == "rejected"
            
            # Revert
            requests.put(
                f"{BASE_URL}/api/applications/{app_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"stage": "applied"}
            )
            
    def test_update_to_on_hold(self, admin_token):
        """Should be able to put applicant on hold"""
        response = requests.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        applicants = response.json()["applicants"]
        
        applied_applicant = next((a for a in applicants if a["stage"] == "applied"), None)
        if applied_applicant:
            app_id = applied_applicant["id"]
            
            update_response = requests.put(
                f"{BASE_URL}/api/applications/{app_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"stage": "on_hold"}
            )
            assert update_response.status_code == 200
            assert update_response.json()["stage"] == "on_hold"
            
            # Revert
            requests.put(
                f"{BASE_URL}/api/applications/{app_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"stage": "applied"}
            )
            
    def test_update_to_over_budget(self, admin_token):
        """Should be able to mark applicant as over budget"""
        response = requests.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        applicants = response.json()["applicants"]
        
        applied_applicant = next((a for a in applicants if a["stage"] == "applied"), None)
        if applied_applicant:
            app_id = applied_applicant["id"]
            
            update_response = requests.put(
                f"{BASE_URL}/api/applications/{app_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"stage": "over_budget"}
            )
            assert update_response.status_code == 200
            assert update_response.json()["stage"] == "over_budget"
            
            # Revert
            requests.put(
                f"{BASE_URL}/api/applications/{app_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"stage": "applied"}
            )
            
    def test_update_to_not_qualified(self, admin_token):
        """Should be able to mark applicant as not qualified"""
        response = requests.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        applicants = response.json()["applicants"]
        
        applied_applicant = next((a for a in applicants if a["stage"] == "applied"), None)
        if applied_applicant:
            app_id = applied_applicant["id"]
            
            update_response = requests.put(
                f"{BASE_URL}/api/applications/{app_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"stage": "not_qualified"}
            )
            assert update_response.status_code == 200
            assert update_response.json()["stage"] == "not_qualified"
            
            # Revert
            requests.put(
                f"{BASE_URL}/api/applications/{app_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"stage": "applied"}
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
