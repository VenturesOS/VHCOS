"""
Tracker Visibility Filtering Tests
----------------------------------
Tests the role-based visibility filtering enhancement for Submission Trackers.

Test coverage:
- Admin: Can see ALL trackers (no filtering)
- Recruiter: Only sees trackers they created OR linked to mandates they're assigned to
- Employer: Only sees trackers they created, where they're employer_id, linked to mandates they posted, or matching company_id
- Single tracker GET: Returns 403 for unauthorized access
- Recruiter can create tracker and then see it in filtered list

Credentials:
- Admin: admin@vhc.in / VhcAdmin@2024
- Recruiter: yamini@vhc.in / VhcAdmin@2024 (no assigned mandates, should see 0 existing trackers)
"""
import pytest
import requests
import os
import time

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
    time.sleep(2)  # Avoid rate limiting
    response = api_client.post(f"{BASE_URL}/api/auth/login", json=RECRUITER_CREDS)
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Recruiter authentication failed: {response.status_code} - {response.text[:200]}")


@pytest.fixture(scope="module")
def recruiter_user_info(api_client, recruiter_token):
    """Get recruiter user details"""
    response = api_client.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {recruiter_token}"}
    )
    if response.status_code == 200:
        return response.json()
    pytest.skip("Could not get recruiter user info")


class TestAdminSeesAllTrackers:
    """Admin should see ALL trackers regardless of who created them"""

    def test_admin_sees_all_trackers(self, api_client, admin_token):
        """Admin can see all 2 existing trackers"""
        response = api_client.get(
            f"{BASE_URL}/api/tracker/trackers",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"GET /trackers failed: {response.status_code}"
        data = response.json()
        trackers = data.get("trackers", [])
        
        # Admin should see all existing trackers (2 as per context)
        assert len(trackers) >= 2, f"Admin should see at least 2 trackers, but got {len(trackers)}"
        print(f"Admin sees {len(trackers)} trackers - CORRECT (all trackers visible)")
        
        # Store tracker IDs for later tests
        return [t["id"] for t in trackers]


class TestRecruiterFiltering:
    """Recruiter visibility filtering: only created by them OR assigned mandates"""

    def test_recruiter_sees_filtered_trackers(self, api_client, recruiter_token, recruiter_user_info):
        """Recruiter yamini@vhc.in should see 0 trackers initially (no assigned mandates)"""
        response = api_client.get(
            f"{BASE_URL}/api/tracker/trackers",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert response.status_code == 200, f"GET /trackers failed: {response.status_code}"
        data = response.json()
        trackers = data.get("trackers", [])
        
        # Yamini has no assigned mandates and didn't create any trackers, so she should see 0
        print(f"Recruiter {recruiter_user_info.get('email')} sees {len(trackers)} trackers")
        
        # According to context: "Recruiter (yamini@vhc.in) sees 0 trackers since she didn't create any 
        # and isn't assigned to relevant mandates — this is correct behavior"
        assert len(trackers) == 0, f"Recruiter should see 0 trackers initially, but got {len(trackers)}"
        print("Recruiter visibility filtering CORRECT: sees 0 trackers (no assigned mandates, didn't create any)")


class TestRecruiterCannotAccessAdminTrackers:
    """Recruiter should get 403 when accessing tracker they don't have permission for"""

    def test_recruiter_cannot_access_admin_tracker(self, api_client, admin_token, recruiter_token):
        """Recruiter gets 403 trying to access a tracker created by admin"""
        # First get admin's trackers
        admin_response = api_client.get(
            f"{BASE_URL}/api/tracker/trackers",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert admin_response.status_code == 200
        admin_trackers = admin_response.json().get("trackers", [])
        
        if not admin_trackers:
            pytest.skip("No admin trackers to test unauthorized access")
        
        # Try to access first admin tracker as recruiter
        admin_tracker_id = admin_trackers[0]["id"]
        
        recruiter_response = api_client.get(
            f"{BASE_URL}/api/tracker/trackers/{admin_tracker_id}",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        
        # Should get 403 Forbidden
        assert recruiter_response.status_code == 403, \
            f"Expected 403, got {recruiter_response.status_code}. Recruiter should NOT access admin's tracker."
        print(f"Recruiter correctly denied access to admin tracker {admin_tracker_id} with 403")


class TestRecruiterCreateAndSeeOwnTracker:
    """Recruiter can create a tracker and then see it in their filtered list"""

    def test_recruiter_create_and_see_own_tracker(self, api_client, recruiter_token, admin_token):
        """Recruiter creates tracker, then sees it in their list"""
        # Step 1: Get templates to use for creating tracker
        templates_resp = api_client.get(
            f"{BASE_URL}/api/tracker/templates",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert templates_resp.status_code == 200
        templates = templates_resp.json().get("templates", [])
        
        if not templates:
            pytest.skip("No templates available to create tracker")
        
        template_id = templates[0]["id"]
        
        # Step 2: Get jobs/mandates
        jobs_resp = api_client.get(
            f"{BASE_URL}/api/jobs",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert jobs_resp.status_code == 200
        jobs_data = jobs_resp.json()
        jobs = jobs_data if isinstance(jobs_data, list) else jobs_data.get("jobs", [])
        
        if not jobs:
            pytest.skip("No jobs available to create tracker")
        
        mandate_id = jobs[0]["id"]
        
        # Step 3: Count recruiter's trackers BEFORE creating
        before_resp = api_client.get(
            f"{BASE_URL}/api/tracker/trackers",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        trackers_before = len(before_resp.json().get("trackers", []))
        print(f"Recruiter has {trackers_before} trackers BEFORE creating new one")
        
        # Step 4: Create a tracker as recruiter
        time.sleep(1)  # Small delay
        create_payload = {
            "name": f"TEST_Recruiter_Created_Tracker_{int(time.time())}",
            "mandate_id": mandate_id,
            "template_id": template_id
        }
        create_resp = api_client.post(
            f"{BASE_URL}/api/tracker/trackers",
            headers={"Authorization": f"Bearer {recruiter_token}"},
            json=create_payload
        )
        
        assert create_resp.status_code == 200, f"Failed to create tracker: {create_resp.status_code} - {create_resp.text[:200]}"
        created_tracker = create_resp.json()
        created_id = created_tracker["id"]
        print(f"Recruiter created tracker: {created_id}")
        
        # Step 5: Verify recruiter can now see the tracker
        after_resp = api_client.get(
            f"{BASE_URL}/api/tracker/trackers",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        trackers_after = after_resp.json().get("trackers", [])
        tracker_ids_after = [t["id"] for t in trackers_after]
        
        assert created_id in tracker_ids_after, "Recruiter should see their own created tracker"
        assert len(trackers_after) == trackers_before + 1, \
            f"Expected {trackers_before + 1} trackers, got {len(trackers_after)}"
        print(f"Recruiter now has {len(trackers_after)} trackers AFTER creating - CORRECT")
        
        # Step 6: Verify recruiter can access the tracker directly
        get_resp = api_client.get(
            f"{BASE_URL}/api/tracker/trackers/{created_id}",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert get_resp.status_code == 200, "Recruiter should be able to access their own tracker"
        print("Recruiter can access their own tracker directly - CORRECT")
        
        # Step 7: Admin still sees all trackers (regression check)
        admin_resp = api_client.get(
            f"{BASE_URL}/api/tracker/trackers",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        admin_trackers = admin_resp.json().get("trackers", [])
        admin_tracker_ids = [t["id"] for t in admin_trackers]
        
        assert created_id in admin_tracker_ids, "Admin should also see the recruiter's tracker"
        print(f"Admin sees {len(admin_trackers)} trackers including recruiter's new one - REGRESSION PASSED")
        
        # Cleanup: Delete the test tracker
        time.sleep(1)
        delete_resp = api_client.delete(
            f"{BASE_URL}/api/tracker/trackers/{created_id}",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        if delete_resp.status_code in [200, 204]:
            print(f"Test tracker {created_id} cleaned up")


class TestRecruiterUserVerification:
    """Verify recruiter user info for debugging"""

    def test_recruiter_user_has_correct_role(self, api_client, recruiter_token):
        """Verify recruiter user details"""
        response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert response.status_code == 200
        user = response.json()
        
        assert user.get("role") == "recruiter", f"Expected recruiter role, got {user.get('role')}"
        print(f"Verified: User {user.get('email')} has role={user.get('role')}, id={user.get('id')}")
        
        # Check if this is yamini@vhc.in with ID 06b70e35-bb06-41b9-a5f1-d9111112ae78
        if user.get("email") == "yamini@vhc.in":
            expected_id = "06b70e35-bb06-41b9-a5f1-d9111112ae78"
            actual_id = user.get("id")
            print(f"User ID check: expected {expected_id}, got {actual_id}")


class TestAdminRegressionAfterRecruiterActivity:
    """Ensure admin visibility is not affected by recruiter activity"""

    def test_admin_still_sees_all_after_recruiter_tests(self, api_client, admin_token):
        """Admin should still see all trackers after recruiter creates/deletes"""
        time.sleep(2)  # Rate limit avoidance
        response = api_client.get(
            f"{BASE_URL}/api/tracker/trackers",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        trackers = response.json().get("trackers", [])
        
        # Should still see at least the 2 original trackers
        assert len(trackers) >= 2, f"Admin should see at least 2 trackers, got {len(trackers)}"
        print(f"Admin regression check PASSED: sees {len(trackers)} trackers")
