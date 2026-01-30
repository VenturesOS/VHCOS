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
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
EMPLOYER_EMAIL = "employer@vhctalent.com"
EMPLOYER_PASSWORD = "VhcTalent@2024"


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
    
    def get_active_job_with_mandate_link(self, token):
        """Get an active job with mandate link enabled"""
        headers = {"Authorization": f"Bearer {token}"}
        jobs_response = self.session.get(f"{BASE_URL}/api/jobs", headers=headers)
        if jobs_response.status_code != 200:
            return None, None
        
        jobs = jobs_response.json()
        # Find job with mandate link enabled
        for job in jobs:
            if job.get("status") == "active" and job.get("mandate_shareable_link_enabled") and job.get("mandate_share_token"):
                return job["id"], job["mandate_share_token"]
        
        # If no job with mandate link, enable one
        active_jobs = [j for j in jobs if j.get("status") == "active"]
        if active_jobs:
            job_id = active_jobs[0]["id"]
            enable_response = self.session.put(
                f"{BASE_URL}/api/jobs/{job_id}/mandate-shareable-link",
                json={"enabled": True},
                headers=headers
            )
            if enable_response.status_code == 200:
                data = enable_response.json()
                return job_id, data.get("mandate_share_token")
        
        return None, None
    
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
    
    def test_enable_mandate_shareable_link_as_employer(self):
        """Test employer can enable mandate shareable link for their jobs"""
        token = self.get_employer_token()
        assert token, "Failed to get employer token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        jobs_response = self.session.get(f"{BASE_URL}/api/jobs", headers=headers)
        assert jobs_response.status_code == 200
        
        jobs = jobs_response.json()
        active_jobs = [j for j in jobs if j.get("status") == "active"]
        
        if not active_jobs:
            pytest.skip("No active jobs found for employer")
        
        test_job = active_jobs[0]
        job_id = test_job["id"]
        
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
        
        jobs_response = self.session.get(f"{BASE_URL}/api/jobs", headers=headers)
        jobs = jobs_response.json()
        
        enabled_jobs = [j for j in jobs if j.get("mandate_shareable_link_enabled")]
        
        if not enabled_jobs:
            pytest.skip("No jobs with mandate link enabled")
        
        test_job = enabled_jobs[0]
        job_id = test_job["id"]
        
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
        
        jobs_response = self.session.get(f"{BASE_URL}/api/jobs", headers=headers)
        jobs = jobs_response.json()
        
        non_active_jobs = [j for j in jobs if j.get("status") != "active"]
        
        if not non_active_jobs:
            pytest.skip("No non-active jobs found to test")
        
        test_job = non_active_jobs[0]
        job_id = test_job["id"]
        
        response = self.session.put(
            f"{BASE_URL}/api/jobs/{job_id}/mandate-shareable-link",
            json={"enabled": True},
            headers=headers
        )
        
        assert response.status_code == 400, f"Expected 400 for non-active job, got {response.status_code}"
        print(f"✅ Correctly rejected mandate link for non-active job (status: {test_job.get('status')})")
    
    def test_public_mandate_job_detail_valid_token(self):
        """Test public mandate job detail endpoint with valid token"""
        token = self.get_admin_token()
        assert token, "Failed to get admin token"
        
        job_id, mandate_token = self.get_active_job_with_mandate_link(token)
        assert job_id and mandate_token, "No job with mandate link found"
        
        response = self.session.get(
            f"{BASE_URL}/api/public/mandate/{job_id}",
            params={"token": mandate_token}
        )
        
        assert response.status_code == 200, f"Failed to get mandate job detail: {response.text}"
        data = response.json()
        
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
        token = self.get_admin_token()
        job_id, _ = self.get_active_job_with_mandate_link(token)
        
        if not job_id:
            pytest.skip("No job with mandate link found")
        
        response = self.session.get(
            f"{BASE_URL}/api/public/mandate/{job_id}",
            params={"token": "invalid-token-12345"}
        )
        
        assert response.status_code == 404, f"Expected 404 for invalid token, got {response.status_code}"
        print("✅ Correctly returned 404 for invalid token")
    
    def test_public_mandate_job_detail_missing_token(self):
        """Test public mandate job detail endpoint without token returns 422 (validation error)"""
        token = self.get_admin_token()
        job_id, _ = self.get_active_job_with_mandate_link(token)
        
        if not job_id:
            pytest.skip("No job with mandate link found")
        
        response = self.session.get(f"{BASE_URL}/api/public/mandate/{job_id}")
        
        # FastAPI returns 422 for missing required query params
        assert response.status_code == 422, f"Expected 422 for missing token, got {response.status_code}"
        print("✅ Correctly returned 422 for missing token (validation error)")
    
    def test_public_mandate_job_detail_nonexistent_job(self):
        """Test public mandate job detail endpoint with non-existent job returns 404"""
        fake_job_id = str(uuid.uuid4())
        response = self.session.get(
            f"{BASE_URL}/api/public/mandate/{fake_job_id}",
            params={"token": "any-token"}
        )
        
        assert response.status_code == 404, f"Expected 404 for non-existent job, got {response.status_code}"
        print("✅ Correctly returned 404 for non-existent job")
    
    def test_public_apply_via_mandate_link(self):
        """Test application submission via mandate link"""
        admin_token = self.get_admin_token()
        assert admin_token, "Failed to get admin token"
        
        job_id, mandate_token = self.get_active_job_with_mandate_link(admin_token)
        assert job_id and mandate_token, "No job with mandate link found"
        
        test_email = f"test_mandate_{int(time.time())}@example.com"
        
        # Create minimal PDF content
        pdf_content = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000101 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF"
        
        # Use multipart form data properly
        files = {
            'resume': ('test_resume.pdf', pdf_content, 'application/pdf')
        }
        data = {
            'job_id': job_id,
            'name': 'Test Mandate Applicant',
            'email': test_email,
            'phone': '+91 9876543210',
            'current_salary': '1200000',
            'notice_period': '30 days',
            'consent_given': 'true',
            'mandate_token': mandate_token
        }
        
        # Remove Content-Type header for multipart
        session = requests.Session()
        response = session.post(
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
        admin_token = self.get_admin_token()
        job_id, _ = self.get_active_job_with_mandate_link(admin_token)
        
        if not job_id:
            pytest.skip("No job with mandate link found")
        
        test_email = f"test_invalid_{int(time.time())}@example.com"
        
        pdf_content = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000101 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF"
        
        files = {
            'resume': ('test_resume.pdf', pdf_content, 'application/pdf')
        }
        data = {
            'job_id': job_id,
            'name': 'Test Invalid Token',
            'email': test_email,
            'phone': '+91 9876543210',
            'consent_given': 'true',
            'mandate_token': 'invalid-token-xyz'
        }
        
        session = requests.Session()
        response = session.post(
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
        
        jobs_response = self.session.get(f"{BASE_URL}/api/jobs", headers=headers)
        assert jobs_response.status_code == 200
        
        jobs = jobs_response.json()
        if not jobs:
            pytest.skip("No jobs found")
        
        job = jobs[0]
        
        # Verify mandate fields exist in response
        assert "mandate_shareable_link_enabled" in job
        # mandate_share_token may be null if not enabled
        
        print(f"✅ Job response includes mandate fields")
        print(f"   mandate_shareable_link_enabled: {job.get('mandate_shareable_link_enabled')}")


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
        
        # Get admin token to find a job
        admin_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        admin_token = admin_response.json().get("access_token")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        jobs_response = self.session.get(f"{BASE_URL}/api/jobs", headers=admin_headers)
        jobs = jobs_response.json()
        active_jobs = [j for j in jobs if j.get("status") == "active"]
        
        if not active_jobs:
            pytest.skip("No active jobs found")
        
        job_id = active_jobs[0]["id"]
        
        # Try to enable mandate link as recruiter
        response = self.session.put(
            f"{BASE_URL}/api/jobs/{job_id}/mandate-shareable-link",
            json={"enabled": True},
            headers=headers
        )
        
        # Should be forbidden (403) or not found (404) depending on job visibility
        assert response.status_code in [403, 404], f"Expected 403/404 for recruiter, got {response.status_code}"
        print("✅ Recruiter correctly denied access to mandate link control")
    
    def test_unauthenticated_cannot_enable_mandate_link(self):
        """Test that unauthenticated users cannot enable mandate links"""
        # Get a job ID first
        admin_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        admin_token = admin_response.json().get("access_token")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        jobs_response = self.session.get(f"{BASE_URL}/api/jobs", headers=admin_headers)
        jobs = jobs_response.json()
        
        if not jobs:
            pytest.skip("No jobs found")
        
        job_id = jobs[0]["id"]
        
        # Try without auth
        response = self.session.put(
            f"{BASE_URL}/api/jobs/{job_id}/mandate-shareable-link",
            json={"enabled": True}
        )
        
        # 401 or 403 are both acceptable for unauthenticated access
        assert response.status_code in [401, 403], f"Expected 401/403 for unauthenticated, got {response.status_code}"
        print("✅ Unauthenticated user correctly denied access")


class TestApplicationChannelTracking:
    """Test that application channel is correctly tracked"""
    
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
    
    def get_active_job_with_mandate_link(self, token):
        """Get an active job with mandate link enabled"""
        headers = {"Authorization": f"Bearer {token}"}
        jobs_response = self.session.get(f"{BASE_URL}/api/jobs", headers=headers)
        if jobs_response.status_code != 200:
            return None, None
        
        jobs = jobs_response.json()
        for job in jobs:
            if job.get("status") == "active" and job.get("mandate_shareable_link_enabled") and job.get("mandate_share_token"):
                return job["id"], job["mandate_share_token"]
        
        active_jobs = [j for j in jobs if j.get("status") == "active"]
        if active_jobs:
            job_id = active_jobs[0]["id"]
            enable_response = self.session.put(
                f"{BASE_URL}/api/jobs/{job_id}/mandate-shareable-link",
                json={"enabled": True},
                headers=headers
            )
            if enable_response.status_code == 200:
                data = enable_response.json()
                return job_id, data.get("mandate_share_token")
        
        return None, None
    
    def test_application_channel_mandate_link(self):
        """Test that applications via mandate link have correct channel"""
        admin_token = self.get_admin_token()
        assert admin_token, "Failed to get admin token"
        
        job_id, mandate_token = self.get_active_job_with_mandate_link(admin_token)
        assert job_id and mandate_token, "No job with mandate link found"
        
        test_email = f"test_channel_{int(time.time())}@example.com"
        
        pdf_content = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000101 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF"
        
        files = {
            'resume': ('test_resume.pdf', pdf_content, 'application/pdf')
        }
        data = {
            'job_id': job_id,
            'name': 'Test Channel Tracking',
            'email': test_email,
            'phone': '+91 9876543210',
            'consent_given': 'true',
            'mandate_token': mandate_token
        }
        
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/public/apply",
            data=data,
            files=files
        )
        
        assert response.status_code == 200, f"Failed to submit application: {response.text}"
        
        # Verify application channel in database via API
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        apps_response = self.session.get(
            f"{BASE_URL}/api/jobs/{job_id}/applicants",
            headers=headers
        )
        
        if apps_response.status_code == 200:
            applications = apps_response.json()
            test_app = next((a for a in applications if a.get("candidate_email") == test_email), None)
            if test_app:
                channel = test_app.get("application_channel")
                assert channel == "mandate_link", f"Expected 'mandate_link' channel, got {channel}"
                print(f"✅ Application channel correctly set to 'mandate_link'")
            else:
                print("⚠️ Test application not found in applicants list")
        else:
            print(f"⚠️ Could not verify application channel (status: {apps_response.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
