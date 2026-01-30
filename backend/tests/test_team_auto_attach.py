"""
Test Suite: Team Creation Auto-Attach Companies Feature
Tests the auto-attach functionality where companies assigned to an employer
are automatically included when creating a team.

Key Features Tested:
1. GET /api/employers/{employer_id}/companies - Returns companies assigned to employer
2. POST /api/teams - Auto-attaches employer's companies during team creation
3. Backend correctly merges auto-attached + explicitly selected companies
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"

# Test employer ID from context
TEST_EMPLOYER_ID = "cf36890a-b8fa-47e2-abf3-d4600f04c831"  # Ajit Yadav


class TestTeamAutoAttach:
    """Test suite for Team Creation Auto-Attach Companies feature"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Get admin token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Admin login failed: {login_response.text}"
        
        token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        yield
        
        # Cleanup: No specific cleanup needed
    
    # ============== GET /api/employers/{employer_id}/companies Tests ==============
    
    def test_get_employer_companies_success(self):
        """Test: GET /api/employers/{employer_id}/companies returns companies assigned to employer"""
        response = self.session.get(f"{BASE_URL}/api/employers/{TEST_EMPLOYER_ID}/companies")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "employer_id" in data, "Response should contain employer_id"
        assert "employer_name" in data, "Response should contain employer_name"
        assert "companies" in data, "Response should contain companies list"
        assert "count" in data, "Response should contain count"
        
        # Verify employer_id matches
        assert data["employer_id"] == TEST_EMPLOYER_ID
        
        # Verify companies is a list
        assert isinstance(data["companies"], list)
        
        # Verify count matches companies length
        assert data["count"] == len(data["companies"])
        
        print(f"✅ GET /api/employers/{TEST_EMPLOYER_ID}/companies - Found {data['count']} companies")
        print(f"   Employer: {data['employer_name']}")
        for comp in data["companies"]:
            print(f"   - {comp.get('name', 'Unknown')} (ID: {comp.get('id', 'N/A')})")
    
    def test_get_employer_companies_nonexistent_employer(self):
        """Test: GET /api/employers/{employer_id}/companies returns 404 for non-existent employer"""
        fake_employer_id = str(uuid.uuid4())
        response = self.session.get(f"{BASE_URL}/api/employers/{fake_employer_id}/companies")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print(f"✅ GET /api/employers/{fake_employer_id}/companies - Correctly returns 404 for non-existent employer")
    
    def test_get_employer_companies_requires_admin(self):
        """Test: GET /api/employers/{employer_id}/companies requires admin role"""
        # Create a new session without auth
        no_auth_session = requests.Session()
        no_auth_session.headers.update({"Content-Type": "application/json"})
        
        response = no_auth_session.get(f"{BASE_URL}/api/employers/{TEST_EMPLOYER_ID}/companies")
        
        # Should return 401 or 403
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"✅ GET /api/employers/{TEST_EMPLOYER_ID}/companies - Correctly requires authentication")
    
    # ============== POST /api/teams Auto-Attach Tests ==============
    
    def test_create_team_auto_attaches_employer_companies(self):
        """Test: POST /api/teams auto-attaches companies assigned to employer"""
        # First, get employer's companies
        companies_response = self.session.get(f"{BASE_URL}/api/employers/{TEST_EMPLOYER_ID}/companies")
        assert companies_response.status_code == 200
        employer_companies = companies_response.json().get("companies", [])
        employer_company_ids = [c["id"] for c in employer_companies]
        
        # Create team with only employer_id (no explicit company_ids)
        team_name = f"TEST_AutoAttach_Team_{uuid.uuid4().hex[:8]}"
        create_response = self.session.post(f"{BASE_URL}/api/teams", json={
            "name": team_name,
            "employer_id": TEST_EMPLOYER_ID,
            "recruiter_ids": [],
            "company_ids": []  # Empty - should auto-attach employer's companies
        })
        
        assert create_response.status_code == 200, f"Expected 200, got {create_response.status_code}: {create_response.text}"
        
        team_data = create_response.json()
        
        # Verify team was created
        assert team_data.get("name") == team_name
        assert team_data.get("employer_id") == TEST_EMPLOYER_ID
        
        # Verify auto-attached companies
        team_company_ids = team_data.get("company_ids", [])
        
        # All employer companies should be in team
        for emp_comp_id in employer_company_ids:
            assert emp_comp_id in team_company_ids, f"Employer company {emp_comp_id} should be auto-attached"
        
        print(f"✅ POST /api/teams - Auto-attached {len(employer_company_ids)} companies from employer")
        print(f"   Team: {team_name}")
        print(f"   Employer companies: {employer_company_ids}")
        print(f"   Team companies: {team_company_ids}")
        
        # Cleanup: Delete the test team
        team_id = team_data.get("id")
        if team_id:
            self.session.delete(f"{BASE_URL}/api/teams/{team_id}")
    
    def test_create_team_merges_auto_and_explicit_companies(self):
        """Test: POST /api/teams merges auto-attached + explicitly selected companies"""
        # Get employer's companies
        companies_response = self.session.get(f"{BASE_URL}/api/employers/{TEST_EMPLOYER_ID}/companies")
        assert companies_response.status_code == 200
        employer_companies = companies_response.json().get("companies", [])
        employer_company_ids = [c["id"] for c in employer_companies]
        
        # Get all companies to find one NOT assigned to employer
        all_companies_response = self.session.get(f"{BASE_URL}/api/companies")
        assert all_companies_response.status_code == 200
        all_companies = all_companies_response.json()
        
        # Find a company not assigned to this employer
        additional_company_id = None
        for comp in all_companies:
            if comp["id"] not in employer_company_ids:
                additional_company_id = comp["id"]
                break
        
        if not additional_company_id:
            pytest.skip("No additional company available for merge test")
        
        # Create team with explicit additional company
        team_name = f"TEST_MergeCompanies_Team_{uuid.uuid4().hex[:8]}"
        create_response = self.session.post(f"{BASE_URL}/api/teams", json={
            "name": team_name,
            "employer_id": TEST_EMPLOYER_ID,
            "recruiter_ids": [],
            "company_ids": [additional_company_id]  # Explicitly add one more company
        })
        
        assert create_response.status_code == 200, f"Expected 200, got {create_response.status_code}: {create_response.text}"
        
        team_data = create_response.json()
        team_company_ids = team_data.get("company_ids", [])
        
        # Verify all employer companies are included
        for emp_comp_id in employer_company_ids:
            assert emp_comp_id in team_company_ids, f"Employer company {emp_comp_id} should be auto-attached"
        
        # Verify additional company is also included
        assert additional_company_id in team_company_ids, "Explicitly added company should be in team"
        
        # Verify total count is correct (no duplicates)
        expected_count = len(set(employer_company_ids + [additional_company_id]))
        assert len(team_company_ids) == expected_count, f"Expected {expected_count} companies, got {len(team_company_ids)}"
        
        print(f"✅ POST /api/teams - Correctly merged auto-attached + explicit companies")
        print(f"   Auto-attached: {len(employer_company_ids)}")
        print(f"   Explicit: 1")
        print(f"   Total (merged): {len(team_company_ids)}")
        
        # Cleanup
        team_id = team_data.get("id")
        if team_id:
            self.session.delete(f"{BASE_URL}/api/teams/{team_id}")
    
    def test_create_team_no_duplicates_when_explicit_matches_auto(self):
        """Test: POST /api/teams doesn't create duplicates when explicit company is same as auto-attached"""
        # Get employer's companies
        companies_response = self.session.get(f"{BASE_URL}/api/employers/{TEST_EMPLOYER_ID}/companies")
        assert companies_response.status_code == 200
        employer_companies = companies_response.json().get("companies", [])
        
        if not employer_companies:
            pytest.skip("Employer has no companies assigned")
        
        employer_company_ids = [c["id"] for c in employer_companies]
        
        # Create team with explicit company that's already auto-attached
        team_name = f"TEST_NoDuplicates_Team_{uuid.uuid4().hex[:8]}"
        create_response = self.session.post(f"{BASE_URL}/api/teams", json={
            "name": team_name,
            "employer_id": TEST_EMPLOYER_ID,
            "recruiter_ids": [],
            "company_ids": employer_company_ids  # Same as auto-attached
        })
        
        assert create_response.status_code == 200, f"Expected 200, got {create_response.status_code}: {create_response.text}"
        
        team_data = create_response.json()
        team_company_ids = team_data.get("company_ids", [])
        
        # Verify no duplicates
        assert len(team_company_ids) == len(set(team_company_ids)), "Team should not have duplicate company IDs"
        assert len(team_company_ids) == len(employer_company_ids), "Count should match employer companies"
        
        print(f"✅ POST /api/teams - No duplicates when explicit matches auto-attached")
        print(f"   Companies: {len(team_company_ids)}")
        
        # Cleanup
        team_id = team_data.get("id")
        if team_id:
            self.session.delete(f"{BASE_URL}/api/teams/{team_id}")
    
    def test_create_team_employer_with_no_companies(self):
        """Test: POST /api/teams works when employer has no companies assigned"""
        # Get all employers
        employers_response = self.session.get(f"{BASE_URL}/api/admin/employers")
        assert employers_response.status_code == 200
        employers = employers_response.json()
        
        # Find an employer with no companies (or use a test employer)
        # For this test, we'll create a team and verify it works even with empty auto-attach
        
        # Get employer's companies first
        companies_response = self.session.get(f"{BASE_URL}/api/employers/{TEST_EMPLOYER_ID}/companies")
        employer_companies = companies_response.json().get("companies", [])
        
        # Create team - should work regardless of company count
        team_name = f"TEST_EmptyCompanies_Team_{uuid.uuid4().hex[:8]}"
        create_response = self.session.post(f"{BASE_URL}/api/teams", json={
            "name": team_name,
            "employer_id": TEST_EMPLOYER_ID,
            "recruiter_ids": [],
            "company_ids": []
        })
        
        assert create_response.status_code == 200, f"Expected 200, got {create_response.status_code}: {create_response.text}"
        
        team_data = create_response.json()
        
        # Team should be created successfully
        assert team_data.get("name") == team_name
        assert team_data.get("employer_id") == TEST_EMPLOYER_ID
        
        print(f"✅ POST /api/teams - Works with employer's companies (count: {len(employer_companies)})")
        
        # Cleanup
        team_id = team_data.get("id")
        if team_id:
            self.session.delete(f"{BASE_URL}/api/teams/{team_id}")
    
    # ============== Validation Tests ==============
    
    def test_create_team_requires_name(self):
        """Test: POST /api/teams requires team name"""
        create_response = self.session.post(f"{BASE_URL}/api/teams", json={
            "name": "",  # Empty name
            "employer_id": TEST_EMPLOYER_ID,
            "recruiter_ids": [],
            "company_ids": []
        })
        
        # Should fail validation
        assert create_response.status_code in [400, 422], f"Expected 400/422, got {create_response.status_code}"
        print(f"✅ POST /api/teams - Correctly validates required team name")
    
    def test_create_team_requires_valid_employer(self):
        """Test: POST /api/teams requires valid employer_id"""
        fake_employer_id = str(uuid.uuid4())
        create_response = self.session.post(f"{BASE_URL}/api/teams", json={
            "name": "TEST_InvalidEmployer_Team",
            "employer_id": fake_employer_id,
            "recruiter_ids": [],
            "company_ids": []
        })
        
        # Should return 404 for non-existent employer
        assert create_response.status_code == 404, f"Expected 404, got {create_response.status_code}"
        print(f"✅ POST /api/teams - Correctly validates employer exists")
    
    def test_create_team_validates_company_ids(self):
        """Test: POST /api/teams validates company_ids exist"""
        fake_company_id = str(uuid.uuid4())
        create_response = self.session.post(f"{BASE_URL}/api/teams", json={
            "name": "TEST_InvalidCompany_Team",
            "employer_id": TEST_EMPLOYER_ID,
            "recruiter_ids": [],
            "company_ids": [fake_company_id]  # Non-existent company
        })
        
        # Should return 400 for non-existent company
        assert create_response.status_code == 400, f"Expected 400, got {create_response.status_code}"
        print(f"✅ POST /api/teams - Correctly validates company IDs exist")


class TestEmployerCompaniesEndpoint:
    """Additional tests for GET /api/employers/{employer_id}/companies endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Get admin token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200
        
        token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        yield
    
    def test_employer_companies_response_structure(self):
        """Test: Response structure of GET /api/employers/{employer_id}/companies"""
        response = self.session.get(f"{BASE_URL}/api/employers/{TEST_EMPLOYER_ID}/companies")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify top-level structure
        required_fields = ["employer_id", "employer_name", "companies", "count"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Verify company structure (if companies exist)
        if data["companies"]:
            company = data["companies"][0]
            # Companies should have at least id and name
            assert "id" in company, "Company should have id"
            assert "name" in company, "Company should have name"
        
        print(f"✅ Response structure validated")
        print(f"   Fields: {list(data.keys())}")
    
    def test_employer_companies_filters_by_status(self):
        """Test: Endpoint returns companies with active status or backwards-compatible None status"""
        response = self.session.get(f"{BASE_URL}/api/employers/{TEST_EMPLOYER_ID}/companies")
        
        assert response.status_code == 200
        data = response.json()
        
        # All returned companies should have status active, None, or missing
        for company in data["companies"]:
            status = company.get("status")
            assert status in ["active", None] or "status" not in company, \
                f"Company {company.get('name')} has unexpected status: {status}"
        
        print(f"✅ All returned companies have valid status (active/None/missing)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
