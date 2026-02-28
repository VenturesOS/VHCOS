"""
LinkedIn Auto-Posting API Tests
Tests:
- GET /api/linkedin/settings (returns settings with connection status)
- PUT /api/linkedin/settings (updates auto_post_enabled and organization_id)
- GET /api/linkedin/post-history (returns post history array)
- POST /api/linkedin/test-post (returns 400 when not connected)
- DELETE /api/linkedin/disconnect
- GET /api/linkedin/authorize (returns authorization URL)
- PUT /api/blog/admin/{blog_id}/publish (blog publish endpoint still works)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://builder-auth.preview.emergentagent.com"

ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    assert "access_token" in data, f"No access_token in response: {data}"
    return data["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin token."""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }


class TestLinkedInSettings:
    """Tests for LinkedIn settings endpoints"""

    def test_get_linkedin_settings(self, admin_headers):
        """GET /api/linkedin/settings returns settings with connection status"""
        response = requests.get(
            f"{BASE_URL}/api/linkedin/settings",
            headers=admin_headers
        )
        assert response.status_code == 200, f"GET settings failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "auto_post_enabled" in data, "Missing auto_post_enabled in response"
        assert "organization_id" in data, "Missing organization_id in response"
        assert "connection" in data, "Missing connection in response"
        
        # Verify connection sub-object
        connection = data["connection"]
        assert "connected" in connection, "Missing connected field in connection object"
        assert isinstance(connection["connected"], bool), "connected should be boolean"
        
        print(f"LinkedIn Settings: auto_post={data['auto_post_enabled']}, org_id={data['organization_id']}, connected={connection['connected']}")

    def test_update_linkedin_settings_auto_post(self, admin_headers):
        """PUT /api/linkedin/settings updates auto_post_enabled"""
        # First get current settings
        get_response = requests.get(
            f"{BASE_URL}/api/linkedin/settings",
            headers=admin_headers
        )
        current = get_response.json()
        original_auto_post = current.get("auto_post_enabled", False)
        
        # Update auto_post_enabled
        new_value = not original_auto_post
        response = requests.put(
            f"{BASE_URL}/api/linkedin/settings",
            headers=admin_headers,
            json={"auto_post_enabled": new_value}
        )
        assert response.status_code == 200, f"PUT settings failed: {response.text}"
        data = response.json()
        assert data.get("auto_post_enabled") == new_value, f"auto_post_enabled not updated: {data}"
        
        # Revert to original
        requests.put(
            f"{BASE_URL}/api/linkedin/settings",
            headers=admin_headers,
            json={"auto_post_enabled": original_auto_post}
        )
        print(f"Updated auto_post_enabled to {new_value}, then reverted to {original_auto_post}")

    def test_update_linkedin_settings_organization_id(self, admin_headers):
        """PUT /api/linkedin/settings updates organization_id"""
        # First get current settings
        get_response = requests.get(
            f"{BASE_URL}/api/linkedin/settings",
            headers=admin_headers
        )
        current = get_response.json()
        original_org_id = current.get("organization_id", "")
        
        # Update organization_id
        test_org_id = "TEST_ORG_123456"
        response = requests.put(
            f"{BASE_URL}/api/linkedin/settings",
            headers=admin_headers,
            json={"organization_id": test_org_id}
        )
        assert response.status_code == 200, f"PUT settings failed: {response.text}"
        data = response.json()
        assert data.get("organization_id") == test_org_id, f"organization_id not updated: {data}"
        
        # Verify with GET
        verify_response = requests.get(
            f"{BASE_URL}/api/linkedin/settings",
            headers=admin_headers
        )
        verify_data = verify_response.json()
        assert verify_data.get("organization_id") == test_org_id, "organization_id not persisted"
        
        # Revert to original
        requests.put(
            f"{BASE_URL}/api/linkedin/settings",
            headers=admin_headers,
            json={"organization_id": original_org_id}
        )
        print(f"Updated organization_id to {test_org_id}, then reverted to {original_org_id}")


class TestLinkedInPostHistory:
    """Tests for LinkedIn post history endpoint"""

    def test_get_post_history(self, admin_headers):
        """GET /api/linkedin/post-history returns post history array"""
        response = requests.get(
            f"{BASE_URL}/api/linkedin/post-history",
            headers=admin_headers
        )
        assert response.status_code == 200, f"GET post-history failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "posts" in data, "Missing posts field in response"
        assert isinstance(data["posts"], list), "posts should be a list"
        assert "total" in data, "Missing total field in response"
        
        print(f"Post history: {data['total']} posts found")
        if data["posts"]:
            first_post = data["posts"][0]
            print(f"Sample post: title={first_post.get('blog_title')}, status={first_post.get('status')}")

    def test_get_post_history_with_limit(self, admin_headers):
        """GET /api/linkedin/post-history with limit parameter"""
        response = requests.get(
            f"{BASE_URL}/api/linkedin/post-history?limit=5",
            headers=admin_headers
        )
        assert response.status_code == 200, f"GET post-history failed: {response.text}"
        data = response.json()
        
        assert "posts" in data
        assert len(data["posts"]) <= 5, "Should respect limit parameter"
        print(f"Post history with limit=5: returned {len(data['posts'])} posts")


class TestLinkedInTestPost:
    """Tests for LinkedIn test post endpoint"""

    def test_test_post_when_not_connected(self, admin_headers):
        """POST /api/linkedin/test-post returns 400 when not connected"""
        response = requests.post(
            f"{BASE_URL}/api/linkedin/test-post",
            headers=admin_headers
        )
        # Should return 400 if LinkedIn is not connected
        # or 502 if connected but API fails
        assert response.status_code in [400, 502], f"Unexpected status: {response.status_code}, {response.text}"
        
        if response.status_code == 400:
            data = response.json()
            assert "detail" in data, "Missing detail in error response"
            print(f"Test post returned expected 400: {data['detail']}")
        else:
            print(f"Test post returned 502 (LinkedIn API error)")


class TestLinkedInDisconnect:
    """Tests for LinkedIn disconnect endpoint"""

    def test_disconnect_linkedin(self, admin_headers):
        """DELETE /api/linkedin/disconnect works correctly"""
        response = requests.delete(
            f"{BASE_URL}/api/linkedin/disconnect",
            headers=admin_headers
        )
        assert response.status_code == 200, f"DELETE disconnect failed: {response.text}"
        data = response.json()
        assert "message" in data, "Missing message in response"
        print(f"Disconnect response: {data['message']}")


class TestLinkedInAuthorize:
    """Tests for LinkedIn authorization endpoint"""

    def test_authorize_returns_url(self, admin_headers):
        """GET /api/linkedin/authorize returns authorization URL"""
        response = requests.get(
            f"{BASE_URL}/api/linkedin/authorize",
            headers=admin_headers
        )
        # May return 500 if LINKEDIN_CLIENT_ID not configured, or 200 with URL
        if response.status_code == 200:
            data = response.json()
            assert "authorization_url" in data, "Missing authorization_url in response"
            assert "linkedin.com" in data["authorization_url"], "URL should contain linkedin.com"
            assert "oauth" in data["authorization_url"], "URL should be OAuth URL"
            print(f"Authorization URL: {data['authorization_url'][:100]}...")
        elif response.status_code == 500:
            # Expected if LINKEDIN_CLIENT_ID not configured
            print("Authorization returned 500 (LinkedIn credentials not configured)")
        else:
            pytest.fail(f"Unexpected status: {response.status_code}, {response.text}")


class TestLinkedInAuthRequired:
    """Tests to verify admin auth is required"""

    def test_settings_requires_auth(self):
        """GET /api/linkedin/settings requires authentication"""
        response = requests.get(f"{BASE_URL}/api/linkedin/settings")
        assert response.status_code in [401, 403], f"Should require auth: {response.status_code}"
        print(f"Settings endpoint correctly requires authentication (returns {response.status_code})")

    def test_post_history_requires_auth(self):
        """GET /api/linkedin/post-history requires authentication"""
        response = requests.get(f"{BASE_URL}/api/linkedin/post-history")
        assert response.status_code in [401, 403], f"Should require auth: {response.status_code}"
        print(f"Post history endpoint correctly requires authentication (returns {response.status_code})")

    def test_authorize_requires_auth(self):
        """GET /api/linkedin/authorize requires authentication"""
        response = requests.get(f"{BASE_URL}/api/linkedin/authorize")
        assert response.status_code in [401, 403], f"Should require auth: {response.status_code}"
        print(f"Authorize endpoint correctly requires authentication (returns {response.status_code})")


class TestBlogPublishEndpoint:
    """Test blog publish endpoint still works"""

    def test_blog_publish_endpoint_exists(self, admin_headers):
        """PUT /api/blog/admin/{blog_id}/publish endpoint exists"""
        # Use a fake blog_id to test endpoint exists
        response = requests.put(
            f"{BASE_URL}/api/blog/admin/fake-blog-id/publish",
            headers=admin_headers
        )
        # Should return 404 (blog not found), not 500 or method not allowed
        assert response.status_code == 404, f"Unexpected status: {response.status_code}, {response.text}"
        print("Blog publish endpoint exists and returns 404 for invalid blog_id")

    def test_blog_publish_with_real_blog(self, admin_headers):
        """Test publish endpoint with a real blog if exists"""
        # Get list of blogs
        list_response = requests.get(
            f"{BASE_URL}/api/blog/admin/list?status=draft",
            headers=admin_headers
        )
        if list_response.status_code != 200:
            pytest.skip("Could not get blog list")
            return
        
        blogs = list_response.json().get("blogs", [])
        if not blogs:
            print("No draft blogs available to test publish, skipping")
            pytest.skip("No draft blogs available")
            return
        
        # Get first draft blog
        blog_id = blogs[0]["id"]
        
        # Publish it
        response = requests.put(
            f"{BASE_URL}/api/blog/admin/{blog_id}/publish",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Publish failed: {response.text}"
        
        # Unpublish it back (cleanup)
        requests.put(
            f"{BASE_URL}/api/blog/admin/{blog_id}/unpublish",
            headers=admin_headers
        )
        print(f"Successfully tested publish/unpublish on blog {blog_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
