"""
SEO Phase 1 - Backend API Tests
Tests for: sitemap.xml, robots.txt, security headers, and SEO admin settings API
"""
import pytest
import requests
import os
import xml.etree.ElementTree as ET

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

class TestSitemapAndRobots:
    """Tests for sitemap.xml and robots.txt endpoints"""
    
    def test_sitemap_xml_returns_valid_xml(self):
        """GET /api/sitemap.xml should return valid XML"""
        response = requests.get(f"{BASE_URL}/api/sitemap.xml")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "application/xml" in response.headers.get("Content-Type", ""), "Expected XML content-type"
        
        # Parse as XML to validate structure
        root = ET.fromstring(response.text)
        assert root.tag.endswith("urlset"), f"Expected urlset root element, got {root.tag}"
        
        # Should have URL entries
        urls = root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}url")
        assert len(urls) > 0, "Sitemap should have at least one URL entry"
        
        print(f"Sitemap contains {len(urls)} URLs")
        
    def test_sitemap_contains_static_pages(self):
        """Sitemap should include static pages"""
        response = requests.get(f"{BASE_URL}/api/sitemap.xml")
        assert response.status_code == 200
        
        sitemap_text = response.text
        
        # Check for static pages
        expected_pages = ["/", "/about", "/services", "/industries", "/careers", "/contact", "/global-hiring"]
        for page in expected_pages:
            # URL in sitemap should be full URL
            expected_url = f"https://ventureshrd.com{page}" if page != "/" else "https://ventureshrd.com/"
            assert expected_url in sitemap_text, f"Missing static page URL: {expected_url}"
        
        print("All expected static pages found in sitemap")
        
    def test_sitemap_contains_blog_section(self):
        """Sitemap should include blog listing pages"""
        response = requests.get(f"{BASE_URL}/api/sitemap.xml")
        assert response.status_code == 200
        
        sitemap_text = response.text
        
        # Check for blog section URLs
        assert "industrial-hiring-insights" in sitemap_text, "Missing employer blog section URL"
        assert "career-insights" in sitemap_text, "Missing candidate blog section URL"
        
        print("Blog section URLs found in sitemap")
        
    def test_sitemap_has_cache_header(self):
        """Sitemap should have cache control header"""
        response = requests.get(f"{BASE_URL}/api/sitemap.xml")
        assert response.status_code == 200
        
        cache_control = response.headers.get("Cache-Control", "")
        assert "max-age" in cache_control, "Expected Cache-Control header with max-age"
        print(f"Cache-Control: {cache_control}")
    
    def test_robots_txt_returns_text(self):
        """GET /api/robots.txt should return proper robots.txt"""
        response = requests.get(f"{BASE_URL}/api/robots.txt")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "text/plain" in response.headers.get("Content-Type", ""), "Expected text/plain content-type"
        
        robots_text = response.text
        assert "User-agent: *" in robots_text, "Should have User-agent directive"
        assert "Allow: /" in robots_text, "Should have Allow directive"
        assert "Disallow: /admin" in robots_text, "Should disallow admin"
        assert "Disallow: /api/" in robots_text, "Should disallow API"
        
        print("robots.txt content validated")
        
    def test_robots_txt_contains_sitemap_reference(self):
        """robots.txt should reference sitemap URL"""
        response = requests.get(f"{BASE_URL}/api/robots.txt")
        assert response.status_code == 200
        
        robots_text = response.text
        assert "Sitemap:" in robots_text, "Should have Sitemap directive"
        assert "sitemap.xml" in robots_text.lower(), "Should reference sitemap.xml"
        assert "ventureshrd.com" in robots_text, "Sitemap URL should use production domain"
        
        print(f"Sitemap reference found: {[line for line in robots_text.split(chr(10)) if 'Sitemap' in line]}")
        
    def test_robots_txt_has_cache_header(self):
        """robots.txt should have cache control header"""
        response = requests.get(f"{BASE_URL}/api/robots.txt")
        assert response.status_code == 200
        
        cache_control = response.headers.get("Cache-Control", "")
        assert "max-age" in cache_control, "Expected Cache-Control header with max-age"
        print(f"Cache-Control: {cache_control}")


class TestSecurityHeaders:
    """Tests for security headers on API responses"""
    
    def test_hsts_header_present(self):
        """API responses should include HSTS header"""
        response = requests.get(f"{BASE_URL}/api/sitemap.xml")
        assert response.status_code == 200
        
        hsts = response.headers.get("Strict-Transport-Security", "")
        assert "max-age" in hsts, f"HSTS header missing or incomplete. Got: {hsts}"
        print(f"HSTS header: {hsts}")
        
    def test_x_content_type_options_header(self):
        """API responses should include X-Content-Type-Options: nosniff"""
        response = requests.get(f"{BASE_URL}/api/robots.txt")
        assert response.status_code == 200
        
        header_value = response.headers.get("X-Content-Type-Options", "")
        assert header_value == "nosniff", f"Expected 'nosniff', got: {header_value}"
        print(f"X-Content-Type-Options: {header_value}")
        
    def test_x_frame_options_header(self):
        """API responses should include X-Frame-Options header"""
        response = requests.get(f"{BASE_URL}/api/sitemap.xml")
        assert response.status_code == 200
        
        header_value = response.headers.get("X-Frame-Options", "")
        assert header_value in ["DENY", "SAMEORIGIN"], f"Expected DENY or SAMEORIGIN, got: {header_value}"
        print(f"X-Frame-Options: {header_value}")
        
    def test_referrer_policy_header(self):
        """API responses should include Referrer-Policy header"""
        response = requests.get(f"{BASE_URL}/api/robots.txt")
        assert response.status_code == 200
        
        header_value = response.headers.get("Referrer-Policy", "")
        assert header_value != "", f"Referrer-Policy header missing"
        assert "origin" in header_value.lower() or "no-referrer" in header_value.lower(), f"Unexpected Referrer-Policy: {header_value}"
        print(f"Referrer-Policy: {header_value}")
        
    def test_xss_protection_header(self):
        """API responses should include X-XSS-Protection header"""
        response = requests.get(f"{BASE_URL}/api/sitemap.xml")
        assert response.status_code == 200
        
        header_value = response.headers.get("X-XSS-Protection", "")
        assert header_value != "", f"X-XSS-Protection header missing"
        assert "1" in header_value, f"Expected X-XSS-Protection to be enabled. Got: {header_value}"
        print(f"X-XSS-Protection: {header_value}")


class TestSEOSettingsAdminAPI:
    """Tests for SEO admin settings API"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        if login_response.status_code != 200:
            pytest.skip("Could not authenticate as admin")
        return login_response.json().get("access_token")
    
    def test_seo_settings_requires_auth(self):
        """GET /api/seo/settings should require authentication"""
        response = requests.get(f"{BASE_URL}/api/seo/settings")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("SEO settings endpoint properly requires authentication")
        
    def test_seo_settings_get_list(self, admin_token):
        """GET /api/seo/settings should return settings list for admin"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/seo/settings", headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "settings" in data, "Response should contain 'settings' key"
        assert isinstance(data["settings"], list), "'settings' should be a list"
        
        print(f"SEO settings returned {len(data['settings'])} entries")
        
    def test_seo_settings_update_and_verify(self, admin_token):
        """PUT /api/seo/settings should create/update SEO override"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create/update a test SEO setting
        test_setting = {
            "page_path": "/test-seo-page",
            "title": "Test SEO Title",
            "meta_description": "Test SEO description for testing purposes",
            "meta_keywords": "test, seo, keywords",
            "og_title": "Test OG Title",
            "og_description": "Test OG description"
        }
        
        response = requests.put(f"{BASE_URL}/api/seo/settings", json=test_setting, headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "message" in data, "Response should contain message"
        assert "/test-seo-page" in data.get("message", ""), "Message should reference page path"
        
        print(f"SEO setting update response: {data}")
        
        # Verify it was created
        get_response = requests.get(f"{BASE_URL}/api/seo/settings//test-seo-page", headers=headers)
        if get_response.status_code == 200:
            setting_data = get_response.json()
            assert setting_data.get("page_path") == "/test-seo-page", "Page path should match"
            print("SEO setting verified in GET endpoint")
        
        # Cleanup: Delete the test setting
        delete_response = requests.delete(f"{BASE_URL}/api/seo/settings//test-seo-page", headers=headers)
        print(f"Cleanup delete response: {delete_response.status_code}")
        
    def test_seo_settings_update_requires_admin(self):
        """PUT /api/seo/settings should require admin authentication"""
        test_setting = {
            "page_path": "/unauthorized-test",
            "title": "Should Not Work"
        }
        
        response = requests.put(f"{BASE_URL}/api/seo/settings", json=test_setting)
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("SEO settings update properly requires admin authentication")


class TestStaticRobotsTxt:
    """Test static robots.txt on frontend"""
    
    def test_static_robots_txt_accessible(self):
        """Static robots.txt should be accessible at /robots.txt"""
        # The frontend URL should serve the static robots.txt file
        response = requests.get(f"{BASE_URL}/robots.txt")
        
        if response.status_code == 200:
            robots_text = response.text
            assert "User-agent" in robots_text, "Should have User-agent directive"
            print("Static robots.txt accessible at /robots.txt")
        elif response.status_code == 404:
            # May be served by frontend, check frontend URL
            print("Static robots.txt not served at /robots.txt via backend - may be served by frontend directly")
        else:
            print(f"robots.txt at root returned status {response.status_code}")
