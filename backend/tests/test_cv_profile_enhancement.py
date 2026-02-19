"""
CV + Profile Enhancement Testing — Iteration 72
Tests for:
1. GET /api/candidate-bank?page=1&limit=5 — returns candidate list (200)
2. GET /api/candidate-bank/{id}/ats-cv — generates valid PDF with Content-Disposition (Firstname_Lastname_VHC.pdf)
3. GET /api/candidate-bank/{id}/ats-cv with invalid ID — returns 404
4. GET /api/candidate-bank/{id}/download-resume — returns 200 or 404 (no 500)
5. POST /api/cv-upload/save — saves profile with full unified schema
6. Extension capture /api/extension/capture — still validates properly (422 for empty)
7. Revenue /api/revenue/aggregate/by-company — regression test (data returns)
8. Pipeline /api/admin/pipeline — regression test (returns data with joined stage)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://revenue-verify-3.preview.emergentagent.com"

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


class TestCVProfileEnhancement:
    """Test CV Upload and Profile Enhancement features"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token before each test"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_candidate_bank_list(self):
        """GET /api/candidate-bank?page=1&limit=5 — returns candidate list successfully"""
        resp = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            params={"page": 1, "limit": 5},
            headers=self.headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "candidates" in data, "Response missing 'candidates' field"
        assert "total" in data, "Response missing 'total' field"
        assert "page" in data, "Response missing 'page' field"
        assert isinstance(data["candidates"], list), "'candidates' should be a list"
        print(f"✅ Candidate bank list: {len(data['candidates'])} candidates, total {data['total']}")

    def test_ats_cv_generation_valid_candidate(self):
        """GET /api/candidate-bank/{id}/ats-cv — generates valid PDF with proper Content-Disposition"""
        # First get a candidate ID
        list_resp = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            params={"page": 1, "limit": 1},
            headers=self.headers
        )
        assert list_resp.status_code == 200
        candidates = list_resp.json().get("candidates", [])
        
        if not candidates:
            pytest.skip("No candidates in bank to test ATS CV generation")
        
        candidate_id = candidates[0]["id"]
        candidate_name = candidates[0].get("name", "Unknown")
        
        # Test ATS CV endpoint
        resp = requests.get(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/ats-cv",
            headers=self.headers,
            stream=True
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        # Check Content-Type is PDF
        content_type = resp.headers.get("Content-Type", "")
        assert "application/pdf" in content_type, f"Expected PDF content-type, got: {content_type}"
        
        # Check Content-Disposition header contains _VHC.pdf
        content_disp = resp.headers.get("Content-Disposition", "")
        assert "_VHC.pdf" in content_disp, f"Expected filename with _VHC.pdf, got: {content_disp}"
        
        # Check Content-Length is set
        content_length = resp.headers.get("Content-Length")
        assert content_length and int(content_length) > 0, f"Expected positive Content-Length"
        
        print(f"✅ ATS CV generation: {candidate_name} -> {content_disp}, {content_length} bytes")

    def test_ats_cv_invalid_candidate_404(self):
        """GET /api/candidate-bank/{id}/ats-cv with invalid ID — returns 404"""
        invalid_id = "00000000-0000-0000-0000-000000000000"
        resp = requests.get(
            f"{BASE_URL}/api/candidate-bank/{invalid_id}/ats-cv",
            headers=self.headers
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print(f"✅ ATS CV invalid ID returns 404")

    def test_download_resume_valid_candidate(self):
        """GET /api/candidate-bank/{id}/download-resume — returns 200 or 404 (no 500)"""
        # First get a candidate ID
        list_resp = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            params={"page": 1, "limit": 5},
            headers=self.headers
        )
        assert list_resp.status_code == 200
        candidates = list_resp.json().get("candidates", [])
        
        if not candidates:
            pytest.skip("No candidates in bank to test resume download")
        
        # Find a candidate with a resume
        candidate_with_resume = None
        for c in candidates:
            if c.get("resume_url") or c.get("active_resume_id"):
                candidate_with_resume = c
                break
        
        if not candidate_with_resume:
            # Test with first candidate anyway - should return 404, not 500
            candidate_with_resume = candidates[0]
        
        candidate_id = candidate_with_resume["id"]
        candidate_name = candidate_with_resume.get("name", "Unknown")
        
        resp = requests.get(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/download-resume",
            headers=self.headers,
            allow_redirects=True
        )
        
        # Should be 200 (with resume) or 404 (no resume) - but NOT 500
        assert resp.status_code in [200, 302, 404], f"Expected 200/302/404, got {resp.status_code}: {resp.text}"
        
        if resp.status_code == 200:
            # Verify proper headers for download
            content_disp = resp.headers.get("Content-Disposition", "")
            assert "VHC" in content_disp or "attachment" in content_disp.lower(), f"Missing proper Content-Disposition: {content_disp}"
            print(f"✅ Resume download for {candidate_name}: 200 OK - {content_disp}")
        elif resp.status_code == 302:
            # R2 redirect
            print(f"✅ Resume download for {candidate_name}: 302 redirect to R2")
        else:
            print(f"✅ Resume download for {candidate_name}: 404 (no resume attached)")

    def test_cv_upload_save_unified_schema(self):
        """POST /api/cv-upload/save — saves profile with full unified schema fields"""
        test_profile = {
            "name": "TEST_CVUpload_Candidate",
            "email": "test_cvupload_schema@example.com",
            "phone": "9876543210",
            "current_company": "Test Corp",
            "current_designation": "Senior Developer",
            "total_experience_years": 5.5,
            "headline": "Full Stack Developer",
            "profile_summary": "Experienced developer with expertise in Python and React",
            "location": "Bangalore",
            "preferred_locations": ["Bangalore", "Mumbai"],
            "key_skills": ["Python", "React", "Node.js", "MongoDB"],
            "it_skills": [{"name": "Python", "version": "3.11", "experience_years": 5}],
            "work_experience": [
                {
                    "company": "Test Corp",
                    "designation": "Senior Developer",
                    "from_date": "2020-01",
                    "to_date": None,
                    "is_current": True,
                    "description": "Building scalable applications"
                }
            ],
            "education": [
                {
                    "degree": "B.Tech",
                    "institution": "IIT Delhi",
                    "year_of_passing": "2018",
                    "specialization": "Computer Science"
                }
            ],
            "certifications": [{"name": "AWS Solutions Architect"}],
            "projects": [{"title": "E-commerce Platform", "description": "Built using microservices"}],
            "languages": [{"language": "English", "proficiency": "Fluent"}],
            "online_profiles": [
                {"platform": "LinkedIn", "url": "https://linkedin.com/in/testuser"},
                {"platform": "GitHub", "url": "https://github.com/testuser"}
            ]
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/cv-upload/save",
            json={"profile": test_profile, "filename": "test_cv.pdf"},
            headers=self.headers
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data.get("success") is True, f"Expected success=True: {data}"
        assert data.get("candidate_id"), "Missing candidate_id"
        assert data.get("action") in ["created", "updated"], f"Unexpected action: {data.get('action')}"
        
        # Verify unified schema fields in response
        profile = data.get("profile", {})
        
        # Check basic info fields
        assert profile.get("name") == test_profile["name"], "Name not saved correctly"
        assert profile.get("email") == test_profile["email"].lower(), "Email not saved correctly"
        
        # Check unified schema specific fields
        assert profile.get("skills_display"), "Missing skills_display field"
        assert profile.get("experience") is not None, "Missing experience field"
        assert profile.get("education") is not None, "Missing education field"
        assert profile.get("has_resume") is True, "has_resume should be True"
        assert profile.get("visibility") is not None, "Missing visibility field"
        assert profile.get("source") == "cv_upload", f"Expected source=cv_upload, got {profile.get('source')}"
        
        # Check career preferences fields exist
        assert "current_salary" in profile, "Missing current_salary field"
        assert "notice_period" in profile, "Missing notice_period field"
        assert "preferred_locations" in profile, "Missing preferred_locations field"
        
        # Check online profiles extraction
        assert profile.get("linkedin_url"), "LinkedIn URL should be extracted"
        assert profile.get("github_url"), "GitHub URL should be extracted"
        
        print(f"✅ CV upload save: {data.get('action')} candidate {data.get('candidate_id')}")
        print(f"   Unified schema fields verified: skills_display, experience, education, visibility, etc.")

    def test_extension_capture_validation(self):
        """Extension capture /api/extension/capture — validates properly (422 for empty payload)"""
        # Test with empty payload - should return 422
        resp = requests.post(
            f"{BASE_URL}/api/extension/capture",
            json={},
            headers=self.headers
        )
        
        # Should return 422 or 400 for validation error, not 500
        assert resp.status_code in [400, 422], f"Expected 400/422, got {resp.status_code}: {resp.text}"
        print(f"✅ Extension capture validation: {resp.status_code} for empty payload")
        
        # Test with missing required fields
        resp2 = requests.post(
            f"{BASE_URL}/api/extension/capture",
            json={"name": "Test Only"},  # Missing required fields
            headers=self.headers
        )
        assert resp2.status_code in [200, 400, 422], f"Expected 200/400/422, got {resp2.status_code}: {resp2.text}"
        print(f"✅ Extension capture partial payload: {resp2.status_code}")


class TestRegressionEndpoints:
    """Regression tests for existing endpoints that must not break"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_revenue_aggregate_by_company(self):
        """GET /api/revenue/aggregate/by-company — still returns data (regression)"""
        resp = requests.get(
            f"{BASE_URL}/api/revenue/aggregate/by-company",
            params={"from_date": "2024-01-01", "to_date": "2026-12-31"},
            headers=self.headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        response_data = resp.json()
        # API returns {"data": [...], "from_date": "...", "to_date": "..."}
        assert "data" in response_data, "Expected 'data' field in response"
        data = response_data["data"]
        assert isinstance(data, list), "Expected list in 'data' field"
        print(f"✅ Revenue aggregate by company: {len(data)} companies with revenue data")
        
        if data:
            # Verify structure of first item
            first = data[0]
            assert "company_name" in first or "company_id" in first, "Missing company identifier"
            print(f"   Sample: {first.get('company_name', first.get('company_id'))} - ₹{first.get('total_revenue', 0)}")

    def test_admin_pipeline_with_joined_stage(self):
        """GET /api/admin/pipeline — returns data with joined stage (regression)"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/pipeline",
            params={"page": 1, "limit": 10},
            headers=self.headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "pipeline" in data, "Response missing 'pipeline' field"
        
        # Pipeline is structured by stage: {"applied": [...], "shortlisted": [...], "joined": [...], ...}
        pipeline = data.get("pipeline", {})
        
        # Check that joined stage exists
        assert "joined" in pipeline, "Missing 'joined' stage in pipeline"
        
        # Count total applications across all stages
        stages_found = list(pipeline.keys())
        total_apps = sum(len(apps) for apps in pipeline.values() if isinstance(apps, list))
        
        print(f"✅ Admin pipeline: {total_apps} total applications")
        print(f"   Stages found: {', '.join(stages_found)}")
        print(f"   Joined candidates: {len(pipeline.get('joined', []))}")
        
        # Verify stage counts if present
        if "stage_counts" in data:
            counts = data["stage_counts"]
            print(f"   Stage counts: applied={counts.get('applied', 0)}, joined={counts.get('joined', 0)}")
        
        # Verify total applications count
        if "total_applications" in data:
            assert data["total_applications"] >= 0, "Invalid total_applications count"
            print(f"   Total applications: {data['total_applications']}")


class TestCandidateBankSearch:
    """Test candidate bank search functionality"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_candidate_bank_search_with_filters(self):
        """GET /api/candidate-bank with search parameter"""
        resp = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            params={"page": 1, "limit": 5, "search": "python"},
            headers=self.headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "candidates" in data
        print(f"✅ Candidate bank search 'python': {len(data['candidates'])} results")

    def test_candidate_bank_pagination(self):
        """GET /api/candidate-bank pagination works correctly"""
        # Get page 1
        resp1 = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            params={"page": 1, "limit": 2},
            headers=self.headers
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        
        # Get page 2 if there are more candidates
        total = data1.get("total", 0)
        if total > 2:
            resp2 = requests.get(
                f"{BASE_URL}/api/candidate-bank",
                params={"page": 2, "limit": 2},
                headers=self.headers
            )
            assert resp2.status_code == 200
            data2 = resp2.json()
            
            # Verify different candidates on different pages
            ids1 = [c["id"] for c in data1["candidates"]]
            ids2 = [c["id"] for c in data2["candidates"]]
            assert not set(ids1).intersection(set(ids2)), "Same candidates on different pages"
            print(f"✅ Pagination working: Page 1 has {len(ids1)}, Page 2 has {len(ids2)} different candidates")
        else:
            print(f"✅ Pagination test skipped: Only {total} candidates in system")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
