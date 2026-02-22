"""
VHC Talent OS - Production Stability Hardening Tests
Tests for email normalization, environment info endpoint, and startup logging.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
RECRUITER_EMAIL = "bhumika@vhc.in"
RECRUITER_PASSWORD = "12345678"


class TestEmailNormalization:
    """Tests for email normalization on login and registration"""

    def test_login_with_lowercase_email(self):
        """Standard lowercase email login should work"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "bhumika@vhc.in",
            "password": "12345678"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == "bhumika@vhc.in"
        print("✓ Login with lowercase email works")

    def test_login_with_mixed_case_email(self):
        """Login with 'Bhumika@VHC.in' should succeed and return lowercase email"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "Bhumika@VHC.in",
            "password": "12345678"
        })
        assert response.status_code == 200, f"Mixed-case login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        # Email in response should be lowercase
        assert data["user"]["email"] == "bhumika@vhc.in", f"Expected lowercase email, got: {data['user']['email']}"
        print("✓ Login with mixed-case email 'Bhumika@VHC.in' works and returns lowercase")

    def test_login_with_uppercase_email(self):
        """Login with 'BHUMIKA@VHC.IN' should succeed"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "BHUMIKA@VHC.IN",
            "password": "12345678"
        })
        assert response.status_code == 200, f"Uppercase login failed: {response.text}"
        data = response.json()
        assert data["user"]["email"] == "bhumika@vhc.in"
        print("✓ Login with uppercase email works")

    def test_login_with_whitespace_padded_email(self):
        """Login with '  bhumika@vhc.in  ' (whitespace padding) should succeed"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "  bhumika@vhc.in  ",
            "password": "12345678"
        })
        assert response.status_code == 200, f"Whitespace-padded login failed: {response.text}"
        data = response.json()
        assert data["user"]["email"] == "bhumika@vhc.in"
        print("✓ Login with whitespace-padded email '  bhumika@vhc.in  ' works")

    def test_login_with_mixed_case_and_whitespace(self):
        """Login with '  Bhumika@VHC.in  ' should succeed"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "  Bhumika@VHC.in  ",
            "password": "12345678"
        })
        assert response.status_code == 200, f"Mixed-case + whitespace login failed: {response.text}"
        data = response.json()
        assert data["user"]["email"] == "bhumika@vhc.in"
        print("✓ Login with '  Bhumika@VHC.in  ' works")

    def test_admin_login_with_mixed_case(self):
        """Admin login with mixed case should work"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "Admin@VHC.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200, f"Admin mixed-case login failed: {response.text}"
        data = response.json()
        assert data["user"]["email"] == "admin@vhc.in"
        print("✓ Admin login with 'Admin@VHC.in' works")


class TestEnvironmentInfoEndpoint:
    """Tests for GET /api/system-health/env-info endpoint"""

    def _get_auth_token(self, email, password):
        """Helper to get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": password
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        return None

    def test_env_info_requires_authentication(self):
        """GET /api/system-health/env-info should return 401/403 without token"""
        response = requests.get(f"{BASE_URL}/api/system-health/env-info")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ env-info endpoint requires authentication (returns 401/403 without token)")

    def test_env_info_with_admin_auth(self):
        """env-info should return environment data for admin"""
        token = self._get_auth_token(ADMIN_EMAIL, ADMIN_PASSWORD)
        assert token, "Failed to get admin token"
        
        response = requests.get(
            f"{BASE_URL}/api/system-health/env-info",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"Admin env-info failed: {response.text}"
        
        data = response.json()
        assert "environment" in data, "Missing 'environment' field"
        assert "is_production" in data, "Missing 'is_production' field"
        assert data["environment"] == "preview", f"Expected 'preview', got: {data['environment']}"
        assert data["is_production"] == False, f"Expected is_production=False, got: {data['is_production']}"
        print(f"✓ Admin env-info returns: environment={data['environment']}, is_production={data['is_production']}")

    def test_env_info_with_recruiter_auth(self):
        """env-info should return environment data for recruiter"""
        token = self._get_auth_token(RECRUITER_EMAIL, RECRUITER_PASSWORD)
        assert token, "Failed to get recruiter token"
        
        response = requests.get(
            f"{BASE_URL}/api/system-health/env-info",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"Recruiter env-info failed: {response.text}"
        
        data = response.json()
        assert data["environment"] == "preview"
        assert data["is_production"] == False
        print(f"✓ Recruiter env-info returns: environment={data['environment']}, is_production={data['is_production']}")


class TestRecruiterDashboard:
    """Tests for recruiter login and dashboard access"""

    def test_recruiter_login(self):
        """bhumika@vhc.in can login as recruiter"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "bhumika@vhc.in",
            "password": "12345678"
        })
        assert response.status_code == 200, f"Recruiter login failed: {response.text}"
        data = response.json()
        
        assert data["user"]["role"] == "recruiter", f"Expected role=recruiter, got: {data['user']['role']}"
        assert data["user"]["email"] == "bhumika@vhc.in"
        print(f"✓ Recruiter bhumika@vhc.in logged in successfully, role={data['user']['role']}")
        return data["access_token"]

    def test_recruiter_can_access_auth_me(self):
        """Recruiter can access /api/auth/me endpoint"""
        # Login first
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "bhumika@vhc.in",
            "password": "12345678"
        })
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        
        # Access /me endpoint
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"/api/auth/me failed: {response.text}"
        
        data = response.json()
        assert data["email"] == "bhumika@vhc.in"
        assert data["role"] == "recruiter"
        print("✓ Recruiter can access /api/auth/me endpoint")


class TestDatabaseEmailNormalization:
    """Tests to verify all emails in DB are lowercase"""

    def test_admin_login_returns_lowercase_email(self):
        """Verify admin email is stored lowercase in DB"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200
        data = response.json()
        
        # Email should be all lowercase
        email = data["user"]["email"]
        assert email == email.lower(), f"Email not lowercase in DB: {email}"
        assert email == "admin@vhc.in"
        print(f"✓ Admin email stored lowercase: {email}")

    def test_recruiter_email_stored_lowercase(self):
        """Verify recruiter email is stored lowercase in DB"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "bhumika@vhc.in",
            "password": "12345678"
        })
        assert response.status_code == 200
        data = response.json()
        
        email = data["user"]["email"]
        assert email == email.lower(), f"Email not lowercase in DB: {email}"
        assert email == "bhumika@vhc.in"
        print(f"✓ Recruiter email stored lowercase: {email}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
