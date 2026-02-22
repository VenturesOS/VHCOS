"""
Training Manual PDF Download API Tests
Tests for GET /api/system-health/training-manual/download endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
NON_ADMIN_EMAIL = "recruiter_test@vhc.in"
NON_ADMIN_PASSWORD = "TestPass123"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    assert "access_token" in data, "No access_token in login response"
    return data["access_token"]


class TestTrainingManualDownload:
    """Tests for training manual PDF download endpoint"""
    
    def test_download_requires_authentication(self):
        """Endpoint should return 401/403 without authentication"""
        response = requests.get(f"{BASE_URL}/api/system-health/training-manual/download")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"✓ Without auth returns {response.status_code}")
    
    def test_download_with_invalid_token(self):
        """Endpoint should reject invalid tokens"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/training-manual/download",
            headers={"Authorization": "Bearer invalid-token-12345"}
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"✓ Invalid token returns {response.status_code}")
    
    def test_download_with_admin_auth(self, admin_token):
        """Admin should be able to download the training manual PDF"""
        response = requests.get(
            f"{BASE_URL}/api/system-health/training-manual/download",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Status code check
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Status code: {response.status_code}")
        
        # Content-type check
        content_type = response.headers.get('Content-Type', '')
        assert 'application/pdf' in content_type, f"Expected application/pdf, got {content_type}"
        print(f"✓ Content-Type: {content_type}")
        
        # Content-Disposition check
        content_disp = response.headers.get('Content-Disposition', '')
        assert 'attachment' in content_disp, f"Expected attachment disposition, got {content_disp}"
        assert 'VHC_Training_Manual.pdf' in content_disp, f"Expected filename in disposition: {content_disp}"
        print(f"✓ Content-Disposition: {content_disp}")
        
        # PDF size check (should be > 50KB based on the markdown source)
        pdf_size = len(response.content)
        assert pdf_size > 50000, f"PDF too small: {pdf_size} bytes"
        print(f"✓ PDF size: {pdf_size} bytes")
        
        # PDF magic bytes check (PDF starts with %PDF)
        assert response.content[:4] == b'%PDF', "Response does not start with PDF magic bytes"
        print("✓ PDF magic bytes validated")


class TestTrainingManualEndpointErrors:
    """Tests for error handling in training manual endpoint"""
    
    def test_endpoint_exists(self, admin_token):
        """Endpoint should exist and be accessible"""
        response = requests.options(f"{BASE_URL}/api/system-health/training-manual/download")
        # OPTIONS might return different codes, but endpoint should respond
        assert response.status_code != 404, "Endpoint not found"
        print(f"✓ Endpoint exists, OPTIONS returned {response.status_code}")
    
    def test_get_method_only(self, admin_token):
        """Endpoint should only accept GET method"""
        # Test POST
        response = requests.post(
            f"{BASE_URL}/api/system-health/training-manual/download",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 405, f"POST should return 405, got {response.status_code}"
        print(f"✓ POST returns {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
