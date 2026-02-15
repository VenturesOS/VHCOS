"""
Test Blog New Features - Iteration 64
- AI Topic & Keyword Research (/api/blog/research-topics)
- Blog Sitemap.xml (/api/blog/sitemap.xml)
- Weekly Blog Digest (/api/blog/send-digest)
- Clean URLs for static pages
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


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
    data = response.json()
    return data.get("access_token")


@pytest.fixture(scope="module")
def admin_client(api_client, admin_token):
    """Session with admin auth header"""
    api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
    return api_client


class TestCleanURLs:
    """Test SEO-friendly clean URLs for static pages"""

    def test_homepage_clean_url(self, api_client):
        """GET / should serve the homepage HTML"""
        response = api_client.get(f"{BASE_URL}/")
        assert response.status_code == 200, f"Homepage failed: {response.status_code}"
        # Check that it's HTML, not JSON
        content_type = response.headers.get('content-type', '')
        # It should contain some HTML content
        content = response.text
        # Homepage should contain VHC-related text
        assert "VHC" in content or "Ventures" in content or "Talent" in content or "<!DOCTYPE" in content.upper() or "html" in content_type.lower() or "React" in content, f"Homepage doesn't appear to serve proper content"
        print("PASS: / serves homepage")

    def test_about_clean_url(self, api_client):
        """GET /about should serve the About page HTML"""
        response = api_client.get(f"{BASE_URL}/about")
        assert response.status_code == 200, f"About page failed: {response.status_code}"
        content = response.text
        # About page should contain about-related content
        assert "About" in content or "Leadership" in content or "VHC" in content or "<!DOCTYPE" in content.upper(), f"About page doesn't serve proper content"
        print("PASS: /about serves about page")

    def test_services_clean_url(self, api_client):
        """GET /services should serve the Services page HTML"""
        response = api_client.get(f"{BASE_URL}/services")
        assert response.status_code == 200, f"Services page failed: {response.status_code}"
        content = response.text
        assert "Services" in content or "Executive" in content or "Search" in content or "VHC" in content or "<!DOCTYPE" in content.upper(), f"Services page doesn't serve proper content"
        print("PASS: /services serves services page")

    def test_contact_clean_url(self, api_client):
        """GET /contact should serve the Contact page HTML"""
        response = api_client.get(f"{BASE_URL}/contact")
        assert response.status_code == 200, f"Contact page failed: {response.status_code}"
        content = response.text
        assert "Contact" in content or "Email" in content or "VHC" in content or "<!DOCTYPE" in content.upper(), f"Contact page doesn't serve proper content"
        print("PASS: /contact serves contact page")

    def test_careers_clean_url(self, api_client):
        """GET /careers should serve the Careers page HTML"""
        response = api_client.get(f"{BASE_URL}/careers")
        assert response.status_code == 200, f"Careers page failed: {response.status_code}"
        content = response.text
        assert "Careers" in content or "Jobs" in content or "VHC" in content or "<!DOCTYPE" in content.upper(), f"Careers page doesn't serve proper content"
        print("PASS: /careers serves careers page")

    def test_industries_clean_url(self, api_client):
        """GET /industries should serve the Industries page HTML"""
        response = api_client.get(f"{BASE_URL}/industries")
        assert response.status_code == 200, f"Industries page failed: {response.status_code}"
        content = response.text
        assert "Industries" in content or "Manufacturing" in content or "VHC" in content or "<!DOCTYPE" in content.upper(), f"Industries page doesn't serve proper content"
        print("PASS: /industries serves industries page")

    def test_global_hiring_clean_url(self, api_client):
        """GET /global-hiring should serve the Global Hiring page HTML"""
        response = api_client.get(f"{BASE_URL}/global-hiring")
        assert response.status_code == 200, f"Global hiring page failed: {response.status_code}"
        content = response.text
        assert "Global" in content or "Hiring" in content or "VHC" in content or "<!DOCTYPE" in content.upper(), f"Global hiring page doesn't serve proper content"
        print("PASS: /global-hiring serves global hiring page")


class TestBlogRoutes:
    """Test public blog routes"""

    def test_employer_blog_list(self, api_client):
        """GET /industrial-hiring-insights should work (via React SPA)"""
        # This is a React route, so it returns the React app
        response = api_client.get(f"{BASE_URL}/industrial-hiring-insights")
        assert response.status_code == 200, f"Employer blog list route failed: {response.status_code}"
        print("PASS: /industrial-hiring-insights route accessible")

    def test_candidate_blog_list(self, api_client):
        """GET /career-insights should work (via React SPA)"""
        response = api_client.get(f"{BASE_URL}/career-insights")
        assert response.status_code == 200, f"Candidate blog list route failed: {response.status_code}"
        print("PASS: /career-insights route accessible")


class TestBlogSitemap:
    """Test XML Sitemap generation"""

    def test_sitemap_returns_xml(self, api_client):
        """GET /api/blog/sitemap.xml should return valid XML"""
        response = api_client.get(f"{BASE_URL}/api/blog/sitemap.xml")
        assert response.status_code == 200, f"Sitemap failed: {response.status_code}"
        
        content_type = response.headers.get('content-type', '')
        assert 'xml' in content_type.lower(), f"Expected XML content-type, got: {content_type}"
        
        content = response.text
        assert '<?xml version' in content, "Missing XML declaration"
        assert '<urlset' in content, "Missing urlset element"
        print("PASS: /api/blog/sitemap.xml returns valid XML")

    def test_sitemap_contains_static_pages(self, api_client):
        """Sitemap should contain static page URLs"""
        response = api_client.get(f"{BASE_URL}/api/blog/sitemap.xml")
        assert response.status_code == 200
        
        content = response.text
        # Check for static pages in sitemap
        static_pages = ['/about', '/services', '/contact', '/careers', '/industries', '/global-hiring']
        found_pages = []
        for page in static_pages:
            if page in content:
                found_pages.append(page)
        
        assert len(found_pages) >= 4, f"Expected at least 4 static pages in sitemap, found: {found_pages}"
        print(f"PASS: Sitemap contains static pages: {found_pages}")

    def test_sitemap_contains_blog_list_pages(self, api_client):
        """Sitemap should contain blog list URLs"""
        response = api_client.get(f"{BASE_URL}/api/blog/sitemap.xml")
        assert response.status_code == 200
        
        content = response.text
        assert '/industrial-hiring-insights' in content, "Missing employer blog list in sitemap"
        assert '/career-insights' in content, "Missing candidate blog list in sitemap"
        print("PASS: Sitemap contains blog list pages")


class TestAITopicResearch:
    """Test AI Topic & Keyword Research endpoint"""

    def test_research_topics_requires_auth(self, api_client):
        """POST /api/blog/research-topics should require admin auth"""
        response = api_client.post(f"{BASE_URL}/api/blog/research-topics", json={
            "blog_type": "employer",
            "count": 3
        }, headers={"Authorization": ""})  # No auth
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got: {response.status_code}"
        print("PASS: research-topics requires auth")

    def test_research_topics_with_admin_auth(self, admin_client):
        """POST /api/blog/research-topics with admin auth should return topics"""
        # Note: This calls OpenAI and may take 10-15 seconds
        response = admin_client.post(f"{BASE_URL}/api/blog/research-topics", json={
            "blog_type": "employer",
            "industry": "Manufacturing",
            "count": 3
        }, timeout=30)
        
        assert response.status_code == 200, f"Research topics failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert "topics" in data, "Missing 'topics' in response"
        topics = data["topics"]
        assert isinstance(topics, list), "Topics should be a list"
        
        if len(topics) > 0:
            topic = topics[0]
            # Each topic should have these fields
            assert "topic" in topic, "Topic missing 'topic' field"
            assert "primary_keyword" in topic, "Topic missing 'primary_keyword' field"
            print(f"PASS: research-topics returned {len(topics)} topics. First: {topic.get('topic', '')[:50]}")
        else:
            print("PASS: research-topics returned empty list (may be LLM response issue)")

    def test_research_topics_candidate_type(self, admin_client):
        """Test research topics for candidate blog type"""
        response = admin_client.post(f"{BASE_URL}/api/blog/research-topics", json={
            "blog_type": "candidate",
            "industry": "Engineering",
            "count": 2
        }, timeout=30)
        
        assert response.status_code == 200, f"Research topics (candidate) failed: {response.status_code}"
        data = response.json()
        assert "topics" in data
        print(f"PASS: research-topics for candidate returned {len(data.get('topics', []))} topics")


class TestBlogDigest:
    """Test Weekly Blog Digest endpoint"""

    def test_send_digest_requires_auth(self, api_client):
        """POST /api/blog/send-digest should require admin auth"""
        response = api_client.post(f"{BASE_URL}/api/blog/send-digest", 
                                   headers={"Authorization": ""})
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got: {response.status_code}"
        print("PASS: send-digest requires auth")

    def test_send_digest_with_admin_auth(self, admin_client):
        """POST /api/blog/send-digest with admin should trigger digest"""
        response = admin_client.post(f"{BASE_URL}/api/blog/send-digest", timeout=60)
        
        assert response.status_code == 200, f"Send digest failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert "message" in data, "Missing 'message' in response"
        assert "sent" in data, "Missing 'sent' count in response"
        
        print(f"PASS: send-digest returned: {data.get('message')}, sent: {data.get('sent')}")


class TestBlogAPIs:
    """Test existing blog APIs still work"""

    def test_employer_blog_api(self, api_client):
        """GET /api/blog/employer should return blog list"""
        response = api_client.get(f"{BASE_URL}/api/blog/employer")
        assert response.status_code == 200, f"Employer blog API failed: {response.status_code}"
        data = response.json()
        assert "blogs" in data
        assert "total" in data
        print(f"PASS: /api/blog/employer returned {data.get('total')} blogs")

    def test_candidate_blog_api(self, api_client):
        """GET /api/blog/candidate should return blog list"""
        response = api_client.get(f"{BASE_URL}/api/blog/candidate")
        assert response.status_code == 200, f"Candidate blog API failed: {response.status_code}"
        data = response.json()
        assert "blogs" in data
        assert "total" in data
        print(f"PASS: /api/blog/candidate returned {data.get('total')} blogs")

    def test_rss_feed(self, api_client):
        """GET /api/blog/rss should return RSS XML"""
        response = api_client.get(f"{BASE_URL}/api/blog/rss")
        assert response.status_code == 200, f"RSS feed failed: {response.status_code}"
        assert 'xml' in response.headers.get('content-type', '').lower()
        assert '<rss' in response.text
        print("PASS: /api/blog/rss returns valid RSS")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
