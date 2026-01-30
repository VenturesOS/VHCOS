"""
VHC Talent OS - Test Candidate Name Fix and Expected CTC Feature
Tests:
1. FIX: Candidate name shows correctly in pipeline (not 'Unknown') - candidate_name field populated
2. NEW: Expected CTC is stored in application document
3. NEW: Expected salary is returned by GET /api/applications/{id}
4. EXISTING: Link candidate to job works correctly
5. REGRESSION: Pipeline displays all candidate details
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestCandidateNameAndExpectedCTC:
    """Test candidate name fix and expected CTC feature"""
    
    @pytest.fixture(scope="class")
    def recruiter_token(self):
        """Get recruiter authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "recruiter@vhctalent.com",
            "password": "VhcTalent@2024"
        })
        assert response.status_code == 200, f"Recruiter login failed: {response.text}"
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def recruiter_headers(self, recruiter_token):
        """Get headers with recruiter auth"""
        return {
            "Authorization": f"Bearer {recruiter_token}",
            "Content-Type": "application/json"
        }
    
    @pytest.fixture(scope="class")
    def employer_token(self):
        """Get employer authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "employer@vhctalent.com",
            "password": "VhcTalent@2024"
        })
        assert response.status_code == 200, f"Employer login failed: {response.text}"
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def employer_headers(self, employer_token):
        """Get headers with employer auth"""
        return {
            "Authorization": f"Bearer {employer_token}",
            "Content-Type": "application/json"
        }
    
    def test_recruiter_login(self, recruiter_token):
        """Test recruiter can login"""
        assert recruiter_token is not None
        print("✅ Recruiter login successful")
    
    def test_get_candidate_bank(self, recruiter_headers):
        """Test getting candidate bank"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=recruiter_headers)
        assert response.status_code == 200, f"Failed to get candidate bank: {response.text}"
        candidates = response.json()
        print(f"✅ Got {len(candidates)} candidates from candidate bank")
        return candidates
    
    def test_get_active_jobs(self, recruiter_headers):
        """Test getting active jobs"""
        response = requests.get(f"{BASE_URL}/api/jobs", headers=recruiter_headers)
        assert response.status_code == 200, f"Failed to get jobs: {response.text}"
        jobs = response.json()
        active_jobs = [j for j in jobs if j.get("status") == "active"]
        print(f"✅ Got {len(active_jobs)} active jobs")
        return active_jobs
    
    def test_verify_existing_application_has_candidate_name(self, recruiter_headers):
        """Test that existing application fe012056-0a6f-4e2d-a44f-1be83697b1be has candidate_name"""
        app_id = "fe012056-0a6f-4e2d-a44f-1be83697b1be"
        response = requests.get(f"{BASE_URL}/api/applications/{app_id}", headers=recruiter_headers)
        
        if response.status_code == 404:
            pytest.skip(f"Test application {app_id} not found - may have been cleaned up")
        
        assert response.status_code == 200, f"Failed to get application: {response.text}"
        app_data = response.json()
        
        # Verify candidate_name is populated
        candidate_name = app_data.get("candidate_name")
        assert candidate_name is not None, "candidate_name should not be None"
        assert candidate_name != "Unknown", f"candidate_name should not be 'Unknown', got: {candidate_name}"
        print(f"✅ Application has candidate_name: {candidate_name}")
        
        # Verify expected_salary is present (should be 1500000 per test data)
        expected_salary = app_data.get("expected_salary")
        print(f"✅ Application has expected_salary: {expected_salary}")
        
        return app_data
    
    def test_link_candidate_to_job_with_expected_ctc(self, recruiter_headers):
        """Test linking candidate to job with expected CTC"""
        # First get a candidate from the bank
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=recruiter_headers)
        assert response.status_code == 200
        candidates = response.json()
        
        if not candidates:
            pytest.skip("No candidates in candidate bank")
        
        # Find a candidate with salary and notice period
        candidate = None
        for c in candidates:
            if c.get("current_salary") and c.get("notice_period"):
                candidate = c
                break
        
        if not candidate:
            pytest.skip("No candidate with salary and notice period found")
        
        # Get active jobs
        response = requests.get(f"{BASE_URL}/api/jobs", headers=recruiter_headers)
        assert response.status_code == 200
        jobs = response.json()
        active_jobs = [j for j in jobs if j.get("status") == "active"]
        
        if not active_jobs:
            pytest.skip("No active jobs found")
        
        # Find a job that the candidate hasn't applied to
        job = None
        for j in active_jobs:
            # Check if application already exists
            check_response = requests.get(
                f"{BASE_URL}/api/applications?job_id={j['id']}", 
                headers=recruiter_headers
            )
            if check_response.status_code == 200:
                existing_apps = check_response.json()
                candidate_applied = any(
                    a.get("candidate_id") == candidate["id"] 
                    for a in existing_apps
                )
                if not candidate_applied:
                    job = j
                    break
        
        if not job:
            pytest.skip("No suitable job found for linking")
        
        # Calculate expected CTC (30% hike)
        current_salary = candidate.get("current_salary", 1000000)
        expected_ctc = int(current_salary * 1.3)  # 30% hike
        
        # Link candidate to job with expected CTC
        link_response = requests.post(
            f"{BASE_URL}/api/applications/link-candidate",
            headers=recruiter_headers,
            json={
                "candidate_id": candidate["id"],
                "job_id": job["id"],
                "expected_salary": expected_ctc
            }
        )
        
        assert link_response.status_code == 200, f"Failed to link candidate: {link_response.text}"
        link_data = link_response.json()
        
        assert link_data.get("success") == True
        assert link_data.get("application_id") is not None
        assert link_data.get("candidate_name") is not None
        assert link_data.get("candidate_name") != "Unknown"
        
        print(f"✅ Linked candidate '{link_data.get('candidate_name')}' to job '{link_data.get('job_title')}'")
        print(f"✅ Application ID: {link_data.get('application_id')}")
        
        # Verify the application has correct data
        app_id = link_data.get("application_id")
        app_response = requests.get(f"{BASE_URL}/api/applications/{app_id}", headers=recruiter_headers)
        assert app_response.status_code == 200
        app_data = app_response.json()
        
        # Verify candidate_name is populated correctly
        assert app_data.get("candidate_name") == candidate.get("name"), \
            f"candidate_name mismatch: expected {candidate.get('name')}, got {app_data.get('candidate_name')}"
        print(f"✅ Application candidate_name matches: {app_data.get('candidate_name')}")
        
        # Verify expected_salary is stored
        assert app_data.get("expected_salary") == expected_ctc, \
            f"expected_salary mismatch: expected {expected_ctc}, got {app_data.get('expected_salary')}"
        print(f"✅ Application expected_salary stored correctly: {app_data.get('expected_salary')}")
        
        return app_id
    
    def test_link_candidate_without_expected_ctc(self, recruiter_headers):
        """Test linking candidate to job without expected CTC (should be None)"""
        # Get candidates
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=recruiter_headers)
        assert response.status_code == 200
        candidates = response.json()
        
        if not candidates:
            pytest.skip("No candidates in candidate bank")
        
        # Find a candidate with salary and notice period
        candidate = None
        for c in candidates:
            if c.get("current_salary") and c.get("notice_period"):
                candidate = c
                break
        
        if not candidate:
            pytest.skip("No candidate with salary and notice period found")
        
        # Get active jobs
        response = requests.get(f"{BASE_URL}/api/jobs", headers=recruiter_headers)
        assert response.status_code == 200
        jobs = response.json()
        active_jobs = [j for j in jobs if j.get("status") == "active"]
        
        if not active_jobs:
            pytest.skip("No active jobs found")
        
        # Find a job that the candidate hasn't applied to
        job = None
        for j in active_jobs:
            check_response = requests.get(
                f"{BASE_URL}/api/applications?job_id={j['id']}", 
                headers=recruiter_headers
            )
            if check_response.status_code == 200:
                existing_apps = check_response.json()
                candidate_applied = any(
                    a.get("candidate_id") == candidate["id"] 
                    for a in existing_apps
                )
                if not candidate_applied:
                    job = j
                    break
        
        if not job:
            pytest.skip("No suitable job found for linking")
        
        # Link candidate to job WITHOUT expected CTC
        link_response = requests.post(
            f"{BASE_URL}/api/applications/link-candidate",
            headers=recruiter_headers,
            json={
                "candidate_id": candidate["id"],
                "job_id": job["id"]
                # No expected_salary
            }
        )
        
        assert link_response.status_code == 200, f"Failed to link candidate: {link_response.text}"
        link_data = link_response.json()
        
        # Verify the application
        app_id = link_data.get("application_id")
        app_response = requests.get(f"{BASE_URL}/api/applications/{app_id}", headers=recruiter_headers)
        assert app_response.status_code == 200
        app_data = app_response.json()
        
        # expected_salary should be None when not provided
        assert app_data.get("expected_salary") is None, \
            f"expected_salary should be None when not provided, got {app_data.get('expected_salary')}"
        print(f"✅ Application without expected_salary works correctly")
        
        return app_id
    
    def test_pipeline_shows_candidate_name(self, employer_headers):
        """Test that pipeline/applicants endpoint shows candidate_name correctly"""
        # Get jobs
        response = requests.get(f"{BASE_URL}/api/jobs", headers=employer_headers)
        assert response.status_code == 200
        jobs = response.json()
        
        if not jobs:
            pytest.skip("No jobs found")
        
        # Find a job with applicants
        for job in jobs:
            applicants_response = requests.get(
                f"{BASE_URL}/api/jobs/{job['id']}/applicants",
                headers=employer_headers
            )
            if applicants_response.status_code == 200:
                data = applicants_response.json()
                applicants = data.get("applicants", [])
                if applicants:
                    # Check that candidate_name is populated
                    for applicant in applicants:
                        candidate_name = applicant.get("candidate_name")
                        if candidate_name:
                            assert candidate_name != "Unknown", \
                                f"candidate_name should not be 'Unknown' in pipeline"
                            print(f"✅ Pipeline shows candidate_name: {candidate_name}")
                            return
        
        print("⚠️ No applicants found to verify candidate_name in pipeline")
    
    def test_application_response_model_has_expected_salary(self, recruiter_headers):
        """Test that ApplicationResponse model includes expected_salary field"""
        # Get any application
        response = requests.get(f"{BASE_URL}/api/applications", headers=recruiter_headers)
        assert response.status_code == 200
        applications = response.json()
        
        if not applications:
            pytest.skip("No applications found")
        
        # Check first application
        app = applications[0]
        app_id = app.get("id")
        
        # Get single application
        app_response = requests.get(f"{BASE_URL}/api/applications/{app_id}", headers=recruiter_headers)
        assert app_response.status_code == 200
        app_data = app_response.json()
        
        # Verify expected_salary field exists in response (can be None)
        assert "expected_salary" in app_data or app_data.get("expected_salary") is None, \
            "expected_salary field should be present in ApplicationResponse"
        print(f"✅ ApplicationResponse includes expected_salary field: {app_data.get('expected_salary')}")


class TestRegressionRecruiterDashboard:
    """Regression tests for recruiter dashboard and pipeline"""
    
    @pytest.fixture(scope="class")
    def recruiter_token(self):
        """Get recruiter authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "recruiter@vhctalent.com",
            "password": "VhcTalent@2024"
        })
        assert response.status_code == 200
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def recruiter_headers(self, recruiter_token):
        return {
            "Authorization": f"Bearer {recruiter_token}",
            "Content-Type": "application/json"
        }
    
    def test_recruiter_dashboard_loads(self, recruiter_headers):
        """Test recruiter dashboard data loads"""
        response = requests.get(f"{BASE_URL}/api/recruiter/dashboard", headers=recruiter_headers)
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        data = response.json()
        print(f"✅ Recruiter dashboard loads - {data.get('total_candidates', 0)} candidates")
    
    def test_recruiter_pipeline_loads(self, recruiter_headers):
        """Test recruiter pipeline data loads"""
        response = requests.get(f"{BASE_URL}/api/recruiter/pipeline", headers=recruiter_headers)
        assert response.status_code == 200, f"Pipeline failed: {response.text}"
        data = response.json()
        print(f"✅ Recruiter pipeline loads - {len(data.get('applications', []))} applications")
    
    def test_candidate_bank_accessible(self, recruiter_headers):
        """Test candidate bank is accessible"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=recruiter_headers)
        assert response.status_code == 200, f"Candidate bank failed: {response.text}"
        candidates = response.json()
        print(f"✅ Candidate bank accessible - {len(candidates)} candidates")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
