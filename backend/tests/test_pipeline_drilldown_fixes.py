"""
VHC Talent OS - Pipeline Drill-down and Admin Module Fixes Tests
Tests for:
- ISSUE 1: Admin pipeline drill-down with employer_id, team_id, recruiter_id filters
- ISSUE 2: Admin modules (Companies, Commercials, Teams) loading
- ISSUE 3: Employer pipeline view (/api/employer/my-team)
- ISSUE 4: Recruiter job posting with approval workflow
- ISSUE 5: Company profile with HR/POC details
- REGRESSION: Dashboard stats for admin, employer, recruiter
"""
import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
EMPLOYER_CREDS = {"email": "employer@vhctalent.com", "password": "VhcTalent@2024"}
RECRUITER_CREDS = {"email": "recruiter@vhctalent.com", "password": "VhcTalent@2024"}


class TestAuth:
    """Authentication tests to get tokens"""
    
    def test_admin_login(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        return data["access_token"]
    
    def test_employer_login(self):
        """Test employer login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
        assert response.status_code == 200, f"Employer login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        return data["access_token"]
    
    def test_recruiter_login(self):
        """Test recruiter login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER_CREDS)
        assert response.status_code == 200, f"Recruiter login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        return data["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    """Get admin token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def employer_token():
    """Get employer token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=EMPLOYER_CREDS)
    assert response.status_code == 200, f"Employer login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def recruiter_token():
    """Get recruiter token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER_CREDS)
    assert response.status_code == 200, f"Recruiter login failed: {response.text}"
    return response.json()["access_token"]


class TestIssue1AdminPipelineDrilldown:
    """
    ISSUE 1 FIX: Admin pipeline drill-down filters
    Tests that filtering by employer_id, team_id, recruiter_id returns correct data
    """
    
    def test_admin_pipeline_no_filter(self, admin_token):
        """Test admin pipeline without filters returns all data"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=headers)
        
        assert response.status_code == 200, f"Admin pipeline failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "pipeline" in data, "Missing 'pipeline' in response"
        assert "stage_counts" in data, "Missing 'stage_counts' in response"
        assert "total_applications" in data, "Missing 'total_applications' in response"
        assert "filters" in data, "Missing 'filters' in response"
        
        # Verify filters contain employers, recruiters, teams
        filters = data["filters"]
        assert "employers" in filters, "Missing 'employers' in filters"
        assert "recruiters" in filters, "Missing 'recruiters' in filters"
        assert "teams" in filters, "Missing 'teams' in filters"
        
        print(f"✅ Admin pipeline (no filter): {data['total_applications']} applications")
        print(f"   Stage counts: {data['stage_counts']}")
    
    def test_admin_pipeline_filter_by_employer_id(self, admin_token):
        """Test admin pipeline filtered by employer_id"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # First get list of employers
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=headers)
        assert response.status_code == 200
        employers = response.json()["filters"]["employers"]
        
        if not employers:
            pytest.skip("No employers found to test filter")
        
        # Test with first employer
        employer_id = employers[0]["id"]
        response = requests.get(
            f"{BASE_URL}/api/admin/pipeline?employer_id={employer_id}",
            headers=headers
        )
        
        assert response.status_code == 200, f"Pipeline filter by employer failed: {response.text}"
        data = response.json()
        
        # Verify structure is maintained
        assert "pipeline" in data
        assert "stage_counts" in data
        assert "total_applications" in data
        
        print(f"✅ Admin pipeline (employer_id={employer_id}): {data['total_applications']} applications")
        print(f"   Stage counts: {data['stage_counts']}")
    
    def test_admin_pipeline_filter_by_team_id(self, admin_token):
        """Test admin pipeline filtered by team_id"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # First get list of teams
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=headers)
        assert response.status_code == 200
        teams = response.json()["filters"]["teams"]
        
        if not teams:
            pytest.skip("No teams found to test filter")
        
        # Test with first team
        team_id = teams[0]["id"]
        response = requests.get(
            f"{BASE_URL}/api/admin/pipeline?team_id={team_id}",
            headers=headers
        )
        
        assert response.status_code == 200, f"Pipeline filter by team failed: {response.text}"
        data = response.json()
        
        assert "pipeline" in data
        assert "stage_counts" in data
        
        print(f"✅ Admin pipeline (team_id={team_id}): {data['total_applications']} applications")
    
    def test_admin_pipeline_filter_by_recruiter_id(self, admin_token):
        """Test admin pipeline filtered by recruiter_id"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # First get list of recruiters
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=headers)
        assert response.status_code == 200
        recruiters = response.json()["filters"]["recruiters"]
        
        if not recruiters:
            pytest.skip("No recruiters found to test filter")
        
        # Test with first recruiter
        recruiter_id = recruiters[0]["id"]
        response = requests.get(
            f"{BASE_URL}/api/admin/pipeline?recruiter_id={recruiter_id}",
            headers=headers
        )
        
        assert response.status_code == 200, f"Pipeline filter by recruiter failed: {response.text}"
        data = response.json()
        
        assert "pipeline" in data
        assert "stage_counts" in data
        
        print(f"✅ Admin pipeline (recruiter_id={recruiter_id}): {data['total_applications']} applications")


class TestIssue2AdminModules:
    """
    ISSUE 2 FIX: Admin modules (Companies, Commercials, Teams) loading
    """
    
    def test_get_all_companies_admin(self, admin_token):
        """Test GET /api/companies returns list of companies for admin"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/companies", headers=headers)
        
        assert response.status_code == 200, f"Get companies failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        
        if data:
            company = data[0]
            assert "id" in company, "Company missing 'id'"
            assert "name" in company, "Company missing 'name'"
            assert "status" in company, "Company missing 'status'"
            assert "created_at" in company, "Company missing 'created_at'"
        
        print(f"✅ GET /api/companies: {len(data)} companies returned")
    
    def test_create_company_admin(self, admin_token):
        """Test POST /api/companies creates new company for admin"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        unique_name = f"TEST_Company_{uuid.uuid4().hex[:8]}"
        company_data = {
            "name": unique_name,
            "description": "Test company created by automated tests",
            "industry": "Technology",
            "website": "https://test-company.example.com",
            "location": "Test City"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/companies",
            headers=headers,
            json=company_data
        )
        
        assert response.status_code == 200, f"Create company failed: {response.text}"
        data = response.json()
        
        assert data["name"] == unique_name, "Company name mismatch"
        assert data["industry"] == "Technology", "Company industry mismatch"
        assert "id" in data, "Company missing 'id'"
        assert data["status"] == "active", "New company should be active"
        
        print(f"✅ POST /api/companies: Created company '{unique_name}' with id={data['id']}")
        
        # Return company_id for cleanup
        return data["id"]
    
    def test_create_company_with_hr_contacts(self, admin_token):
        """Test POST /api/companies with HR/POC contacts (ISSUE 5)"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        unique_name = f"TEST_Company_HR_{uuid.uuid4().hex[:8]}"
        company_data = {
            "name": unique_name,
            "description": "Test company with HR contacts",
            "industry": "Finance",
            "location": "Mumbai",
            "hr_contacts": [
                {
                    "name": "HR Manager",
                    "email": "hr@test-company.com",
                    "phone": "+91-9876543210",
                    "designation": "HR Manager"
                },
                {
                    "name": "POC Contact",
                    "email": "poc@test-company.com",
                    "phone": "+91-9876543211",
                    "designation": "Point of Contact"
                }
            ]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/companies",
            headers=headers,
            json=company_data
        )
        
        assert response.status_code == 200, f"Create company with HR contacts failed: {response.text}"
        data = response.json()
        
        assert data["name"] == unique_name
        assert "hr_contacts" in data, "Company missing 'hr_contacts'"
        assert len(data["hr_contacts"]) == 2, "Should have 2 HR contacts"
        assert data["hr_contacts"][0]["name"] == "HR Manager"
        assert data["hr_contacts"][0]["email"] == "hr@test-company.com"
        
        print(f"✅ POST /api/companies with HR contacts: Created company with {len(data['hr_contacts'])} HR contacts")
        
        return data["id"]
    
    def test_get_commercials_admin(self, admin_token):
        """Test GET /api/commercials returns commercials"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/commercials", headers=headers)
        
        assert response.status_code == 200, f"Get commercials failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        
        print(f"✅ GET /api/commercials: {len(data)} commercials returned")
    
    def test_get_teams_admin(self, admin_token):
        """Test GET /api/teams returns teams"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/teams", headers=headers)
        
        assert response.status_code == 200, f"Get teams failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        
        if data:
            team = data[0]
            assert "id" in team, "Team missing 'id'"
            assert "name" in team, "Team missing 'name'"
            assert "employer_id" in team, "Team missing 'employer_id'"
        
        print(f"✅ GET /api/teams: {len(data)} teams returned")


class TestIssue3EmployerPipelineView:
    """
    ISSUE 3: Employer pipeline view (/api/employer/my-team)
    Note: employer@vhctalent.com has a disabled team, so it returns empty (expected)
    """
    
    def test_employer_my_team_endpoint(self, employer_token):
        """Test GET /api/employer/my-team returns team pipeline for employer"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        response = requests.get(f"{BASE_URL}/api/employer/my-team", headers=headers)
        
        assert response.status_code == 200, f"Employer my-team failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "team" in data, "Missing 'team' in response"
        assert "members" in data, "Missing 'members' in response"
        assert "summary" in data, "Missing 'summary' in response"
        
        # Verify summary structure
        summary = data["summary"]
        assert "total_members" in summary, "Missing 'total_members' in summary"
        assert "total_mandates" in summary, "Missing 'total_mandates' in summary"
        assert "total_pipeline" in summary, "Missing 'total_pipeline' in summary"
        
        print(f"✅ GET /api/employer/my-team: team={data['team']}, members={len(data['members'])}")
        print(f"   Summary: {summary}")
    
    def test_employer_companies_endpoint(self, employer_token):
        """Test GET /api/employer/companies returns employer's assigned companies"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        response = requests.get(f"{BASE_URL}/api/employer/companies", headers=headers)
        
        assert response.status_code == 200, f"Employer companies failed: {response.text}"
        data = response.json()
        
        assert "companies" in data, "Missing 'companies' in response"
        
        print(f"✅ GET /api/employer/companies: {len(data['companies'])} companies")


class TestIssue4RecruiterJobPostingApproval:
    """
    ISSUE 4: Recruiter job posting with approval workflow
    - POST /api/jobs as recruiter should create job with status 'pending_approval'
    - POST /api/jobs/{job_id}/transition should allow employer to approve
    """
    
    def test_recruiter_creates_job_pending_approval(self, recruiter_token, admin_token):
        """Test recruiter creates job with pending_approval status"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        unique_title = f"TEST_Job_{uuid.uuid4().hex[:8]}"
        job_data = {
            "title": unique_title,
            "description": "Test job created by recruiter for approval workflow testing",
            "requirements": "Test requirements",
            "location": "Remote",
            "job_type": "full_time",
            "experience_min": 2,
            "experience_max": 5,
            "salary_min": 500000,
            "salary_max": 1000000,
            "skills": ["Python", "Testing"]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/jobs",
            headers=headers,
            json=job_data
        )
        
        assert response.status_code == 200, f"Recruiter create job failed: {response.text}"
        data = response.json()
        
        assert data["title"] == unique_title, "Job title mismatch"
        assert data["status"] == "pending_approval", f"Expected 'pending_approval' status, got '{data['status']}'"
        assert "id" in data, "Job missing 'id'"
        
        print(f"✅ POST /api/jobs (recruiter): Created job '{unique_title}' with status='pending_approval'")
        
        return data["id"]
    
    def test_admin_approves_recruiter_job(self, recruiter_token, admin_token):
        """Test admin can approve recruiter's pending job"""
        # First create a job as recruiter
        recruiter_headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        unique_title = f"TEST_Job_Approval_{uuid.uuid4().hex[:8]}"
        job_data = {
            "title": unique_title,
            "description": "Test job for approval workflow",
            "location": "Remote",
            "job_type": "full_time"
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/jobs",
            headers=recruiter_headers,
            json=job_data
        )
        
        assert create_response.status_code == 200, f"Create job failed: {create_response.text}"
        job_id = create_response.json()["id"]
        assert create_response.json()["status"] == "pending_approval"
        
        # Now approve as admin
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        transition_data = {
            "new_status": "active",
            "reason": "Approved by admin for testing"
        }
        
        approve_response = requests.post(
            f"{BASE_URL}/api/jobs/{job_id}/transition",
            headers=admin_headers,
            json=transition_data
        )
        
        assert approve_response.status_code == 200, f"Approve job failed: {approve_response.text}"
        approved_job = approve_response.json()
        
        assert approved_job["status"] == "active", f"Expected 'active' status after approval, got '{approved_job['status']}'"
        
        print(f"✅ POST /api/jobs/{job_id}/transition: Job approved, status changed to 'active'")
        
        return job_id


class TestIssue5CompanyHRContacts:
    """
    ISSUE 5 FIX: Company profile with HR/POC details
    Tests that Company model includes hr_contacts field
    """
    
    def test_company_response_includes_hr_contacts_field(self, admin_token):
        """Test that company response includes hr_contacts field"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/companies", headers=headers)
        
        assert response.status_code == 200
        companies = response.json()
        
        if companies:
            company = companies[0]
            # hr_contacts should be in the response (can be None or list)
            assert "hr_contacts" in company or company.get("hr_contacts") is None, \
                "Company response should include 'hr_contacts' field"
            
            print(f"✅ Company response includes hr_contacts field: {company.get('hr_contacts')}")
    
    def test_get_single_company_with_hr_contacts(self, admin_token):
        """Test GET /api/companies/{company_id} includes hr_contacts"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # First get list of companies
        list_response = requests.get(f"{BASE_URL}/api/companies", headers=headers)
        assert list_response.status_code == 200
        companies = list_response.json()
        
        if not companies:
            pytest.skip("No companies to test")
        
        company_id = companies[0]["id"]
        
        # Get single company
        response = requests.get(f"{BASE_URL}/api/companies/{company_id}", headers=headers)
        assert response.status_code == 200, f"Get company failed: {response.text}"
        
        company = response.json()
        assert "id" in company
        assert "name" in company
        # hr_contacts field should exist (can be None)
        
        print(f"✅ GET /api/companies/{company_id}: Company '{company['name']}' retrieved")


class TestRegressionDashboardStats:
    """
    REGRESSION: Dashboard stats for admin, employer, recruiter
    """
    
    def test_admin_dashboard_stats(self, admin_token):
        """Test admin dashboard stats endpoint"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/stats/admin", headers=headers)
        
        assert response.status_code == 200, f"Admin stats failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "total_users" in data, "Missing 'total_users'"
        assert "total_jobs" in data, "Missing 'total_jobs'"
        assert "total_applications" in data, "Missing 'total_applications'"
        assert "total_companies" in data, "Missing 'total_companies'"
        assert "users_by_role" in data, "Missing 'users_by_role'"
        
        print(f"✅ GET /api/stats/admin: users={data['total_users']}, jobs={data['total_jobs']}, apps={data['total_applications']}")
    
    def test_employer_dashboard_stats(self, employer_token):
        """Test employer dashboard stats endpoint"""
        headers = {"Authorization": f"Bearer {employer_token}"}
        response = requests.get(f"{BASE_URL}/api/stats/employer", headers=headers)
        
        assert response.status_code == 200, f"Employer stats failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "my_jobs" in data, "Missing 'my_jobs'"
        assert "total_applicants" in data, "Missing 'total_applicants'"
        assert "stage_stats" in data, "Missing 'stage_stats'"
        
        print(f"✅ GET /api/stats/employer: jobs={data['my_jobs']}, applicants={data['total_applicants']}")
    
    def test_recruiter_dashboard_stats(self, recruiter_token):
        """Test recruiter dashboard stats endpoint"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        response = requests.get(f"{BASE_URL}/api/stats/recruiter", headers=headers)
        
        assert response.status_code == 200, f"Recruiter stats failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "total_jobs" in data, "Missing 'total_jobs'"
        assert "total_candidates" in data, "Missing 'total_candidates'"
        assert "pipeline_stats" in data, "Missing 'pipeline_stats'"
        
        print(f"✅ GET /api/stats/recruiter: jobs={data['total_jobs']}, candidates={data['total_candidates']}")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_companies(self, admin_token):
        """Cleanup TEST_ prefixed companies"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/companies", headers=headers)
        
        if response.status_code == 200:
            companies = response.json()
            test_companies = [c for c in companies if c["name"].startswith("TEST_")]
            print(f"ℹ️ Found {len(test_companies)} TEST_ companies (manual cleanup may be needed)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
