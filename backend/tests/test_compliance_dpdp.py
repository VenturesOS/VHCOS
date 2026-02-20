"""
VHC Talent OS — DPDP 2023 Compliance API Tests
Tests for compliance routes: consent-version, dashboard-stats, audit-logs, 
cookie-consent, governance-requests
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"

@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session

@pytest.fixture(scope="module")
def admin_token(api_client):
    """Get admin authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token")
    pytest.fail(f"Admin login failed: {response.status_code} - {response.text}")

@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth token"""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}"
    }


class TestConsentVersionPublicEndpoint:
    """Test GET /api/compliance/consent-version (public endpoint)"""
    
    def test_consent_version_returns_200(self, api_client):
        """Consent version endpoint should be publicly accessible"""
        response = api_client.get(f"{BASE_URL}/api/compliance/consent-version")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Consent version endpoint returns 200")
    
    def test_consent_version_returns_correct_format(self, api_client):
        """Consent version should return v1.0_2026"""
        response = api_client.get(f"{BASE_URL}/api/compliance/consent-version")
        data = response.json()
        assert "consent_version" in data, "Response should contain consent_version key"
        assert data["consent_version"] == "v1.0_2026", f"Expected v1.0_2026, got {data['consent_version']}"
        print(f"PASS: Consent version is {data['consent_version']}")


class TestCookieConsentPublicEndpoint:
    """Test POST /api/compliance/cookie-consent (public endpoint)"""
    
    def test_cookie_consent_accept_all(self, api_client):
        """Accept all cookies consent should return ok"""
        payload = {
            "action": "accept_all",
            "preferences": {
                "essential": True,
                "analytics": True,
                "marketing": True
            }
        }
        response = api_client.post(f"{BASE_URL}/api/compliance/cookie-consent", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got {data}"
        print("PASS: Cookie consent (accept all) logged successfully")
    
    def test_cookie_consent_reject_nonessential(self, api_client):
        """Reject non-essential cookies consent should return ok"""
        payload = {
            "action": "reject_non_essential",
            "preferences": {
                "essential": True,
                "analytics": False,
                "marketing": False
            }
        }
        response = api_client.post(f"{BASE_URL}/api/compliance/cookie-consent", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got {data}"
        print("PASS: Cookie consent (reject non-essential) logged successfully")
    
    def test_cookie_consent_custom_preferences(self, api_client):
        """Custom cookie preferences consent should return ok"""
        payload = {
            "action": "custom",
            "preferences": {
                "essential": True,
                "analytics": True,
                "marketing": False
            }
        }
        response = api_client.post(f"{BASE_URL}/api/compliance/cookie-consent", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got {data}"
        print("PASS: Cookie consent (custom) logged successfully")


class TestDashboardStatsAdminEndpoint:
    """Test GET /api/compliance/dashboard-stats (admin only)"""
    
    def test_dashboard_stats_requires_auth(self, api_client):
        """Dashboard stats should require authentication"""
        response = api_client.get(f"{BASE_URL}/api/compliance/dashboard-stats")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print("PASS: Dashboard stats requires authentication")
    
    def test_dashboard_stats_returns_200_for_admin(self, api_client, admin_headers):
        """Dashboard stats should return 200 for admin"""
        response = api_client.get(f"{BASE_URL}/api/compliance/dashboard-stats", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Dashboard stats returns 200 for admin")
    
    def test_dashboard_stats_contains_required_fields(self, api_client, admin_headers):
        """Dashboard stats should contain all required fields"""
        response = api_client.get(f"{BASE_URL}/api/compliance/dashboard-stats", headers=admin_headers)
        data = response.json()
        
        # Check consent_health object
        assert "consent_health" in data, "Response should contain consent_health"
        health = data["consent_health"]
        assert "total_profiles" in health, "consent_health should have total_profiles"
        assert "consent_recorded" in health, "consent_health should have consent_recorded"
        assert "compliance_percentage" in health, "consent_health should have compliance_percentage"
        
        # Check data_risk_alerts array
        assert "data_risk_alerts" in data, "Response should contain data_risk_alerts"
        assert isinstance(data["data_risk_alerts"], list), "data_risk_alerts should be a list"
        
        # Check audit entries and version
        assert "total_audit_entries" in data, "Response should contain total_audit_entries"
        assert "consent_version" in data, "Response should contain consent_version"
        assert data["consent_version"] == "v1.0_2026", f"Expected v1.0_2026, got {data['consent_version']}"
        
        print(f"PASS: Dashboard stats contains all required fields")
        print(f"  - consent_health: {health}")
        print(f"  - data_risk_alerts count: {len(data['data_risk_alerts'])}")
        print(f"  - total_audit_entries: {data['total_audit_entries']}")


class TestAuditLogsAdminEndpoint:
    """Test GET /api/compliance/audit-logs (admin only)"""
    
    def test_audit_logs_requires_auth(self, api_client):
        """Audit logs should require authentication"""
        response = api_client.get(f"{BASE_URL}/api/compliance/audit-logs")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print("PASS: Audit logs requires authentication")
    
    def test_audit_logs_returns_200_for_admin(self, api_client, admin_headers):
        """Audit logs should return 200 for admin"""
        response = api_client.get(f"{BASE_URL}/api/compliance/audit-logs", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Audit logs returns 200 for admin")
    
    def test_audit_logs_pagination(self, api_client, admin_headers):
        """Audit logs should support pagination"""
        response = api_client.get(f"{BASE_URL}/api/compliance/audit-logs?page=1&limit=10", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "logs" in data, "Response should contain logs"
        assert "total" in data, "Response should contain total"
        assert "page" in data, "Response should contain page"
        assert "limit" in data, "Response should contain limit"
        assert data["page"] == 1, f"Expected page 1, got {data['page']}"
        assert data["limit"] == 10, f"Expected limit 10, got {data['limit']}"
        
        print(f"PASS: Audit logs pagination works (total: {data['total']}, logs: {len(data['logs'])})")
    
    def test_audit_logs_filter_by_action(self, api_client, admin_headers):
        """Audit logs should support action filter"""
        response = api_client.get(f"{BASE_URL}/api/compliance/audit-logs?action=consent_given", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "logs" in data, "Response should contain logs"
        print(f"PASS: Audit logs action filter works (found {len(data['logs'])} entries)")
    
    def test_audit_logs_filter_by_source(self, api_client, admin_headers):
        """Audit logs should support source filter"""
        response = api_client.get(f"{BASE_URL}/api/compliance/audit-logs?source=career_page", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "logs" in data, "Response should contain logs"
        print(f"PASS: Audit logs source filter works (found {len(data['logs'])} entries)")


class TestGovernanceRequestsAdminEndpoint:
    """Test GET /api/compliance/governance-requests (admin only)"""
    
    def test_governance_requests_requires_auth(self, api_client):
        """Governance requests should require authentication"""
        response = api_client.get(f"{BASE_URL}/api/compliance/governance-requests")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print("PASS: Governance requests requires authentication")
    
    def test_governance_requests_returns_200_for_admin(self, api_client, admin_headers):
        """Governance requests should return 200 for admin"""
        response = api_client.get(f"{BASE_URL}/api/compliance/governance-requests", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Governance requests returns 200 for admin")
    
    def test_governance_requests_pagination(self, api_client, admin_headers):
        """Governance requests should support pagination"""
        response = api_client.get(f"{BASE_URL}/api/compliance/governance-requests?page=1&limit=10", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "requests" in data, "Response should contain requests"
        assert "total" in data, "Response should contain total"
        assert "page" in data, "Response should contain page"
        assert "limit" in data, "Response should contain limit"
        
        print(f"PASS: Governance requests pagination works (total: {data['total']}, requests: {len(data['requests'])})")
    
    def test_governance_requests_filter_by_status(self, api_client, admin_headers):
        """Governance requests should support status filter"""
        response = api_client.get(f"{BASE_URL}/api/compliance/governance-requests?status=pending", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "requests" in data, "Response should contain requests"
        print(f"PASS: Governance requests status filter works (found {len(data['requests'])} entries)")


class TestRegressionAdminAuth:
    """Regression: Verify admin login still works"""
    
    def test_admin_login_success(self, api_client):
        """Admin login should work with correct credentials"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.status_code}"
        data = response.json()
        assert "access_token" in data, "Response should contain access_token"
        print("PASS: Admin login successful")
    
    def test_admin_analytics_api(self, api_client, admin_headers):
        """Admin analytics API should work"""
        response = api_client.get(f"{BASE_URL}/api/analytics/admin", headers=admin_headers)
        assert response.status_code == 200, f"Admin analytics failed: {response.status_code}"
        data = response.json()
        assert "kpis" in data, "Response should contain kpis"
        print("PASS: Admin analytics API works")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
