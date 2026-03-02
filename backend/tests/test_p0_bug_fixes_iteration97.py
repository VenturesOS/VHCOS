"""
P0 Bug Fixes Test Suite - Iteration 97
Tests for:
1. ATS CV download with ?token= query param (GET /api/candidate-bank/{id}/ats-cv?token=JWT)
2. Resume download with ?token= query param (GET /api/candidate-bank/{id}/download-resume?token=JWT)
3. PUT /api/candidate-bank/{id}/salary-notice endpoint (newly created)
4. PATCH /api/candidate-bank/{id} for updating candidate fields
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://talent-platform-29.preview.emergentagent.com")

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
USER_EMAIL = "siddharth@vhc.in"
USER_PASSWORD = "12345678"


class TestAuthTokenFixes:
    """Test authentication token handling fixes"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin JWT token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        token = data.get("access_token")  # Note: returns 'access_token' not 'token'
        assert token, f"No access_token in response: {data}"
        return token
    
    @pytest.fixture(scope="class")
    def user_token(self):
        """Get regular user JWT token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        })
        assert response.status_code == 200, f"User login failed: {response.text}"
        data = response.json()
        token = data.get("access_token")
        assert token, f"No access_token in response: {data}"
        return token

    @pytest.fixture(scope="class")
    def candidate_id(self, admin_token):
        """Get a valid candidate ID from candidate bank"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=headers, params={"limit": 1})
        assert response.status_code == 200, f"Failed to get candidates: {response.text}"
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            pytest.skip("No candidates in candidate bank for testing")
        return candidates[0]["id"]


class TestAtsCvDownloadAuth(TestAuthTokenFixes):
    """Fix 1: ATS CV download with ?token= query param"""
    
    def test_ats_cv_with_token_param_returns_200(self, admin_token, candidate_id):
        """
        GET /api/candidate-bank/{id}/ats-cv?token=JWT should return 200 with LaTeX content
        This tests the fix for new-tab downloads that can't send Authorization header
        """
        # Call without Authorization header, using query param instead
        url = f"{BASE_URL}/api/candidate-bank/{candidate_id}/ats-cv"
        response = requests.get(url, params={"token": admin_token})
        
        assert response.status_code == 200, f"ATS CV with token param failed: {response.status_code} - {response.text}"
        
        # Verify it returns LaTeX content
        content = response.text
        assert len(content) > 100, "Response too short for valid LaTeX"
        # LaTeX documents typically start with \documentclass or have \begin{document}
        assert "\\documentclass" in content or "\\begin{document}" in content or "\\section" in content, \
            f"Response doesn't look like LaTeX: {content[:200]}"
        
        print(f"✓ ATS CV with ?token= param returns valid LaTeX ({len(content)} chars)")
    
    def test_ats_cv_without_token_returns_401(self, candidate_id):
        """Without token param or Authorization header, should return 401"""
        url = f"{BASE_URL}/api/candidate-bank/{candidate_id}/ats-cv"
        response = requests.get(url)
        
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ ATS CV without auth correctly returns 401")
    
    def test_ats_cv_with_invalid_token_returns_401(self, candidate_id):
        """Invalid token should return 401"""
        url = f"{BASE_URL}/api/candidate-bank/{candidate_id}/ats-cv"
        response = requests.get(url, params={"token": "invalid_token_xyz"})
        
        assert response.status_code == 401, f"Expected 401 with invalid token, got {response.status_code}"
        print("✓ ATS CV with invalid token correctly returns 401")
    
    def test_ats_cv_with_user_token_works(self, user_token, candidate_id):
        """Regular user (recruiter) should also be able to download ATS CV"""
        url = f"{BASE_URL}/api/candidate-bank/{candidate_id}/ats-cv"
        response = requests.get(url, params={"token": user_token})
        
        # Should return 200 (recruiter/employer/admin can access)
        assert response.status_code == 200, f"ATS CV with user token failed: {response.status_code}"
        print("✓ ATS CV works for regular user token")


class TestResumeDownloadAuth(TestAuthTokenFixes):
    """Fix 4: Resume download with ?token= query param"""
    
    def test_download_resume_with_token_param(self, admin_token, candidate_id):
        """
        GET /api/candidate-bank/{id}/download-resume?token=JWT
        Should work (may return 404 if no resume file, but NOT 401)
        """
        url = f"{BASE_URL}/api/candidate-bank/{candidate_id}/download-resume"
        response = requests.get(url, params={"token": admin_token})
        
        # 200 = resume found and returned
        # 404 = candidate found but no resume file attached (this is OK)
        # 401 = auth failed (this is the bug we're testing)
        assert response.status_code in [200, 404], \
            f"Resume download failed with auth error: {response.status_code} - {response.text}"
        
        if response.status_code == 404:
            print(f"✓ Resume download with token: 404 (no resume file - expected for many candidates)")
        else:
            print(f"✓ Resume download with token: 200 (resume returned)")
    
    def test_download_resume_without_token_returns_401(self, candidate_id):
        """Without token, should return 401"""
        url = f"{BASE_URL}/api/candidate-bank/{candidate_id}/download-resume"
        response = requests.get(url)
        
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Resume download without auth correctly returns 401")


class TestSalaryNoticeEndpoint(TestAuthTokenFixes):
    """Fix 3: PUT /api/candidate-bank/{id}/salary-notice endpoint"""
    
    def test_update_salary_notice_all_fields(self, admin_token, candidate_id):
        """
        PUT /api/candidate-bank/{id}/salary-notice with all query params
        """
        headers = {"Authorization": f"Bearer {admin_token}"}
        url = f"{BASE_URL}/api/candidate-bank/{candidate_id}/salary-notice"
        params = {
            "current_salary": 500000,
            "notice_period": "30 days",
            "location": "Mumbai",
            "experience_years": 5
        }
        
        response = requests.put(url, headers=headers, params=params)
        
        assert response.status_code == 200, f"Update salary-notice failed: {response.status_code} - {response.text}"
        data = response.json()
        assert data.get("success") == True, f"Expected success=True, got {data}"
        assert data.get("candidate_id") == candidate_id, f"Wrong candidate_id in response"
        
        print(f"✓ PUT salary-notice with all fields succeeded")
        
        # Verify the data was persisted
        get_response = requests.get(f"{BASE_URL}/api/candidate-bank/{candidate_id}", headers=headers)
        assert get_response.status_code == 200
        candidate = get_response.json()
        
        assert candidate.get("current_salary") == 500000, f"current_salary not persisted: {candidate.get('current_salary')}"
        assert candidate.get("notice_period") == "30 days", f"notice_period not persisted: {candidate.get('notice_period')}"
        assert candidate.get("location") == "Mumbai", f"location not persisted: {candidate.get('location')}"
        assert candidate.get("experience_years") == 5, f"experience_years not persisted: {candidate.get('experience_years')}"
        
        print("✓ All salary-notice fields verified as persisted")
    
    def test_update_salary_notice_partial_fields(self, admin_token, candidate_id):
        """Update only some fields"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        url = f"{BASE_URL}/api/candidate-bank/{candidate_id}/salary-notice"
        params = {
            "current_salary": 600000,
            "notice_period": "60 days"
        }
        
        response = requests.put(url, headers=headers, params=params)
        
        assert response.status_code == 200, f"Partial update failed: {response.status_code}"
        
        # Verify partial update
        get_response = requests.get(f"{BASE_URL}/api/candidate-bank/{candidate_id}", headers=headers)
        candidate = get_response.json()
        assert candidate.get("current_salary") == 600000
        assert candidate.get("notice_period") == "60 days"
        # Previous values should still be there
        assert candidate.get("location") == "Mumbai"  # From previous test
        
        print("✓ Partial salary-notice update succeeded")
    
    def test_update_salary_notice_without_auth_fails(self, candidate_id):
        """Without auth, should return 401"""
        url = f"{BASE_URL}/api/candidate-bank/{candidate_id}/salary-notice"
        params = {"current_salary": 700000}
        
        response = requests.put(url, params=params)
        
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ salary-notice without auth correctly returns 401")
    
    def test_update_salary_notice_nonexistent_candidate(self, admin_token):
        """Non-existent candidate should return 404"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        url = f"{BASE_URL}/api/candidate-bank/nonexistent-id-12345/salary-notice"
        params = {"current_salary": 500000}
        
        response = requests.put(url, headers=headers, params=params)
        
        assert response.status_code == 404, f"Expected 404 for non-existent candidate, got {response.status_code}"
        print("✓ salary-notice for non-existent candidate returns 404")


class TestCandidatePatchUpdate(TestAuthTokenFixes):
    """Fix 3b: PATCH /api/candidate-bank/{id} with JSON body"""
    
    def test_patch_candidate_updates_fields(self, admin_token, candidate_id):
        """
        PATCH /api/candidate-bank/{id} with JSON body should update candidate fields
        """
        headers = {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"
        }
        url = f"{BASE_URL}/api/candidate-bank/{candidate_id}"
        payload = {
            "name": "Test Candidate Updated",
            "headline": "Senior Software Engineer",
            "summary": "Updated summary for testing",
            "current_employer": "Test Company Inc"
        }
        
        response = requests.patch(url, headers=headers, json=payload)
        
        assert response.status_code == 200, f"PATCH update failed: {response.status_code} - {response.text}"
        data = response.json()
        assert data.get("success") == True, f"Expected success=True, got {data}"
        
        print("✓ PATCH candidate update succeeded")
        
        # Verify persistence
        get_response = requests.get(url, headers=headers)
        assert get_response.status_code == 200
        candidate = get_response.json()
        
        assert candidate.get("name") == "Test Candidate Updated", f"name not updated: {candidate.get('name')}"
        assert candidate.get("headline") == "Senior Software Engineer", f"headline not updated"
        assert candidate.get("summary") == "Updated summary for testing", f"summary not updated"
        assert candidate.get("current_employer") == "Test Company Inc", f"current_employer not updated"
        
        print("✓ All PATCH fields verified as persisted")
    
    def test_patch_candidate_without_auth_fails(self, candidate_id):
        """Without auth, should return 401"""
        url = f"{BASE_URL}/api/candidate-bank/{candidate_id}"
        payload = {"name": "Should Not Update"}
        
        response = requests.patch(url, json=payload)
        
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ PATCH without auth correctly returns 401")


class TestEndpointExistence:
    """Verify all endpoints exist and are routed correctly"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        return response.json().get("access_token")
    
    def test_salary_notice_endpoint_exists(self, admin_token):
        """Verify PUT /salary-notice endpoint is routed"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        # Get a candidate first
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=headers, params={"limit": 1})
        if response.status_code != 200 or not response.json().get("candidates"):
            pytest.skip("No candidates available")
        
        candidate_id = response.json()["candidates"][0]["id"]
        
        # Test the endpoint exists (should not return 404 Method Not Allowed or 405)
        url = f"{BASE_URL}/api/candidate-bank/{candidate_id}/salary-notice"
        response = requests.put(url, headers=headers, params={"current_salary": 100000})
        
        assert response.status_code not in [404, 405], \
            f"salary-notice endpoint not properly routed: {response.status_code}"
        print(f"✓ PUT /salary-notice endpoint exists and returns {response.status_code}")
    
    def test_ats_cv_endpoint_exists(self, admin_token):
        """Verify GET /ats-cv endpoint is routed"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=headers, params={"limit": 1})
        if response.status_code != 200 or not response.json().get("candidates"):
            pytest.skip("No candidates available")
        
        candidate_id = response.json()["candidates"][0]["id"]
        
        url = f"{BASE_URL}/api/candidate-bank/{candidate_id}/ats-cv"
        response = requests.get(url, params={"token": admin_token})
        
        assert response.status_code not in [404, 405], \
            f"ats-cv endpoint not properly routed: {response.status_code}"
        print(f"✓ GET /ats-cv endpoint exists and returns {response.status_code}")
    
    def test_download_resume_endpoint_exists(self, admin_token):
        """Verify GET /download-resume endpoint is routed"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=headers, params={"limit": 1})
        if response.status_code != 200 or not response.json().get("candidates"):
            pytest.skip("No candidates available")
        
        candidate_id = response.json()["candidates"][0]["id"]
        
        url = f"{BASE_URL}/api/candidate-bank/{candidate_id}/download-resume"
        response = requests.get(url, params={"token": admin_token})
        
        # 404 for missing resume is OK, 401 without token would be auth working
        assert response.status_code not in [405], \
            f"download-resume endpoint not properly routed: {response.status_code}"
        print(f"✓ GET /download-resume endpoint exists and returns {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
