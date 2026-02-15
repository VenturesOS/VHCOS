"""
Test Contact Form API Endpoints
Features:
- Contact form submission (public)
- Admin contact submissions list
- Admin status update
- Admin delete

Backend: /app/backend/routes/contact.py
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "http://localhost:8001"

ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


class TestContactAPI:
    """Contact Form API Tests"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json().get("access_token")
    
    @pytest.fixture
    def test_submission_id(self, admin_token):
        """Create a test submission and return its ID, clean up after test"""
        # Create a unique test submission
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "full_name": f"TEST_Contact_User_{unique_id}",
            "email": f"test_contact_{unique_id}@example.com",
            "company_name": "TEST Company",
            "phone": "+1234567890",
            "service_interest": "executive-search",
            "message": "This is a test message for automated testing"
        }
        
        # Submit the contact form
        response = requests.post(f"{BASE_URL}/api/contact-submission", json=payload)
        assert response.status_code == 200, f"Failed to create test submission: {response.text}"
        
        # Get submission ID from admin list
        headers = {"Authorization": f"Bearer {admin_token}"}
        list_response = requests.get(f"{BASE_URL}/api/contact-submissions", headers=headers)
        assert list_response.status_code == 200, f"Failed to list submissions: {list_response.text}"
        
        submissions = list_response.json().get("submissions", [])
        # Find our test submission by email
        test_submission = next(
            (s for s in submissions if s.get("email") == payload["email"]),
            None
        )
        
        assert test_submission is not None, "Could not find the test submission"
        submission_id = test_submission.get("id")
        
        yield submission_id
        
        # Cleanup - try to delete after test
        try:
            requests.delete(
                f"{BASE_URL}/api/contact-submissions/{submission_id}",
                headers=headers
            )
        except:
            pass

    # Test 1: Contact form submission (public endpoint)
    def test_contact_form_submission(self):
        """POST /api/contact-submission - Submit contact form"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "full_name": f"TEST_John_Doe_{unique_id}",
            "email": f"john_{unique_id}@example.com",
            "company_name": "Acme Corp",
            "phone": "+1 555 123 4567",
            "service_interest": "executive-search",
            "message": "Interested in executive search services for our startup."
        }
        
        response = requests.post(f"{BASE_URL}/api/contact-submission", json=payload)
        
        assert response.status_code == 200, f"Contact submission failed: {response.text}"
        data = response.json()
        assert "message" in data
        assert "Thank you" in data["message"]
        print(f"PASS: Contact form submission successful - {data['message']}")

    # Test 2: Contact form submission - validation
    def test_contact_form_validation(self):
        """POST /api/contact-submission - Validate required fields"""
        # Missing required fields
        payload = {
            "full_name": "John",
            # Missing: email, service_interest, message
        }
        
        response = requests.post(f"{BASE_URL}/api/contact-submission", json=payload)
        
        assert response.status_code == 422, f"Expected validation error, got: {response.status_code}"
        print("PASS: Contact form validation works - missing fields rejected")

    # Test 3: Admin - Get all submissions
    def test_admin_get_submissions(self, admin_token):
        """GET /api/contact-submissions - Admin only"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.get(f"{BASE_URL}/api/contact-submissions", headers=headers)
        
        assert response.status_code == 200, f"Failed to get submissions: {response.text}"
        data = response.json()
        assert "submissions" in data
        assert "total" in data
        assert isinstance(data["submissions"], list)
        print(f"PASS: Admin get submissions - found {data['total']} submissions")

    # Test 4: Admin - Filter by status
    def test_admin_filter_by_status(self, admin_token, test_submission_id):
        """GET /api/contact-submissions?status=new - Filter by status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.get(f"{BASE_URL}/api/contact-submissions?status=new", headers=headers)
        
        assert response.status_code == 200, f"Failed to filter submissions: {response.text}"
        data = response.json()
        
        # All returned submissions should have status 'new'
        for sub in data["submissions"]:
            assert sub["status"] == "new", f"Found submission with status {sub['status']}, expected 'new'"
        
        print(f"PASS: Admin filter by status - {len(data['submissions'])} 'new' submissions")

    # Test 5: Admin - Update status
    def test_admin_update_status(self, admin_token, test_submission_id):
        """PUT /api/contact-submissions/{id}/status - Update submission status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Update to 'reviewed'
        response = requests.put(
            f"{BASE_URL}/api/contact-submissions/{test_submission_id}/status?new_status=reviewed",
            headers=headers
        )
        
        assert response.status_code == 200, f"Failed to update status: {response.text}"
        data = response.json()
        assert "message" in data
        assert "reviewed" in data["message"].lower()
        
        # Verify the update by getting all submissions and checking
        list_response = requests.get(f"{BASE_URL}/api/contact-submissions", headers=headers)
        submissions = list_response.json().get("submissions", [])
        updated = next((s for s in submissions if s.get("id") == test_submission_id), None)
        
        assert updated is not None, "Could not find updated submission"
        assert updated.get("status") == "reviewed", f"Status not updated, got: {updated.get('status')}"
        
        print(f"PASS: Admin status update - submission {test_submission_id[:8]}... -> reviewed")

    # Test 6: Admin - Invalid status
    def test_admin_invalid_status(self, admin_token, test_submission_id):
        """PUT /api/contact-submissions/{id}/status - Invalid status should fail"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.put(
            f"{BASE_URL}/api/contact-submissions/{test_submission_id}/status?new_status=invalid_status",
            headers=headers
        )
        
        assert response.status_code == 400, f"Expected 400 for invalid status, got: {response.status_code}"
        print("PASS: Admin invalid status rejected correctly")

    # Test 7: Admin - Delete submission
    def test_admin_delete_submission(self, admin_token):
        """DELETE /api/contact-submissions/{id} - Delete submission"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # First create a submission to delete
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "full_name": f"TEST_Delete_User_{unique_id}",
            "email": f"delete_test_{unique_id}@example.com",
            "service_interest": "other",
            "message": "To be deleted"
        }
        
        requests.post(f"{BASE_URL}/api/contact-submission", json=payload)
        
        # Get the submission ID
        list_response = requests.get(f"{BASE_URL}/api/contact-submissions", headers=headers)
        submissions = list_response.json().get("submissions", [])
        test_sub = next((s for s in submissions if s.get("email") == payload["email"]), None)
        
        assert test_sub is not None, "Could not find test submission for deletion"
        sub_id = test_sub["id"]
        
        # Now delete it
        response = requests.delete(f"{BASE_URL}/api/contact-submissions/{sub_id}", headers=headers)
        
        assert response.status_code == 200, f"Failed to delete submission: {response.text}"
        data = response.json()
        assert "deleted" in data["message"].lower() or "message" in data
        
        # Verify deletion
        list_response2 = requests.get(f"{BASE_URL}/api/contact-submissions", headers=headers)
        submissions2 = list_response2.json().get("submissions", [])
        deleted_sub = next((s for s in submissions2 if s.get("id") == sub_id), None)
        
        assert deleted_sub is None, "Submission still exists after deletion"
        print(f"PASS: Admin delete submission - {sub_id[:8]}... deleted successfully")

    # Test 8: Non-admin cannot access admin endpoints
    def test_non_admin_access_denied(self):
        """GET /api/contact-submissions - Non-admin should be denied"""
        # Get employer token
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "ajit@vhc.in", "password": "12345678"}
        )
        
        if response.status_code != 200:
            pytest.skip("Employer user not available for testing")
        
        employer_token = response.json().get("access_token")
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        # Try to access admin endpoint
        response = requests.get(f"{BASE_URL}/api/contact-submissions", headers=headers)
        
        assert response.status_code == 403, f"Expected 403 for non-admin, got: {response.status_code}"
        print("PASS: Non-admin access correctly denied")

    # Test 9: Unauthenticated cannot access admin endpoints
    def test_unauthenticated_access_denied(self):
        """GET /api/contact-submissions - Unauthenticated should be denied"""
        response = requests.get(f"{BASE_URL}/api/contact-submissions")
        
        assert response.status_code == 401, f"Expected 401 for unauthenticated, got: {response.status_code}"
        print("PASS: Unauthenticated access correctly denied")

    # Test 10: Delete non-existent submission
    def test_delete_nonexistent(self, admin_token):
        """DELETE /api/contact-submissions/{id} - Non-existent ID should return 404"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        fake_id = str(uuid.uuid4())
        
        response = requests.delete(f"{BASE_URL}/api/contact-submissions/{fake_id}", headers=headers)
        
        assert response.status_code == 404, f"Expected 404 for non-existent ID, got: {response.status_code}"
        print("PASS: Delete non-existent returns 404 correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
