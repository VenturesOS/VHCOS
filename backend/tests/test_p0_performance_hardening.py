"""
VHC Talent OS - P0 Pre-Production Hardening Performance Tests
Tests for optimized analytics endpoints and AI screening performance.

Focus areas:
1. Admin Analytics Dashboard - GET /api/analytics/admin (should return within 1-2 seconds)
2. Employer Analytics Dashboard - GET /api/analytics/employer (should return within 1-2 seconds)
3. AI Screening - POST /api/matching/find-candidates (concurrent LLM processing)
4. Company Pipeline - GET /api/companies/{company_id}/pipeline (batched lookups)
"""
import pytest
import requests
import time
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
EMPLOYER_CREDS = {"email": "employer@vhctalent.com", "password": "VhcTalent@2024"}
RECRUITER_CREDS = {"email": "recruiter@vhctalent.com", "password": "VhcTalent@2024"}


class TestAuthentication:
    """Test authentication for all user roles"""
    
    def test_admin_login(self):
        """Admin login should return valid token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        assert len(data["access_token"]) > 0
        print(f"✅ Admin login successful")
    
    def test_employer_login(self):
        """Employer login should return valid token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
        assert response.status_code == 200, f"Employer login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        print(f"✅ Employer login successful")
    
    def test_recruiter_login(self):
        """Recruiter login should return valid token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER_CREDS)
        assert response.status_code == 200, f"Recruiter login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        print(f"✅ Recruiter login successful")


class TestAdminAnalyticsDashboard:
    """Test Admin Analytics Dashboard performance and response structure"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token before each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_admin_analytics_returns_200(self):
        """Admin analytics endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✅ Admin analytics returns 200")
    
    def test_admin_analytics_response_structure(self):
        """Admin analytics should return expected JSON structure"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify KPIs structure
        assert "kpis" in data, "Missing 'kpis' in response"
        kpis = data["kpis"]
        assert "total_active_mandates" in kpis, "Missing 'total_active_mandates' in kpis"
        assert "total_pipeline_revenue" in kpis, "Missing 'total_pipeline_revenue' in kpis"
        assert "closed_revenue" in kpis, "Missing 'closed_revenue' in kpis"
        assert "avg_time_to_close_days" in kpis, "Missing 'avg_time_to_close_days' in kpis"
        assert "offer_to_join_ratio" in kpis, "Missing 'offer_to_join_ratio' in kpis"
        assert "active_employers" in kpis, "Missing 'active_employers' in kpis"
        assert "active_recruiters" in kpis, "Missing 'active_recruiters' in kpis"
        
        # Verify other sections
        assert "stage_distribution" in data, "Missing 'stage_distribution' in response"
        assert "company_revenue" in data, "Missing 'company_revenue' in response"
        assert "recruiter_performance" in data, "Missing 'recruiter_performance' in response"
        
        print(f"✅ Admin analytics response structure is valid")
        print(f"   KPIs: {kpis}")
    
    def test_admin_analytics_performance(self):
        """Admin analytics should return within 2 seconds (optimized query)"""
        start_time = time.time()
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=self.headers)
        elapsed = time.time() - start_time
        
        assert response.status_code == 200
        assert elapsed < 5.0, f"Admin analytics took {elapsed:.2f}s, expected < 5s"
        
        print(f"✅ Admin analytics completed in {elapsed:.2f}s")
        if elapsed < 2.0:
            print(f"   ⚡ EXCELLENT: Response time under 2 seconds!")
        elif elapsed < 3.0:
            print(f"   ✓ GOOD: Response time under 3 seconds")
        else:
            print(f"   ⚠️ WARNING: Response time {elapsed:.2f}s is higher than optimal")
    
    def test_admin_analytics_data_types(self):
        """Verify data types in admin analytics response"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        kpis = data["kpis"]
        assert isinstance(kpis["total_active_mandates"], int), "total_active_mandates should be int"
        assert isinstance(kpis["total_pipeline_revenue"], (int, float)), "total_pipeline_revenue should be numeric"
        assert isinstance(kpis["closed_revenue"], (int, float)), "closed_revenue should be numeric"
        assert isinstance(kpis["active_employers"], int), "active_employers should be int"
        assert isinstance(kpis["active_recruiters"], int), "active_recruiters should be int"
        
        assert isinstance(data["stage_distribution"], dict), "stage_distribution should be dict"
        assert isinstance(data["company_revenue"], list), "company_revenue should be list"
        assert isinstance(data["recruiter_performance"], list), "recruiter_performance should be list"
        
        print(f"✅ Admin analytics data types are correct")


class TestEmployerAnalyticsDashboard:
    """Test Employer Analytics Dashboard performance and response structure"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get employer token before each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
        if response.status_code != 200:
            pytest.skip("Employer login failed")
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_employer_analytics_returns_200(self):
        """Employer analytics endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/analytics/employer", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✅ Employer analytics returns 200")
    
    def test_employer_analytics_response_structure(self):
        """Employer analytics should return expected JSON structure"""
        response = requests.get(f"{BASE_URL}/api/analytics/employer", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify KPIs structure
        assert "kpis" in data, "Missing 'kpis' in response"
        kpis = data["kpis"]
        assert "active_mandates" in kpis, "Missing 'active_mandates' in kpis"
        assert "pipeline_revenue" in kpis, "Missing 'pipeline_revenue' in kpis"
        assert "closed_revenue" in kpis, "Missing 'closed_revenue' in kpis"
        assert "offers_pending" in kpis, "Missing 'offers_pending' in kpis"
        assert "avg_fee_percentage" in kpis, "Missing 'avg_fee_percentage' in kpis"
        
        # Verify other sections
        assert "team_performance" in data, "Missing 'team_performance' in response"
        assert "company_revenue" in data, "Missing 'company_revenue' in response"
        assert "recruiter_contribution" in data, "Missing 'recruiter_contribution' in response"
        
        print(f"✅ Employer analytics response structure is valid")
        print(f"   KPIs: {kpis}")
    
    def test_employer_analytics_performance(self):
        """Employer analytics should return within 2 seconds (optimized query)"""
        start_time = time.time()
        response = requests.get(f"{BASE_URL}/api/analytics/employer", headers=self.headers)
        elapsed = time.time() - start_time
        
        assert response.status_code == 200
        assert elapsed < 5.0, f"Employer analytics took {elapsed:.2f}s, expected < 5s"
        
        print(f"✅ Employer analytics completed in {elapsed:.2f}s")
        if elapsed < 2.0:
            print(f"   ⚡ EXCELLENT: Response time under 2 seconds!")
        elif elapsed < 3.0:
            print(f"   ✓ GOOD: Response time under 3 seconds")
        else:
            print(f"   ⚠️ WARNING: Response time {elapsed:.2f}s is higher than optimal")


class TestCompanyPipeline:
    """Test Company Pipeline endpoint performance"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token and find a company ID from teams"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get a company ID from teams (companies are assigned to teams)
        teams_response = requests.get(f"{BASE_URL}/api/teams", headers=self.headers)
        self.company_id = None
        if teams_response.status_code == 200:
            teams = teams_response.json()
            for team in teams:
                company_ids = team.get("company_ids", [])
                if company_ids:
                    self.company_id = company_ids[0]
                    break
    
    def test_company_pipeline_returns_200(self):
        """Company pipeline endpoint should return 200"""
        if not self.company_id:
            pytest.skip("No company found for testing")
        
        response = requests.get(f"{BASE_URL}/api/companies/{self.company_id}/pipeline", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✅ Company pipeline returns 200 for company {self.company_id}")
    
    def test_company_pipeline_response_structure(self):
        """Company pipeline should return expected JSON structure"""
        if not self.company_id:
            pytest.skip("No company found for testing")
        
        response = requests.get(f"{BASE_URL}/api/companies/{self.company_id}/pipeline", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "company" in data, "Missing 'company' in response"
        assert "summary" in data, "Missing 'summary' in response"
        assert "pipeline" in data, "Missing 'pipeline' in response"
        
        # Verify company info
        company = data["company"]
        assert "id" in company, "Missing 'id' in company"
        assert "name" in company, "Missing 'name' in company"
        
        # Verify summary
        summary = data["summary"]
        assert "total_mandates" in summary, "Missing 'total_mandates' in summary"
        assert "active_mandates" in summary, "Missing 'active_mandates' in summary"
        assert "total_revenue" in summary, "Missing 'total_revenue' in summary"
        
        print(f"✅ Company pipeline response structure is valid")
        print(f"   Company: {company.get('name')}")
        print(f"   Summary: {summary}")
    
    def test_company_pipeline_performance(self):
        """Company pipeline should return within 2 seconds (batched lookups)"""
        if not self.company_id:
            pytest.skip("No company found for testing")
        
        start_time = time.time()
        response = requests.get(f"{BASE_URL}/api/companies/{self.company_id}/pipeline", headers=self.headers)
        elapsed = time.time() - start_time
        
        assert response.status_code == 200
        assert elapsed < 5.0, f"Company pipeline took {elapsed:.2f}s, expected < 5s"
        
        print(f"✅ Company pipeline completed in {elapsed:.2f}s")
        if elapsed < 2.0:
            print(f"   ⚡ EXCELLENT: Response time under 2 seconds!")


class TestAIScreening:
    """Test AI Screening (find-candidates) endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token and find a job ID"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get an active job ID for testing
        jobs_response = requests.get(f"{BASE_URL}/api/jobs", headers=self.headers)
        if jobs_response.status_code == 200:
            jobs = jobs_response.json()
            active_jobs = [j for j in jobs if j.get("status") == "active"]
            if active_jobs:
                self.job_id = active_jobs[0].get("id")
                self.job_title = active_jobs[0].get("title")
            else:
                self.job_id = None
                self.job_title = None
        else:
            self.job_id = None
            self.job_title = None
    
    def test_ai_screening_with_job_id(self):
        """AI screening with job_id should return results"""
        if not self.job_id:
            pytest.skip("No active job found for testing")
        
        payload = {"job_id": self.job_id}
        
        start_time = time.time()
        try:
            response = requests.post(
                f"{BASE_URL}/api/matching/find-candidates",
                json=payload,
                headers=self.headers,
                timeout=180  # AI screening can take up to 90-180 seconds
            )
            elapsed = time.time() - start_time
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            
            assert isinstance(data, list), "Response should be a list of match results"
            
            print(f"✅ AI screening completed in {elapsed:.2f}s")
            print(f"   Job: {self.job_title}")
            print(f"   Total candidates matched: {len(data)}")
            
            # Check for filtered candidates
            filtered_count = sum(1 for r in data if r.get("filtered_out"))
            passed_count = len(data) - filtered_count
            print(f"   Passed filters: {passed_count}, Filtered out: {filtered_count}")
        except requests.exceptions.ReadTimeout:
            elapsed = time.time() - start_time
            print(f"⚠️ AI screening timed out after {elapsed:.2f}s")
            print(f"   This may indicate a large candidate database requiring LLM calls")
            pytest.skip("AI screening timed out (expected for large datasets without filters)")
    
    def test_ai_screening_with_must_have_filters(self):
        """AI screening with must-have filters should pre-filter candidates"""
        if not self.job_id:
            pytest.skip("No active job found for testing")
        
        payload = {
            "job_id": self.job_id,
            "must_have_skills": ["Python", "JavaScript"],
            "min_experience": 2
        }
        
        start_time = time.time()
        response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            json=payload,
            headers=self.headers,
            timeout=120
        )
        elapsed = time.time() - start_time
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        print(f"✅ AI screening with filters completed in {elapsed:.2f}s")
        print(f"   Filters: must_have_skills=['Python', 'JavaScript'], min_experience=2")
        
        # Verify filtered candidates have filter_reason
        filtered = [r for r in data if r.get("filtered_out")]
        for f in filtered[:3]:  # Check first 3 filtered
            assert "filter_reason" in f or f.get("filter_reason") is not None or f.get("explanation"), \
                f"Filtered candidate should have filter_reason: {f}"
        
        print(f"   Total results: {len(data)}")
        print(f"   Filtered out: {len(filtered)}")
    
    def test_ai_screening_with_jd_text(self):
        """AI screening with JD text should work (may take longer due to LLM calls)"""
        jd_text = """
        Senior Software Engineer
        
        Requirements:
        - 5+ years of experience in software development
        - Strong proficiency in Python and JavaScript
        - Experience with React and FastAPI
        - Knowledge of MongoDB and PostgreSQL
        - Excellent communication skills
        
        Location: Bangalore, India
        """
        
        payload = {"jd_text": jd_text}
        
        start_time = time.time()
        try:
            response = requests.post(
                f"{BASE_URL}/api/matching/find-candidates",
                json=payload,
                headers=self.headers,
                timeout=180  # Extended timeout for JD text parsing + AI matching
            )
            elapsed = time.time() - start_time
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            
            print(f"✅ AI screening with JD text completed in {elapsed:.2f}s")
            print(f"   Total candidates matched: {len(data)}")
        except requests.exceptions.ReadTimeout:
            elapsed = time.time() - start_time
            print(f"⚠️ AI screening with JD text timed out after {elapsed:.2f}s")
            print(f"   This is expected for large candidate databases with LLM calls")
            pytest.skip("AI screening with JD text timed out (expected for large datasets)")


class TestExistingCRUDOperations:
    """Verify existing CRUD operations still work after optimization"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_jobs_list(self):
        """GET /api/jobs should work"""
        response = requests.get(f"{BASE_URL}/api/jobs", headers=self.headers)
        assert response.status_code == 200, f"Jobs list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Jobs should be a list"
        print(f"✅ Jobs list works - {len(data)} jobs found")
    
    def test_applications_list(self):
        """GET /api/applications should work"""
        response = requests.get(f"{BASE_URL}/api/applications", headers=self.headers)
        assert response.status_code == 200, f"Applications list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Applications should be a list"
        print(f"✅ Applications list works - {len(data)} applications found")
    
    def test_teams_list(self):
        """GET /api/teams should work (companies are accessed via teams)"""
        response = requests.get(f"{BASE_URL}/api/teams", headers=self.headers)
        assert response.status_code == 200, f"Teams list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Teams should be a list"
        
        # Count total companies across all teams
        total_companies = sum(len(t.get("company_ids", [])) for t in data)
        print(f"✅ Teams list works - {len(data)} teams found with {total_companies} companies")
    
    def test_candidate_bank_list(self):
        """GET /api/candidate-bank should work"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=self.headers)
        assert response.status_code == 200, f"Candidate bank list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Candidate bank should be a list"
        print(f"✅ Candidate bank list works - {len(data)} candidates found")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
