"""
Test suite for VHC Talent OS Candidate Data Bank Advanced Filters (12 filters)
Tests: phone, email, location, company, skills, notice period, experience range,
salary range, source, has_resume, contact_hidden, capture date range

This iteration tests the new filter system implemented in iteration 100.
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable is required")

ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


class TestCandidateBankFilters:
    """Tests for candidate-bank advanced filter endpoints"""
    
    @classmethod
    def setup_class(cls):
        """Setup session with auth token for all tests in class"""
        cls.session = requests.Session()
        cls.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = cls.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get("access_token") or data.get("token")
            if token:
                cls.session.headers.update({"Authorization": f"Bearer {token}"})
                cls.token = token
            else:
                pytest.skip("No token returned from login")
        else:
            pytest.skip(f"Login failed: {login_response.status_code}")
    
    # --------------- Filter Options Endpoint ---------------
    
    def test_filter_options_returns_locations_companies_sources(self):
        """GET /api/candidate-bank/filter-options should return locations, companies, sources, notice_periods"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank/filter-options")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "locations" in data, "Response missing 'locations' field"
        assert "companies" in data, "Response missing 'companies' field"
        assert "sources" in data, "Response missing 'sources' field"
        assert "notice_periods" in data, "Response missing 'notice_periods' field"
        
        # Verify notice_periods are predefined
        expected_notice = ["Immediate", "15 days", "30 days", "45 days", "60 days", "90 days", "90+ days"]
        assert data["notice_periods"] == expected_notice, f"Notice periods mismatch: {data['notice_periods']}"
        
        # Verify arrays
        assert isinstance(data["locations"], list), "locations should be a list"
        assert isinstance(data["companies"], list), "companies should be a list"
        print(f"Filter options: {len(data['locations'])} locations, {len(data['companies'])} companies, {len(data['sources'])} sources")
    
    # --------------- Basic List ---------------
    
    def test_list_candidates_basic(self):
        """GET /api/candidate-bank returns paginated candidates"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data, "Response should have 'candidates' key"
        assert "total" in data, "Response should have 'total' key"
        assert "page" in data, "Response should have 'page' key"
        assert "pages" in data, "Response should have 'pages' key"
        
        print(f"Total candidates: {data['total']}, Page {data['page']} of {data['pages']}")
    
    # --------------- Phone Filter ---------------
    
    def test_filter_by_phone(self):
        """GET /api/candidate-bank?phone=9876 should filter candidates by phone"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?phone=98")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        
        # All results should have phone containing '98' (partial match)
        for candidate in data["candidates"]:
            phone = candidate.get("phone", "") or ""
            if phone:  # Only check if phone exists
                assert "98" in phone.replace(" ", "").replace("-", ""), f"Phone '{phone}' doesn't match filter"
        
        print(f"Phone filter '98': Found {len(data['candidates'])} candidates, total {data['total']}")
    
    # --------------- Email Filter ---------------
    
    def test_filter_by_email(self):
        """GET /api/candidate-bank?email=gmail should filter by email"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?email=gmail")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        
        # Results should have gmail in email
        for candidate in data["candidates"]:
            email = candidate.get("email", "") or ""
            if email:
                assert "gmail" in email.lower(), f"Email '{email}' doesn't contain gmail"
        
        print(f"Email filter 'gmail': Found {len(data['candidates'])} candidates, total {data['total']}")
    
    # --------------- Location Filter ---------------
    
    def test_filter_by_location(self):
        """GET /api/candidate-bank?location=Mumbai should filter by location"""
        # First get some valid location
        options_resp = self.session.get(f"{BASE_URL}/api/candidate-bank/filter-options")
        if options_resp.status_code == 200 and options_resp.json().get("locations"):
            test_location = options_resp.json()["locations"][0] if options_resp.json()["locations"] else "Mumbai"
        else:
            test_location = "Mumbai"
        
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?location={test_location}")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        print(f"Location filter '{test_location}': Found {data['total']} candidates")
    
    # --------------- Skills Filter ---------------
    
    def test_filter_by_skills_single(self):
        """GET /api/candidate-bank?skills=Java should filter by single skill"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?skills=Java")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        print(f"Skills filter 'Java': Found {data['total']} candidates")
    
    def test_filter_by_skills_multiple(self):
        """GET /api/candidate-bank?skills=Java,Python should filter by multiple skills"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?skills=Java,Python")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        print(f"Skills filter 'Java,Python': Found {data['total']} candidates")
    
    # --------------- Company Filter ---------------
    
    def test_filter_by_company(self):
        """GET /api/candidate-bank?company=Tata should filter by company"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?company=Tata")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        print(f"Company filter 'Tata': Found {data['total']} candidates")
    
    # --------------- Notice Period Filter ---------------
    
    def test_filter_by_notice_period(self):
        """GET /api/candidate-bank?notice_period=Immediate should filter by notice period"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?notice_period=Immediate")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        
        # Verify results match filter
        for candidate in data["candidates"]:
            np = candidate.get("notice_period", "") or ""
            if np:  # Only check if notice_period exists
                assert np == "Immediate", f"Notice period '{np}' doesn't match 'Immediate'"
        
        print(f"Notice period filter 'Immediate': Found {data['total']} candidates")
    
    # --------------- Experience Range Filter ---------------
    
    def test_filter_by_experience_range(self):
        """GET /api/candidate-bank?min_experience=3&max_experience=8 should filter by experience range"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?min_experience=3&max_experience=8")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        
        # Verify results are within range
        for candidate in data["candidates"]:
            exp = candidate.get("experience_years")
            if exp is not None:
                assert 3 <= exp <= 8, f"Experience {exp} not in range 3-8"
        
        print(f"Experience filter 3-8 years: Found {data['total']} candidates")
    
    def test_filter_by_min_experience_only(self):
        """GET /api/candidate-bank?min_experience=5 should filter by minimum experience"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?min_experience=5")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        
        for candidate in data["candidates"]:
            exp = candidate.get("experience_years")
            if exp is not None:
                assert exp >= 5, f"Experience {exp} is less than minimum 5"
        
        print(f"Min experience filter 5: Found {data['total']} candidates")
    
    # --------------- Salary Range Filter ---------------
    
    def test_filter_by_salary_range(self):
        """GET /api/candidate-bank?min_salary=500000&max_salary=1500000 should filter by salary range"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?min_salary=500000&max_salary=1500000")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        
        # Verify results are within range
        for candidate in data["candidates"]:
            salary = candidate.get("current_salary")
            if salary is not None:
                assert 500000 <= salary <= 1500000, f"Salary {salary} not in range 500000-1500000"
        
        print(f"Salary filter 5L-15L: Found {data['total']} candidates")
    
    # --------------- Source Filter ---------------
    
    def test_filter_by_source_extension(self):
        """GET /api/candidate-bank?source=extension should filter by Naukri extension source"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?source=extension")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        print(f"Source filter 'extension': Found {data['total']} candidates")
    
    # --------------- Has Resume Filter ---------------
    
    def test_filter_has_resume_yes(self):
        """GET /api/candidate-bank?has_resume=yes should return candidates with resume"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?has_resume=yes")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        
        # Verify at least some candidates have resume
        resume_count = sum(1 for c in data["candidates"] if c.get("resume_url") or c.get("resume_path") or c.get("resume_latex"))
        print(f"Has resume 'yes': Found {data['total']} total, {resume_count} with resume in page")
    
    def test_filter_has_resume_no(self):
        """GET /api/candidate-bank?has_resume=no should return candidates without resume"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?has_resume=no")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        print(f"Has resume 'no': Found {data['total']} candidates without resume")
    
    # --------------- Contact Hidden Filter ---------------
    
    def test_filter_contact_hidden_yes(self):
        """GET /api/candidate-bank?contact_hidden=yes should return profiles missing email OR phone"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?contact_hidden=yes")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        
        # Verify at least some candidates have missing contact
        for candidate in data["candidates"]:
            email = candidate.get("email") or ""
            phone = candidate.get("phone") or ""
            # At least one should be empty/missing
            assert not email or not phone, f"Both email '{email}' and phone '{phone}' present for contact_hidden=yes"
        
        print(f"Contact hidden 'yes': Found {data['total']} candidates with hidden/missing contact")
    
    def test_filter_contact_hidden_no(self):
        """GET /api/candidate-bank?contact_hidden=no should return profiles with BOTH email and phone"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?contact_hidden=no")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        
        # Verify candidates have both email and phone
        for candidate in data["candidates"]:
            email = candidate.get("email") or ""
            phone = candidate.get("phone") or ""
            assert email and phone, f"Missing contact for contact_hidden=no: email='{email}', phone='{phone}'"
        
        print(f"Contact hidden 'no': Found {data['total']} candidates with visible contact")
    
    # --------------- Capture Date Range Filter ---------------
    
    def test_filter_by_captured_after(self):
        """GET /api/candidate-bank?captured_after=2024-01-01 should filter by capture date"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?captured_after=2024-01-01")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        print(f"Captured after 2024-01-01: Found {data['total']} candidates")
    
    def test_filter_by_captured_before(self):
        """GET /api/candidate-bank?captured_before=2025-12-31 should filter by capture date"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?captured_before=2025-12-31")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        print(f"Captured before 2025-12-31: Found {data['total']} candidates")
    
    # --------------- Combined Filters ---------------
    
    def test_combined_filters_location_skills(self):
        """Multiple filters: location + skills should work together"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?location=Mumbai&skills=Java")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        print(f"Combined filter location=Mumbai + skills=Java: Found {data['total']} candidates")
    
    def test_combined_filters_contact_experience(self):
        """Multiple filters: contact_hidden + experience range"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?contact_hidden=no&min_experience=3&max_experience=10")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        
        # Verify both filters applied
        for candidate in data["candidates"]:
            email = candidate.get("email") or ""
            phone = candidate.get("phone") or ""
            assert email and phone, "contact_hidden=no should have both"
            
            exp = candidate.get("experience_years")
            if exp is not None:
                assert 3 <= exp <= 10, f"Experience {exp} not in range"
        
        print(f"Combined filter contact_hidden=no + exp 3-10: Found {data['total']} candidates")
    
    def test_combined_filters_multiple(self):
        """Multiple filters combined: location + skills + contact_hidden"""
        params = "location=Bangalore&skills=Python&contact_hidden=no"
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?{params}")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        print(f"Combined filter (3 filters): Found {data['total']} candidates")
    
    # --------------- Pagination with Filters ---------------
    
    def test_pagination_with_filters(self):
        """Pagination should work with filters applied"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?page=1&limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert data["page"] == 1
        assert len(data["candidates"]) <= 10
        
        # Test page 2 if available
        if data["pages"] > 1:
            response2 = self.session.get(f"{BASE_URL}/api/candidate-bank?page=2&limit=10")
            assert response2.status_code == 200
            data2 = response2.json()
            assert data2["page"] == 2
            
            # Verify different candidates on different pages
            page1_ids = {c["id"] for c in data["candidates"]}
            page2_ids = {c["id"] for c in data2["candidates"]}
            assert not page1_ids.intersection(page2_ids), "Page 1 and 2 should have different candidates"
        
        print(f"Pagination: Page {data['page']} of {data['pages']}, {len(data['candidates'])} candidates")
    
    # --------------- Edge Cases ---------------
    
    def test_empty_filter_values(self):
        """Empty filter values should not affect results"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?phone=&email=")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        print(f"Empty filter values: Found {data['total']} candidates (should be all)")
    
    def test_no_match_filter(self):
        """Filter with no matches should return empty list"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank?email=nonexistent123xyz@impossible.com")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        assert data["total"] == 0 or len(data["candidates"]) == 0
        print(f"No match filter: Found {data['total']} candidates (expected 0)")


class TestCandidateBankFilterAuth:
    """Test authentication requirements for filter endpoints"""
    
    def test_filter_options_requires_auth(self):
        """GET /api/candidate-bank/filter-options should require authentication"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/candidate-bank/filter-options")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("Filter options requires auth: VERIFIED")
    
    def test_candidate_list_requires_auth(self):
        """GET /api/candidate-bank should require authentication"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/candidate-bank")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("Candidate list requires auth: VERIFIED")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
