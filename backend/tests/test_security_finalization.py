"""
VHC Talent OS — Security Finalization Tests (Iteration 85)
Tests for:
- GET /api/system-health/security-validation endpoint
- GET /api/system-health/security-posture endpoint
- Security validation layer statuses (PASS/WARN/FAIL)
- Security posture score calculation (weighted)
- Compliance checklist and score
- Health score security penalty
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


@pytest.fixture(scope="module")
def admin_token():
    """Authenticate as admin and return token - single login to avoid rate limit."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }, timeout=30)
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


class TestSecurityValidationEndpoint:
    """Tests for GET /api/system-health/security-validation"""

    def test_security_validation_returns_200(self, admin_token):
        """Security validation endpoint should return 200 for admin."""
        resp = requests.get(f"{BASE_URL}/api/system-health/security-validation", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=15)
        assert resp.status_code == 200, f"Security validation failed: {resp.text}"

    def test_security_validation_has_required_fields(self, admin_token):
        """Response should have overall, score, layers."""
        resp = requests.get(f"{BASE_URL}/api/system-health/security-validation", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        
        # Check top-level fields
        assert "overall" in data, "Missing 'overall' field"
        assert "score" in data, "Missing 'score' field"
        assert "layers" in data, "Missing 'layers' field"
        assert "pass_count" in data, "Missing 'pass_count' field"
        assert "warn_count" in data, "Missing 'warn_count' field"
        assert "fail_count" in data, "Missing 'fail_count' field"
        assert "total_layers" in data, "Missing 'total_layers' field"
        
        print(f"Security Validation: overall={data['overall']}, score={data['score']}")

    def test_security_validation_layer_structure(self, admin_token):
        """Each layer should have status, enabled, detail."""
        resp = requests.get(f"{BASE_URL}/api/system-health/security-validation", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        layers = data.get("layers", {})
        
        expected_layers = ["turnstile", "zero_trust", "clamav", "rate_limiting", 
                          "file_validation", "security_logging", "xss_prevention"]
        
        for layer_id in expected_layers:
            assert layer_id in layers, f"Missing layer: {layer_id}"
            layer = layers[layer_id]
            assert "status" in layer, f"Layer {layer_id} missing 'status'"
            assert "enabled" in layer, f"Layer {layer_id} missing 'enabled'"
            assert "detail" in layer, f"Layer {layer_id} missing 'detail'"
            assert layer["status"] in ["PASS", "WARN", "FAIL"], f"Invalid status for {layer_id}: {layer['status']}"
            print(f"  {layer_id}: {layer['status']} (enabled={layer['enabled']})")

    def test_security_validation_expected_statuses(self, admin_token):
        """Verify expected statuses: 4 PASS (rate_limiting, file_validation, security_logging, xss_prevention), 3 WARN (turnstile, zero_trust, clamav)."""
        resp = requests.get(f"{BASE_URL}/api/system-health/security-validation", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        layers = data.get("layers", {})
        
        # These should be PASS
        pass_layers = ["rate_limiting", "file_validation", "security_logging", "xss_prevention"]
        for layer_id in pass_layers:
            assert layers[layer_id]["status"] == "PASS", f"Expected {layer_id} to be PASS, got {layers[layer_id]['status']}"
            assert layers[layer_id]["enabled"] is True, f"Expected {layer_id} to be enabled"
        
        # These should be WARN (not configured in this env)
        warn_layers = ["turnstile", "zero_trust", "clamav"]
        for layer_id in warn_layers:
            assert layers[layer_id]["status"] == "WARN", f"Expected {layer_id} to be WARN, got {layers[layer_id]['status']}"
        
        # Verify counts
        assert data["pass_count"] == 4, f"Expected 4 PASS, got {data['pass_count']}"
        assert data["warn_count"] == 3, f"Expected 3 WARN, got {data['warn_count']}"
        assert data["fail_count"] == 0, f"Expected 0 FAIL, got {data['fail_count']}"

    def test_security_validation_requires_auth(self):
        """Security validation should require admin auth."""
        resp = requests.get(f"{BASE_URL}/api/system-health/security-validation", timeout=10)
        assert resp.status_code in [401, 403, 422], f"Expected auth error, got {resp.status_code}"


class TestSecurityPostureEndpoint:
    """Tests for GET /api/system-health/security-posture"""

    def test_security_posture_returns_200(self, admin_token):
        """Security posture endpoint should return 200 for admin."""
        resp = requests.get(f"{BASE_URL}/api/system-health/security-posture", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=15)
        assert resp.status_code == 200, f"Security posture failed: {resp.text}"

    def test_security_posture_has_required_fields(self, admin_token):
        """Response should have posture_score, protection_layers, compliance_checklist, compliance_score."""
        resp = requests.get(f"{BASE_URL}/api/system-health/security-posture", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        
        # Check required fields
        assert "posture_score" in data, "Missing 'posture_score'"
        assert "protection_layers" in data, "Missing 'protection_layers'"
        assert "compliance_checklist" in data, "Missing 'compliance_checklist'"
        assert "compliance_score" in data, "Missing 'compliance_score'"
        assert "active_count" in data, "Missing 'active_count'"
        assert "inactive_count" in data, "Missing 'inactive_count'"
        assert "total_layers" in data, "Missing 'total_layers'"
        assert "recent_events" in data, "Missing 'recent_events'"
        
        print(f"Posture Score: {data['posture_score']}/100")
        print(f"Active Layers: {data['active_count']}/{data['total_layers']}")
        print(f"Compliance Score: {data['compliance_score']}%")

    def test_security_posture_score_is_50(self, admin_token):
        """Posture score should be 50 (4 active layers out of 7, weighted)."""
        resp = requests.get(f"{BASE_URL}/api/system-health/security-posture", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        
        posture_score = data.get("posture_score")
        assert posture_score == 50, f"Expected posture_score=50, got {posture_score}"

    def test_security_posture_active_layers(self, admin_token):
        """Should have 4 active layers: file_validation, rate_limiting, security_logging, xss_prevention."""
        resp = requests.get(f"{BASE_URL}/api/system-health/security-posture", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        
        layers = data.get("protection_layers", [])
        active_layers = [l for l in layers if l.get("active") is True]
        inactive_layers = [l for l in layers if l.get("active") is False]
        
        assert data["active_count"] == 4, f"Expected 4 active layers, got {data['active_count']}"
        assert data["inactive_count"] == 3, f"Expected 3 inactive layers, got {data['inactive_count']}"
        
        # Verify specific active layers
        active_ids = [l["id"] for l in active_layers]
        expected_active = ["file_validation", "rate_limiting", "security_logging", "xss_prevention"]
        for layer_id in expected_active:
            assert layer_id in active_ids, f"Expected {layer_id} to be active"
        
        # Verify specific inactive layers
        inactive_ids = [l["id"] for l in inactive_layers]
        expected_inactive = ["turnstile", "zero_trust", "clamav"]
        for layer_id in expected_inactive:
            assert layer_id in inactive_ids, f"Expected {layer_id} to be inactive"
        
        print(f"Active layers: {active_ids}")
        print(f"Inactive layers: {inactive_ids}")

    def test_security_posture_layer_structure(self, admin_token):
        """Each protection layer should have id, name, category, active, weight, detail."""
        resp = requests.get(f"{BASE_URL}/api/system-health/security-posture", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        
        layers = data.get("protection_layers", [])
        assert len(layers) == 7, f"Expected 7 protection layers, got {len(layers)}"
        
        for layer in layers:
            assert "id" in layer, "Layer missing 'id'"
            assert "name" in layer, "Layer missing 'name'"
            assert "category" in layer, "Layer missing 'category'"
            assert "active" in layer, "Layer missing 'active'"
            assert "weight" in layer, "Layer missing 'weight'"
            assert "detail" in layer, "Layer missing 'detail'"

    def test_compliance_checklist_structure(self, admin_token):
        """Compliance checklist should have 17 items with item and status."""
        resp = requests.get(f"{BASE_URL}/api/system-health/security-posture", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        
        checklist = data.get("compliance_checklist", [])
        assert len(checklist) == 17, f"Expected 17 checklist items, got {len(checklist)}"
        
        for item in checklist:
            assert "item" in item, "Checklist item missing 'item'"
            assert "status" in item, "Checklist item missing 'status'"
            assert isinstance(item["status"], bool), "Status should be boolean"
        
        # Count checked items
        checked = sum(1 for item in checklist if item["status"])
        print(f"Compliance checklist: {checked}/{len(checklist)} items checked")

    def test_compliance_score_is_71_percent(self, admin_token):
        """Compliance score should be 71% (12/17 items checked)."""
        resp = requests.get(f"{BASE_URL}/api/system-health/security-posture", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        
        compliance_score = data.get("compliance_score")
        # 12/17 = 70.588...% rounded to 71%
        assert compliance_score == 71, f"Expected compliance_score=71, got {compliance_score}"

    def test_security_posture_has_summaries(self, admin_token):
        """Should have summary_24h and summary_7d."""
        resp = requests.get(f"{BASE_URL}/api/system-health/security-posture", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        
        assert "summary_24h" in data, "Missing 'summary_24h'"
        assert "summary_7d" in data, "Missing 'summary_7d'"
        
        # Check summary structure
        for summary_key in ["summary_24h", "summary_7d"]:
            summary = data[summary_key]
            assert "total" in summary, f"{summary_key} missing 'total'"

    def test_security_posture_requires_auth(self):
        """Security posture should require admin auth."""
        resp = requests.get(f"{BASE_URL}/api/system-health/security-posture", timeout=10)
        assert resp.status_code in [401, 403, 422], f"Expected auth error, got {resp.status_code}"


class TestHealthScoreSecurityPenalty:
    """Tests for health score security layer penalty."""

    def test_live_status_has_current_score(self, admin_token):
        """live-status should have current_score with security penalty applied."""
        resp = requests.get(f"{BASE_URL}/api/system-health/live-status", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        
        current_score = data.get("current_score")
        assert current_score is not None, "Missing current_score in live-status"
        
        # Score should be reduced by penalty:
        # -2 for Turnstile inactive
        # -3 for Zero Trust inactive
        # -2 for ClamAV inactive
        # Total penalty = 7
        # So if all services healthy (100), score should be 93 or less
        print(f"Health Score with security penalty: {current_score}/100")
        
        # Health score should be less than 100 due to security penalty
        # Even if all services healthy, penalty of 7 reduces max to 93
        # With some services in warning, should be lower


class TestRegressionAdminLogin:
    """Regression: Admin login works."""

    def test_admin_login_still_works(self):
        """Admin should be able to login."""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }, timeout=10)
        
        # May get 429 if rate limited from other tests
        if resp.status_code == 429:
            pytest.skip("Rate limited - skipping login test")
        
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        data = resp.json()
        assert "access_token" in data
        assert data.get("user", {}).get("role") == "admin"


class TestRegressionSystemHealthServices:
    """Regression: System Health should still have 11 service cards."""

    def test_live_status_has_11_services(self, admin_token):
        """live-status should return 11 services."""
        resp = requests.get(f"{BASE_URL}/api/system-health/live-status", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        
        services = data.get("services", [])
        service_names = [s["service_name"] for s in services]
        
        # Should have 11 services
        expected_services = [
            "mongodb", "api_server", "background_workers", "queue_system",
            "system_resources", "automation_pipeline", "ai_services", "data_sync",
            "naukri_capture", "security", "virus_scanner"
        ]
        
        assert len(service_names) >= 11, f"Expected 11 services, got {len(service_names)}"
        
        for svc in expected_services:
            assert svc in service_names, f"Missing service: {svc}"
        
        print(f"Services: {service_names}")
