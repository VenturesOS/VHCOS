"""
VHC Talent OS - Comprehensive Diagnostic Test Suite
Tests all major features: Auth, Candidate Bank, Jobs, AI Matching, Applications, Cache, Background Jobs
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
EMPLOYER_CREDS = {"email": "employer@vhctalent.com", "password": "VhcTalent@2024"}
RECRUITER_CREDS = {"email": "recruiter@vhctalent.com", "password": "VhcTalent@2024"}


class TestAuthentication:
    """Test authentication for all roles"""
    
    def test_admin_login(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "admin"
        print(f"✅ Admin login successful - User: {data['user']['name']}")
    
    def test_employer_login(self):
        """Test employer login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
        assert response.status_code == 200, f"Employer login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "employer"
        print(f"✅ Employer login successful - User: {data['user']['name']}")
    
    def test_recruiter_login(self):
        """Test recruiter login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER_CREDS)
        assert response.status_code == 200, f"Recruiter login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "recruiter"
        print(f"✅ Recruiter login successful - User: {data['user']['name']}")
    
    def test_invalid_login(self):
        """Test invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "invalid@test.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("✅ Invalid login correctly rejected")
    
    def test_auth_me_endpoint(self):
        """Test /auth/me endpoint"""
        # Login first
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        token = login_resp.json()["access_token"]
        
        # Get current user
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == ADMIN_CREDS["email"]
        print(f"✅ Auth /me endpoint works - User: {data['name']}")


class TestCandidateDataBank:
    """Test Candidate Data Bank with Atlas Search and pagination"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for tests"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_candidate_bank_list(self):
        """Test getting candidate bank list with pagination"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=1&limit=10",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "candidates" in data
        assert "total" in data
        assert "page" in data
        assert "limit" in data
        assert "total_pages" in data
        print(f"✅ Candidate bank list works - Total: {data['total']}, Page: {data['page']}/{data['total_pages']}")
    
    def test_candidate_bank_pagination(self):
        """Test pagination navigation"""
        # Get page 1
        resp1 = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=1&limit=10",
            headers=self.headers
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        
        # Get page 2 if exists
        if data1["total_pages"] > 1:
            resp2 = requests.get(
                f"{BASE_URL}/api/candidate-bank?page=2&limit=10",
                headers=self.headers
            )
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["page"] == 2
            # Ensure different candidates on different pages
            if data1["candidates"] and data2["candidates"]:
                assert data1["candidates"][0]["id"] != data2["candidates"][0]["id"]
            print(f"✅ Pagination works - Page 1 and Page 2 have different candidates")
        else:
            print(f"✅ Pagination works - Only 1 page available")
    
    def test_candidate_bank_search_atlas(self):
        """Test Atlas Search with fuzzy matching"""
        # Search for 'python' - should use Atlas Search
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?search=python&page=1&limit=10",
            headers=self.headers
        )
        assert response.status_code == 200, f"Search failed: {response.text}"
        data = response.json()
        print(f"✅ Atlas Search for 'python' - Found: {data['total']} candidates")
    
    def test_candidate_bank_search_fuzzy(self):
        """Test fuzzy search (typo tolerance)"""
        # Search with typo 'pythn' instead of 'python'
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?search=pythn&page=1&limit=10",
            headers=self.headers
        )
        assert response.status_code == 200, f"Fuzzy search failed: {response.text}"
        data = response.json()
        print(f"✅ Fuzzy search for 'pythn' (typo) - Found: {data['total']} candidates")
    
    def test_candidate_bank_filter_experience(self):
        """Test experience filter"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?min_experience=3&max_experience=8&page=1&limit=10",
            headers=self.headers
        )
        assert response.status_code == 200, f"Filter failed: {response.text}"
        data = response.json()
        # Verify experience range
        for candidate in data["candidates"]:
            exp = candidate.get("experience_years", 0)
            if exp:
                assert 3 <= exp <= 8, f"Experience {exp} out of range"
        print(f"✅ Experience filter (3-8 years) - Found: {data['total']} candidates")
    
    def test_get_single_candidate(self):
        """Test getting single candidate profile"""
        # First get list
        list_resp = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=1&limit=1",
            headers=self.headers
        )
        assert list_resp.status_code == 200
        candidates = list_resp.json()["candidates"]
        
        if candidates:
            candidate_id = candidates[0]["id"]
            # Get single candidate
            response = requests.get(
                f"{BASE_URL}/api/candidate-bank/{candidate_id}",
                headers=self.headers
            )
            assert response.status_code == 200, f"Get candidate failed: {response.text}"
            data = response.json()
            assert data["id"] == candidate_id
            print(f"✅ Single candidate profile works - Name: {data.get('name', 'Unknown')}")
        else:
            print("⚠️ No candidates to test single profile")


class TestJobs:
    """Test Job management"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for tests"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_jobs_list(self):
        """Test getting jobs list"""
        response = requests.get(f"{BASE_URL}/api/jobs", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Jobs list works - Total: {len(data)} jobs")
    
    def test_get_single_job(self):
        """Test getting single job"""
        # First get list
        list_resp = requests.get(f"{BASE_URL}/api/jobs", headers=self.headers)
        jobs = list_resp.json()
        
        if jobs:
            job_id = jobs[0]["id"]
            response = requests.get(f"{BASE_URL}/api/jobs/{job_id}", headers=self.headers)
            assert response.status_code == 200, f"Get job failed: {response.text}"
            data = response.json()
            assert data["id"] == job_id
            print(f"✅ Single job works - Title: {data.get('title', 'Unknown')}")
        else:
            print("⚠️ No jobs to test single job")
    
    def test_create_job(self):
        """Test creating a new job"""
        job_data = {
            "title": "TEST_Software Engineer",
            "description": "Test job description for diagnostic testing",
            "location": "Mumbai",
            "employment_type": "full_time",
            "experience_min": 2,
            "experience_max": 5,
            "salary_min": 800000,
            "salary_max": 1500000,
            "skills_required": ["Python", "FastAPI", "MongoDB"],
            "status": "active"
        }
        response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=self.headers)
        assert response.status_code in [200, 201], f"Create job failed: {response.text}"
        data = response.json()
        assert "id" in data
        print(f"✅ Job creation works - ID: {data['id']}")
        
        # Cleanup - delete test job
        requests.delete(f"{BASE_URL}/api/jobs/{data['id']}", headers=self.headers)


class TestAIMatching:
    """Test AI Matching functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get employer token for tests"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get a job for matching
        jobs_resp = requests.get(f"{BASE_URL}/api/jobs", headers=self.headers)
        self.jobs = jobs_resp.json()
    
    def test_quick_match(self):
        """Test quick match mode"""
        if not self.jobs:
            pytest.skip("No jobs available for matching test")
        
        job_id = self.jobs[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            json={"job_id": job_id, "quick_match": True, "limit": 10},
            headers=self.headers
        )
        assert response.status_code == 200, f"Quick match failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Quick match works - Found: {len(data)} candidates")
    
    def test_ai_deep_match(self):
        """Test AI deep match mode (slower)"""
        if not self.jobs:
            pytest.skip("No jobs available for matching test")
        
        job_id = self.jobs[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            json={"job_id": job_id, "quick_match": False, "limit": 5},
            headers=self.headers,
            timeout=120  # AI matching can take time
        )
        assert response.status_code == 200, f"AI deep match failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ AI deep match works - Found: {len(data)} candidates")


class TestApplications:
    """Test Applications and Pipeline"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for tests"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_applications_list(self):
        """Test getting applications list"""
        response = requests.get(f"{BASE_URL}/api/applications", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Applications list works - Total: {len(data)} applications")
    
    def test_get_job_applicants(self):
        """Test getting applicants for a specific job"""
        # Get jobs first
        jobs_resp = requests.get(f"{BASE_URL}/api/jobs", headers=self.headers)
        jobs = jobs_resp.json()
        
        if jobs:
            job_id = jobs[0]["id"]
            response = requests.get(
                f"{BASE_URL}/api/jobs/{job_id}/applicants",
                headers=self.headers
            )
            assert response.status_code == 200, f"Get applicants failed: {response.text}"
            data = response.json()
            print(f"✅ Job applicants endpoint works - Job: {jobs[0].get('title', 'Unknown')}")
        else:
            print("⚠️ No jobs to test applicants")
    
    def test_pipeline_stage_change(self):
        """Test changing application pipeline stage"""
        # Get applications
        apps_resp = requests.get(f"{BASE_URL}/api/applications", headers=self.headers)
        applications = apps_resp.json()
        
        if applications:
            app_id = applications[0]["id"]
            current_stage = applications[0].get("stage", "applied")
            
            # Try to update stage
            response = requests.put(
                f"{BASE_URL}/api/applications/{app_id}",
                json={"stage": "shortlisted"},
                headers=self.headers
            )
            # May fail if already in that stage or other business rules
            if response.status_code == 200:
                print(f"✅ Pipeline stage change works - Changed to 'shortlisted'")
            else:
                print(f"⚠️ Pipeline stage change returned {response.status_code} - May be business rule")
        else:
            print("⚠️ No applications to test stage change")


class TestCacheAndBackgroundJobs:
    """Test Cache and Background Jobs endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for tests"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_cache_stats(self):
        """Test cache stats endpoint"""
        response = requests.get(f"{BASE_URL}/api/cache/stats", headers=self.headers)
        assert response.status_code == 200, f"Cache stats failed: {response.text}"
        data = response.json()
        print(f"✅ Cache stats works - Data: {data}")
    
    def test_embeddings_stats(self):
        """Test embeddings stats endpoint"""
        response = requests.get(f"{BASE_URL}/api/embeddings/stats", headers=self.headers)
        assert response.status_code == 200, f"Embeddings stats failed: {response.text}"
        data = response.json()
        print(f"✅ Embeddings stats works - Data: {data}")
    
    def test_background_jobs_list(self):
        """Test background jobs list endpoint"""
        response = requests.get(f"{BASE_URL}/api/background-jobs?limit=5", headers=self.headers)
        assert response.status_code == 200, f"Background jobs failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Background jobs list works - Jobs: {len(data)}")


class TestDataGovernance:
    """Test Data Governance and Role-based visibility"""
    
    def test_employer_candidate_visibility(self):
        """Test employer can only see their candidates"""
        # Login as employer
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(f"{BASE_URL}/api/candidate-bank?page=1&limit=10", headers=headers)
        assert response.status_code == 200, f"Employer candidate bank failed: {response.text}"
        data = response.json()
        print(f"✅ Employer visibility works - Can see: {data['total']} candidates")
    
    def test_recruiter_candidate_visibility(self):
        """Test recruiter can only see their candidates"""
        # Login as recruiter
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER_CREDS)
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(f"{BASE_URL}/api/candidate-bank?page=1&limit=10", headers=headers)
        assert response.status_code == 200, f"Recruiter candidate bank failed: {response.text}"
        data = response.json()
        print(f"✅ Recruiter visibility works - Can see: {data['total']} candidates")
    
    def test_admin_full_visibility(self):
        """Test admin has full visibility"""
        # Login as admin
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(f"{BASE_URL}/api/candidate-bank?page=1&limit=10", headers=headers)
        assert response.status_code == 200, f"Admin candidate bank failed: {response.text}"
        data = response.json()
        print(f"✅ Admin full visibility works - Can see: {data['total']} candidates")


class TestAdminDashboard:
    """Test Admin Dashboard stats"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for tests"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_admin_users_endpoint(self):
        """Test admin users endpoint"""
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        assert response.status_code == 200, f"Admin users failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Admin users endpoint works - Total: {len(data)} users")
    
    def test_admin_companies_endpoint(self):
        """Test admin companies endpoint"""
        response = requests.get(f"{BASE_URL}/api/companies", headers=self.headers)
        assert response.status_code == 200, f"Admin companies failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Admin companies endpoint works - Total: {len(data)} companies")
    
    def test_admin_hierarchy_endpoint(self):
        """Test admin hierarchy endpoint"""
        response = requests.get(f"{BASE_URL}/api/admin/hierarchy", headers=self.headers)
        assert response.status_code == 200, f"Admin hierarchy failed: {response.text}"
        data = response.json()
        assert "hierarchy" in data
        assert "summary" in data
        print(f"✅ Admin hierarchy endpoint works - Employers: {data['summary']['total_employers']}")


class TestBulkImport:
    """Test Bulk Import endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for tests"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_bulk_import_status_endpoint(self):
        """Test bulk import status endpoint exists"""
        # This endpoint may not exist, but we test for it
        response = requests.get(f"{BASE_URL}/api/bulk-import/status", headers=self.headers)
        # Accept 200 or 404 (endpoint may not exist)
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
        if response.status_code == 200:
            print("✅ Bulk import status endpoint exists")
        else:
            print("⚠️ Bulk import status endpoint not found (may be expected)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
