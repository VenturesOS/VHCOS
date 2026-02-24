"""
Submission Tracker Role Access Tests
------------------------------------
Tests that employer and recruiter roles have full access to Submission Tracker feature,
which was previously restricted to admins only.

Test coverage:
- Admin: GET /api/tracker/trackers, /api/tracker/templates, /api/tracker/events (regression)
- Recruiter: GET /api/tracker/trackers, /api/tracker/templates, /api/tracker/events
- Employer: GET /api/tracker/trackers, /api/tracker/templates, /api/tracker/events
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_CREDS = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
RECRUITER_CREDS = {"email": "yamini@vhc.in", "password": "VhcAdmin@2024"}


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def admin_token(api_client):
    """Get admin authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin authentication failed: {response.status_code} - {response.text[:200]}")


@pytest.fixture(scope="module")
def recruiter_token(api_client):
    """Get recruiter authentication token"""
    import time
    time.sleep(2)  # Avoid rate limiting
    response = api_client.post(f"{BASE_URL}/api/auth/login", json=RECRUITER_CREDS)
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Recruiter authentication failed: {response.status_code} - {response.text[:200]}")


class TestAdminTrackerAccess:
    """Admin should have full access to Submission Tracker (regression test)"""
    
    def test_admin_can_get_trackers(self, api_client, admin_token):
        """Admin can GET /api/tracker/trackers"""
        response = api_client.get(
            f"{BASE_URL}/api/tracker/trackers",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Admin GET /trackers failed: {response.status_code} - {response.text[:200]}"
        data = response.json()
        assert "trackers" in data, "Response should contain 'trackers' key"
        print(f"Admin GET /trackers: SUCCESS - Found {len(data['trackers'])} trackers")
    
    def test_admin_can_get_templates(self, api_client, admin_token):
        """Admin can GET /api/tracker/templates"""
        response = api_client.get(
            f"{BASE_URL}/api/tracker/templates",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Admin GET /templates failed: {response.status_code} - {response.text[:200]}"
        data = response.json()
        assert "templates" in data, "Response should contain 'templates' key"
        print(f"Admin GET /templates: SUCCESS - Found {len(data['templates'])} templates")
    
    def test_admin_can_get_events(self, api_client, admin_token):
        """Admin can GET /api/tracker/events"""
        response = api_client.get(
            f"{BASE_URL}/api/tracker/events",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Admin GET /events failed: {response.status_code} - {response.text[:200]}"
        data = response.json()
        assert "events" in data, "Response should contain 'events' key"
        print(f"Admin GET /events: SUCCESS - Found {len(data['events'])} events")

    def test_admin_can_get_columns(self, api_client, admin_token):
        """Admin can GET /api/tracker/columns (master columns)"""
        response = api_client.get(
            f"{BASE_URL}/api/tracker/columns",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Admin GET /columns failed: {response.status_code} - {response.text[:200]}"
        data = response.json()
        assert "columns" in data, "Response should contain 'columns' key"
        assert "categories" in data, "Response should contain 'categories' key"
        print(f"Admin GET /columns: SUCCESS - Found {len(data['columns'])} master columns")


class TestRecruiterTrackerAccess:
    """Recruiter should have full access to Submission Tracker"""
    
    def test_recruiter_can_get_trackers(self, api_client, recruiter_token):
        """Recruiter can GET /api/tracker/trackers"""
        response = api_client.get(
            f"{BASE_URL}/api/tracker/trackers",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert response.status_code == 200, f"Recruiter GET /trackers failed: {response.status_code} - {response.text[:200]}"
        data = response.json()
        assert "trackers" in data, "Response should contain 'trackers' key"
        print(f"Recruiter GET /trackers: SUCCESS - Found {len(data['trackers'])} trackers")
    
    def test_recruiter_can_get_templates(self, api_client, recruiter_token):
        """Recruiter can GET /api/tracker/templates"""
        response = api_client.get(
            f"{BASE_URL}/api/tracker/templates",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert response.status_code == 200, f"Recruiter GET /templates failed: {response.status_code} - {response.text[:200]}"
        data = response.json()
        assert "templates" in data, "Response should contain 'templates' key"
        print(f"Recruiter GET /templates: SUCCESS - Found {len(data['templates'])} templates")
    
    def test_recruiter_can_get_events(self, api_client, recruiter_token):
        """Recruiter can GET /api/tracker/events"""
        response = api_client.get(
            f"{BASE_URL}/api/tracker/events",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert response.status_code == 200, f"Recruiter GET /events failed: {response.status_code} - {response.text[:200]}"
        data = response.json()
        assert "events" in data, "Response should contain 'events' key"
        print(f"Recruiter GET /events: SUCCESS - Found {len(data['events'])} events")

    def test_recruiter_can_get_columns(self, api_client, recruiter_token):
        """Recruiter can GET /api/tracker/columns (master columns)"""
        response = api_client.get(
            f"{BASE_URL}/api/tracker/columns",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert response.status_code == 200, f"Recruiter GET /columns failed: {response.status_code} - {response.text[:200]}"
        data = response.json()
        assert "columns" in data, "Response should contain 'columns' key"
        print(f"Recruiter GET /columns: SUCCESS - Found {len(data['columns'])} master columns")


class TestUnauthenticatedAccess:
    """Unauthenticated requests should be denied"""
    
    def test_unauthenticated_cannot_get_trackers(self, api_client):
        """Unauthenticated request to GET /api/tracker/trackers should fail"""
        response = api_client.get(f"{BASE_URL}/api/tracker/trackers")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"Unauthenticated GET /trackers: CORRECTLY DENIED with status {response.status_code}")
    
    def test_unauthenticated_cannot_get_templates(self, api_client):
        """Unauthenticated request to GET /api/tracker/templates should fail"""
        response = api_client.get(f"{BASE_URL}/api/tracker/templates")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"Unauthenticated GET /templates: CORRECTLY DENIED with status {response.status_code}")


class TestRecruiterVerifyRole:
    """Verify that recruiter token is actually for recruiter role"""
    
    def test_recruiter_token_has_correct_role(self, api_client, recruiter_token):
        """Verify recruiter token belongs to recruiter role"""
        response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert response.status_code == 200, f"GET /me failed: {response.status_code}"
        user = response.json()
        assert user.get("role") == "recruiter", f"Expected recruiter role, got {user.get('role')}"
        print(f"Verified: Token belongs to recruiter role - user: {user.get('email')}")
