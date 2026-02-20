"""
VHC Talent OS - Unified Filter Bar and Combined PDF Export Tests
Testing the analytics unified filter bar endpoints and combined PDF export.
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAnalyticsEndpoints:
    """Tests for analytics endpoints used by unified filter bar."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for all tests."""
        self.admin_email = "admin@vhc.in"
        self.admin_password = "VhcAdmin@2024"
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_password}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_admin_analytics_returns_filter_options(self):
        """GET /api/analytics/admin - should return filter options for dropdowns."""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=self.headers)
        assert response.status_code == 200

        data = response.json()
        assert "filters" in data, "Missing 'filters' key in response"
        filters = data["filters"]

        # Verify filter options structure
        assert "employers" in filters, "Missing 'employers' in filters"
        assert "teams" in filters, "Missing 'teams' in filters"
        assert "recruiters" in filters, "Missing 'recruiters' in filters"

        # Verify employer structure
        if filters["employers"]:
            emp = filters["employers"][0]
            assert "id" in emp, "Employer missing 'id'"
            assert "name" in emp, "Employer missing 'name'"

        # Verify team structure with employer_id for cascading filter
        if filters["teams"]:
            team = filters["teams"][0]
            assert "id" in team, "Team missing 'id'"
            assert "name" in team, "Team missing 'name'"
            assert "employer_id" in team, "Team missing 'employer_id' for cascade filter"

        # Verify recruiter structure
        if filters["recruiters"]:
            rec = filters["recruiters"][0]
            assert "id" in rec, "Recruiter missing 'id'"
            assert "name" in rec, "Recruiter missing 'name'"

    def test_admin_analytics_with_date_filters(self):
        """GET /api/analytics/admin - should accept date_from and date_to params."""
        params = {
            "date_from": "2025-01-01",
            "date_to": "2026-02-20"
        }
        response = requests.get(
            f"{BASE_URL}/api/analytics/admin",
            headers=self.headers,
            params=params
        )
        assert response.status_code == 200

        data = response.json()
        assert "kpis" in data, "Missing 'kpis' in response"
        assert "total_captures" in data.get("kpis", {})

    def test_admin_analytics_with_entity_filters(self):
        """GET /api/analytics/admin - should accept employer_id, team_id, recruiter_id."""
        # First get a valid employer_id
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=self.headers)
        data = response.json()
        employers = data.get("filters", {}).get("employers", [])
        
        if employers:
            employer_id = employers[0]["id"]
            params = {"employer_id": employer_id}
            response = requests.get(
                f"{BASE_URL}/api/analytics/admin",
                headers=self.headers,
                params=params
            )
            assert response.status_code == 200

    def test_pipeline_conversion_with_date_filters(self):
        """GET /api/analytics/pipeline-conversion - should filter by date range."""
        params = {
            "from_date": "2025-01-01",
            "to_date": "2026-02-20"
        }
        response = requests.get(
            f"{BASE_URL}/api/analytics/pipeline-conversion",
            headers=self.headers,
            params=params
        )
        assert response.status_code == 200

        data = response.json()
        assert "conversions" in data
        assert "stage_counts" in data
        assert "total_applications" in data
        assert isinstance(data["total_applications"], int)

    def test_pipeline_conversion_with_recruiter_filter(self):
        """GET /api/analytics/pipeline-conversion - should filter by recruiter_id."""
        # Get a valid recruiter_id first
        admin_response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=self.headers)
        recruiters = admin_response.json().get("filters", {}).get("recruiters", [])
        
        if recruiters:
            recruiter_id = recruiters[0]["id"]
            params = {"recruiter_id": recruiter_id}
            response = requests.get(
                f"{BASE_URL}/api/analytics/pipeline-conversion",
                headers=self.headers,
                params=params
            )
            assert response.status_code == 200
            assert "conversions" in response.json()

    def test_revenue_forecast_with_employer_filter(self):
        """GET /api/analytics/revenue-forecast - should filter by employer_id."""
        # Get a valid employer_id
        admin_response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=self.headers)
        employers = admin_response.json().get("filters", {}).get("employers", [])
        
        if employers:
            employer_id = employers[0]["id"]
            params = {"employer_id": employer_id}
            response = requests.get(
                f"{BASE_URL}/api/analytics/revenue-forecast",
                headers=self.headers,
                params=params
            )
            assert response.status_code == 200
            
            data = response.json()
            assert "total_forecast_pipeline" in data
            assert "total_realized_revenue" in data
            assert "by_stage" in data
            assert "probability_map" in data

    def test_recruiter_performance_endpoint(self):
        """GET /api/analytics/recruiter-performance - admin only."""
        response = requests.get(
            f"{BASE_URL}/api/analytics/recruiter-performance",
            headers=self.headers
        )
        assert response.status_code == 200

        data = response.json()
        assert "recruiters" in data
        
        if data["recruiters"]:
            rec = data["recruiters"][0]
            assert "recruiter_id" in rec
            assert "recruiter_name" in rec
            assert "total_candidates" in rec
            assert "submitted" in rec
            assert "offered" in rec
            assert "joined" in rec
            assert "total_revenue" in rec
            assert "conversion_rate" in rec

    def test_mandate_performance_endpoint(self):
        """GET /api/analytics/mandate-performance - admin and employer."""
        response = requests.get(
            f"{BASE_URL}/api/analytics/mandate-performance",
            headers=self.headers
        )
        assert response.status_code == 200

        data = response.json()
        assert "mandates" in data

        if data["mandates"]:
            mandate = data["mandates"][0]
            assert "mandate_id" in mandate
            assert "mandate_name" in mandate
            assert "total_candidates" in mandate
            assert "submitted" in mandate
            assert "total_revenue" in mandate
            assert "submission_rate" in mandate


class TestCombinedPDFExport:
    """Tests for the combined PDF export endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for all tests."""
        self.admin_email = "admin@vhc.in"
        self.admin_password = "VhcAdmin@2024"
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_password}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_export_combined_pdf_returns_pdf(self):
        """GET /api/analytics/export-combined-pdf - should return valid PDF."""
        response = requests.get(
            f"{BASE_URL}/api/analytics/export-combined-pdf",
            headers=self.headers
        )
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/pdf"
        
        # PDF files start with %PDF
        assert response.content[:4] == b"%PDF", "Response is not a valid PDF"
        
        # Check content-disposition header for filename
        content_disp = response.headers.get("content-disposition", "")
        assert "VHC_Complete_Analytics" in content_disp, f"Unexpected filename: {content_disp}"

    def test_export_combined_pdf_with_date_filters(self):
        """GET /api/analytics/export-combined-pdf - should work with date params."""
        params = {
            "date_from": "2025-01-01",
            "date_to": "2026-02-20"
        }
        response = requests.get(
            f"{BASE_URL}/api/analytics/export-combined-pdf",
            headers=self.headers,
            params=params
        )
        assert response.status_code == 200
        assert response.content[:4] == b"%PDF"

    def test_export_combined_pdf_with_all_filters(self):
        """GET /api/analytics/export-combined-pdf - should work with all filter params."""
        # Get valid filter options first
        admin_response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=self.headers)
        filters = admin_response.json().get("filters", {})
        
        params = {
            "date_from": "2025-01-01",
            "date_to": "2026-02-20"
        }
        
        if filters.get("employers"):
            params["employer_id"] = filters["employers"][0]["id"]
        if filters.get("recruiters"):
            params["recruiter_id"] = filters["recruiters"][0]["id"]
            
        response = requests.get(
            f"{BASE_URL}/api/analytics/export-combined-pdf",
            headers=self.headers,
            params=params
        )
        assert response.status_code == 200
        assert response.content[:4] == b"%PDF"

    def test_export_combined_pdf_requires_auth(self):
        """GET /api/analytics/export-combined-pdf - should require admin auth."""
        response = requests.get(
            f"{BASE_URL}/api/analytics/export-combined-pdf"
        )
        # Should fail without auth token
        assert response.status_code in [401, 403, 422]

    def test_export_combined_pdf_size(self):
        """GET /api/analytics/export-combined-pdf - should return reasonable PDF size."""
        response = requests.get(
            f"{BASE_URL}/api/analytics/export-combined-pdf",
            headers=self.headers
        )
        assert response.status_code == 200
        
        # PDF should be at least 1KB and less than 10MB
        pdf_size = len(response.content)
        assert pdf_size > 1000, f"PDF too small: {pdf_size} bytes"
        assert pdf_size < 10 * 1024 * 1024, f"PDF too large: {pdf_size} bytes"


class TestDatePresets:
    """Tests for verifying date preset calculations work correctly with API."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for all tests."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
        )
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_7d_preset_date_range(self):
        """Test 7-day date range filter."""
        now = datetime.now()
        date_to = now.strftime("%Y-%m-%d")
        date_from = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        
        params = {"from_date": date_from, "to_date": date_to}
        response = requests.get(
            f"{BASE_URL}/api/analytics/pipeline-conversion",
            headers=self.headers,
            params=params
        )
        assert response.status_code == 200

    def test_30d_preset_date_range(self):
        """Test 30-day date range filter."""
        now = datetime.now()
        date_to = now.strftime("%Y-%m-%d")
        date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        
        params = {"from_date": date_from, "to_date": date_to}
        response = requests.get(
            f"{BASE_URL}/api/analytics/pipeline-conversion",
            headers=self.headers,
            params=params
        )
        assert response.status_code == 200

    def test_90d_preset_date_range(self):
        """Test 90-day date range filter."""
        now = datetime.now()
        date_to = now.strftime("%Y-%m-%d")
        date_from = (now - timedelta(days=90)).strftime("%Y-%m-%d")
        
        params = {"from_date": date_from, "to_date": date_to}
        response = requests.get(
            f"{BASE_URL}/api/analytics/pipeline-conversion",
            headers=self.headers,
            params=params
        )
        assert response.status_code == 200

    def test_ytd_preset_date_range(self):
        """Test Year-to-Date filter."""
        now = datetime.now()
        date_to = now.strftime("%Y-%m-%d")
        date_from = f"{now.year}-01-01"
        
        params = {"from_date": date_from, "to_date": date_to}
        response = requests.get(
            f"{BASE_URL}/api/analytics/pipeline-conversion",
            headers=self.headers,
            params=params
        )
        assert response.status_code == 200
