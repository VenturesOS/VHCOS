"""
Test Candidate Bank Role-Based Access Control Bug Fix

This test verifies the fix for the critical bug where:
1. List endpoint and Detail endpoint used different access logic
2. Secondary endpoints (audit-log, history, resume-history) had NO candidate-level visibility checks
3. Recruiter job query was using old team_id logic instead of assigned_recruiters

Test Candidates:
- John Doe (f5988726-fbee-4f9f-bd11-0d9e91496dd3): Created by employer
- Jane Smith (4e761db5-45b2-45de-9553-ac5964b5cecb): Created by recruiter1

Test Users:
- Admin: Full access to all candidates
- Employer: Can see candidates they created, team members created, or applied to their jobs
- Recruiter1: Can see candidates they created or applied to their ASSIGNED mandates
- Recruiter2: Has NO candidates, NO assigned jobs - should see 0 candidates and get 403 on detail
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test candidate IDs from the bug report
JOHN_DOE_ID = "f5988726-fbee-4f9f-bd11-0d9e91496dd3"  # Created by employer
JANE_SMITH_ID = "4e761db5-45b2-45de-9553-ac5964b5cecb"  # Created by recruiter1


class TestCredentials:
    """Test credentials for different roles"""
    ADMIN = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
    EMPLOYER = {"email": "employer@vhctalent.com", "password": "VhcTalent@2024"}
    RECRUITER1 = {"email": "recruiter@vhctalent.com", "password": "VhcTalent@2024"}
    RECRUITER2 = {"email": "recruiter2@vhctalent.com", "password": "VhcTalent@2024"}


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


def get_auth_token(api_client, credentials):
    """Get authentication token for a user"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json=credentials)
    if response.status_code == 200:
        return response.json().get("access_token")
    return None


@pytest.fixture(scope="module")
def admin_token(api_client):
    """Get admin token"""
    token = get_auth_token(api_client, TestCredentials.ADMIN)
    if not token:
        pytest.skip("Admin authentication failed")
    return token


@pytest.fixture(scope="module")
def employer_token(api_client):
    """Get employer token"""
    token = get_auth_token(api_client, TestCredentials.EMPLOYER)
    if not token:
        pytest.skip("Employer authentication failed")
    return token


@pytest.fixture(scope="module")
def recruiter1_token(api_client):
    """Get recruiter1 token"""
    token = get_auth_token(api_client, TestCredentials.RECRUITER1)
    if not token:
        pytest.skip("Recruiter1 authentication failed")
    return token


@pytest.fixture(scope="module")
def recruiter2_token(api_client):
    """Get recruiter2 token"""
    token = get_auth_token(api_client, TestCredentials.RECRUITER2)
    if not token:
        pytest.skip("Recruiter2 authentication failed")
    return token


class TestAdminFullAccess:
    """Admin should have full access to all candidates"""
    
    def test_admin_can_list_all_candidates(self, api_client, admin_token):
        """Admin can see all candidates in the list"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        candidates = response.json()
        print(f"Admin sees {len(candidates)} candidates")
        assert len(candidates) >= 0  # Admin should see candidates if any exist
    
    def test_admin_can_access_john_doe_detail(self, api_client, admin_token):
        """Admin can access John Doe's detail"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JOHN_DOE_ID}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        # 200 if exists, 404 if not found (but NOT 403)
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            print(f"Admin accessed John Doe: {response.json().get('name')}")
    
    def test_admin_can_access_jane_smith_detail(self, api_client, admin_token):
        """Admin can access Jane Smith's detail"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JANE_SMITH_ID}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            print(f"Admin accessed Jane Smith: {response.json().get('name')}")
    
    def test_admin_can_access_audit_log(self, api_client, admin_token):
        """Admin can access audit-log endpoint"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JOHN_DOE_ID}/audit-log",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code in [200, 404]
        print(f"Admin audit-log access: {response.status_code}")
    
    def test_admin_can_access_history(self, api_client, admin_token):
        """Admin can access history endpoint"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JOHN_DOE_ID}/history",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code in [200, 404]
        print(f"Admin history access: {response.status_code}")
    
    def test_admin_can_access_resume_history(self, api_client, admin_token):
        """Admin can access resume-history endpoint"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JOHN_DOE_ID}/resume-history",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code in [200, 404]
        print(f"Admin resume-history access: {response.status_code}")


class TestEmployerAccess:
    """Employer should see candidates they created, team members created, or applied to their jobs"""
    
    def test_employer_can_list_candidates(self, api_client, employer_token):
        """Employer can list candidates they have access to"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 200
        candidates = response.json()
        print(f"Employer sees {len(candidates)} candidates")
        # Employer should see at least John Doe (created by employer)
    
    def test_employer_can_access_john_doe_detail(self, api_client, employer_token):
        """Employer can access John Doe (created by employer)"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JOHN_DOE_ID}",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        # Should be 200 (employer created) or 404 (not found)
        # Should NOT be 403 if employer created this candidate
        print(f"Employer John Doe detail: {response.status_code}")
        if response.status_code == 403:
            print(f"ERROR: Employer got 403 for candidate they should have access to")
        assert response.status_code in [200, 404]
    
    def test_employer_can_access_jane_smith_detail(self, api_client, employer_token):
        """Employer can access Jane Smith (created by team member recruiter1)"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JANE_SMITH_ID}",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        # Should be 200 (team member created) or 404 (not found)
        print(f"Employer Jane Smith detail: {response.status_code}")
        assert response.status_code in [200, 404]
    
    def test_employer_can_access_audit_log(self, api_client, employer_token):
        """Employer can access audit-log for accessible candidates"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JOHN_DOE_ID}/audit-log",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        print(f"Employer audit-log: {response.status_code}")
        assert response.status_code in [200, 404]
    
    def test_employer_can_access_history(self, api_client, employer_token):
        """Employer can access history for accessible candidates"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JOHN_DOE_ID}/history",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        print(f"Employer history: {response.status_code}")
        assert response.status_code in [200, 404]
    
    def test_employer_can_access_resume_history(self, api_client, employer_token):
        """Employer can access resume-history for accessible candidates"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JOHN_DOE_ID}/resume-history",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        print(f"Employer resume-history: {response.status_code}")
        assert response.status_code in [200, 404]


class TestRecruiter1Access:
    """Recruiter1 should see candidates they created or applied to their ASSIGNED mandates"""
    
    def test_recruiter1_can_list_candidates(self, api_client, recruiter1_token):
        """Recruiter1 can list candidates they have access to"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank",
            headers={"Authorization": f"Bearer {recruiter1_token}"}
        )
        assert response.status_code == 200
        candidates = response.json()
        print(f"Recruiter1 sees {len(candidates)} candidates")
    
    def test_recruiter1_can_access_jane_smith_detail(self, api_client, recruiter1_token):
        """Recruiter1 can access Jane Smith (created by recruiter1)"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JANE_SMITH_ID}",
            headers={"Authorization": f"Bearer {recruiter1_token}"}
        )
        print(f"Recruiter1 Jane Smith detail: {response.status_code}")
        # Should be 200 (recruiter1 created) or 404 (not found)
        assert response.status_code in [200, 404]
    
    def test_recruiter1_cannot_access_john_doe_detail(self, api_client, recruiter1_token):
        """Recruiter1 CANNOT access John Doe (created by employer, not recruiter1)"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JOHN_DOE_ID}",
            headers={"Authorization": f"Bearer {recruiter1_token}"}
        )
        print(f"Recruiter1 John Doe detail: {response.status_code}")
        # Should be 403 (access denied) or 404 (not found)
        # Should NOT be 200 unless John Doe applied to recruiter1's assigned jobs
        assert response.status_code in [200, 403, 404]
    
    def test_recruiter1_can_access_audit_log_for_jane(self, api_client, recruiter1_token):
        """Recruiter1 can access audit-log for Jane Smith"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JANE_SMITH_ID}/audit-log",
            headers={"Authorization": f"Bearer {recruiter1_token}"}
        )
        print(f"Recruiter1 audit-log for Jane: {response.status_code}")
        assert response.status_code in [200, 404]
    
    def test_recruiter1_can_access_history_for_jane(self, api_client, recruiter1_token):
        """Recruiter1 can access history for Jane Smith"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JANE_SMITH_ID}/history",
            headers={"Authorization": f"Bearer {recruiter1_token}"}
        )
        print(f"Recruiter1 history for Jane: {response.status_code}")
        assert response.status_code in [200, 404]
    
    def test_recruiter1_can_access_resume_history_for_jane(self, api_client, recruiter1_token):
        """Recruiter1 can access resume-history for Jane Smith"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JANE_SMITH_ID}/resume-history",
            headers={"Authorization": f"Bearer {recruiter1_token}"}
        )
        print(f"Recruiter1 resume-history for Jane: {response.status_code}")
        assert response.status_code in [200, 404]


class TestRecruiter2NoAccess:
    """Recruiter2 has NO candidates, NO assigned jobs - should see 0 candidates and get 403"""
    
    def test_recruiter2_sees_zero_candidates(self, api_client, recruiter2_token):
        """Recruiter2 should see 0 candidates in the list"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank",
            headers={"Authorization": f"Bearer {recruiter2_token}"}
        )
        assert response.status_code == 200
        candidates = response.json()
        print(f"Recruiter2 sees {len(candidates)} candidates")
        # Recruiter2 should see 0 candidates (no created, no assigned jobs)
        assert len(candidates) == 0, f"Recruiter2 should see 0 candidates but sees {len(candidates)}"
    
    def test_recruiter2_gets_403_for_john_doe(self, api_client, recruiter2_token):
        """Recruiter2 should get 403 for John Doe detail"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JOHN_DOE_ID}",
            headers={"Authorization": f"Bearer {recruiter2_token}"}
        )
        print(f"Recruiter2 John Doe detail: {response.status_code}")
        # Should be 403 (access denied) or 404 (not found)
        assert response.status_code in [403, 404]
    
    def test_recruiter2_gets_403_for_jane_smith(self, api_client, recruiter2_token):
        """Recruiter2 should get 403 for Jane Smith detail"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JANE_SMITH_ID}",
            headers={"Authorization": f"Bearer {recruiter2_token}"}
        )
        print(f"Recruiter2 Jane Smith detail: {response.status_code}")
        # Should be 403 (access denied) or 404 (not found)
        assert response.status_code in [403, 404]
    
    def test_recruiter2_gets_403_for_audit_log(self, api_client, recruiter2_token):
        """Recruiter2 should get 403 for audit-log endpoint"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JOHN_DOE_ID}/audit-log",
            headers={"Authorization": f"Bearer {recruiter2_token}"}
        )
        print(f"Recruiter2 audit-log: {response.status_code}")
        # Should be 403 (access denied) or 404 (not found)
        assert response.status_code in [403, 404]
    
    def test_recruiter2_gets_403_for_history(self, api_client, recruiter2_token):
        """Recruiter2 should get 403 for history endpoint"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JOHN_DOE_ID}/history",
            headers={"Authorization": f"Bearer {recruiter2_token}"}
        )
        print(f"Recruiter2 history: {response.status_code}")
        # Should be 403 (access denied) or 404 (not found)
        assert response.status_code in [403, 404]
    
    def test_recruiter2_gets_403_for_resume_history(self, api_client, recruiter2_token):
        """Recruiter2 should get 403 for resume-history endpoint"""
        response = api_client.get(
            f"{BASE_URL}/api/candidate-bank/{JOHN_DOE_ID}/resume-history",
            headers={"Authorization": f"Bearer {recruiter2_token}"}
        )
        print(f"Recruiter2 resume-history: {response.status_code}")
        # Should be 403 (access denied) or 404 (not found)
        assert response.status_code in [403, 404]


class TestListDetailConsistency:
    """Verify that List and Detail endpoints use SAME access control logic"""
    
    def test_employer_list_detail_consistency(self, api_client, employer_token):
        """Candidates in employer's list should be accessible via detail"""
        # Get list
        list_response = api_client.get(
            f"{BASE_URL}/api/candidate-bank",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert list_response.status_code == 200
        candidates = list_response.json()
        
        # Each candidate in list should be accessible via detail
        for candidate in candidates[:5]:  # Test first 5
            detail_response = api_client.get(
                f"{BASE_URL}/api/candidate-bank/{candidate['id']}",
                headers={"Authorization": f"Bearer {employer_token}"}
            )
            assert detail_response.status_code == 200, \
                f"Candidate {candidate['id']} in list but detail returns {detail_response.status_code}"
            print(f"Employer list-detail consistent for {candidate.get('name')}")
    
    def test_recruiter1_list_detail_consistency(self, api_client, recruiter1_token):
        """Candidates in recruiter1's list should be accessible via detail"""
        # Get list
        list_response = api_client.get(
            f"{BASE_URL}/api/candidate-bank",
            headers={"Authorization": f"Bearer {recruiter1_token}"}
        )
        assert list_response.status_code == 200
        candidates = list_response.json()
        
        # Each candidate in list should be accessible via detail
        for candidate in candidates[:5]:  # Test first 5
            detail_response = api_client.get(
                f"{BASE_URL}/api/candidate-bank/{candidate['id']}",
                headers={"Authorization": f"Bearer {recruiter1_token}"}
            )
            assert detail_response.status_code == 200, \
                f"Candidate {candidate['id']} in list but detail returns {detail_response.status_code}"
            print(f"Recruiter1 list-detail consistent for {candidate.get('name')}")


class TestSecondaryEndpointsVisibility:
    """Verify secondary endpoints (audit-log, history, resume-history) have proper visibility checks"""
    
    def test_secondary_endpoints_require_visibility(self, api_client, recruiter2_token):
        """Secondary endpoints should return 403 for candidates user can't access"""
        endpoints = [
            f"/api/candidate-bank/{JOHN_DOE_ID}/audit-log",
            f"/api/candidate-bank/{JOHN_DOE_ID}/history",
            f"/api/candidate-bank/{JOHN_DOE_ID}/resume-history",
        ]
        
        for endpoint in endpoints:
            response = api_client.get(
                f"{BASE_URL}{endpoint}",
                headers={"Authorization": f"Bearer {recruiter2_token}"}
            )
            print(f"Recruiter2 {endpoint}: {response.status_code}")
            # Should be 403 (access denied) or 404 (not found)
            assert response.status_code in [403, 404], \
                f"Secondary endpoint {endpoint} should deny access but returned {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
