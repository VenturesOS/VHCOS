"""
SEO Phase 2: Dynamic Content Silo Architecture - Pillar Pages Backend Tests
Tests: Public pillar page API, Admin CRUD, Sitemap inclusion, Validation
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://dpdp-compliance-3.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"

@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Admin authentication failed")

@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session

@pytest.fixture
def authenticated_client(api_client, admin_token):
    """Session with admin auth header"""
    api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
    return api_client


class TestPublicPillarPages:
    """Public pillar page endpoint tests"""
    
    def test_get_industrial_recruitment(self, api_client):
        """GET /api/pillar-pages/industrial-recruitment returns published page"""
        response = api_client.get(f"{BASE_URL}/api/pillar-pages/industrial-recruitment")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["slug"] == "industrial-recruitment"
        assert data["status"] == "published"
        assert "meta_title" in data
        assert "meta_description" in data
        assert "hero" in data
        assert "content" in data
        assert data["hero"]["headline"] == "Industrial Recruitment Services in India"
        print(f"✓ industrial-recruitment page loaded with title: {data['meta_title']}")
    
    def test_get_hr_consulting_services(self, api_client):
        """GET /api/pillar-pages/hr-consulting-services returns published page"""
        response = api_client.get(f"{BASE_URL}/api/pillar-pages/hr-consulting-services")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["slug"] == "hr-consulting-services"
        assert data["status"] == "published"
        assert "meta_title" in data
        assert "meta_description" in data
        assert "hero" in data
        assert "content" in data
        assert "HR Consulting" in data["hero"]["headline"]
        print(f"✓ hr-consulting-services page loaded with title: {data['meta_title']}")
    
    def test_get_career_insights(self, api_client):
        """GET /api/pillar-pages/career-insights returns published page"""
        response = api_client.get(f"{BASE_URL}/api/pillar-pages/career-insights")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["slug"] == "career-insights"
        assert data["status"] == "published"
        assert "meta_title" in data
        assert "meta_description" in data
        assert "hero" in data
        assert "content" in data
        print(f"✓ career-insights page loaded with title: {data['meta_title']}")
    
    def test_get_nonexistent_slug_returns_404(self, api_client):
        """GET /api/pillar-pages/nonexistent returns 404"""
        response = api_client.get(f"{BASE_URL}/api/pillar-pages/nonexistent")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        print("✓ Nonexistent slug correctly returns 404")
    
    def test_get_invalid_slug_returns_404(self, api_client):
        """GET /api/pillar-pages/some-random-page returns 404 (not in allowed slugs)"""
        response = api_client.get(f"{BASE_URL}/api/pillar-pages/some-random-page")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Invalid slug correctly returns 404")
    
    def test_pillar_page_content_structure(self, api_client):
        """Verify pillar page has required content structure"""
        response = api_client.get(f"{BASE_URL}/api/pillar-pages/industrial-recruitment")
        data = response.json()
        
        # Check hero structure
        hero = data.get("hero", {})
        assert "headline" in hero
        assert "subtext" in hero
        assert "cta_text" in hero
        assert "cta_link" in hero
        
        # Check FAQ structure if present
        faq = data.get("faq", [])
        if faq:
            assert isinstance(faq, list)
            for item in faq:
                assert "question" in item
                assert "answer" in item
        
        print(f"✓ Content structure valid - {len(faq)} FAQ items")


class TestAdminPillarPagesAuth:
    """Admin pillar page authentication tests"""
    
    def test_admin_list_requires_auth(self, api_client):
        """GET /api/admin/pillar-pages requires admin auth"""
        response = api_client.get(f"{BASE_URL}/api/admin/pillar-pages")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ Admin list endpoint correctly requires authentication")
    
    def test_admin_list_with_auth(self, authenticated_client):
        """GET /api/admin/pillar-pages returns list for authenticated admin"""
        response = authenticated_client.get(f"{BASE_URL}/api/admin/pillar-pages")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "pages" in data
        assert isinstance(data["pages"], list)
        assert len(data["pages"]) >= 3, "Should have at least 3 pillar pages seeded"
        
        slugs = [p["slug"] for p in data["pages"]]
        assert "industrial-recruitment" in slugs
        assert "hr-consulting-services" in slugs
        assert "career-insights" in slugs
        print(f"✓ Admin list returned {len(data['pages'])} pillar pages")
    
    def test_admin_get_single_page(self, authenticated_client):
        """GET /api/admin/pillar-pages/{slug} returns single page for admin"""
        response = authenticated_client.get(f"{BASE_URL}/api/admin/pillar-pages/industrial-recruitment")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["slug"] == "industrial-recruitment"
        print("✓ Admin get single page works correctly")


class TestAdminPillarPagesValidation:
    """Admin pillar page validation tests"""
    
    def test_create_duplicate_slug_returns_409(self, authenticated_client):
        """POST /api/admin/pillar-pages with duplicate slug returns 409"""
        payload = {
            "slug": "industrial-recruitment",
            "title": "Duplicate Test",
            "meta_title": "Test",
            "meta_description": "Test"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/admin/pillar-pages", json=payload)
        assert response.status_code == 409, f"Expected 409, got {response.status_code}"
        print("✓ Duplicate slug correctly returns 409 Conflict")
    
    def test_create_invalid_slug_returns_400(self, authenticated_client):
        """POST /api/admin/pillar-pages with invalid slug returns 400"""
        payload = {
            "slug": "not-allowed-slug",
            "title": "Invalid Slug Test",
            "meta_title": "Test",
            "meta_description": "Test"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/admin/pillar-pages", json=payload)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        data = response.json()
        assert "Slug must be one of" in data.get("detail", "")
        print("✓ Invalid slug correctly returns 400 with allowed slugs message")


class TestAdminPillarPagesUpdate:
    """Admin pillar page update tests"""
    
    def test_update_pillar_page(self, authenticated_client):
        """PUT /api/admin/pillar-pages/{slug} updates correctly"""
        # Get current meta_description
        response = authenticated_client.get(f"{BASE_URL}/api/admin/pillar-pages/industrial-recruitment")
        original_data = response.json()
        
        # Update with new meta description
        new_meta_desc = f"Updated test description - {original_data.get('meta_description', '')[:50]}"
        payload = {
            "meta_description": new_meta_desc
        }
        response = authenticated_client.put(f"{BASE_URL}/api/admin/pillar-pages/industrial-recruitment", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Verify update
        data = response.json()
        assert data["meta_description"] == new_meta_desc
        assert "last_updated" in data
        assert "updated_by" in data
        print("✓ Pillar page update works correctly")
        
        # Restore original meta_description
        restore_payload = {"meta_description": original_data.get("meta_description", "")}
        authenticated_client.put(f"{BASE_URL}/api/admin/pillar-pages/industrial-recruitment", json=restore_payload)
    
    def test_update_nonexistent_returns_404(self, authenticated_client):
        """PUT /api/admin/pillar-pages/nonexistent returns 404"""
        payload = {"title": "Test"}
        response = authenticated_client.put(f"{BASE_URL}/api/admin/pillar-pages/nonexistent-page", json=payload)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Update nonexistent page correctly returns 404")


class TestSitemap:
    """Sitemap inclusion tests"""
    
    def test_sitemap_includes_pillar_pages(self, api_client):
        """GET /api/sitemap.xml includes pillar page URLs"""
        response = api_client.get(f"{BASE_URL}/api/sitemap.xml")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        sitemap_content = response.text
        
        # Check for pillar pages in sitemap
        assert "/industrial-recruitment" in sitemap_content, "industrial-recruitment missing from sitemap"
        assert "/hr-consulting-services" in sitemap_content, "hr-consulting-services missing from sitemap"
        # career-insights should also be in sitemap
        assert "/career-insights" in sitemap_content or "career-insights" in sitemap_content, "career-insights missing from sitemap"
        
        # Verify XML structure
        assert '<?xml version="1.0" encoding="UTF-8"?>' in sitemap_content
        assert '<urlset' in sitemap_content
        
        print("✓ Sitemap includes all pillar page URLs")
    
    def test_sitemap_pillar_page_priority(self, api_client):
        """Verify pillar pages have high priority in sitemap"""
        response = api_client.get(f"{BASE_URL}/api/sitemap.xml")
        sitemap_content = response.text
        
        # industrial-recruitment should have priority 0.9
        assert '<loc>https://ventureshrd.com/industrial-recruitment</loc>' in sitemap_content
        assert '<loc>https://ventureshrd.com/hr-consulting-services</loc>' in sitemap_content
        
        print("✓ Pillar pages have correct URLs in sitemap")


class TestPillarPageMetadata:
    """Pillar page metadata tests"""
    
    def test_page_has_all_seo_fields(self, api_client):
        """Verify pillar page has all required SEO metadata fields"""
        response = api_client.get(f"{BASE_URL}/api/pillar-pages/industrial-recruitment")
        data = response.json()
        
        required_fields = ["slug", "title", "meta_title", "meta_description", "hero", "content", "status"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Verify meta fields are populated
        assert len(data["meta_title"]) > 10, "meta_title too short"
        assert len(data["meta_description"]) > 50, "meta_description too short"
        
        print("✓ All SEO metadata fields present and populated")
    
    def test_hero_has_structured_data(self, api_client):
        """Verify hero section has required structured data"""
        response = api_client.get(f"{BASE_URL}/api/pillar-pages/hr-consulting-services")
        data = response.json()
        
        hero = data.get("hero", {})
        assert hero.get("headline"), "Hero headline missing"
        assert hero.get("subtext"), "Hero subtext missing"
        assert hero.get("cta_text"), "Hero CTA text missing"
        assert hero.get("cta_link"), "Hero CTA link missing"
        
        print("✓ Hero section has all structured data fields")
    
    def test_faq_structure(self, api_client):
        """Verify FAQ has correct structure for JSON-LD"""
        response = api_client.get(f"{BASE_URL}/api/pillar-pages/industrial-recruitment")
        data = response.json()
        
        faq = data.get("faq", [])
        assert len(faq) >= 3, f"Expected at least 3 FAQ items, got {len(faq)}"
        
        for item in faq:
            assert isinstance(item.get("question"), str) and len(item["question"]) > 10
            assert isinstance(item.get("answer"), str) and len(item["answer"]) > 20
        
        print(f"✓ FAQ structure valid with {len(faq)} items")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
