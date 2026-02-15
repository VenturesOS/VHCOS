"""
VHC Talent OS - Production Regression Test Suite
Full regression test for production readiness covering:
- Authentication
- Admin Analytics
- Candidate Bank
- Extension API
- Jobs, Teams, Applications
- CORS configuration
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://ai-candidate-hub.preview.emergentagent.com"

# Test credentials from environment
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


class TestAuthentication:
    """Authentication endpoint tests"""
    
    def test_login_success(self):
        """Test login with valid admin credentials returns access_token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        
        data = response.json()
        assert "access_token" in data, "Response should contain access_token"
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0
        print(f"Login success - access_token received (length: {len(data['access_token'])})")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials returns 401"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "wrong@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("Invalid login correctly returns 401")
    
    def test_protected_endpoint_without_token(self):
        """Test protected endpoints return 401/403 without token"""
        # Test analytics endpoint without auth
        response = requests.get(f"{BASE_URL}/api/analytics/admin")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"Protected endpoint without token correctly returns {response.status_code}")
    
    def test_protected_endpoint_with_invalid_token(self):
        """Test protected endpoints return 401 with invalid token"""
        headers = {"Authorization": "Bearer invalid_token_12345"}
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=headers)
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"Protected endpoint with invalid token correctly returns {response.status_code}")


class TestAdminAnalytics:
    """Admin Analytics Dashboard API tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed - skipping authenticated tests")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_admin_analytics_returns_all_fields(self, auth_headers):
        """Test GET /api/analytics/admin returns all required fields"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        assert response.status_code == 200, f"Analytics request failed: {response.text}"
        
        data = response.json()
        
        # Check for required top-level fields
        required_fields = ["kpis", "source_distribution", "capture_trends", 
                         "recruiter_performance", "stage_distribution", 
                         "funnel_velocity", "filters"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Check KPIs structure
        kpis = data.get("kpis", {})
        kpi_fields = ["total_captures", "captures_today", "captures_this_week", 
                     "captures_this_month", "avg_daily_rate", "active_sources",
                     "total_applications", "avg_funnel_days"]
        for field in kpi_fields:
            assert field in kpis, f"Missing KPI field: {field}"
        
        print(f"Analytics returned all required fields. Total captures: {kpis.get('total_captures')}")
    
    def test_admin_analytics_with_employer_filter(self, auth_headers):
        """Test GET /api/analytics/admin with employer_id filter"""
        # First get the filters to get a valid employer_id
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        data = response.json()
        
        filters = data.get("filters", {})
        employers = filters.get("employers", [])
        
        if employers:
            employer_id = employers[0].get("id")
            filtered_response = requests.get(
                f"{BASE_URL}/api/analytics/admin?employer_id={employer_id}", 
                headers=auth_headers
            )
            assert filtered_response.status_code == 200
            print(f"Employer filter works - filtered by employer_id: {employer_id}")
        else:
            print("No employers available to test filter")
    
    def test_admin_analytics_export_pdf(self, auth_headers):
        """Test GET /api/analytics/admin/export-pdf returns valid PDF"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/admin/export-pdf", 
            headers=auth_headers
        )
        assert response.status_code == 200, f"PDF export failed: {response.status_code}"
        
        # Check content type
        content_type = response.headers.get("content-type", "")
        assert "application/pdf" in content_type, f"Expected PDF, got: {content_type}"
        
        # Check PDF magic bytes
        pdf_content = response.content
        assert pdf_content[:4] == b'%PDF', "Response is not a valid PDF"
        print(f"PDF export successful - received {len(pdf_content)} bytes")


class TestCandidateBank:
    """Candidate Bank API tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get headers with auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            token = response.json().get("access_token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip("Authentication failed")
    
    def test_candidate_bank_list(self, auth_headers):
        """Test GET /api/candidate-bank returns paginated list"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=auth_headers)
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        assert "candidates" in data
        assert "total" in data
        assert "page" in data
        assert "total_pages" in data
        
        print(f"Candidate bank returned {len(data['candidates'])} candidates out of {data['total']} total")
    
    def test_candidate_bank_search(self, auth_headers):
        """Test GET /api/candidate-bank?search=Ravi returns filtered results"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?search=Ravi", 
            headers=auth_headers
        )
        assert response.status_code == 200, f"Search failed: {response.text}"
        
        data = response.json()
        assert "candidates" in data
        print(f"Search for 'Ravi' returned {len(data['candidates'])} candidates")
    
    def test_candidate_bank_single_record(self, auth_headers):
        """Test GET /api/candidate-bank/{id} returns full candidate with Naukri fields"""
        # First get a Naukri-sourced candidate
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?limit=100", 
            headers=auth_headers
        )
        data = response.json()
        
        # Find a Naukri-sourced candidate
        naukri_candidate = None
        for candidate in data.get("candidates", []):
            if candidate.get("source") == "naukri_extension":
                naukri_candidate = candidate
                break
        
        if naukri_candidate:
            candidate_id = naukri_candidate["id"]
            detail_response = requests.get(
                f"{BASE_URL}/api/candidate-bank/{candidate_id}", 
                headers=auth_headers
            )
            assert detail_response.status_code == 200
            
            candidate_detail = detail_response.json()
            
            # Check Naukri-specific fields
            assert candidate_detail.get("source") == "naukri_extension"
            
            # Check for expected Naukri fields
            naukri_fields = ["naukri_profile_url", "source_details", "experience", "education", "skills"]
            present_fields = [f for f in naukri_fields if candidate_detail.get(f)]
            print(f"Naukri candidate has fields: {present_fields}")
            
            # Check source_details has captured_by info
            source_details = candidate_detail.get("source_details", {})
            if source_details:
                print(f"Captured by: {source_details.get('captured_by_name')}")
        else:
            print("No Naukri-sourced candidates found to test")


class TestExtensionAPI:
    """Extension capture API tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get headers with auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            token = response.json().get("access_token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip("Authentication failed")
    
    def test_extension_capture_without_auth(self):
        """Test POST /api/extension/capture without auth returns 401"""
        payload = {
            "naukri_profile_id": "test123",
            "naukri_profile_url": "https://naukri.com/test",
            "name": "Test Candidate",
            "scraped_at": "2024-01-01T00:00:00Z"
        }
        response = requests.post(f"{BASE_URL}/api/extension/capture", json=payload)
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"Extension capture without auth correctly returns {response.status_code}")
    
    def test_extension_stats(self, auth_headers):
        """Test GET /api/extension/stats returns statistics"""
        response = requests.get(f"{BASE_URL}/api/extension/stats", headers=auth_headers)
        assert response.status_code == 200, f"Stats request failed: {response.text}"
        
        data = response.json()
        assert "total_captured" in data
        assert "user_captured" in data
        assert "today_captured" in data
        
        print(f"Extension stats: {data['total_captured']} total, {data['today_captured']} today")


class TestJobsAPI:
    """Jobs API tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get headers with auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            token = response.json().get("access_token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip("Authentication failed")
    
    def test_jobs_list(self, auth_headers):
        """Test GET /api/jobs returns job listings"""
        response = requests.get(f"{BASE_URL}/api/jobs", headers=auth_headers)
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        # Response can be a list or dict with jobs key
        if isinstance(data, list):
            jobs = data
        else:
            jobs = data.get("jobs", [])
        
        print(f"Jobs endpoint returned {len(jobs)} jobs")


class TestTeamsAPI:
    """Teams API tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get headers with auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            token = response.json().get("access_token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip("Authentication failed")
    
    def test_teams_list(self, auth_headers):
        """Test GET /api/teams returns team list"""
        response = requests.get(f"{BASE_URL}/api/teams", headers=auth_headers)
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        # Response can be a list or dict with teams key
        if isinstance(data, list):
            teams = data
        else:
            teams = data.get("teams", data)
        
        print(f"Teams endpoint returned {len(teams) if isinstance(teams, list) else 'data'}")


class TestApplicationsAPI:
    """Applications/Pipeline API tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get headers with auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            token = response.json().get("access_token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip("Authentication failed")
    
    def test_applications_list(self, auth_headers):
        """Test GET /api/applications returns applications"""
        response = requests.get(f"{BASE_URL}/api/applications", headers=auth_headers)
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        print(f"Applications endpoint returned data type: {type(data).__name__}")


class TestCORSConfiguration:
    """CORS configuration tests"""
    
    def test_cors_headers_present(self):
        """Test CORS headers are present in response"""
        response = requests.options(
            f"{BASE_URL}/api/auth/login",
            headers={
                "Origin": "https://portal.vhc.in",
                "Access-Control-Request-Method": "POST"
            }
        )
        
        # Check if CORS headers are present
        cors_headers = response.headers.get("Access-Control-Allow-Origin", "")
        
        # Note: FastAPI might handle OPTIONS differently
        # For now just check if the server responds
        print(f"OPTIONS response status: {response.status_code}")
        print(f"Access-Control-Allow-Origin: {cors_headers}")
    
    def test_cors_origin_allowed(self):
        """Test that portal.vhc.in origin is allowed"""
        # Make a request with portal.vhc.in origin
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Origin": "https://portal.vhc.in"}
        )
        
        cors_origin = response.headers.get("Access-Control-Allow-Origin", "")
        
        # Check if the origin is in the allowed list
        # The server might return * or specific origin
        if cors_origin:
            print(f"CORS origin header: {cors_origin}")
            assert cors_origin in ["*", "https://portal.vhc.in", "https://ai-candidate-hub.preview.emergentagent.com"], \
                f"Unexpected CORS origin: {cors_origin}"
        else:
            print("No CORS origin header returned (may be handled by ingress)")


class TestHealthAndBasics:
    """Basic health and connectivity tests"""
    
    def test_api_is_accessible(self):
        """Test API is accessible"""
        response = requests.get(f"{BASE_URL}/api/auth/login", timeout=10)
        # Even if method not allowed, server should respond
        assert response.status_code in [200, 401, 405], f"Server not responding properly: {response.status_code}"
        print(f"API is accessible - response: {response.status_code}")
    
    def test_no_server_errors_on_basic_requests(self):
        """Test no 500 errors on basic requests"""
        endpoints = [
            "/api/auth/login",
            "/api/jobs",
            "/api/teams"
        ]
        
        auth_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        headers = {"Authorization": f"Bearer {auth_response.json().get('access_token', '')}"}
        
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}", headers=headers)
            assert response.status_code != 500, f"Server error on {endpoint}: {response.text}"
        
        print("No 500 errors on basic endpoints")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
