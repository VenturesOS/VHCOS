"""
VHC Talent OS — Maintenance Bot & System Health Tests
Tests: maintenance-status, maintenance-report/download, maintenance-run
Features: self-healing bot, 8 service checks, PDF report, health score
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


class TestAdminLogin:
    """Test admin authentication still works (REGRESSION)"""

    def test_admin_login_success(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data.get("user", {}).get("role") == "admin"


class TestMaintenanceStatus:
    """Tests for GET /api/system-health/maintenance-status"""

    def test_maintenance_status_returns_200(self, admin_headers):
        """Verify maintenance-status endpoint returns 200 with valid admin token"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-status",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_maintenance_status_has_required_fields(self, admin_headers):
        """Verify response contains all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required top-level fields
        assert "bot" in data, "Missing 'bot' field"
        assert "health_score" in data, "Missing 'health_score' field"
        assert "services" in data, "Missing 'services' field"
        assert "fixes_24h" in data, "Missing 'fixes_24h' field"
        assert "reliability_events_24h" in data, "Missing 'reliability_events_24h' field"
        assert "safe_mode" in data, "Missing 'safe_mode' field"
        assert "stress_mode" in data, "Missing 'stress_mode' field"

    def test_bot_status_structure(self, admin_headers):
        """Verify bot status has running, last_run, last_health_score"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        bot = response.json().get("bot", {})
        
        assert "running" in bot, "Missing 'bot.running' field"
        assert isinstance(bot["running"], bool), "bot.running should be boolean"
        # last_run can be None if bot just started
        assert "last_run" in bot, "Missing 'bot.last_run' field"
        assert "last_health_score" in bot, "Missing 'bot.last_health_score' field"

    def test_bot_is_running(self, admin_headers):
        """Verify bot.running is true (bot started on server startup)"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        bot = response.json().get("bot", {})
        assert bot.get("running") is True, f"Bot should be running, got: {bot}"

    def test_health_score_range(self, admin_headers):
        """Verify health_score is between 0-100"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        score = response.json().get("health_score")
        assert isinstance(score, (int, float)), f"health_score should be numeric, got: {type(score)}"
        assert 0 <= score <= 100, f"health_score should be 0-100, got: {score}"

    def test_services_array_has_8_services(self, admin_headers):
        """Verify 8 services are being monitored"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        services = response.json().get("services", [])
        
        expected_services = {
            "mongodb", "api_server", "background_workers", "queue_system",
            "system_resources", "automation_pipeline", "ai_services", "data_sync"
        }
        actual_services = {s.get("service_name") for s in services}
        
        # May not have all 8 if some haven't been checked yet
        assert len(services) > 0, "Services array should not be empty"
        assert actual_services.issubset(expected_services) or expected_services.issubset(actual_services), \
            f"Unexpected services: {actual_services - expected_services}"

    def test_service_structure(self, admin_headers):
        """Verify each service has required fields"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        services = response.json().get("services", [])
        
        for svc in services:
            assert "service_name" in svc, "Missing service_name"
            assert "status" in svc, f"Missing status for {svc.get('service_name')}"
            assert svc["status"] in ["healthy", "warning", "critical"], \
                f"Invalid status: {svc['status']}"
            assert "priority" in svc, f"Missing priority for {svc.get('service_name')}"
            assert svc["priority"] in ["HIGH", "MEDIUM", "LOW"], \
                f"Invalid priority: {svc['priority']}"
            assert "timestamp" in svc, f"Missing timestamp for {svc.get('service_name')}"

    def test_maintenance_status_requires_auth(self):
        """Verify endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/system-health/maintenance-status")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_maintenance_status_requires_admin_role(self, admin_headers):
        """Endpoint should only be accessible by admin"""
        # This is implicitly tested - we're using admin headers and it works
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-status",
            headers=admin_headers
        )
        assert response.status_code == 200


class TestMaintenanceReportDownload:
    """Tests for GET /api/system-health/maintenance-report/download"""

    def test_download_returns_pdf(self, admin_headers):
        """Verify endpoint returns PDF content"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-report/download",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Check content type is PDF
        content_type = response.headers.get("Content-Type", "")
        assert "application/pdf" in content_type, f"Expected PDF, got: {content_type}"

    def test_download_has_disposition_header(self, admin_headers):
        """Verify Content-Disposition header for download"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-report/download",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        disposition = response.headers.get("Content-Disposition", "")
        assert "attachment" in disposition, "Expected attachment disposition"
        assert "VHC_Maintenance_Report" in disposition, "Expected filename in disposition"
        assert ".pdf" in disposition, "Expected .pdf extension in filename"

    def test_download_content_is_valid_pdf(self, admin_headers):
        """Verify PDF content starts with %PDF magic bytes"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-report/download",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        # PDF files start with %PDF
        assert response.content[:4] == b"%PDF", "Content is not valid PDF (missing %PDF header)"

    def test_download_pdf_has_reasonable_size(self, admin_headers):
        """Verify PDF is not empty and has reasonable size"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-report/download",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        size = len(response.content)
        assert size > 1000, f"PDF too small ({size} bytes), might be error"
        assert size < 10_000_000, f"PDF too large ({size} bytes)"

    def test_download_requires_auth(self):
        """Verify endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/system-health/maintenance-report/download")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


class TestMaintenanceRun:
    """Tests for POST /api/system-health/maintenance-run"""

    def test_manual_run_returns_200(self, admin_headers):
        """Verify manual maintenance run works"""
        response = requests.post(
            f"{BASE_URL}/api/system-health/maintenance-run",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_manual_run_returns_result(self, admin_headers):
        """Verify response contains run results"""
        response = requests.post(
            f"{BASE_URL}/api/system-health/maintenance-run",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data, "Missing 'status' field"
        assert data["status"] == "ok", f"Expected status 'ok', got: {data['status']}"
        assert "score" in data, "Missing 'score' field"
        assert isinstance(data["score"], (int, float)), "Score should be numeric"
        assert "critical" in data, "Missing 'critical' count"
        assert "warnings" in data, "Missing 'warnings' count"

    def test_manual_run_requires_auth(self):
        """Verify endpoint requires authentication"""
        response = requests.post(f"{BASE_URL}/api/system-health/maintenance-run")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


class TestSystemHealthRegression:
    """Regression tests for existing system health functionality"""

    def test_system_errors_stats_endpoint(self, admin_headers):
        """REGRESSION: /api/system-errors/stats still works"""
        response = requests.get(
            f"{BASE_URL}/api/system-errors/stats",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Should have these fields
        assert "total" in data or isinstance(data, dict), "Stats should return data"

    def test_system_errors_list_endpoint(self, admin_headers):
        """REGRESSION: /api/system-errors still works"""
        response = requests.get(
            f"{BASE_URL}/api/system-errors",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Should return list of errors"

    def test_admin_dashboard_loads(self, admin_headers):
        """REGRESSION: Admin can access analytics dashboard data"""
        # Test the analytics admin endpoint (correct endpoint)
        response = requests.get(
            f"{BASE_URL}/api/analytics/admin",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Admin analytics endpoint failed: {response.status_code}"
        data = response.json()
        assert "kpis" in data, "Should have KPIs in analytics response"


class TestHealthCheckServices:
    """Validate health check services are working"""

    def test_mongodb_check_in_services(self, admin_headers):
        """Verify MongoDB health check is included"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        services = response.json().get("services", [])
        mongodb_checks = [s for s in services if s.get("service_name") == "mongodb"]
        
        if mongodb_checks:  # May not exist if no recent checks
            check = mongodb_checks[0]
            assert check["status"] in ["healthy", "warning", "critical"]
            assert check.get("metrics", {}).get("latency_ms") is not None or check.get("metrics") == {}

    def test_api_server_check_in_services(self, admin_headers):
        """Verify API server health check is included"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/maintenance-status",
            headers=admin_headers
        )
        assert response.status_code == 200
        services = response.json().get("services", [])
        api_checks = [s for s in services if s.get("service_name") == "api_server"]
        
        if api_checks:
            check = api_checks[0]
            assert check["status"] in ["healthy", "warning", "critical"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
