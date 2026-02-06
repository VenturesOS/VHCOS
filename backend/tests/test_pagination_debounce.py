"""
Test Suite: Server-side Pagination and Search for Candidate Data Bank
Tests pagination parameters, response structure, and search filtering
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestCandidateBankPagination:
    """Tests for server-side pagination on /api/candidate-bank endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_pagination_response_structure(self):
        """Test that response includes pagination metadata"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=1&limit=50",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify pagination fields exist
        assert "candidates" in data, "Response missing 'candidates' field"
        assert "total" in data, "Response missing 'total' field"
        assert "page" in data, "Response missing 'page' field"
        assert "limit" in data, "Response missing 'limit' field"
        assert "total_pages" in data, "Response missing 'total_pages' field"
        
        # Verify data types
        assert isinstance(data["candidates"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["page"], int)
        assert isinstance(data["limit"], int)
        assert isinstance(data["total_pages"], int)
    
    def test_pagination_page_1_limit_50(self):
        """Test first page with 50 items per page"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=1&limit=50",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["page"] == 1
        assert data["limit"] == 50
        assert len(data["candidates"]) <= 50
        
        # With 1701 candidates, should have 35 pages
        if data["total"] == 1701:
            assert data["total_pages"] == 35
    
    def test_pagination_page_2(self):
        """Test second page returns different candidates"""
        # Get page 1
        response1 = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=1&limit=50",
            headers=self.headers
        )
        data1 = response1.json()
        
        # Get page 2
        response2 = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=2&limit=50",
            headers=self.headers
        )
        data2 = response2.json()
        
        assert response2.status_code == 200
        assert data2["page"] == 2
        
        # Verify different candidates on different pages
        if data1["candidates"] and data2["candidates"]:
            page1_ids = {c["id"] for c in data1["candidates"]}
            page2_ids = {c["id"] for c in data2["candidates"]}
            assert page1_ids.isdisjoint(page2_ids), "Page 1 and Page 2 should have different candidates"
    
    def test_pagination_last_page(self):
        """Test last page returns remaining candidates"""
        # First get total to calculate last page
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=1&limit=50",
            headers=self.headers
        )
        data = response.json()
        total_pages = data["total_pages"]
        total = data["total"]
        
        # Get last page
        response_last = requests.get(
            f"{BASE_URL}/api/candidate-bank?page={total_pages}&limit=50",
            headers=self.headers
        )
        data_last = response_last.json()
        
        assert response_last.status_code == 200
        assert data_last["page"] == total_pages
        
        # Last page should have remaining candidates
        expected_last_page_count = total % 50 if total % 50 != 0 else 50
        assert len(data_last["candidates"]) == expected_last_page_count
    
    def test_pagination_beyond_total_pages(self):
        """Test requesting page beyond total returns empty candidates"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=100&limit=50",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should return empty candidates but valid pagination info
        assert len(data["candidates"]) == 0
        assert data["page"] == 100
        assert data["total"] > 0  # Total should still be accurate
    
    def test_pagination_limit_enforcement(self):
        """Test that limit is capped at 100"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=1&limit=200",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Limit should be capped at 100
        assert data["limit"] == 100
        assert len(data["candidates"]) <= 100
    
    def test_pagination_minimum_values(self):
        """Test minimum page and limit values"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=0&limit=0",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should enforce minimum values
        assert data["page"] >= 1
        assert data["limit"] >= 1


class TestCandidateBankSearch:
    """Tests for search filtering with pagination"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
        )
        assert login_response.status_code == 200
        self.token = login_response.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_search_by_name(self):
        """Test search filters by candidate name"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?search=Ankita&page=1&limit=50",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should return filtered results
        assert data["total"] < 1701  # Less than total
        
        # All returned candidates should match search
        for candidate in data["candidates"]:
            name = candidate.get("name", "").lower()
            email = candidate.get("email", "").lower()
            skills = " ".join(candidate.get("skills", [])).lower()
            assert "ankita" in name or "ankita" in email or "ankita" in skills
    
    def test_search_by_skill(self):
        """Test search filters by skill"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?search=Python&page=1&limit=50",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should return filtered results
        assert data["total"] > 0
        assert data["total"] < 1701  # Less than total
    
    def test_search_updates_total_count(self):
        """Test that search updates total count correctly"""
        # Get total without search
        response_all = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=1&limit=50",
            headers=self.headers
        )
        total_all = response_all.json()["total"]
        
        # Get total with search
        response_search = requests.get(
            f"{BASE_URL}/api/candidate-bank?search=Ankita&page=1&limit=50",
            headers=self.headers
        )
        total_search = response_search.json()["total"]
        
        # Search total should be less than all
        assert total_search < total_all
        
        # Total pages should be recalculated
        data_search = response_search.json()
        expected_pages = (total_search + 49) // 50  # Ceiling division
        assert data_search["total_pages"] == expected_pages
    
    def test_search_with_pagination(self):
        """Test search works correctly with pagination"""
        # Search that returns multiple pages
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?search=a&page=1&limit=10",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have pagination info
        assert data["page"] == 1
        assert data["limit"] == 10
        assert len(data["candidates"]) <= 10
    
    def test_empty_search_returns_all(self):
        """Test empty search returns all candidates"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?search=&page=1&limit=50",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should return all candidates
        assert data["total"] == 1701 or data["total"] > 1000  # Allow some variance


class TestPaginationCalculations:
    """Tests for pagination calculation accuracy"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
        )
        assert login_response.status_code == 200
        self.token = login_response.json().get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_total_pages_calculation(self):
        """Test total_pages is calculated correctly (ceiling division)"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=1&limit=50",
            headers=self.headers
        )
        data = response.json()
        
        total = data["total"]
        limit = data["limit"]
        total_pages = data["total_pages"]
        
        # Verify ceiling division: (total + limit - 1) // limit
        expected_pages = (total + limit - 1) // limit
        assert total_pages == expected_pages, f"Expected {expected_pages} pages, got {total_pages}"
    
    def test_different_limits_affect_total_pages(self):
        """Test that different limits produce correct total_pages"""
        # Test with limit 50
        response_50 = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=1&limit=50",
            headers=self.headers
        )
        data_50 = response_50.json()
        
        # Test with limit 100
        response_100 = requests.get(
            f"{BASE_URL}/api/candidate-bank?page=1&limit=100",
            headers=self.headers
        )
        data_100 = response_100.json()
        
        # Same total, different pages
        assert data_50["total"] == data_100["total"]
        assert data_50["total_pages"] > data_100["total_pages"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
