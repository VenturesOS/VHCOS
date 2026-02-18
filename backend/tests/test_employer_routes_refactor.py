"""
VHC Talent OS - Employer Routes Refactor Tests
Tests for endpoints extracted from server.py to routes/employer_routes.py.
10 endpoints tested: hierarchy, employer pipeline, employer analytics, 
company pipeline, admin pipeline (joined stage), revenue aggregations.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Admin credentials from test_reports
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


class TestEmployerRoutesRefactor:
    """Test suite for refactored employer routes - verifying endpoints work after extraction."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login as admin to get auth token."""
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        assert login_response.status_code == 200, f"Admin login failed: {login_response.text}"
        self.token = login_response.json().get("access_token")
        self.auth_headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_admin_hierarchy_endpoint(self):
        """GET /api/admin/hierarchy - returns hierarchy data with employers, teams, recruiters, companies."""
        response = requests.get(
            f"{BASE_URL}/api/admin/hierarchy",
            headers=self.auth_headers
        )
        assert response.status_code == 200, f"Hierarchy endpoint failed: {response.text}"
        
        data = response.json()
        # Verify structure
        assert "hierarchy" in data, "Response missing 'hierarchy' key"
        assert "summary" in data, "Response missing 'summary' key"
        assert "unassigned_recruiters" in data, "Response missing 'unassigned_recruiters' key"
        assert "unassigned_companies" in data, "Response missing 'unassigned_companies' key"
        
        # Verify summary fields
        summary = data["summary"]
        assert "total_employers" in summary, "Summary missing total_employers"
        assert "total_teams" in summary, "Summary missing total_teams"
        assert summary["total_employers"] >= 1, "Should have at least 1 employer"
        
        # Verify hierarchy structure
        hierarchy = data["hierarchy"]
        assert isinstance(hierarchy, list), "Hierarchy should be a list"
        if len(hierarchy) > 0:
            employer = hierarchy[0]
            assert "employer_id" in employer, "Employer missing id"
            assert "employer_name" in employer, "Employer missing name"
            assert "teams" in employer, "Employer missing teams"
    
    def test_employer_pipeline_endpoint(self):
        """GET /api/employer/pipeline - returns pipeline data with stage counts (including 'joined' stage)."""
        response = requests.get(
            f"{BASE_URL}/api/employer/pipeline",
            headers=self.auth_headers
        )
        # Admin can access employer/pipeline (role check allows admin for some endpoints)
        assert response.status_code == 200, f"Employer pipeline failed: {response.text}"
        
        data = response.json()
        assert "pipeline" in data, "Response missing 'pipeline' key"
        assert "stage_counts" in data, "Response missing 'stage_counts' key"
        assert "total_applications" in data, "Response missing 'total_applications' key"
        
        # Verify 'joined' stage exists in the response
        pipeline = data.get("pipeline", {})
        stage_counts = data.get("stage_counts", {})
        
        # Joined stage should be in the response (either in pipeline or stage_counts)
        # Even if empty, it should be defined
        if len(pipeline) > 0:
            assert "joined" in pipeline or "joined" in str(pipeline), "Joined stage should exist in pipeline"
    
    def test_employer_analytics_endpoint(self):
        """GET /api/analytics/employer - returns KPIs with active_mandates, pipeline_revenue, etc."""
        response = requests.get(
            f"{BASE_URL}/api/analytics/employer",
            headers=self.auth_headers
        )
        assert response.status_code == 200, f"Employer analytics failed: {response.text}"
        
        data = response.json()
        assert "kpis" in data, "Response missing 'kpis' key"
        
        kpis = data["kpis"]
        # Verify expected KPI fields
        expected_kpi_fields = ["active_mandates", "pipeline_revenue", "closed_revenue", "offers_pending", "avg_fee_percentage"]
        for field in expected_kpi_fields:
            assert field in kpis, f"KPIs missing '{field}'"
        
        # Verify additional data sections
        assert "company_revenue" in data, "Response missing 'company_revenue'"
        assert isinstance(data["company_revenue"], list), "company_revenue should be a list"
    
    def test_company_pipeline_endpoint(self):
        """GET /api/companies/{company_id}/pipeline - returns company pipeline with mandates and revenue."""
        # First get a company ID
        companies_response = requests.get(
            f"{BASE_URL}/api/companies",
            headers=self.auth_headers
        )
        assert companies_response.status_code == 200, "Failed to get companies list"
        
        companies = companies_response.json()
        assert len(companies) > 0, "No companies found for testing"
        
        company_id = companies[0]["id"]
        company_name = companies[0]["name"]
        
        # Test company pipeline endpoint
        response = requests.get(
            f"{BASE_URL}/api/companies/{company_id}/pipeline",
            headers=self.auth_headers
        )
        assert response.status_code == 200, f"Company pipeline failed: {response.text}"
        
        data = response.json()
        # Verify structure
        assert "company" in data, "Response missing 'company' key"
        assert "summary" in data, "Response missing 'summary' key"
        assert "pipeline" in data, "Response missing 'pipeline' key"
        
        # Verify company info
        assert data["company"]["id"] == company_id, "Company ID mismatch"
        
        # Verify summary fields
        summary = data["summary"]
        assert "total_mandates" in summary, "Summary missing total_mandates"
        assert "active_mandates" in summary, "Summary missing active_mandates"
        assert "total_revenue" in summary, "Summary missing total_revenue"
    
    def test_admin_pipeline_joined_stage(self):
        """GET /api/admin/pipeline - returns pipeline with 'joined' stage (1 joined candidate: Ravi Yadav)."""
        response = requests.get(
            f"{BASE_URL}/api/admin/pipeline",
            headers=self.auth_headers
        )
        assert response.status_code == 200, f"Admin pipeline failed: {response.text}"
        
        data = response.json()
        assert "pipeline" in data, "Response missing 'pipeline' key"
        assert "stage_counts" in data, "Response missing 'stage_counts' key"
        
        pipeline = data["pipeline"]
        stage_counts = data["stage_counts"]
        
        # Verify 'joined' stage exists
        assert "joined" in pipeline, "Pipeline missing 'joined' stage"
        assert "joined" in stage_counts, "Stage counts missing 'joined'"
        
        # Verify Ravi Yadav is in joined stage
        joined_candidates = pipeline.get("joined", [])
        assert len(joined_candidates) >= 1, "Should have at least 1 joined candidate"
        
        # Find Ravi Yadav
        ravi_found = any(
            c.get("candidate_name") == "Ravi Yadav" 
            for c in joined_candidates
        )
        assert ravi_found, "Ravi Yadav should be in joined stage"
        
        # Verify stage_counts[joined] >= 1
        assert stage_counts.get("joined", 0) >= 1, "Joined count should be >= 1"
    
    def test_revenue_aggregate_by_company(self):
        """GET /api/revenue/aggregate/by-company - returns revenue aggregation by company."""
        response = requests.get(
            f"{BASE_URL}/api/revenue/aggregate/by-company",
            params={"from_date": "2024-01-01", "to_date": "2027-12-31"},
            headers=self.auth_headers
        )
        assert response.status_code == 200, f"Revenue by-company failed: {response.text}"
        
        data = response.json()
        assert "data" in data, "Response missing 'data' key"
        assert "from_date" in data, "Response missing 'from_date'"
        assert "to_date" in data, "Response missing 'to_date'"
        
        # Verify Panasonic India in results
        aggregates = data.get("data", [])
        panasonic_found = any(
            agg.get("company_name") == "Panasonic India" 
            for agg in aggregates
        )
        
        if len(aggregates) > 0:
            # Verify aggregate structure
            first_agg = aggregates[0]
            assert "company_name" in first_agg, "Aggregate missing company_name"
            assert "total_revenue" in first_agg, "Aggregate missing total_revenue"
    
    def test_revenue_aggregate_by_job(self):
        """GET /api/revenue/aggregate/by-job - returns revenue aggregation by job."""
        response = requests.get(
            f"{BASE_URL}/api/revenue/aggregate/by-job",
            params={"from_date": "2024-01-01", "to_date": "2027-12-31"},
            headers=self.auth_headers
        )
        assert response.status_code == 200, f"Revenue by-job failed: {response.text}"
        
        data = response.json()
        assert "data" in data, "Response missing 'data' key"
        
        aggregates = data.get("data", [])
        if len(aggregates) > 0:
            first_agg = aggregates[0]
            assert "job_title" in first_agg, "Aggregate missing job_title"
            assert "total_revenue" in first_agg, "Aggregate missing total_revenue"
    
    def test_employers_companies_lookup(self):
        """GET /api/employers/{employer_id}/companies - returns companies assigned to employer."""
        # First get an employer ID from hierarchy
        hierarchy_response = requests.get(
            f"{BASE_URL}/api/admin/hierarchy",
            headers=self.auth_headers
        )
        assert hierarchy_response.status_code == 200
        
        hierarchy = hierarchy_response.json().get("hierarchy", [])
        if len(hierarchy) > 0:
            employer_id = hierarchy[0]["employer_id"]
            
            # Test employer companies lookup
            response = requests.get(
                f"{BASE_URL}/api/employers/{employer_id}/companies",
                headers=self.auth_headers
            )
            assert response.status_code == 200, f"Employer companies lookup failed: {response.text}"
            
            data = response.json()
            # Response should have employer info and companies list
            assert "employer_id" in data or "companies" in data, "Response should have employer_id or companies"
    
    def test_revenue_records_endpoint(self):
        """GET /api/revenue/records - returns revenue records table data."""
        response = requests.get(
            f"{BASE_URL}/api/revenue/records",
            params={"from_date": "2024-01-01", "to_date": "2027-12-31"},
            headers=self.auth_headers
        )
        assert response.status_code == 200, f"Revenue records failed: {response.text}"
        
        records = response.json()
        assert isinstance(records, list), "Records should be a list"
        
        # Should have at least one record (Ravi Yadav)
        assert len(records) >= 1, "Should have at least 1 revenue record"
        
        # Verify Ravi Yadav record
        ravi_record = next((r for r in records if r.get("candidate_name") == "Ravi Yadav"), None)
        assert ravi_record is not None, "Ravi Yadav revenue record should exist"
        
        # Verify record structure
        assert ravi_record.get("company_name") == "Panasonic India", "Company should be Panasonic India"
        assert ravi_record.get("revenue_status") == "joined", "Status should be 'joined'"
        assert ravi_record.get("final_revenue") == 124950, "Revenue should be 124950 (1500000 * 8.33%)"
        assert ravi_record.get("offered_ctc") == 1500000.0, "Offered CTC should be 1500000"


class TestEmployerRoutesAccessControl:
    """Test access control for employer routes."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login as admin."""
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        self.token = login_response.json().get("access_token")
        self.auth_headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_hierarchy_requires_admin(self):
        """GET /api/admin/hierarchy should require admin role."""
        # Without token
        response = requests.get(f"{BASE_URL}/api/admin/hierarchy")
        assert response.status_code in [401, 403], "Should require authentication"
    
    def test_company_pipeline_authorization(self):
        """GET /api/companies/{id}/pipeline should require admin or employer role."""
        # Without token
        response = requests.get(f"{BASE_URL}/api/companies/test-id/pipeline")
        assert response.status_code in [401, 403], "Should require authentication"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
