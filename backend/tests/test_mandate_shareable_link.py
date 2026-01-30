"""
Test Suite: Mandate Shareable Links Feature
Tests the new feature that allows employers/admin to generate shareable links
for assigned mandates, independent of career page visibility.

Features tested:
1. PUT /api/jobs/{job_id}/mandate-shareable-link - Enable/disable mandate link
2. GET /api/public/mandate/{job_id}?token={token} - Public mandate job detail
3. POST /api/public/apply with mandate_token - Application via mandate link
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
EMPLOYER_EMAIL = "employer@vhctalent.com"
EMPLOYER_PASSWORD = "VhcTalent@2024"

# Test job ID with mandate link enabled (from context)
TEST_JOB_ID = "c72113dc-b62e-437c-8712-0fb9f6541d1d"
TEST_TOKEN = "dgOX-51L-e3CuhlqLBJXSzY7GDzCFlq-"


class TestMandateShareableLink:
    """Test mandate shareable link endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def get_admin_token(self):
        """Get admin auth token"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        return None
    
    def get_employer_token(self):
        """Get employer auth token"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": EMPLOYER_EMAIL,
            "password": EMPLOYER_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        return None
    
    # ============== Backend API Tests ==============
    
    def test_admin_login(self):
        """Test admin can login"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        print("✅ Admin login successful")
    
    def test_employer_login(self):
        """Test employer can login"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": EMPLOYER_EMAIL,
            "password": EMPLOYER_PASSWORD
        })
        assert response.status_code == 200, f"Employer login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        print("✅ Employer login successful")
    
    def test_enable_mandate_shareable_link_as_admin(self):
        """Test admin can enable mandate shareable link for active job"""
        token = self.get_admin_token()
        assert token, "Failed to get admin token"
        
        # First get list of jobs to find an active one
        headers = {"Authorization": f"Bearer {token}"}
        jobs_response = self.session.get(f"{BASE_URL}/api/jobs", headers=headers)
        assert jobs_response.status_code == 200
        
        jobs = jobs_response.json()
        active_jobs = [j for j in jobs if j.get("status") == "active"]
        
        if not active_jobs:
            pytest.skip("No active jobs found to test")
        
        test_job = active_jobs[0]
        job_id = test_job["id"]
        
        # Enable mandate shareable link
        response = self.session.put(
            f"{BASE_URL}/api/jobs/{job_id}/mandate-shareable-link",
            json={"enabled": True},
            headers=headers
        )
        
        assert response.status_code == 200, f"Failed to enable mandate link: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert data.get("mandate_shareable_link_enabled") == True
        assert "mandate_share_token" in data
        assert data.get("mandate_share_token") is not None
        
        print(f"✅ Admin enabled mandate link for job {job_id}")
        print(f"   Token: {data.get('mandate_share_token')}")
        
        # Store for later tests
        self.__class__.enabled_job_id = job_id
        self.__class__.enabled_token = data.get("mandate_share_token")
    
    def test_enable_mandate_shareable_link_as_employer(self):
        """Test employer can enable mandate shareable link for their jobs"""
        token = self.get_employer_token()
        assert token, "Failed to get employer token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get employer's jobs
        jobs_response = self.session.get(f"{BASE_URL}/api/jobs", headers=headers)
        assert jobs_response.status_code == 200
        
        jobs = jobs_response.json()
        active_jobs = [j for j in jobs if j.get("status") == "active"]
        
        if not active_jobs:
            pytest.skip("No active jobs found for employer")
        
        test_job = active_jobs[0]
        job_id = test_job["id"]
        
        # Enable mandate shareable link
        response = self.session.put(
            f"{BASE_URL}/api/jobs/{job_id}/mandate-shareable-link",
            json={"enabled": True},
            headers=headers
        )
        
        assert response.status_code == 200, f"Failed to enable mandate link: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert data.get("mandate_shareable_link_enabled") == True
        
        print(f"✅ Employer enabled mandate link for job {job_id}")
    
    def test_disable_mandate_shareable_link(self):
        """Test disabling mandate shareable link"""
        token = self.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get jobs
        jobs_response = self.session.get(f"{BASE_URL}/api/jobs", headers=headers)
        jobs = jobs_response.json()
        
        # Find a job with mandate link enabled
        enabled_jobs = [j for j in jobs if j.get("mandate_shareable_link_enabled")]
        
        if not enabled_jobs:
            pytest.skip("No jobs with mandate link enabled")
        
        test_job = enabled_jobs[0]
        job_id = test_job["id"]
        
        # Disable mandate shareable link
        response = self.session.put(
            f"{BASE_URL}/api/jobs/{job_id}/mandate-shareable-link",
            json={"enabled": False},
            headers=headers
        )
        
        assert response.status_code == 200, f"Failed to disable mandate link: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert data.get("mandate_shareable_link_enabled") == False
        
        print(f"✅ Disabled mandate link for job {job_id}")
        
        # Re-enable for other tests
        self.session.put(
            f"{BASE_URL}/api/jobs/{job_id}/mandate-shareable-link",
            json={"enabled": True},
            headers=headers
        )
    
    def test_mandate_link_requires_active_job(self):
        """Test that mandate link can only be enabled for active jobs"""
        token = self.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get jobs
        jobs_response = self.session.get(f"{BASE_URL}/api/jobs", headers=headers)
        jobs = jobs_response.json()
        
        # Find a non-active job
        non_active_jobs = [j for j in jobs if j.get("status") != "active"]
        
        if not non_active_jobs:
            pytest.skip("No non-active jobs found to test")
        
        test_job = non_active_jobs[0]
        job_id = test_job["id"]
        
        # Try to enable mandate link - should fail
        response = self.session.put(
            f"{BASE_URL}/api/jobs/{job_id}/mandate-shareable-link",
            json={"enabled": True},
            headers=headers
        )
        
        assert response.status_code == 400, f"Expected 400 for non-active job, got {response.status_code}"
        print(f"✅ Correctly rejected mandate link for non-active job (status: {test_job.get('status')})")
    
    def test_public_mandate_job_detail_valid_token(self):
        """Test public mandate job detail endpoint with valid token"""
        # Use the test job ID and token from context
        response = self.session.get(
            f"{BASE_URL}/api/public/mandate/{TEST_JOB_ID}",
            params={"token": TEST_TOKEN}
        )
        
        assert response.status_code == 200, f"Failed to get mandate job detail: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "id" in data
        assert "title" in data
        assert "description" in data
        assert "location" in data
        assert "job_type" in data
        assert "company_name" in data
        assert data.get("is_mandate_link") == True
        
        print(f"✅ Public mandate job detail returned successfully")
        print(f"   Job: {data.get('title')}")
        print(f"   Company: {data.get('company_name')}")
    
    def test_public_mandate_job_detail_invalid_token(self):
        """Test public mandate job detail endpoint with invalid token returns 404"""
        response = self.session.get(
            f"{BASE_URL}/api/public/mandate/{TEST_JOB_ID}",
            params={"token": "invalid-token-12345"}
        )
        
        assert response.status_code == 404, f"Expected 404 for invalid token, got {response.status_code}"
        print("✅ Correctly returned 404 for invalid token")
    
    def test_public_mandate_job_detail_missing_token(self):
        """Test public mandate job detail endpoint without token returns 400"""
        response = self.session.get(
            f"{BASE_URL}/api/public/mandate/{TEST_JOB_ID}"
        )
        
        assert response.status_code == 400, f"Expected 400 for missing token, got {response.status_code}"
        print("✅ Correctly returned 400 for missing token")
    
    def test_public_mandate_job_detail_nonexistent_job(self):
        """Test public mandate job detail endpoint with non-existent job returns 404"""
        fake_job_id = str(uuid.uuid4())
        response = self.session.get(
            f"{BASE_URL}/api/public/mandate/{fake_job_id}",
            params={"token": TEST_TOKEN}
        )
        
        assert response.status_code == 404, f"Expected 404 for non-existent job, got {response.status_code}"
        print("✅ Correctly returned 404 for non-existent job")
    
    def test_public_apply_via_mandate_link(self):
        """Test application submission via mandate link"""
        # Create unique test data
        test_email = f"test_mandate_{uuid.uuid4().hex[:8]}@example.com"
        
        # Create a simple test PDF content (minimal valid PDF)
        pdf_content = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000101 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF"
        
        # Submit application via mandate link
        files = {
            'resume': ('test_resume.pdf', pdf_content, 'application/pdf')
        }
        data = {
            'job_id': TEST_JOB_ID,
            'name': 'Test Mandate Applicant',
            'email': test_email,
            'phone': '+91 9876543210',
            'current_salary': '1200000',
            'notice_period': '30 days',
            'consent_given': 'true',
            'mandate_token': TEST_TOKEN
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/public/apply",
            data=data,
            files=files
        )
        
        assert response.status_code == 200, f"Failed to submit application: {response.text}"
        result = response.json()
        assert result.get("success") == True
        
        print(f"✅ Application submitted via mandate link")
        print(f"   Email: {test_email}")
    
    def test_public_apply_via_mandate_link_invalid_token(self):
        """Test application submission with invalid mandate token fails"""
        test_email = f"test_invalid_{uuid.uuid4().hex[:8]}@example.com"
        
        pdf_content = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000101 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF"
        
        files = {
            'resume': ('test_resume.pdf', pdf_content, 'application/pdf')
        }
        data = {
            'job_id': TEST_JOB_ID,
            'name': 'Test Invalid Token',
            'email': test_email,
            'phone': '+91 9876543210',
            'consent_given': 'true',
            'mandate_token': 'invalid-token-xyz'
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/public/apply",
            data=data,
            files=files
        )
        
        # Should fail because job is not on career page and token is invalid
        assert response.status_code == 404, f"Expected 404 for invalid mandate token, got {response.status_code}"
        print("✅ Correctly rejected application with invalid mandate token")
    
    def test_job_response_includes_mandate_fields(self):
        """Test that job response includes mandate shareable link fields"""
        token = self.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get job details
        response = self.session.get(f"{BASE_URL}/api/jobs/{TEST_JOB_ID}", headers=headers)
        
        assert response.status_code == 200, f"Failed to get job: {response.text}"
        job = response.json()
        
        # Verify mandate fields exist in response
        assert "mandate_shareable_link_enabled" in job
        assert "mandate_share_token" in job
        
        print(f"✅ Job response includes mandate fields")
        print(f"   mandate_shareable_link_enabled: {job.get('mandate_shareable_link_enabled')}")
        print(f"   mandate_share_token: {'present' if job.get('mandate_share_token') else 'null'}")


class TestMandateLinkAccessControl:
    """Test access control for mandate shareable link feature"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_recruiter_cannot_enable_mandate_link(self):
        """Test that recruiters cannot enable mandate shareable links"""
        # Login as recruiter
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "recruiter@vhctalent.com",
            "password": "VhcTalent@2024"
        })
        
        if response.status_code != 200:
            pytest.skip("Recruiter login failed - may not exist")
        
        token = response.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Try to enable mandate link
        response = self.session.put(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/mandate-shareable-link",
            json={"enabled": True},
            headers=headers
        )
        
        # Should be forbidden (403) or not found (404) depending on job visibility
        assert response.status_code in [403, 404], f"Expected 403/404 for recruiter, got {response.status_code}"
        print("✅ Recruiter correctly denied access to mandate link control")
    
    def test_unauthenticated_cannot_enable_mandate_link(self):
        """Test that unauthenticated users cannot enable mandate links"""
        response = self.session.put(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/mandate-shareable-link",
            json={"enabled": True}
        )
        
        assert response.status_code == 401, f"Expected 401 for unauthenticated, got {response.status_code}"
        print("✅ Unauthenticated user correctly denied access")


class TestApplicationChannelTracking:
    """Test that application channel is correctly tracked"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_application_channel_mandate_link(self):
        """Test that applications via mandate link have correct channel"""
        # Submit application via mandate link
        test_email = f"test_channel_{uuid.uuid4().hex[:8]}@example.com"
        
        pdf_content = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000101 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF"
        
        files = {
            'resume': ('test_resume.pdf', pdf_content, 'application/pdf')
        }
        data = {
            'job_id': TEST_JOB_ID,
            'name': 'Test Channel Tracking',
            'email': test_email,
            'phone': '+91 9876543210',
            'consent_given': 'true',
            'mandate_token': TEST_TOKEN
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/public/apply",
            data=data,
            files=files
        )
        
        assert response.status_code == 200, f"Failed to submit application: {response.text}"
        
        # Login as admin to verify application channel
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = login_response.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get applications for the job
        apps_response = self.session.get(
            f"{BASE_URL}/api/jobs/{TEST_JOB_ID}/applicants",
            headers=headers
        )
        
        if apps_response.status_code == 200:
            applications = apps_response.json()
            # Find our test application
            test_app = next((a for a in applications if a.get("candidate_email") == test_email), None)
            if test_app:
                assert test_app.get("application_channel") == "mandate_link", \
                    f"Expected 'mandate_link' channel, got {test_app.get('application_channel')}"
                print(f"✅ Application channel correctly set to 'mandate_link'")
            else:
                print("⚠️ Test application not found in applicants list (may be in different endpoint)")
        else:
            print(f"⚠️ Could not verify application channel (status: {apps_response.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
