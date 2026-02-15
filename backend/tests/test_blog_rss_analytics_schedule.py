"""
Blog RSS Feed, Analytics, and Auto-Schedule Tests
Tests for the new features: RSS 2.0 feed, analytics tracking, and auto-scheduling
"""
import pytest
import requests
import os
import time
import xml.etree.ElementTree as ET

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


@pytest.fixture(scope="session")
def admin_token():
    """Get admin auth token for protected endpoints"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Admin authentication failed")


@pytest.fixture
def admin_headers(admin_token):
    """Headers with admin auth token"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestRSSFeed:
    """RSS 2.0 Feed endpoint tests - Public (no auth required)"""
    
    def test_rss_feed_returns_valid_xml(self):
        """GET /api/blog/rss should return valid RSS 2.0 XML"""
        response = requests.get(f"{BASE_URL}/api/blog/rss")
        
        # Status assertion
        assert response.status_code == 200
        assert "application/rss+xml" in response.headers.get("content-type", "")
        
        # Parse XML to validate structure
        root = ET.fromstring(response.text)
        assert root.tag == "rss"
        assert root.attrib.get("version") == "2.0"
        
        # Verify channel exists
        channel = root.find("channel")
        assert channel is not None
        
        # Verify required channel elements
        title = channel.find("title")
        link = channel.find("link")
        description = channel.find("description")
        
        assert title is not None and title.text
        assert link is not None and link.text
        assert description is not None
        print(f"RSS Feed title: {title.text}")
        print(f"RSS Feed has {len(channel.findall('item'))} items")

    def test_rss_feed_employer_filter(self):
        """GET /api/blog/rss?blog_type=employer should return only employer blogs"""
        response = requests.get(f"{BASE_URL}/api/blog/rss?blog_type=employer")
        
        assert response.status_code == 200
        
        root = ET.fromstring(response.text)
        channel = root.find("channel")
        items = channel.findall("item")
        
        # All items should be employer type
        for item in items:
            category = item.find("category")
            if category is not None:
                assert category.text == "employer", f"Expected employer, got {category.text}"
        
        title = channel.find("title")
        assert "Industrial Hiring Insights" in title.text or "employer" in title.text.lower() or "VHC" in title.text
        print(f"Employer RSS: {len(items)} items found")

    def test_rss_feed_candidate_filter(self):
        """GET /api/blog/rss?blog_type=candidate should return only candidate blogs"""
        response = requests.get(f"{BASE_URL}/api/blog/rss?blog_type=candidate")
        
        assert response.status_code == 200
        
        root = ET.fromstring(response.text)
        channel = root.find("channel")
        items = channel.findall("item")
        
        # All items should be candidate type
        for item in items:
            category = item.find("category")
            if category is not None:
                assert category.text == "candidate", f"Expected candidate, got {category.text}"
        
        print(f"Candidate RSS: {len(items)} items found")

    def test_rss_items_have_required_elements(self):
        """RSS items should have title, link, description, pubDate, guid, category"""
        response = requests.get(f"{BASE_URL}/api/blog/rss")
        assert response.status_code == 200
        
        root = ET.fromstring(response.text)
        channel = root.find("channel")
        items = channel.findall("item")
        
        if len(items) == 0:
            pytest.skip("No RSS items to validate")
        
        # Check first item has all required elements
        item = items[0]
        required_elements = ["title", "link", "description", "pubDate", "guid", "category"]
        
        for elem_name in required_elements:
            elem = item.find(elem_name)
            assert elem is not None, f"RSS item missing {elem_name}"
            print(f"  {elem_name}: {elem.text[:50] if elem.text and len(elem.text) > 50 else elem.text}")


class TestAnalyticsTracking:
    """Blog analytics tracking tests - POST /api/blog/track (public, no auth)"""
    
    def test_track_view_event(self):
        """POST /api/blog/track with view event should return {ok: true}"""
        response = requests.post(
            f"{BASE_URL}/api/blog/track",
            json={"blog_id": "test-blog-123", "event_type": "view"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") == True
        print("View event tracked successfully")

    def test_track_cta_click_event(self):
        """POST /api/blog/track with cta_click event should return {ok: true}"""
        response = requests.post(
            f"{BASE_URL}/api/blog/track",
            json={"blog_id": "test-blog-123", "event_type": "cta_click"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") == True
        print("CTA click event tracked successfully")

    def test_track_event_with_metadata(self):
        """POST /api/blog/track with metadata should return {ok: true}"""
        response = requests.post(
            f"{BASE_URL}/api/blog/track",
            json={
                "blog_id": "test-blog-456",
                "event_type": "view",
                "metadata": {"source": "test", "device": "desktop"}
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") == True
        print("Event with metadata tracked successfully")

    def test_track_event_invalid_type(self):
        """POST /api/blog/track with invalid event_type should return 422"""
        response = requests.post(
            f"{BASE_URL}/api/blog/track",
            json={"blog_id": "test-blog-123", "event_type": "invalid_event"}
        )
        
        # Pydantic validation should reject invalid event type
        assert response.status_code == 422
        print("Invalid event type properly rejected")


class TestAnalyticsStats:
    """Blog analytics stats endpoints (admin auth required)"""
    
    def test_analytics_stats_requires_auth(self):
        """GET /api/blog/analytics/stats without auth should return 401/403"""
        response = requests.get(f"{BASE_URL}/api/blog/analytics/stats")
        assert response.status_code in [401, 403]
        print("Analytics stats properly requires authentication")

    def test_analytics_stats_returns_data(self, admin_headers):
        """GET /api/blog/analytics/stats with admin auth should return stats"""
        response = requests.get(
            f"{BASE_URL}/api/blog/analytics/stats?days=30",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify expected fields
        assert "employer_published" in data
        assert "candidate_published" in data
        assert "total_views" in data
        assert "total_cta_clicks" in data
        assert "ctr" in data
        
        print(f"Stats: {data}")

    def test_views_over_time_requires_auth(self):
        """GET /api/blog/analytics/views-over-time without auth should return 401/403"""
        response = requests.get(f"{BASE_URL}/api/blog/analytics/views-over-time")
        assert response.status_code in [401, 403]

    def test_views_over_time_returns_data(self, admin_headers):
        """GET /api/blog/analytics/views-over-time should return daily views array"""
        response = requests.get(
            f"{BASE_URL}/api/blog/analytics/views-over-time?days=30",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        print(f"Views over time: {len(data['data'])} days of data")

    def test_top_blogs_requires_auth(self):
        """GET /api/blog/analytics/top-blogs without auth should return 401/403"""
        response = requests.get(f"{BASE_URL}/api/blog/analytics/top-blogs")
        assert response.status_code in [401, 403]

    def test_top_blogs_returns_data(self, admin_headers):
        """GET /api/blog/analytics/top-blogs should return top blogs by views"""
        response = requests.get(
            f"{BASE_URL}/api/blog/analytics/top-blogs?days=30&limit=10",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        print(f"Top blogs: {len(data['data'])} blogs with views")

    def test_top_clicks_requires_auth(self):
        """GET /api/blog/analytics/top-clicks without auth should return 401/403"""
        response = requests.get(f"{BASE_URL}/api/blog/analytics/top-clicks")
        assert response.status_code in [401, 403]

    def test_top_clicks_returns_data(self, admin_headers):
        """GET /api/blog/analytics/top-clicks should return top blogs by CTA clicks"""
        response = requests.get(
            f"{BASE_URL}/api/blog/analytics/top-clicks?days=30&limit=10",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        print(f"Top clicks: {len(data['data'])} blogs with clicks")


class TestScheduleConfig:
    """Blog auto-scheduling configuration endpoints (admin auth required)"""
    
    def test_schedule_config_requires_auth(self):
        """GET /api/blog/schedule/config without auth should return 401/403"""
        response = requests.get(f"{BASE_URL}/api/blog/schedule/config")
        assert response.status_code in [401, 403]

    def test_get_schedule_config(self, admin_headers):
        """GET /api/blog/schedule/config should return schedule config with defaults"""
        response = requests.get(
            f"{BASE_URL}/api/blog/schedule/config",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "config" in data
        assert "draft_queue" in data
        
        config = data["config"]
        assert "employer" in config
        assert "candidate" in config
        
        # Verify employer config has expected keys
        employer = config["employer"]
        assert "enabled" in employer
        assert "posts_per_week" in employer or "days" in employer
        
        draft_queue = data["draft_queue"]
        assert "employer" in draft_queue
        assert "candidate" in draft_queue
        
        print(f"Schedule config: {config}")
        print(f"Draft queue: {draft_queue}")

    def test_update_schedule_config_requires_auth(self):
        """PUT /api/blog/schedule/config without auth should return 401/403"""
        response = requests.put(
            f"{BASE_URL}/api/blog/schedule/config",
            json={"employer": {"enabled": True}}
        )
        assert response.status_code in [401, 403]

    def test_update_schedule_config(self, admin_headers):
        """PUT /api/blog/schedule/config should update schedule"""
        # First get current config
        get_response = requests.get(
            f"{BASE_URL}/api/blog/schedule/config",
            headers=admin_headers
        )
        current = get_response.json()["config"]
        
        # Update employer enabled status (toggle)
        new_enabled = not current.get("employer", {}).get("enabled", False)
        
        response = requests.put(
            f"{BASE_URL}/api/blog/schedule/config",
            headers=admin_headers,
            json={"employer": {"enabled": new_enabled}}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "config" in data
        
        # Restore original state
        requests.put(
            f"{BASE_URL}/api/blog/schedule/config",
            headers=admin_headers,
            json={"employer": {"enabled": current.get("employer", {}).get("enabled", True)}}
        )
        
        print(f"Schedule update response: {data['message']}")


class TestScheduleTrigger:
    """Blog auto-publish trigger endpoint (admin auth required)"""
    
    def test_trigger_requires_auth(self):
        """POST /api/blog/schedule/trigger without auth should return 401/403"""
        response = requests.post(f"{BASE_URL}/api/blog/schedule/trigger?blog_type=employer")
        assert response.status_code in [401, 403]

    def test_trigger_employer_publish(self, admin_headers):
        """POST /api/blog/schedule/trigger?blog_type=employer should attempt publish"""
        response = requests.post(
            f"{BASE_URL}/api/blog/schedule/trigger?blog_type=employer",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        
        # Either "No drafts available" or "Published one blog"
        print(f"Trigger employer: {data['message']}")

    def test_trigger_candidate_publish(self, admin_headers):
        """POST /api/blog/schedule/trigger?blog_type=candidate should attempt publish"""
        response = requests.post(
            f"{BASE_URL}/api/blog/schedule/trigger?blog_type=candidate",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"Trigger candidate: {data['message']}")

    def test_trigger_invalid_type(self, admin_headers):
        """POST /api/blog/schedule/trigger with invalid type should return 422"""
        response = requests.post(
            f"{BASE_URL}/api/blog/schedule/trigger?blog_type=invalid",
            headers=admin_headers
        )
        
        assert response.status_code == 422
        print("Invalid blog type properly rejected")


class TestScheduleLog:
    """Blog auto-publish log endpoint (admin auth required)"""
    
    def test_schedule_log_requires_auth(self):
        """GET /api/blog/schedule/log without auth should return 401/403"""
        response = requests.get(f"{BASE_URL}/api/blog/schedule/log")
        assert response.status_code in [401, 403]

    def test_get_schedule_log(self, admin_headers):
        """GET /api/blog/schedule/log should return publish history"""
        response = requests.get(
            f"{BASE_URL}/api/blog/schedule/log?limit=20",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert isinstance(data["logs"], list)
        
        print(f"Schedule log: {len(data['logs'])} entries")
        
        # If logs exist, verify structure
        if data["logs"]:
            log = data["logs"][0]
            assert "blog_id" in log or "title" in log
            assert "action" in log or "timestamp" in log


class TestAnalyticsIntegration:
    """Integration tests for analytics flow"""
    
    def test_track_then_verify_stats(self, admin_headers):
        """Track events and verify they appear in stats"""
        # Track some test events
        test_blog_id = f"integration-test-{int(time.time())}"
        
        # Track 2 views
        for _ in range(2):
            response = requests.post(
                f"{BASE_URL}/api/blog/track",
                json={"blog_id": test_blog_id, "event_type": "view"}
            )
            assert response.status_code == 200
        
        # Track 1 click
        response = requests.post(
            f"{BASE_URL}/api/blog/track",
            json={"blog_id": test_blog_id, "event_type": "cta_click"}
        )
        assert response.status_code == 200
        
        # Get stats (should include our new events)
        response = requests.get(
            f"{BASE_URL}/api/blog/analytics/stats?days=1",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Stats should have at least our tracked events
        assert data["total_views"] >= 2
        assert data["total_cta_clicks"] >= 1
        
        print(f"Integration test - Views: {data['total_views']}, Clicks: {data['total_cta_clicks']}, CTR: {data['ctr']}%")
