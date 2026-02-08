"""
VHC Talent OS - Bug Reports & Registration Restriction Tests
Testing:
1. POST /api/auth/register - Only candidate role allowed (employer/recruiter blocked)
2. Bug Reports CRUD - /api/bug-reports endpoints
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
EMPLOYER_EMAIL = "employer@vhctalent.com"
EMPLOYER_PASSWORD = "VhcTalent@2024"
RECRUITER_EMAIL = "recruiter@vhctalent.com"
RECRUITER_PASSWORD = "VhcTalent@2024"


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
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def employer_token(api_client):
    """Get employer authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": EMPLOYER_EMAIL,
        "password": EMPLOYER_PASSWORD
    })
    assert response.status_code == 200, f"Employer login failed: {response.text}"
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def recruiter_token(api_client):
    """Get recruiter authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": RECRUITER_EMAIL,
        "password": RECRUITER_PASSWORD
    })
    assert response.status_code == 200, f"Recruiter login failed: {response.text}"
    return response.json().get("access_token")


class TestRegistrationRestriction:
    """Test self-registration is restricted to candidate role only"""

    def test_register_employer_blocked(self, api_client):
        """POST /api/auth/register with role=employer should return 403"""
        response = api_client.post(f"{BASE_URL}/api/auth/register", json={
            "name": "Test Employer",
            "email": f"test_employer_{uuid.uuid4().hex[:8]}@example.com",
            "password": "TestPassword123",
            "role": "employer"
        })
        assert response.status_code == 403, f"Expected 403 for employer registration, got {response.status_code}: {response.text}"
        data = response.json()
        assert "Only candidate registration is allowed" in data.get("detail", "")
        print("✅ Employer self-registration correctly blocked with 403")

    def test_register_recruiter_blocked(self, api_client):
        """POST /api/auth/register with role=recruiter should return 403"""
        response = api_client.post(f"{BASE_URL}/api/auth/register", json={
            "name": "Test Recruiter",
            "email": f"test_recruiter_{uuid.uuid4().hex[:8]}@example.com",
            "password": "TestPassword123",
            "role": "recruiter"
        })
        assert response.status_code == 403, f"Expected 403 for recruiter registration, got {response.status_code}: {response.text}"
        data = response.json()
        assert "Only candidate registration is allowed" in data.get("detail", "")
        print("✅ Recruiter self-registration correctly blocked with 403")

    def test_register_admin_blocked(self, api_client):
        """POST /api/auth/register with role=admin should return 403"""
        response = api_client.post(f"{BASE_URL}/api/auth/register", json={
            "name": "Test Admin",
            "email": f"test_admin_{uuid.uuid4().hex[:8]}@example.com",
            "password": "TestPassword123",
            "role": "admin"
        })
        assert response.status_code == 403, f"Expected 403 for admin registration, got {response.status_code}: {response.text}"
        print("✅ Admin self-registration correctly blocked with 403")

    def test_register_candidate_allowed(self, api_client):
        """POST /api/auth/register with role=candidate should succeed"""
        unique_email = f"test_candidate_{uuid.uuid4().hex[:8]}@example.com"
        response = api_client.post(f"{BASE_URL}/api/auth/register", json={
            "name": "Test Candidate",
            "email": unique_email,
            "password": "TestPassword123",
            "role": "candidate"
        })
        assert response.status_code == 200, f"Expected 200 for candidate registration, got {response.status_code}: {response.text}"
        data = response.json()
        assert "access_token" in data, "Response should contain access_token"
        assert data["user"]["email"] == unique_email
        assert data["user"]["role"] == "candidate"
        print(f"✅ Candidate registration succeeded for {unique_email}")


class TestBugReportsAPI:
    """Test Bug Reports CRUD endpoints"""

    def test_create_bug_report_employer(self, api_client, employer_token):
        """POST /api/bug-reports creates a bug report (employer auth)"""
        response = api_client.post(
            f"{BASE_URL}/api/bug-reports",
            headers={"Authorization": f"Bearer {employer_token}"},
            json={
                "title": "TEST_Bug Report from Employer",
                "description": "This is a test bug report created by employer",
                "category": "ui",
                "severity": "medium"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["title"] == "TEST_Bug Report from Employer"
        assert data["category"] == "ui"
        assert data["severity"] == "medium"
        assert data["status"] == "open"
        assert data["reported_by_role"] == "employer"
        print(f"✅ Bug report created successfully by employer: {data['id']}")
        return data["id"]

    def test_create_bug_report_recruiter(self, api_client, recruiter_token):
        """POST /api/bug-reports creates a bug report (recruiter auth)"""
        response = api_client.post(
            f"{BASE_URL}/api/bug-reports",
            headers={"Authorization": f"Bearer {recruiter_token}"},
            json={
                "title": "TEST_Bug Report from Recruiter",
                "description": "This is a test bug report created by recruiter",
                "category": "performance",
                "severity": "high"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["title"] == "TEST_Bug Report from Recruiter"
        assert data["reported_by_role"] == "recruiter"
        print(f"✅ Bug report created successfully by recruiter: {data['id']}")
        return data["id"]

    def test_get_bug_reports_employer_sees_own(self, api_client, employer_token):
        """GET /api/bug-reports - employer sees only their own reports"""
        response = api_client.get(
            f"{BASE_URL}/api/bug-reports",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        # Verify all reports belong to employer
        for report in data:
            assert report["reported_by_role"] == "employer", f"Employer should only see own reports, got {report['reported_by_role']}"
        print(f"✅ Employer sees only their own {len(data)} bug reports")

    def test_get_bug_reports_admin_sees_all(self, api_client, admin_token):
        """GET /api/bug-reports - admin sees all reports"""
        response = api_client.get(
            f"{BASE_URL}/api/bug-reports",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        # Admin should see reports from multiple roles
        roles_seen = set(report["reported_by_role"] for report in data)
        print(f"✅ Admin sees all bug reports: {len(data)} total, roles: {roles_seen}")

    def test_get_bug_reports_stats_admin_only(self, api_client, admin_token, employer_token):
        """GET /api/bug-reports/stats/summary - admin only"""
        # Admin can access stats
        response = api_client.get(
            f"{BASE_URL}/api/bug-reports/stats/summary",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200 for admin, got {response.status_code}: {response.text}"
        data = response.json()
        assert "total" in data
        assert "open" in data
        assert "in_progress" in data
        assert "resolved" in data
        assert "closed" in data
        print(f"✅ Admin can access stats: {data}")

        # Employer cannot access stats
        response = api_client.get(
            f"{BASE_URL}/api/bug-reports/stats/summary",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 403, f"Expected 403 for employer, got {response.status_code}: {response.text}"
        print("✅ Employer correctly blocked from stats endpoint")

    def test_update_bug_report_admin_only(self, api_client, admin_token, employer_token):
        """PUT /api/bug-reports/{id} - admin only can update status/notes"""
        # First create a report
        create_response = api_client.post(
            f"{BASE_URL}/api/bug-reports",
            headers={"Authorization": f"Bearer {employer_token}"},
            json={
                "title": "TEST_Report for Update Test",
                "description": "Testing update functionality",
                "category": "general",
                "severity": "low"
            }
        )
        assert create_response.status_code == 200
        report_id = create_response.json()["id"]

        # Employer cannot update (should be 403)
        response = api_client.put(
            f"{BASE_URL}/api/bug-reports/{report_id}?status=in_progress",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 403, f"Expected 403 for employer update, got {response.status_code}: {response.text}"
        print("✅ Employer correctly blocked from updating bug reports")

        # Admin can update
        response = api_client.put(
            f"{BASE_URL}/api/bug-reports/{report_id}?status=in_progress&admin_notes=Investigating",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200 for admin update, got {response.status_code}: {response.text}"
        print(f"✅ Admin successfully updated bug report {report_id}")

        # Verify update
        get_response = api_client.get(
            f"{BASE_URL}/api/bug-reports/{report_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert get_response.status_code == 200
        updated_data = get_response.json()
        assert updated_data["status"] == "in_progress"
        assert updated_data["admin_notes"] == "Investigating"
        print("✅ Bug report update verified")

    def test_bug_reports_requires_auth(self, api_client):
        """Bug reports endpoints require authentication"""
        # List reports without auth
        response = api_client.get(f"{BASE_URL}/api/bug-reports")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ GET /api/bug-reports requires authentication")

        # Create report without auth
        response = api_client.post(f"{BASE_URL}/api/bug-reports", json={
            "title": "Test",
            "description": "Test"
        })
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ POST /api/bug-reports requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
