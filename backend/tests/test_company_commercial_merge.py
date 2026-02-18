"""
Test Suite: Company-Commercial Merge Feature
Tests for unified company/commercial flow where commercial is embedded within company.

Features tested:
- POST /api/companies with percentage commercial (admin only)
- POST /api/companies with fixed commercial (admin only)
- POST /api/companies with level_based commercial with 3+ ranges (admin only)
- POST /api/companies validation: no commercial returns 400
- POST /api/companies validation: overlapping ranges returns 400
- POST /api/companies validation: min >= max returns 400
- POST /api/companies validation: percentage <= 0 returns 400
- PUT /api/companies/{id} update with HR contacts and commercial
- GET /api/companies returns all companies with embedded commercial field
- Existing companies with migrated commercials still return correct data
- Legacy level_based companies show legacy_level_mapping
- PUT /api/companies/{id}/assign-employer still works
- GET /api/employer/my-team loads without errors
- GET /api/employer/companies loads with commercial data
- GET /api/employer/pipeline loads without errors
- GET /api/analytics/admin loads without errors
"""

import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://pillar-pages-hub.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
EMPLOYER_EMAIL = "ajit@vhc.in"
EMPLOYER_PASSWORD = "12345678"


class TestCompanyCommercialMerge:
    """Test company creation with embedded commercial models"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with admin auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        token = login_resp.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.admin_token = token
        
        # Track created companies for cleanup
        self.created_company_ids = []
        
        yield
        
        # Cleanup: delete test companies
        for company_id in self.created_company_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/companies/{company_id}")
            except:
                pass
    
    # ================== CREATE COMPANY TESTS ==================
    
    def test_create_company_percentage_commercial(self):
        """POST /api/companies with percentage type commercial"""
        payload = {
            "name": f"TEST_Percentage_Co_{uuid.uuid4().hex[:6]}",
            "description": "Test company with percentage commercial",
            "industry": "IT",
            "location": "Mumbai",
            "hr_contacts": [
                {"name": "HR Manager", "email": "hr@test.com", "phone": "9876543210"}
            ],
            "commercial": {
                "type": "percentage",
                "percentage_value": 8.33
            }
        }
        
        resp = self.session.post(f"{BASE_URL}/api/companies", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        self.created_company_ids.append(data["id"])
        
        # Verify response structure
        assert data["name"] == payload["name"]
        assert "commercial" in data
        assert data["commercial"]["type"] == "percentage"
        assert data["commercial"]["percentage_value"] == 8.33
        print(f"✓ Created percentage commercial company: {data['id']}")
    
    def test_create_company_fixed_commercial(self):
        """POST /api/companies with fixed fee type commercial"""
        payload = {
            "name": f"TEST_Fixed_Co_{uuid.uuid4().hex[:6]}",
            "industry": "Manufacturing",
            "location": "Chennai",
            "commercial": {
                "type": "fixed",
                "fixed_fee_amount": 50000
            }
        }
        
        resp = self.session.post(f"{BASE_URL}/api/companies", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        self.created_company_ids.append(data["id"])
        
        assert data["commercial"]["type"] == "fixed"
        assert data["commercial"]["fixed_fee_amount"] == 50000
        print(f"✓ Created fixed fee commercial company: {data['id']}")
    
    def test_create_company_level_based_commercial(self):
        """POST /api/companies with level_based commercial with 3+ ranges"""
        payload = {
            "name": f"TEST_LevelBased_Co_{uuid.uuid4().hex[:6]}",
            "industry": "Finance",
            "location": "Delhi",
            "commercial": {
                "type": "level_based",
                "level_config": [
                    {"min_salary": 100000, "max_salary": 500000, "percentage": 10.0},
                    {"min_salary": 500001, "max_salary": 1200000, "percentage": 8.33},
                    {"min_salary": 1200001, "max_salary": 2500000, "percentage": 6.5}
                ]
            }
        }
        
        resp = self.session.post(f"{BASE_URL}/api/companies", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        self.created_company_ids.append(data["id"])
        
        assert data["commercial"]["type"] == "level_based"
        assert len(data["commercial"]["level_config"]) == 3
        print(f"✓ Created level-based commercial company with 3 ranges: {data['id']}")
    
    # ================== VALIDATION TESTS ==================
    
    def test_create_company_no_commercial_returns_400(self):
        """POST /api/companies without commercial returns 400"""
        payload = {
            "name": f"TEST_NoCommercial_{uuid.uuid4().hex[:6]}",
            "industry": "Retail"
        }
        
        resp = self.session.post(f"{BASE_URL}/api/companies", json=payload)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "commercial" in resp.text.lower() or "required" in resp.text.lower()
        print("✓ No commercial validation works: 400 returned")
    
    def test_create_company_overlapping_ranges_returns_400(self):
        """POST /api/companies with overlapping salary ranges returns 400"""
        payload = {
            "name": f"TEST_Overlap_{uuid.uuid4().hex[:6]}",
            "commercial": {
                "type": "level_based",
                "level_config": [
                    {"min_salary": 100000, "max_salary": 500000, "percentage": 10.0},
                    {"min_salary": 400000, "max_salary": 800000, "percentage": 8.0}  # Overlaps!
                ]
            }
        }
        
        resp = self.session.post(f"{BASE_URL}/api/companies", json=payload)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "overlap" in resp.text.lower()
        print("✓ Overlapping ranges validation works: 400 returned")
    
    def test_create_company_min_gte_max_returns_400(self):
        """POST /api/companies with min_salary >= max_salary returns 400"""
        payload = {
            "name": f"TEST_MinMax_{uuid.uuid4().hex[:6]}",
            "commercial": {
                "type": "level_based",
                "level_config": [
                    {"min_salary": 500000, "max_salary": 100000, "percentage": 10.0}  # min > max
                ]
            }
        }
        
        resp = self.session.post(f"{BASE_URL}/api/companies", json=payload)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "min_salary must be less than max_salary" in resp.text.lower()
        print("✓ Min >= Max validation works: 400 returned")
    
    def test_create_company_percentage_lte_0_returns_400(self):
        """POST /api/companies with percentage <= 0 returns 400"""
        payload = {
            "name": f"TEST_ZeroPct_{uuid.uuid4().hex[:6]}",
            "commercial": {
                "type": "percentage",
                "percentage_value": 0
            }
        }
        
        resp = self.session.post(f"{BASE_URL}/api/companies", json=payload)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "percentage_value" in resp.text.lower() and "> 0" in resp.text.lower()
        print("✓ Percentage <= 0 validation works: 400 returned")
    
    # ================== UPDATE COMPANY TESTS ==================
    
    def test_update_company_with_hr_contacts_and_commercial(self):
        """PUT /api/companies/{id} updates HR contacts and commercial"""
        # First create a company
        create_payload = {
            "name": f"TEST_UpdateTest_{uuid.uuid4().hex[:6]}",
            "commercial": {"type": "percentage", "percentage_value": 8.0}
        }
        create_resp = self.session.post(f"{BASE_URL}/api/companies", json=create_payload)
        assert create_resp.status_code == 200
        company_id = create_resp.json()["id"]
        self.created_company_ids.append(company_id)
        
        # Update with new HR contacts and different commercial
        update_payload = {
            "name": create_payload["name"],  # Keep same name
            "industry": "Updated Industry",
            "hr_contacts": [
                {"name": "New HR 1", "email": "newhr1@test.com", "phone": "1111111111"},
                {"name": "New HR 2", "email": "newhr2@test.com", "phone": "2222222222"}
            ],
            "commercial": {
                "type": "fixed",
                "fixed_fee_amount": 75000
            }
        }
        
        update_resp = self.session.put(f"{BASE_URL}/api/companies/{company_id}", json=update_payload)
        assert update_resp.status_code == 200, f"Expected 200, got {update_resp.status_code}: {update_resp.text}"
        
        data = update_resp.json()
        assert data["industry"] == "Updated Industry"
        assert len(data["hr_contacts"]) == 2
        assert data["commercial"]["type"] == "fixed"
        assert data["commercial"]["fixed_fee_amount"] == 75000
        print(f"✓ Company updated with HR contacts and commercial: {company_id}")
    
    # ================== GET COMPANIES TEST ==================
    
    def test_get_all_companies_returns_commercial(self):
        """GET /api/companies returns all companies with embedded commercial"""
        resp = self.session.get(f"{BASE_URL}/api/companies")
        assert resp.status_code == 200
        
        companies = resp.json()
        assert isinstance(companies, list)
        
        # Check at least some companies have commercial data
        companies_with_commercial = [c for c in companies if c.get("commercial")]
        print(f"✓ GET /api/companies: {len(companies)} total, {len(companies_with_commercial)} with commercial data")
        assert len(companies_with_commercial) > 0, "Expected at least one company with commercial data"
    
    def test_migrated_companies_return_correct_data(self):
        """Existing companies with migrated commercials still return correct data"""
        resp = self.session.get(f"{BASE_URL}/api/companies")
        assert resp.status_code == 200
        
        companies = resp.json()
        
        # Find companies with different commercial types (handle None commercial)
        percentage_cos = [c for c in companies if c.get("commercial") and c["commercial"].get("type") == "percentage"]
        level_based_cos = [c for c in companies if c.get("commercial") and c["commercial"].get("type") == "level_based"]
        
        print(f"✓ Found {len(percentage_cos)} percentage commercial companies")
        print(f"✓ Found {len(level_based_cos)} level-based commercial companies")
        
        # Verify structure of migrated data
        for c in percentage_cos[:2]:
            assert "percentage_value" in c["commercial"] or c["commercial"].get("percentage_value") is not None
        
        for c in level_based_cos[:2]:
            comm = c["commercial"]
            # Should have either level_config array or legacy_level_mapping
            has_config = comm.get("level_config") and len(comm.get("level_config", [])) > 0
            has_legacy = comm.get("legacy_level_mapping") is not None
            assert has_config or has_legacy, f"Level-based company {c['name']} missing config"
    
    def test_legacy_level_based_shows_legacy_mapping(self):
        """Legacy level_based companies show legacy_level_mapping"""
        resp = self.session.get(f"{BASE_URL}/api/companies")
        assert resp.status_code == 200
        
        companies = resp.json()
        
        # Find companies with legacy_level_mapping (handle None commercial)
        legacy_cos = [c for c in companies if c.get("commercial") and c["commercial"].get("legacy_level_mapping")]
        
        print(f"✓ Found {len(legacy_cos)} companies with legacy_level_mapping")
        
        for c in legacy_cos[:3]:
            legacy = c["commercial"]["legacy_level_mapping"]
            print(f"  - {c['name']}: {list(legacy.keys())}")


class TestAssignEmployer:
    """Test employer assignment still works"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Admin login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        self.created_company_ids = []
        yield
        
        for company_id in self.created_company_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/companies/{company_id}")
            except:
                pass
    
    def test_assign_employer_to_company(self):
        """PUT /api/companies/{id}/assign-employer still works"""
        # Create a test company
        create_resp = self.session.post(f"{BASE_URL}/api/companies", json={
            "name": f"TEST_AssignTest_{uuid.uuid4().hex[:6]}",
            "commercial": {"type": "percentage", "percentage_value": 10.0}
        })
        assert create_resp.status_code == 200
        company_id = create_resp.json()["id"]
        self.created_company_ids.append(company_id)
        
        # Get an employer to assign
        employers_resp = self.session.get(f"{BASE_URL}/api/admin/employers")
        assert employers_resp.status_code == 200
        employers = employers_resp.json()
        
        if not employers:
            pytest.skip("No employers available for assignment test")
        
        employer_id = employers[0]["id"]
        employer_name = employers[0].get("name")
        
        # Assign employer
        assign_resp = self.session.put(
            f"{BASE_URL}/api/companies/{company_id}/assign-employer",
            params={"employer_id": employer_id}
        )
        assert assign_resp.status_code == 200, f"Expected 200, got {assign_resp.status_code}: {assign_resp.text}"
        
        # Verify assignment
        get_resp = self.session.get(f"{BASE_URL}/api/companies/{company_id}")
        assert get_resp.status_code == 200
        
        company_data = get_resp.json()
        assert company_data["assigned_employer_id"] == employer_id
        print(f"✓ Employer {employer_name} assigned to company {company_id}")


class TestEmployerEndpoints:
    """Test employer portal endpoints load correctly"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Try employer login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": EMPLOYER_EMAIL,
            "password": EMPLOYER_PASSWORD
        })
        
        if login_resp.status_code != 200:
            pytest.skip(f"Employer login failed: {login_resp.text}")
        
        token = login_resp.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    def test_employer_my_team_loads(self):
        """GET /api/employer/my-team loads without errors"""
        resp = self.session.get(f"{BASE_URL}/api/employer/my-team")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "team" in data or data.get("team") is None  # May be null if no team
        assert "members" in data
        assert "summary" in data
        print(f"✓ /api/employer/my-team loaded: {data.get('summary', {}).get('total_members', 0)} members")
    
    def test_employer_companies_loads_with_commercial(self):
        """GET /api/employer/companies loads with commercial data"""
        resp = self.session.get(f"{BASE_URL}/api/employer/companies")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "companies" in data
        
        companies = data["companies"]
        print(f"✓ /api/employer/companies loaded: {len(companies)} companies")
        
        # Check commercial data is present
        for c in companies[:3]:
            print(f"  - {c.get('name')}: commercial type = {c.get('commercial', {}).get('type', 'N/A')}")
    
    def test_employer_pipeline_loads(self):
        """GET /api/employer/pipeline loads without errors"""
        resp = self.session.get(f"{BASE_URL}/api/employer/pipeline")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "pipeline" in data
        assert "stage_counts" in data
        assert "total_applications" in data
        print(f"✓ /api/employer/pipeline loaded: {data.get('total_applications', 0)} applications")


class TestAdminAnalytics:
    """Test admin analytics endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    def test_admin_analytics_loads(self):
        """GET /api/analytics/admin loads without errors"""
        resp = self.session.get(f"{BASE_URL}/api/analytics/admin")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "kpis" in data
        assert "stage_distribution" in data
        
        kpis = data["kpis"]
        print(f"✓ Admin analytics loaded:")
        print(f"  - Active mandates: {kpis.get('total_active_mandates', 0)}")
        print(f"  - Pipeline revenue: {kpis.get('total_pipeline_revenue', 0)}")
        print(f"  - Closed revenue: {kpis.get('closed_revenue', 0)}")


class TestNoRegressions:
    """Regression tests to ensure other features still work"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    def test_admin_pipeline_loads(self):
        """GET /api/admin/pipeline still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/pipeline")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "pipeline" in data
        print(f"✓ Admin pipeline loads: {data.get('total_applications', 0)} applications")
    
    def test_teams_endpoint_works(self):
        """GET /api/teams still works"""
        resp = self.session.get(f"{BASE_URL}/api/teams")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        teams = resp.json()
        print(f"✓ Teams endpoint works: {len(teams)} teams")
    
    def test_hierarchy_endpoint_works(self):
        """GET /api/admin/hierarchy still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/hierarchy")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "hierarchy" in data
        print(f"✓ Hierarchy endpoint works: {data.get('summary', {}).get('total_employers', 0)} employers")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
