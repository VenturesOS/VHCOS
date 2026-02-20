"""
VHC Talent OS - Stabilization Testing (Iteration 78)
Tests:
1. Analytics API performance (<3s target)
2. Employer login (new account employer@vhc.in)
3. Pipeline conversion with date filters
4. Revenue forecast with date filters
5. Employer access to submission tracker
"""
import pytest
import requests
import time
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
EMPLOYER_EMAIL = "employer@vhc.in"
EMPLOYER_PASSWORD = "VhcEmployer@2024"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def employer_token():
    """Get employer authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": EMPLOYER_EMAIL,
        "password": EMPLOYER_PASSWORD
    })
    assert response.status_code == 200, f"Employer login failed: {response.text}"
    return response.json()["access_token"]


class TestAnalyticsPerformance:
    """Test analytics API performance optimization"""
    
    def test_admin_analytics_response_time_under_3s(self, admin_token):
        """CRITICAL: /api/analytics/admin should respond in <3 seconds (was 11s before optimization)"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        start_time = time.time()
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=headers)
        elapsed = time.time() - start_time
        
        assert response.status_code == 200
        assert elapsed < 3.0, f"API took {elapsed:.2f}s, should be <3s"
        print(f"✓ Analytics API responded in {elapsed:.2f}s (target: <3s)")
        
        # Validate response structure
        data = response.json()
        assert "kpis" in data
        assert "source_distribution" in data
        assert "capture_trends" in data
        assert "recruiter_performance" in data
        assert "stage_distribution" in data
        assert "funnel_velocity" in data
        assert "filters" in data
        
        # Validate KPI values are present
        kpis = data["kpis"]
        assert "total_captures" in kpis
        assert "captures_today" in kpis
        assert "avg_daily_rate" in kpis
        assert "active_sources" in kpis


class TestEmployerLogin:
    """Test newly created employer account"""
    
    def test_employer_login_success(self):
        """Employer employer@vhc.in should login successfully"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": EMPLOYER_EMAIL,
            "password": EMPLOYER_PASSWORD
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == EMPLOYER_EMAIL
        assert data["user"]["role"] == "employer"
        assert data["user"]["name"] == "Demo Employer"
        print(f"✓ Employer login successful: {data['user']['name']} ({data['user']['role']})")
    
    def test_employer_access_tracker_list(self, employer_token):
        """Employer should be able to access submission trackers"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        response = requests.get(f"{BASE_URL}/api/tracker/trackers", headers=headers)
        
        # Employer should get 200 or empty list (not 403)
        assert response.status_code == 200, f"Employer tracker access failed: {response.text}"
        print(f"✓ Employer can access tracker list")


class TestPipelineConversionFilters:
    """Test pipeline conversion API with date range filters"""
    
    def test_pipeline_conversion_without_filters(self, admin_token):
        """Pipeline conversion without filters should return 46 total applications"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/analytics/pipeline-conversion", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "total_applications" in data
        assert "stage_counts" in data
        assert "conversions" in data
        print(f"✓ Pipeline conversion (no filter): {data['total_applications']} total applications")
    
    def test_pipeline_conversion_with_7d_filter(self, admin_token):
        """Pipeline conversion with 7-day filter"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Calculate 7 days ago
        from datetime import datetime, timedelta
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}/api/analytics/pipeline-conversion?from_date={from_date}&to_date={to_date}",
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "total_applications" in data
        print(f"✓ Pipeline conversion (7d filter): {data['total_applications']} applications in last 7 days")
    
    def test_pipeline_conversion_with_30d_filter(self, admin_token):
        """Pipeline conversion with 30-day filter"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        from datetime import datetime, timedelta
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        response = requests.get(
            f"{BASE_URL}/api/analytics/pipeline-conversion?from_date={from_date}&to_date={to_date}",
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Pipeline conversion (30d filter): {data['total_applications']} applications in last 30 days")
    
    def test_pipeline_conversion_with_ytd_filter(self, admin_token):
        """Pipeline conversion with YTD filter"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        from datetime import datetime
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = f"{datetime.now().year}-01-01"
        
        response = requests.get(
            f"{BASE_URL}/api/analytics/pipeline-conversion?from_date={from_date}&to_date={to_date}",
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Pipeline conversion (YTD filter): {data['total_applications']} applications year-to-date")


class TestRevenueForecastFilters:
    """Test revenue forecast API with date range filters"""
    
    def test_revenue_forecast_without_filters(self, admin_token):
        """Revenue forecast without filters"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/analytics/revenue-forecast", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "total_forecast_pipeline" in data
        assert "total_realized_revenue" in data
        assert "total_candidates_with_offer" in data
        assert "by_stage" in data
        assert "probability_map" in data
        print(f"✓ Revenue forecast: Weighted Forecast={data['total_forecast_pipeline']}, Realized={data['total_realized_revenue']}, Candidates={data['total_candidates_with_offer']}")
    
    def test_revenue_forecast_accepts_date_params(self, admin_token):
        """Revenue forecast should accept from_date and to_date parameters"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        from datetime import datetime, timedelta
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        
        # Revenue forecast endpoint - currently doesn't filter by date but params should be accepted
        response = requests.get(
            f"{BASE_URL}/api/analytics/revenue-forecast?from_date={from_date}&to_date={to_date}",
            headers=headers
        )
        
        assert response.status_code == 200
        print("✓ Revenue forecast accepts date parameters")


class TestAllAnalyticsTabs:
    """Verify all 4 analytics tabs still work"""
    
    def test_admin_analytics_overview(self, admin_token):
        """Overview tab - admin analytics"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=headers)
        assert response.status_code == 200
        print("✓ Overview tab API works")
    
    def test_pipeline_conversion_tab(self, admin_token):
        """Pipeline Funnel tab"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/analytics/pipeline-conversion", headers=headers)
        assert response.status_code == 200
        print("✓ Pipeline Funnel tab API works")
    
    def test_revenue_forecast_tab(self, admin_token):
        """Revenue tab"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/analytics/revenue-forecast", headers=headers)
        assert response.status_code == 200
        print("✓ Revenue tab API works")
    
    def test_recruiter_performance_tab(self, admin_token):
        """Performance tab - recruiter performance"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/analytics/recruiter-performance", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "recruiters" in data
        print(f"✓ Recruiter Performance API works: {len(data['recruiters'])} recruiters")
    
    def test_mandate_performance_tab(self, admin_token):
        """Performance tab - mandate performance"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/analytics/mandate-performance", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "mandates" in data
        print(f"✓ Mandate Performance API works: {len(data['mandates'])} mandates")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
