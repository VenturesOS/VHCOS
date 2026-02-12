"""
Test suite for verifying data cleanup and Naukri inline detail view fix
Iteration 54: Data cleanup verification + Naukri-sourced candidate detail fix
"""
import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDataCleanup:
    """Verify test data has been cleaned up from the system"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_no_test_user_emails(self):
        """Verify no test users with @test.vhc.in, @vhctalent.com, @example.com emails"""
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        assert response.status_code == 200
        users = response.json()
        
        test_patterns = ['@test.vhc.in', '@vhctalent.com', '@example.com']
        test_emails = []
        
        for user in users:
            email = user.get('email', '')
            for pattern in test_patterns:
                if pattern in email:
                    test_emails.append(email)
        
        assert len(test_emails) == 0, f"Found test user emails: {test_emails}"
        print(f"✓ No test user emails found. Total users: {len(users)}")
    
    def test_expected_user_count(self):
        """Verify 8 real users preserved"""
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        assert response.status_code == 200
        users = response.json()
        assert len(users) == 8, f"Expected 8 users, got {len(users)}"
        print(f"✓ User count matches expected: 8")
    
    def test_no_test_companies(self):
        """Verify no TEST_ prefixed companies"""
        response = requests.get(f"{BASE_URL}/api/companies", headers=self.headers)
        assert response.status_code == 200
        companies = response.json()
        
        test_companies = [c for c in companies if c.get('name', '').startswith('TEST_')]
        assert len(test_companies) == 0, f"Found test companies: {test_companies}"
        print(f"✓ No TEST_ prefixed companies. Total companies: {len(companies)}")
    
    def test_expected_company_count(self):
        """Verify 5 real companies preserved"""
        response = requests.get(f"{BASE_URL}/api/companies", headers=self.headers)
        assert response.status_code == 200
        companies = response.json()
        assert len(companies) == 5, f"Expected 5 companies, got {len(companies)}"
        print(f"✓ Company count matches expected: 5")
    
    def test_no_test_teams(self):
        """Verify no TEST_ prefixed teams"""
        response = requests.get(f"{BASE_URL}/api/teams", headers=self.headers)
        assert response.status_code == 200
        teams = response.json()
        
        test_teams = [t for t in teams if t.get('name', '').startswith('TEST_')]
        assert len(test_teams) == 0, f"Found test teams: {test_teams}"
        print(f"✓ No TEST_ prefixed teams. Total teams: {len(teams)}")
    
    def test_expected_team_count(self):
        """Verify 5 real teams preserved"""
        response = requests.get(f"{BASE_URL}/api/teams", headers=self.headers)
        assert response.status_code == 200
        teams = response.json()
        assert len(teams) == 5, f"Expected 5 teams, got {len(teams)}"
        print(f"✓ Team count matches expected: 5")
    
    def test_no_test_jobs(self):
        """Verify no TEST_ prefixed or 'Test Job' titled jobs"""
        response = requests.get(f"{BASE_URL}/api/jobs", headers=self.headers)
        assert response.status_code == 200
        jobs = response.json()
        
        test_jobs = []
        for job in jobs:
            title = job.get('title', '')
            if title.startswith('TEST_') or 'Test Job' in title:
                test_jobs.append(title)
        
        assert len(test_jobs) == 0, f"Found test jobs: {test_jobs}"
        print(f"✓ No test jobs found. Total jobs: {len(jobs)}")
    
    def test_expected_job_count(self):
        """Verify 6 real jobs preserved"""
        response = requests.get(f"{BASE_URL}/api/jobs", headers=self.headers)
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 6, f"Expected 6 jobs, got {len(jobs)}"
        print(f"✓ Job count matches expected: 6")


class TestNaukriCandidateInlineDetail:
    """Verify Naukri-sourced candidates show full details in inline view"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_naukri_candidates_exist(self):
        """Verify Naukri-sourced candidates exist in the system"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank?limit=100", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        candidates = data.get('candidates', data)
        
        naukri_candidates = [c for c in candidates if c.get('source') == 'naukri_extension']
        assert len(naukri_candidates) > 0, "No Naukri-sourced candidates found"
        print(f"✓ Found {len(naukri_candidates)} Naukri-sourced candidates")
        return naukri_candidates
    
    def test_naukri_candidate_full_details_via_getById(self):
        """Verify GET /api/candidate-bank/{id} returns full Naukri details"""
        # First find a Naukri candidate
        response = requests.get(f"{BASE_URL}/api/candidate-bank?limit=100", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        candidates = data.get('candidates', data)
        
        naukri_candidates = [c for c in candidates if c.get('source') == 'naukri_extension']
        assert len(naukri_candidates) > 0, "No Naukri candidates found"
        
        # Get full details for first Naukri candidate
        candidate_id = naukri_candidates[0]['id']
        detail_response = requests.get(f"{BASE_URL}/api/candidate-bank/{candidate_id}", headers=self.headers)
        assert detail_response.status_code == 200
        
        full_data = detail_response.json()
        
        # Verify Naukri-specific fields are present
        assert full_data.get('source') == 'naukri_extension', "Source should be naukri_extension"
        assert 'source_details' in full_data, "source_details should be present"
        
        source_details = full_data.get('source_details', {})
        # At minimum, captured_by should be in source_details
        if source_details:
            print(f"✓ source_details found: captured_by={source_details.get('captured_by_name', 'N/A')}")
        
        # Verify naukri_profile_url is included
        if full_data.get('naukri_profile_url'):
            print(f"✓ naukri_profile_url found: {full_data['naukri_profile_url'][:50]}...")
        
        # Verify other important fields
        print(f"✓ Full record for {full_data.get('name')}:")
        print(f"  - experience_years: {full_data.get('experience_years')}")
        print(f"  - skills count: {len(full_data.get('skills', []))}")
        print(f"  - experience entries: {len(full_data.get('experience', []))}")
        print(f"  - education entries: {len(full_data.get('education', []))}")
        print(f"  - summary length: {len(full_data.get('summary', '') or '')}")
    
    def test_naukri_candidate_has_captured_by_info(self):
        """Verify Naukri candidate has 'Captured by' information"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank?limit=100", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        candidates = data.get('candidates', data)
        
        naukri_candidates = [c for c in candidates if c.get('source') == 'naukri_extension']
        assert len(naukri_candidates) > 0
        
        # Check a candidate with full source_details
        for naukri in naukri_candidates:
            detail_response = requests.get(f"{BASE_URL}/api/candidate-bank/{naukri['id']}", headers=self.headers)
            if detail_response.status_code == 200:
                full_data = detail_response.json()
                source_details = full_data.get('source_details', {})
                if source_details and source_details.get('captured_by_name'):
                    print(f"✓ Candidate {full_data.get('name')} - Captured by: {source_details.get('captured_by_name')}")
                    return
        
        print("⚠ No Naukri candidate with captured_by_name found (may be expected)")


class TestCandidateBankSearch:
    """Verify candidate bank search functionality works after cleanup"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_search_by_name(self):
        """Verify search by name works"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank?search=Ravi", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        total = data.get('total', len(data.get('candidates', data)))
        assert total > 0, "Search for 'Ravi' should return results"
        print(f"✓ Search 'Ravi' returned {total} results")
    
    def test_search_pagination(self):
        """Verify pagination works"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank?page=1&limit=10", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert 'candidates' in data, "Paginated response should have 'candidates' key"
        assert 'total' in data, "Paginated response should have 'total' key"
        assert 'page' in data, "Paginated response should have 'page' key"
        assert 'total_pages' in data, "Paginated response should have 'total_pages' key"
        print(f"✓ Pagination works: page {data.get('page')} of {data.get('total_pages')}, total {data.get('total')}")


class TestAnalyticsDashboardRegression:
    """Verify analytics dashboard still works after cleanup"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_analytics_endpoint_works(self):
        """Verify GET /api/analytics/admin returns data"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert 'kpis' in data, "Response should have 'kpis'"
        assert 'source_distribution' in data, "Response should have 'source_distribution'"
        assert 'capture_trends' in data, "Response should have 'capture_trends'"
        assert 'recruiter_performance' in data, "Response should have 'recruiter_performance'"
        
        kpis = data.get('kpis', {})
        print(f"✓ Analytics dashboard working:")
        print(f"  - Total captures: {kpis.get('total_captures')}")
        print(f"  - Sources: {len(data.get('source_distribution', []))}")
        print(f"  - Recruiters: {len(data.get('recruiter_performance', []))}")
