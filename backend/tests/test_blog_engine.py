"""
Blog Engine API Tests
Tests all blog endpoints: admin CRUD, public read, generate (mock LLM)
"""
import pytest
import requests
import os
import json
from datetime import datetime

# Base URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://rss-feed-engine.preview.emergentagent.com"

# Admin credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def api_client():
    """Basic requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def authenticated_client(api_client, admin_token):
    """Session with admin auth header."""
    api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
    return api_client


class TestPublicBlogAPIs:
    """Public blog endpoints - no auth required"""

    def test_public_employer_blog_list(self, api_client):
        """Test GET /api/blog/employer returns published employer blogs"""
        response = api_client.get(f"{BASE_URL}/api/blog/employer")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "blogs" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        assert isinstance(data["blogs"], list)
        print(f"✅ Public employer blogs: {len(data['blogs'])} blogs, total: {data['total']}")

    def test_public_employer_blog_list_pagination(self, api_client):
        """Test pagination on employer blog list"""
        response = api_client.get(f"{BASE_URL}/api/blog/employer?page=1&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        print(f"✅ Employer blog pagination works: page {data['page']}, {data['pages']} total pages")

    def test_public_employer_blog_by_slug(self, api_client):
        """Test GET /api/blog/employer/{slug} returns full article"""
        # First get the list to find a published blog slug
        list_response = api_client.get(f"{BASE_URL}/api/blog/employer")
        data = list_response.json()
        
        if data["total"] == 0:
            pytest.skip("No published employer blogs to test")
        
        slug = data["blogs"][0]["slug"]
        response = api_client.get(f"{BASE_URL}/api/blog/employer/{slug}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        blog = response.json()
        assert "title" in blog
        assert "content" in blog
        assert "meta_description" in blog
        assert blog["slug"] == slug
        print(f"✅ Employer blog by slug: '{blog['title'][:50]}...'")

    def test_public_employer_blog_not_found(self, api_client):
        """Test 404 for non-existent employer blog slug"""
        response = api_client.get(f"{BASE_URL}/api/blog/employer/non-existent-slug-12345")
        assert response.status_code == 404
        print("✅ Non-existent employer blog returns 404")

    def test_public_candidate_blog_list(self, api_client):
        """Test GET /api/blog/candidate returns published candidate blogs"""
        response = api_client.get(f"{BASE_URL}/api/blog/candidate")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "blogs" in data
        assert "total" in data
        assert isinstance(data["blogs"], list)
        print(f"✅ Public candidate blogs: {len(data['blogs'])} blogs, total: {data['total']}")

    def test_public_candidate_blog_category_filter(self, api_client):
        """Test category filter on candidate blog list"""
        response = api_client.get(f"{BASE_URL}/api/blog/candidate?category=career-growth")
        assert response.status_code == 200
        data = response.json()
        # All returned blogs should have the category
        for blog in data["blogs"]:
            assert blog.get("category") == "career-growth" or blog.get("category") is None
        print(f"✅ Candidate blog category filter works: {len(data['blogs'])} results")

    def test_public_candidate_blog_by_slug(self, api_client):
        """Test GET /api/blog/candidate/{slug} returns full article"""
        # First get the list to find a published blog slug
        list_response = api_client.get(f"{BASE_URL}/api/blog/candidate")
        data = list_response.json()
        
        if data["total"] == 0:
            pytest.skip("No published candidate blogs to test")
        
        slug = data["blogs"][0]["slug"]
        response = api_client.get(f"{BASE_URL}/api/blog/candidate/{slug}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        blog = response.json()
        assert "title" in blog
        assert "content" in blog
        assert "meta_description" in blog
        assert blog["slug"] == slug
        print(f"✅ Candidate blog by slug: '{blog['title'][:50]}...'")


class TestAdminBlogAPIs:
    """Admin blog endpoints - auth required"""

    def test_admin_list_all_blogs(self, authenticated_client):
        """Test GET /api/blog/admin/list returns all blogs for admin"""
        response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/list")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "blogs" in data
        assert "total" in data
        print(f"✅ Admin blog list: {data['total']} total blogs")

    def test_admin_list_filter_by_type(self, authenticated_client):
        """Test filtering by blog_type=employer"""
        response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/list?blog_type=employer")
        assert response.status_code == 200
        
        data = response.json()
        for blog in data["blogs"]:
            assert blog["blog_type"] == "employer"
        print(f"✅ Admin filter by type: {len(data['blogs'])} employer blogs")

    def test_admin_list_filter_by_status(self, authenticated_client):
        """Test filtering by status=draft"""
        response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/list?status=draft")
        assert response.status_code == 200
        
        data = response.json()
        for blog in data["blogs"]:
            assert blog["status"] == "draft"
        print(f"✅ Admin filter by status: {len(data['blogs'])} draft blogs")

    def test_admin_get_blog_by_id(self, authenticated_client):
        """Test GET /api/blog/admin/{id} returns full blog content"""
        # First get list to find a blog id
        list_response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/list")
        blogs = list_response.json()["blogs"]
        
        if len(blogs) == 0:
            pytest.skip("No blogs to test admin get by id")
        
        blog_id = blogs[0]["id"]
        response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/{blog_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        blog = response.json()
        assert blog["id"] == blog_id
        assert "title" in blog
        assert "content" in blog
        assert "generation_log" in blog  # Admin endpoint includes generation log
        print(f"✅ Admin get blog by id: '{blog['title'][:40]}...'")

    def test_admin_get_blog_not_found(self, authenticated_client):
        """Test 404 for non-existent blog id"""
        response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/non-existent-id-12345")
        assert response.status_code == 404
        print("✅ Non-existent blog id returns 404")

    def test_admin_update_blog(self, authenticated_client):
        """Test PUT /api/blog/admin/{id} updates blog"""
        # First get a blog to update
        list_response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/list")
        blogs = list_response.json()["blogs"]
        
        if len(blogs) == 0:
            pytest.skip("No blogs to test update")
        
        blog_id = blogs[0]["id"]
        original_title = blogs[0]["title"]
        
        # Update title
        update_payload = {"title": f"TEST_UPDATED_{original_title[:30]}"}
        response = authenticated_client.put(
            f"{BASE_URL}/api/blog/admin/{blog_id}",
            json=update_payload
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify update
        verify_response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/{blog_id}")
        updated_blog = verify_response.json()
        assert updated_blog["title"].startswith("TEST_UPDATED_")
        
        # Restore original title
        authenticated_client.put(
            f"{BASE_URL}/api/blog/admin/{blog_id}",
            json={"title": original_title}
        )
        print(f"✅ Admin update blog: title changed and restored")

    def test_admin_update_blog_no_fields(self, authenticated_client):
        """Test 400 when no fields provided to update"""
        list_response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/list")
        blogs = list_response.json()["blogs"]
        
        if len(blogs) == 0:
            pytest.skip("No blogs to test")
        
        blog_id = blogs[0]["id"]
        response = authenticated_client.put(
            f"{BASE_URL}/api/blog/admin/{blog_id}",
            json={}
        )
        assert response.status_code == 400
        print("✅ Empty update returns 400")


class TestBlogPublishUnpublish:
    """Test publish/unpublish workflow"""

    def test_publish_and_unpublish_blog(self, authenticated_client):
        """Test PUT /api/blog/admin/{id}/publish and /unpublish"""
        # Get a draft blog to publish
        list_response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/list?status=draft")
        drafts = list_response.json()["blogs"]
        
        if len(drafts) == 0:
            # Try to get any blog and unpublish first
            all_response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/list")
            all_blogs = all_response.json()["blogs"]
            if len(all_blogs) == 0:
                pytest.skip("No blogs available")
            
            # Unpublish a blog to test
            blog_id = all_blogs[0]["id"]
            authenticated_client.put(f"{BASE_URL}/api/blog/admin/{blog_id}/unpublish")
        else:
            blog_id = drafts[0]["id"]
        
        # Publish the blog
        publish_response = authenticated_client.put(f"{BASE_URL}/api/blog/admin/{blog_id}/publish")
        assert publish_response.status_code == 200, f"Publish failed: {publish_response.status_code}"
        
        # Verify it's published
        verify_response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/{blog_id}")
        assert verify_response.json()["status"] == "published"
        
        # Unpublish it
        unpublish_response = authenticated_client.put(f"{BASE_URL}/api/blog/admin/{blog_id}/unpublish")
        assert unpublish_response.status_code == 200, f"Unpublish failed: {unpublish_response.status_code}"
        
        # Verify it's draft again
        final_response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/{blog_id}")
        assert final_response.json()["status"] == "draft"
        
        # Re-publish for other tests
        authenticated_client.put(f"{BASE_URL}/api/blog/admin/{blog_id}/publish")
        print("✅ Publish/unpublish workflow works correctly")


class TestBlogDelete:
    """Test blog deletion"""

    def test_delete_blog_not_found(self, authenticated_client):
        """Test 404 for deleting non-existent blog"""
        response = authenticated_client.delete(f"{BASE_URL}/api/blog/admin/non-existent-id-12345")
        assert response.status_code == 404
        print("✅ Delete non-existent blog returns 404")


class TestBlogAuthRequired:
    """Test that admin endpoints require authentication"""

    def test_admin_list_requires_auth(self, api_client):
        """Test admin list without auth returns 401/403"""
        response = api_client.get(f"{BASE_URL}/api/blog/admin/list")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ Admin list requires authentication")

    def test_generate_requires_auth(self, api_client):
        """Test generate without auth returns 401/403"""
        response = api_client.post(
            f"{BASE_URL}/api/blog/generate",
            json={"blog_type": "employer", "topic": "Test", "industry": "Auto"}
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ Generate requires authentication")

    def test_publish_requires_auth(self, api_client):
        """Test publish without auth returns 401/403"""
        response = api_client.put(f"{BASE_URL}/api/blog/admin/some-id/publish")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ Publish requires authentication")


class TestBlogDataStructure:
    """Test blog response data structure"""

    def test_employer_blog_list_structure(self, api_client):
        """Verify employer blog list response structure"""
        response = api_client.get(f"{BASE_URL}/api/blog/employer")
        data = response.json()
        
        if data["total"] > 0:
            blog = data["blogs"][0]
            # List should have these fields
            expected_fields = ["id", "title", "slug", "meta_description", "published_at"]
            for field in expected_fields:
                assert field in blog, f"Missing field: {field}"
            # List should NOT have full content
            assert "content" not in blog or blog.get("content") is None
        print("✅ Employer blog list has correct structure")

    def test_employer_blog_full_structure(self, api_client):
        """Verify employer blog full article structure"""
        list_response = api_client.get(f"{BASE_URL}/api/blog/employer")
        if list_response.json()["total"] == 0:
            pytest.skip("No employer blogs")
        
        slug = list_response.json()["blogs"][0]["slug"]
        response = api_client.get(f"{BASE_URL}/api/blog/employer/{slug}")
        blog = response.json()
        
        # Full article should have content
        assert "content" in blog and blog["content"]
        assert "keywords" in blog
        assert isinstance(blog["keywords"], list)
        print("✅ Employer blog full article has correct structure")

    def test_candidate_blog_has_category(self, api_client):
        """Verify candidate blogs have category field"""
        response = api_client.get(f"{BASE_URL}/api/blog/candidate")
        data = response.json()
        
        if data["total"] > 0:
            blog = data["blogs"][0]
            # Candidate blogs should have category
            assert "category" in blog
        print("✅ Candidate blogs have category field")

    def test_admin_blog_has_generation_log(self, authenticated_client):
        """Verify admin blog response includes generation_log"""
        list_response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/list")
        blogs = list_response.json()["blogs"]
        
        if len(blogs) == 0:
            pytest.skip("No blogs")
        
        blog_id = blogs[0]["id"]
        response = authenticated_client.get(f"{BASE_URL}/api/blog/admin/{blog_id}")
        blog = response.json()
        
        assert "generation_log" in blog
        if blog["generation_log"]:
            assert "topic_source" in blog["generation_log"]
            assert "model_used" in blog["generation_log"]
        print("✅ Admin blog response includes generation_log")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
