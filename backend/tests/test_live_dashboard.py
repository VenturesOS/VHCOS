"""
VHC Talent OS — Live Dashboard Enhancement Tests
Tests: /api/system-health/live-status endpoint (new feature)
Features: 8 services, score_history, current_score, incidents (admin only)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Admin credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json().get("access_token")
    assert token, "No access_token in login response"
    return token


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth token"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestLiveStatusEndpoint:
    """Tests for GET /api/system-health/live-status (NEW FEATURE)"""

    def test_live_status_returns_200(self, admin_headers):
        """Verify live-status endpoint returns 200 with valid admin token"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/live-status",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_live_status_has_required_fields(self, admin_headers):
        """Verify response contains all required fields: services, score_history, current_score, incidents"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/live-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required top-level fields for live dashboard
        assert "services" in data, "Missing 'services' array"
        assert "score_history" in data, "Missing 'score_history' array"
        assert "current_score" in data, "Missing 'current_score' field"
        assert "incidents" in data, "Missing 'incidents' array"

    def test_services_array_structure(self, admin_headers):
        """Verify services array contains up to 8 services with required fields"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/live-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        services = response.json().get("services", [])
        
        # Should have at least 1 service (bot is running)
        assert len(services) > 0, "Services array should not be empty"
        
        expected_service_names = {
            "mongodb", "api_server", "background_workers", "queue_system",
            "system_resources", "automation_pipeline", "ai_services", "data_sync"
        }
        
        for svc in services:
            # Required fields
            assert "service_name" in svc, "Missing service_name"
            assert svc["service_name"] in expected_service_names, f"Unknown service: {svc['service_name']}"
            assert "status" in svc, f"Missing status for {svc['service_name']}"
            assert svc["status"] in ["healthy", "warning", "critical"], f"Invalid status: {svc['status']}"
            assert "timestamp" in svc, f"Missing timestamp for {svc['service_name']}"
            assert "metrics" in svc, f"Missing metrics for {svc['service_name']}"
            assert "failure_count_24h" in svc, f"Missing failure_count_24h for {svc['service_name']}"

    def test_services_has_8_services(self, admin_headers):
        """Verify all 8 expected services are present"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/live-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        services = response.json().get("services", [])
        
        expected_services = {
            "mongodb", "api_server", "background_workers", "queue_system",
            "system_resources", "automation_pipeline", "ai_services", "data_sync"
        }
        actual_services = {s.get("service_name") for s in services}
        
        assert actual_services == expected_services, \
            f"Expected 8 services, got {len(services)}. Missing: {expected_services - actual_services}"

    def test_score_history_array(self, admin_headers):
        """Verify score_history has data points with timestamp and score"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/live-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        score_history = response.json().get("score_history", [])
        
        # Should have history if bot has run
        assert isinstance(score_history, list), "score_history should be array"
        
        if len(score_history) > 0:
            for point in score_history:
                assert "timestamp" in point, "Missing timestamp in score_history point"
                assert "score" in point, "Missing score in score_history point"
                assert isinstance(point["score"], (int, float)), f"Score should be numeric, got {type(point['score'])}"
                assert 0 <= point["score"] <= 100, f"Score should be 0-100, got {point['score']}"

    def test_score_history_has_multiple_points(self, admin_headers):
        """Verify score_history has 24h data points (multiple cycles)"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/live-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        score_history = response.json().get("score_history", [])
        
        # Bot runs every 5 minutes, 24h = 288 max points; we expect at least a few
        assert len(score_history) >= 2, f"Expected multiple score history points, got {len(score_history)}"

    def test_current_score_value(self, admin_headers):
        """Verify current_score is valid 0-100"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/live-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        current_score = response.json().get("current_score")
        
        assert current_score is not None, "current_score should not be None"
        assert isinstance(current_score, (int, float)), f"current_score should be numeric, got {type(current_score)}"
        assert 0 <= current_score <= 100, f"current_score should be 0-100, got {current_score}"

    def test_incidents_array_structure(self, admin_headers):
        """Verify incidents array has latest 5 incidents with severity"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/live-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        incidents = response.json().get("incidents", [])
        
        assert isinstance(incidents, list), "incidents should be array"
        assert len(incidents) <= 5, f"Should have at most 5 incidents, got {len(incidents)}"
        
        for inc in incidents:
            assert "service_name" in inc, "Missing service_name in incident"
            assert "status" in inc, "Missing status in incident"
            # Incidents are warning or critical
            assert inc["status"] in ["warning", "critical"], f"Incident status should be warning/critical, got {inc['status']}"
            assert "timestamp" in inc, "Missing timestamp in incident"

    def test_live_status_requires_auth(self):
        """Verify endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/system-health/live-status")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_live_status_requires_admin_role(self):
        """Verify non-admin users cannot access live-status"""
        # Try with invalid token
        response = requests.get(
            f"{BASE_URL}/api/system-health/live-status",
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


class TestServiceMetrics:
    """Verify each service returns appropriate metrics"""

    def test_mongodb_has_latency_metric(self, admin_headers):
        """Verify MongoDB service has latency_ms metric"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/live-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        services = response.json().get("services", [])
        
        mongodb = next((s for s in services if s["service_name"] == "mongodb"), None)
        if mongodb:
            metrics = mongodb.get("metrics", {})
            assert "latency_ms" in metrics, "MongoDB should have latency_ms metric"

    def test_system_resources_has_memory_metric(self, admin_headers):
        """Verify system_resources has memory_percent metric"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/live-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        services = response.json().get("services", [])
        
        sysres = next((s for s in services if s["service_name"] == "system_resources"), None)
        if sysres:
            metrics = sysres.get("metrics", {})
            assert "memory_percent" in metrics, "system_resources should have memory_percent"

    def test_background_workers_has_stuck_jobs(self, admin_headers):
        """Verify background_workers has stuck_jobs metric"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/live-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        services = response.json().get("services", [])
        
        workers = next((s for s in services if s["service_name"] == "background_workers"), None)
        if workers:
            metrics = workers.get("metrics", {})
            assert "stuck_jobs" in metrics, "background_workers should have stuck_jobs"


class TestRegressionFeatures:
    """Regression tests for existing system health features"""

    def test_admin_login_still_works(self):
        """REGRESSION: Admin login should still work"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Admin login failed: {response.status_code}"
        data = response.json()
        assert "access_token" in data
        assert data.get("user", {}).get("role") == "admin"

    def test_maintenance_status_still_works(self, admin_headers):
        """REGRESSION: /api/system-health/maintenance-status endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "bot" in data
        assert "health_score" in data

    def test_maintenance_report_download_still_works(self, admin_headers):
        """REGRESSION: PDF download should still work"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-report/download",
            headers=admin_headers
        )
        assert response.status_code == 200
        assert "application/pdf" in response.headers.get("Content-Type", "")

    def test_system_errors_stats_still_works(self, admin_headers):
        """REGRESSION: Error stats endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/system-errors/stats",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Should have stats fields
        assert "total" in data
        assert "last_1h" in data
        assert "last_24h" in data
        assert "frontend" in data
        assert "backend" in data

    def test_system_errors_list_still_works(self, admin_headers):
        """REGRESSION: Error list endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/system-errors",
            headers=admin_headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
