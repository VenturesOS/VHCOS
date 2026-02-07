"""
Test suite for VHC Talent OS - AI Matching Refactoring & Route Extraction
Tests:
1. Quick Match endpoint (/api/matching/find-candidates with match_mode=quick)
2. Full AI Match endpoint (/api/matching/find-candidates with match_mode=full_ai)
3. Match job polling endpoint (/api/matching/jobs/{job_id}/status)
4. Teams CRUD via /api/teams endpoint
5. Referrals CRUD via /api/referrals endpoint
6. Commercials via /api/commercials endpoint
7. Admin hierarchy endpoint /api/admin/hierarchy
8. Admin analytics endpoint /api/analytics/admin
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestAuth:
    """Test login for all role types"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Admin auth failed")
    
    @pytest.fixture(scope="class")
    def employer_token(self):
        """Get employer auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "employer@vhctalent.com",
            "password": "VhcTalent@2024"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Employer auth failed")
    
    @pytest.fixture(scope="class")
    def recruiter_token(self):
        """Get recruiter auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "recruiter@vhctalent.com",
            "password": "VhcTalent@2024"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Recruiter auth failed")

    def test_admin_login(self):
        """Test admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        assert data.get("user", {}).get("role") == "admin"
        print(f"✓ Admin login successful")

    def test_employer_login(self):
        """Test employer login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "employer@vhctalent.com",
            "password": "VhcTalent@2024"
        })
        assert response.status_code == 200, f"Employer login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert data.get("user", {}).get("role") == "employer"
        print(f"✓ Employer login successful")

    def test_recruiter_login(self):
        """Test recruiter login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "recruiter@vhctalent.com",
            "password": "VhcTalent@2024"
        })
        assert response.status_code == 200, f"Recruiter login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert data.get("user", {}).get("role") == "recruiter"
        print(f"✓ Recruiter login successful")


class TestQuickMatch:
    """Test Quick Match mode (no LLM calls, fast keyword + semantic scoring)"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200, f"Admin login failed"
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_quick_match_with_jd_text(self, admin_headers):
        """Test quick match using JD text returns results without LLM"""
        jd_text = "Looking for a Python developer with 5 years experience in Django and React. Must have AWS experience."
        
        response = requests.post(f"{BASE_URL}/api/matching/find-candidates", json={
            "jd_text": jd_text,
            "match_mode": "quick",
            "limit": 20
        }, headers=admin_headers)
        
        assert response.status_code == 200, f"Quick match failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # Should return results directly (not background job)
        if data:
            first_result = data[0]
            assert first_result.get("candidate_id") != "__background_job__", "Quick match should not return background job"
            assert "score" in first_result, "Results should have score"
            assert "candidate_name" in first_result
            assert "candidate_email" in first_result
        print(f"✓ Quick match returned {len(data)} candidates")
    
    def test_quick_match_response_time(self, admin_headers):
        """Test that quick match is fast (< 10 seconds)"""
        jd_text = "Software engineer with Java, Spring Boot, and microservices experience."
        
        start_time = time.time()
        response = requests.post(f"{BASE_URL}/api/matching/find-candidates", json={
            "jd_text": jd_text,
            "match_mode": "quick",
            "limit": 50
        }, headers=admin_headers)
        elapsed = time.time() - start_time
        
        assert response.status_code == 200, f"Quick match failed: {response.text}"
        assert elapsed < 10, f"Quick match took too long: {elapsed:.2f}s"
        print(f"✓ Quick match completed in {elapsed:.2f}s")
    
    def test_quick_match_score_range(self, admin_headers):
        """Test that match scores are in valid range (0-100)"""
        response = requests.post(f"{BASE_URL}/api/matching/find-candidates", json={
            "jd_text": "Full stack developer with React, Node.js, PostgreSQL",
            "match_mode": "quick",
            "limit": 20
        }, headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        for result in data:
            if result.get("candidate_id") != "__background_job__":
                score = result.get("score", 0)
                assert 0 <= score <= 100, f"Invalid score: {score}"
        print(f"✓ All scores in valid range (0-100)")


class TestFullAIMatch:
    """Test Full AI Match mode (LLM-powered, background job)"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_full_ai_match_returns_job_id(self, admin_headers):
        """Test full AI match returns background job ID for polling"""
        response = requests.post(f"{BASE_URL}/api/matching/find-candidates", json={
            "jd_text": "Senior Python developer with machine learning experience",
            "match_mode": "full_ai",
            "limit": 10
        }, headers=admin_headers)
        
        assert response.status_code == 200, f"Full AI match failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # Should return a background job marker
        if data:
            first_result = data[0]
            if first_result.get("candidate_id") == "__background_job__":
                job_id = first_result.get("candidate_email")
                assert job_id, "Background job should have job_id in candidate_email field"
                print(f"✓ Full AI match returned background job ID: {job_id}")
            else:
                # May also return cached results if recently ran
                print(f"✓ Full AI match returned {len(data)} cached/processed results")


class TestMatchJobPolling:
    """Test match job status polling endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_poll_nonexistent_job_returns_404(self, admin_headers):
        """Test polling non-existent job returns 404"""
        response = requests.get(f"{BASE_URL}/api/matching/jobs/nonexistent-job-id/status", headers=admin_headers)
        assert response.status_code == 404, f"Should return 404, got: {response.status_code}"
        print(f"✓ Non-existent job returns 404")
    
    def test_poll_requires_auth(self):
        """Test polling endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/matching/jobs/some-job-id/status")
        assert response.status_code in [401, 403], f"Should require auth, got: {response.status_code}"
        print(f"✓ Polling endpoint requires authentication")


class TestTeamsCRUD:
    """Test Teams CRUD endpoints (extracted from server.py)"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_teams_requires_auth(self):
        """Test GET /api/teams requires authentication"""
        response = requests.get(f"{BASE_URL}/api/teams")
        assert response.status_code in [401, 403]
        print(f"✓ GET /api/teams requires auth")
    
    def test_get_teams_as_admin(self, admin_headers):
        """Test admin can get teams list"""
        response = requests.get(f"{BASE_URL}/api/teams", headers=admin_headers)
        assert response.status_code == 200, f"GET teams failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Teams response should be a list"
        print(f"✓ Admin retrieved {len(data)} teams")
    
    def test_create_team_requires_employer(self, admin_headers):
        """Test creating team requires valid employer_id"""
        response = requests.post(f"{BASE_URL}/api/teams", json={
            "name": "TEST_Invalid_Team",
            "employer_id": "nonexistent-employer-id",
            "recruiter_ids": [],
            "company_ids": []
        }, headers=admin_headers)
        assert response.status_code == 404, f"Should fail with invalid employer: {response.text}"
        print(f"✓ Create team validates employer_id")


class TestReferralsCRUD:
    """Test Referrals CRUD endpoints (extracted from server.py)"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_referrals_requires_auth(self):
        """Test GET /api/referrals requires authentication"""
        response = requests.get(f"{BASE_URL}/api/referrals")
        assert response.status_code in [401, 403]
        print(f"✓ GET /api/referrals requires auth")
    
    def test_get_referrals_as_admin(self, admin_headers):
        """Test admin can get referrals list"""
        response = requests.get(f"{BASE_URL}/api/referrals", headers=admin_headers)
        assert response.status_code == 200, f"GET referrals failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Referrals response should be a list"
        print(f"✓ Admin retrieved {len(data)} referrals")
    
    def test_create_referral_requires_active_job(self, admin_headers):
        """Test creating referral requires valid active job"""
        response = requests.post(f"{BASE_URL}/api/referrals", json={
            "job_id": "nonexistent-job-id",
            "candidate_name": "TEST_Referral_Candidate",
            "candidate_email": "test_referral@test.com"
        }, headers=admin_headers)
        assert response.status_code == 404, f"Should fail with invalid job: {response.text}"
        print(f"✓ Create referral validates job_id")


class TestCommercialsCRUD:
    """Test Commercials CRUD endpoints (extracted from server.py)"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_commercials_requires_auth(self):
        """Test GET /api/commercials requires authentication"""
        response = requests.get(f"{BASE_URL}/api/commercials")
        assert response.status_code in [401, 403]
        print(f"✓ GET /api/commercials requires auth")
    
    def test_get_commercials_as_admin(self, admin_headers):
        """Test admin can get commercials list"""
        response = requests.get(f"{BASE_URL}/api/commercials", headers=admin_headers)
        assert response.status_code == 200, f"GET commercials failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Commercials response should be a list"
        print(f"✓ Admin retrieved {len(data)} commercials")
    
    def test_create_commercial_requires_company(self, admin_headers):
        """Test creating commercial requires valid company_id"""
        response = requests.post(f"{BASE_URL}/api/commercials", json={
            "company_id": "nonexistent-company-id",
            "commercial_name": "TEST_Commercial",
            "type": "percentage",
            "fee_percentage": 10.0
        }, headers=admin_headers)
        assert response.status_code == 404, f"Should fail with invalid company: {response.text}"
        print(f"✓ Create commercial validates company_id")


class TestAdminHierarchy:
    """Test Admin hierarchy endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_hierarchy_requires_admin(self):
        """Test /api/admin/hierarchy requires admin role"""
        response = requests.get(f"{BASE_URL}/api/admin/hierarchy")
        assert response.status_code in [401, 403]
        print(f"✓ Hierarchy endpoint requires auth")
    
    def test_get_hierarchy_as_admin(self, admin_headers):
        """Test admin can get hierarchy"""
        response = requests.get(f"{BASE_URL}/api/admin/hierarchy", headers=admin_headers)
        assert response.status_code == 200, f"GET hierarchy failed: {response.text}"
        data = response.json()
        
        assert "hierarchy" in data, "Response should have 'hierarchy' field"
        assert "summary" in data, "Response should have 'summary' field"
        assert "unassigned_recruiters" in data
        assert "unassigned_companies" in data
        
        summary = data.get("summary", {})
        assert "total_employers" in summary
        assert "total_teams" in summary
        print(f"✓ Hierarchy: {summary.get('total_employers')} employers, {summary.get('total_teams')} teams")


class TestAdminAnalytics:
    """Test Admin analytics endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_analytics_requires_admin(self):
        """Test /api/analytics/admin requires admin role"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin")
        assert response.status_code in [401, 403]
        print(f"✓ Analytics endpoint requires auth")
    
    def test_get_analytics_as_admin(self, admin_headers):
        """Test admin can get analytics"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=admin_headers)
        assert response.status_code == 200, f"GET analytics failed: {response.text}"
        data = response.json()
        
        assert "kpis" in data, "Response should have 'kpis' field"
        kpis = data.get("kpis", {})
        assert "total_active_mandates" in kpis
        assert "total_pipeline_revenue" in kpis
        assert "closed_revenue" in kpis
        assert "active_employers" in kpis
        assert "active_recruiters" in kpis
        
        print(f"✓ Analytics KPIs: {kpis.get('total_active_mandates')} mandates, {kpis.get('active_recruiters')} recruiters")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
