"""
VHC Talent OS - Admin Analytics Dashboard API Tests
Tests for GET /api/analytics/admin endpoint with various filters.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


class TestAdminAnalyticsAPI:
    """Tests for /api/analytics/admin endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        return data.get("access_token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, admin_token):
        """Headers with admin token"""
        return {"Authorization": f"Bearer {admin_token}"}
    
    # === Authentication Tests ===
    
    def test_analytics_requires_auth(self):
        """Test that /api/analytics/admin returns 401/403 without auth"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin")
        # API may return 401 (Not authenticated) or 403 (Forbidden) for unauthorized access
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        data = response.json()
        assert "detail" in data or "message" in data
    
    # === Basic Response Structure Tests ===
    
    def test_analytics_returns_all_required_fields(self, auth_headers):
        """Test that API returns all required fields: kpis, source_distribution, capture_trends, 
        recruiter_performance, stage_distribution, funnel_velocity, filters"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        assert response.status_code == 200, f"API failed: {response.text}"
        
        data = response.json()
        
        # Verify all top-level keys
        required_keys = ["kpis", "source_distribution", "capture_trends", 
                         "recruiter_performance", "stage_distribution", 
                         "funnel_velocity", "filters"]
        for key in required_keys:
            assert key in data, f"Missing required key: {key}"
    
    def test_analytics_kpis_structure(self, auth_headers):
        """Test KPIs structure and data types"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        assert response.status_code == 200
        
        kpis = response.json()["kpis"]
        
        # KPIs should include capture metrics
        assert "total_captures" in kpis
        assert "captures_today" in kpis
        assert "captures_this_week" in kpis
        assert "captures_this_month" in kpis
        assert "avg_daily_rate" in kpis
        assert "active_sources" in kpis
        assert "total_applications" in kpis
        assert "avg_funnel_days" in kpis
        
        # Verify data types are numeric
        assert isinstance(kpis["total_captures"], int)
        assert isinstance(kpis["captures_today"], int)
        assert isinstance(kpis["captures_this_week"], int)
        assert isinstance(kpis["captures_this_month"], int)
        assert isinstance(kpis["avg_daily_rate"], (int, float))
        assert isinstance(kpis["active_sources"], int)
    
    def test_analytics_source_distribution(self, auth_headers):
        """Test source distribution data for pie chart"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        assert response.status_code == 200
        
        source_dist = response.json()["source_distribution"]
        
        assert isinstance(source_dist, list)
        assert len(source_dist) > 0, "Should have at least one source"
        
        # Each source should have source name and count
        for source in source_dist:
            assert "source" in source
            assert "count" in source
            assert isinstance(source["count"], int)
            assert source["count"] >= 0
    
    def test_analytics_capture_trends(self, auth_headers):
        """Test capture trends data for line chart"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        assert response.status_code == 200
        
        trends = response.json()["capture_trends"]
        
        assert isinstance(trends, list)
        
        # Each trend point should have date and count
        for point in trends:
            assert "date" in point
            assert "count" in point
            assert isinstance(point["count"], int)
    
    def test_analytics_recruiter_performance(self, auth_headers):
        """Test recruiter performance data for bar chart"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        assert response.status_code == 200
        
        recruiters = response.json()["recruiter_performance"]
        
        assert isinstance(recruiters, list)
        
        # Each recruiter should have user info and captures
        for rec in recruiters:
            assert "user_id" in rec
            assert "name" in rec
            assert "role" in rec
            assert "team" in rec
            assert "captures" in rec
            assert isinstance(rec["captures"], int)
    
    def test_analytics_stage_distribution(self, auth_headers):
        """Test stage distribution data"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        assert response.status_code == 200
        
        stages = response.json()["stage_distribution"]
        
        assert isinstance(stages, dict)
        # Should have application stages
        for stage, count in stages.items():
            assert isinstance(count, int)
            assert count >= 0
    
    def test_analytics_funnel_velocity(self, auth_headers):
        """Test funnel velocity data (avg days per stage)"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        assert response.status_code == 200
        
        funnel = response.json()["funnel_velocity"]
        
        assert isinstance(funnel, dict)
        # Should have velocity for hiring stages
        expected_stages = ["shortlisted", "interview", "offered", "hired"]
        for stage in expected_stages:
            assert stage in funnel, f"Missing funnel velocity for {stage}"
            assert isinstance(funnel[stage], (int, float))
    
    def test_analytics_filter_options(self, auth_headers):
        """Test that filters contain employers, teams, recruiters"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        assert response.status_code == 200
        
        filters = response.json()["filters"]
        
        assert "employers" in filters
        assert "teams" in filters
        assert "recruiters" in filters
        
        assert isinstance(filters["employers"], list)
        assert isinstance(filters["teams"], list)
        assert isinstance(filters["recruiters"], list)
        
        # Employers should have id and name
        if len(filters["employers"]) > 0:
            emp = filters["employers"][0]
            assert "id" in emp
            assert "name" in emp
        
        # Teams should have id, name, employer_id
        if len(filters["teams"]) > 0:
            team = filters["teams"][0]
            assert "id" in team
            assert "name" in team
            assert "employer_id" in team
        
        # Recruiters should have id, name, role
        if len(filters["recruiters"]) > 0:
            rec = filters["recruiters"][0]
            assert "id" in rec
            assert "name" in rec
            assert "role" in rec
    
    # === Filter Tests ===
    
    def test_analytics_employer_filter(self, auth_headers):
        """Test filtering by employer_id narrows results"""
        # Get unfiltered data
        response_all = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        assert response_all.status_code == 200
        data_all = response_all.json()
        
        # Get an employer ID from filters
        employers = data_all["filters"]["employers"]
        if len(employers) == 0:
            pytest.skip("No employers in database")
        
        employer_id = employers[0]["id"]
        
        # Get filtered data
        response_filtered = requests.get(
            f"{BASE_URL}/api/analytics/admin?employer_id={employer_id}",
            headers=auth_headers
        )
        assert response_filtered.status_code == 200
        data_filtered = response_filtered.json()
        
        # Filtered total should be <= unfiltered
        assert data_filtered["kpis"]["total_captures"] <= data_all["kpis"]["total_captures"]
    
    def test_analytics_team_filter(self, auth_headers):
        """Test filtering by team_id narrows results"""
        # Get unfiltered data
        response_all = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        assert response_all.status_code == 200
        data_all = response_all.json()
        
        # Get a team ID from filters
        teams = data_all["filters"]["teams"]
        if len(teams) == 0:
            pytest.skip("No teams in database")
        
        team_id = teams[0]["id"]
        
        # Get filtered data
        response_filtered = requests.get(
            f"{BASE_URL}/api/analytics/admin?team_id={team_id}",
            headers=auth_headers
        )
        assert response_filtered.status_code == 200
        data_filtered = response_filtered.json()
        
        # Filtered total should be <= unfiltered
        assert data_filtered["kpis"]["total_captures"] <= data_all["kpis"]["total_captures"]
    
    def test_analytics_recruiter_filter(self, auth_headers):
        """Test filtering by recruiter_id narrows results"""
        # Get unfiltered data
        response_all = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        assert response_all.status_code == 200
        data_all = response_all.json()
        
        # Get a recruiter ID from filters
        recruiters = data_all["filters"]["recruiters"]
        if len(recruiters) == 0:
            pytest.skip("No recruiters in database")
        
        recruiter_id = recruiters[0]["id"]
        
        # Get filtered data
        response_filtered = requests.get(
            f"{BASE_URL}/api/analytics/admin?recruiter_id={recruiter_id}",
            headers=auth_headers
        )
        assert response_filtered.status_code == 200
        data_filtered = response_filtered.json()
        
        # Filtered total should be <= unfiltered
        assert data_filtered["kpis"]["total_captures"] <= data_all["kpis"]["total_captures"]
        
        # Recruiter performance should only show the filtered recruiter
        if len(data_filtered["recruiter_performance"]) > 0:
            assert data_filtered["recruiter_performance"][0]["user_id"] == recruiter_id
    
    def test_analytics_date_range_filter(self, auth_headers):
        """Test filtering by date_from and date_to"""
        # Get unfiltered data
        response_all = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        assert response_all.status_code == 200
        data_all = response_all.json()
        
        # Filter for a specific date range
        response_filtered = requests.get(
            f"{BASE_URL}/api/analytics/admin?date_from=2026-01-31&date_to=2026-01-31",
            headers=auth_headers
        )
        assert response_filtered.status_code == 200
        data_filtered = response_filtered.json()
        
        # Filtered total should be <= unfiltered
        assert data_filtered["kpis"]["total_captures"] <= data_all["kpis"]["total_captures"]
    
    def test_analytics_combined_filters(self, auth_headers):
        """Test multiple filters combined"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/admin?date_from=2026-01-01&date_to=2026-12-31",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should still return valid structure
        assert "kpis" in data
        assert "source_distribution" in data
        assert "capture_trends" in data
    
    # === Data Validation Tests ===
    
    def test_analytics_has_real_data(self, auth_headers):
        """Verify analytics returns real data (not empty)"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Based on provided context, we expect real data
        assert data["kpis"]["total_captures"] > 0, "Expected real capture data"
        assert len(data["source_distribution"]) > 0, "Expected source distribution data"
        assert len(data["recruiter_performance"]) > 0, "Expected recruiter performance data"
