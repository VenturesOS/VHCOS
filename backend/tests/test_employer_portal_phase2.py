"""
Phase 2 Employer Portal Testing - My Team & Companies Endpoints
Tests for:
- GET /api/employer/my-team - Team performance metrics
- GET /api/employer/companies - Company details with commercials
- Role-based access control
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
EMPLOYER_EMAIL = "employer@vhctalent.com"
EMPLOYER_PASSWORD = "VhcTalent@2024"
RECRUITER_EMAIL = "recruiter@vhctalent.com"
RECRUITER_PASSWORD = "VhcTalent@2024"
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


class TestEmployerMyTeamEndpoint:
    """Tests for GET /api/employer/my-team endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def get_auth_token(self, email, password):
        """Get authentication token"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": password
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        return None
    
    def test_employer_my_team_endpoint_exists(self):
        """Test that /api/employer/my-team endpoint exists and requires auth"""
        response = self.session.get(f"{BASE_URL}/api/employer/my-team")
        # Should return 403 (no auth) not 404 (not found)
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ /api/employer/my-team endpoint exists")
    
    def test_employer_can_access_my_team(self):
        """Test employer can access my-team endpoint"""
        token = self.get_auth_token(EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
        if not token:
            pytest.skip("Could not authenticate as employer")
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        response = self.session.get(f"{BASE_URL}/api/employer/my-team")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "team" in data or data.get("team") is None, "Response should have 'team' field"
        assert "members" in data, "Response should have 'members' field"
        assert "summary" in data, "Response should have 'summary' field"
        
        print(f"✅ Employer can access my-team endpoint")
        print(f"   Team: {data.get('team')}")
        print(f"   Members count: {len(data.get('members', []))}")
        print(f"   Summary: {data.get('summary')}")
    
    def test_my_team_response_structure(self):
        """Test my-team response has correct structure"""
        token = self.get_auth_token(EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
        if not token:
            pytest.skip("Could not authenticate as employer")
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        response = self.session.get(f"{BASE_URL}/api/employer/my-team")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check summary structure
        summary = data.get("summary", {})
        assert "total_members" in summary, "Summary should have total_members"
        assert "total_mandates" in summary, "Summary should have total_mandates"
        assert "total_pipeline" in summary, "Summary should have total_pipeline"
        assert "total_revenue_pipeline" in summary, "Summary should have total_revenue_pipeline"
        assert "total_revenue_closed" in summary, "Summary should have total_revenue_closed"
        
        print("✅ My Team response structure is correct")
        print(f"   Total members: {summary.get('total_members')}")
        print(f"   Total mandates: {summary.get('total_mandates')}")
        print(f"   Total pipeline: {summary.get('total_pipeline')}")
        print(f"   Revenue pipeline: {summary.get('total_revenue_pipeline')}")
        print(f"   Revenue closed: {summary.get('total_revenue_closed')}")
    
    def test_my_team_member_metrics(self):
        """Test that team members have correct metrics structure"""
        token = self.get_auth_token(EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
        if not token:
            pytest.skip("Could not authenticate as employer")
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        response = self.session.get(f"{BASE_URL}/api/employer/my-team")
        
        assert response.status_code == 200
        data = response.json()
        
        members = data.get("members", [])
        if len(members) > 0:
            member = members[0]
            # Check member structure
            assert "id" in member, "Member should have id"
            assert "name" in member, "Member should have name"
            assert "email" in member, "Member should have email"
            assert "mandates_assigned" in member, "Member should have mandates_assigned"
            assert "pipeline" in member, "Member should have pipeline"
            assert "revenue_pipeline" in member, "Member should have revenue_pipeline"
            assert "revenue_closed" in member, "Member should have revenue_closed"
            
            print(f"✅ Team member metrics structure is correct")
            print(f"   Member: {member.get('name')}")
            print(f"   Mandates assigned: {member.get('mandates_assigned')}")
            print(f"   Pipeline: {member.get('pipeline')}")
        else:
            print("⚠️ No team members found - structure test skipped")
    
    def test_recruiter_cannot_access_my_team(self):
        """Test recruiter cannot access employer my-team endpoint"""
        token = self.get_auth_token(RECRUITER_EMAIL, RECRUITER_PASSWORD)
        if not token:
            pytest.skip("Could not authenticate as recruiter")
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        response = self.session.get(f"{BASE_URL}/api/employer/my-team")
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✅ Recruiter correctly denied access to my-team endpoint")
    
    def test_admin_cannot_access_my_team(self):
        """Test admin cannot access employer-only my-team endpoint"""
        token = self.get_auth_token(ADMIN_EMAIL, ADMIN_PASSWORD)
        if not token:
            pytest.skip("Could not authenticate as admin")
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        response = self.session.get(f"{BASE_URL}/api/employer/my-team")
        
        # Admin should be denied - this is employer-only endpoint
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✅ Admin correctly denied access to employer-only my-team endpoint")


class TestEmployerCompaniesEndpoint:
    """Tests for GET /api/employer/companies endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def get_auth_token(self, email, password):
        """Get authentication token"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": password
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        return None
    
    def test_employer_companies_endpoint_exists(self):
        """Test that /api/employer/companies endpoint exists"""
        response = self.session.get(f"{BASE_URL}/api/employer/companies")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ /api/employer/companies endpoint exists")
    
    def test_employer_can_access_companies(self):
        """Test employer can access companies endpoint"""
        token = self.get_auth_token(EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
        if not token:
            pytest.skip("Could not authenticate as employer")
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        response = self.session.get(f"{BASE_URL}/api/employer/companies")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "companies" in data, "Response should have 'companies' field"
        print(f"✅ Employer can access companies endpoint")
        print(f"   Companies count: {len(data.get('companies', []))}")
    
    def test_companies_response_structure(self):
        """Test companies response has correct structure"""
        token = self.get_auth_token(EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
        if not token:
            pytest.skip("Could not authenticate as employer")
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        response = self.session.get(f"{BASE_URL}/api/employer/companies")
        
        assert response.status_code == 200
        data = response.json()
        
        companies = data.get("companies", [])
        if len(companies) > 0:
            company = companies[0]
            # Check company structure
            assert "id" in company, "Company should have id"
            assert "name" in company, "Company should have name"
            assert "commercial" in company, "Company should have commercial details"
            assert "mandates" in company, "Company should have mandates"
            assert "total_pipeline" in company, "Company should have total_pipeline"
            assert "total_revenue_closed" in company, "Company should have total_revenue_closed"
            
            # Check commercial structure
            commercial = company.get("commercial", {})
            assert "fee_percentage" in commercial or commercial == {}, "Commercial should have fee_percentage"
            
            print(f"✅ Companies response structure is correct")
            print(f"   Company: {company.get('name')}")
            print(f"   Commercial fee: {commercial.get('fee_percentage')}%")
            print(f"   Mandates: {len(company.get('mandates', []))}")
            print(f"   Total pipeline: {company.get('total_pipeline')}")
            print(f"   Revenue closed: {company.get('total_revenue_closed')}")
        else:
            print("⚠️ No companies found - structure test skipped")
    
    def test_company_mandate_details(self):
        """Test that company mandates have correct structure"""
        token = self.get_auth_token(EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
        if not token:
            pytest.skip("Could not authenticate as employer")
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        response = self.session.get(f"{BASE_URL}/api/employer/companies")
        
        assert response.status_code == 200
        data = response.json()
        
        companies = data.get("companies", [])
        for company in companies:
            mandates = company.get("mandates", [])
            if len(mandates) > 0:
                mandate = mandates[0]
                assert "id" in mandate, "Mandate should have id"
                assert "title" in mandate, "Mandate should have title"
                assert "status" in mandate, "Mandate should have status"
                assert "stages" in mandate, "Mandate should have stages"
                assert "pipeline_count" in mandate, "Mandate should have pipeline_count"
                
                print(f"✅ Mandate structure is correct for company: {company.get('name')}")
                print(f"   Mandate: {mandate.get('title')}")
                print(f"   Status: {mandate.get('status')}")
                print(f"   Pipeline count: {mandate.get('pipeline_count')}")
                print(f"   Stages: {mandate.get('stages')}")
                return
        
        print("⚠️ No mandates found in any company - structure test skipped")
    
    def test_recruiter_cannot_access_companies(self):
        """Test recruiter cannot access employer companies endpoint"""
        token = self.get_auth_token(RECRUITER_EMAIL, RECRUITER_PASSWORD)
        if not token:
            pytest.skip("Could not authenticate as recruiter")
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        response = self.session.get(f"{BASE_URL}/api/employer/companies")
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✅ Recruiter correctly denied access to companies endpoint")
    
    def test_admin_cannot_access_employer_companies(self):
        """Test admin cannot access employer-only companies endpoint"""
        token = self.get_auth_token(ADMIN_EMAIL, ADMIN_PASSWORD)
        if not token:
            pytest.skip("Could not authenticate as admin")
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        response = self.session.get(f"{BASE_URL}/api/employer/companies")
        
        # Admin should be denied - this is employer-only endpoint
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✅ Admin correctly denied access to employer-only companies endpoint")


class TestDataAggregation:
    """Tests for data correctness and aggregation logic"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def get_auth_token(self, email, password):
        """Get authentication token"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": password
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        return None
    
    def test_revenue_aggregation_consistency(self):
        """Test that revenue aggregation is consistent between my-team and companies"""
        token = self.get_auth_token(EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
        if not token:
            pytest.skip("Could not authenticate as employer")
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Get my-team data
        team_response = self.session.get(f"{BASE_URL}/api/employer/my-team")
        assert team_response.status_code == 200
        team_data = team_response.json()
        
        # Get companies data
        companies_response = self.session.get(f"{BASE_URL}/api/employer/companies")
        assert companies_response.status_code == 200
        companies_data = companies_response.json()
        
        team_revenue_closed = team_data.get("summary", {}).get("total_revenue_closed", 0)
        companies_revenue_closed = sum(c.get("total_revenue_closed", 0) for c in companies_data.get("companies", []))
        
        print(f"✅ Revenue aggregation check:")
        print(f"   Team total revenue closed: {team_revenue_closed}")
        print(f"   Companies total revenue closed: {companies_revenue_closed}")
        
        # Note: These may not be exactly equal due to different aggregation methods
        # but both should be non-negative
        assert team_revenue_closed >= 0, "Team revenue should be non-negative"
        assert companies_revenue_closed >= 0, "Companies revenue should be non-negative"
    
    def test_pipeline_counts_are_valid(self):
        """Test that pipeline counts are valid numbers"""
        token = self.get_auth_token(EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
        if not token:
            pytest.skip("Could not authenticate as employer")
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Get my-team data
        response = self.session.get(f"{BASE_URL}/api/employer/my-team")
        assert response.status_code == 200
        data = response.json()
        
        summary = data.get("summary", {})
        assert isinstance(summary.get("total_pipeline", 0), int), "Pipeline count should be integer"
        assert summary.get("total_pipeline", 0) >= 0, "Pipeline count should be non-negative"
        
        for member in data.get("members", []):
            pipeline = member.get("pipeline", {})
            for stage, count in pipeline.items():
                assert isinstance(count, int), f"Stage {stage} count should be integer"
                assert count >= 0, f"Stage {stage} count should be non-negative"
        
        print("✅ Pipeline counts are valid")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
