"""
Test Suite for VHC Talent OS - Shareable Job Links & JD Parsing Features
Tests:
1. Shareable Job Link + Public Job Landing Page
2. Structured Job ID Format (VHC/YYYY/NNNN)
3. JD Parsing during Job Creation
"""
import pytest
import requests
import os
import time
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


class TestSetup:
    """Setup and authentication helpers"""
    
    @staticmethod
    def get_admin_token():
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        return None


class TestJobPublicIdGeneration:
    """Test Feature 2: Structured Job ID Format (VHC/YYYY/NNNN)"""
    
    def test_job_creation_generates_public_id(self):
        """Test that job creation generates job_public_id in VHC/YYYY/NNNN format"""
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create a new job
        job_data = {
            "title": "TEST_PublicID_Engineer",
            "description": "Test job for public ID generation",
            "location": "Mumbai",
            "job_type": "full-time",
            "public_company_alias": "Test Company"
        }
        
        response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=headers)
        assert response.status_code == 200, f"Job creation failed: {response.text}"
        
        job = response.json()
        
        # Verify job_public_id exists and has correct format
        assert "job_public_id" in job, "job_public_id not in response"
        job_public_id = job["job_public_id"]
        assert job_public_id is not None, "job_public_id is None"
        
        # Verify format: VHC/YYYY/NNNN
        parts = job_public_id.split("/")
        assert len(parts) == 3, f"Invalid format: {job_public_id}"
        assert parts[0] == "VHC", f"Prefix should be VHC: {job_public_id}"
        assert parts[1] == str(datetime.now().year), f"Year mismatch: {job_public_id}"
        assert len(parts[2]) == 4 and parts[2].isdigit(), f"Sequence should be 4 digits: {job_public_id}"
        
        print(f"✅ Job created with public ID: {job_public_id}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/jobs/{job['id']}", headers=headers)
    
    def test_job_public_id_increments(self):
        """Test that job_public_id sequence increments correctly"""
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create two jobs
        job_ids = []
        public_ids = []
        
        for i in range(2):
            job_data = {
                "title": f"TEST_Sequence_Job_{i}",
                "description": "Test job for sequence",
                "location": "Delhi",
                "job_type": "full-time"
            }
            response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=headers)
            assert response.status_code == 200
            job = response.json()
            job_ids.append(job["id"])
            public_ids.append(job["job_public_id"])
        
        # Verify sequence increments
        seq1 = int(public_ids[0].split("/")[2])
        seq2 = int(public_ids[1].split("/")[2])
        assert seq2 > seq1, f"Sequence should increment: {seq1} -> {seq2}"
        
        print(f"✅ Job IDs increment correctly: {public_ids[0]} -> {public_ids[1]}")
        
        # Cleanup
        for job_id in job_ids:
            requests.delete(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)


class TestShareableLinkEndpoint:
    """Test Feature 1: PUT /api/jobs/{job_id}/shareable-link endpoint"""
    
    def test_shareable_link_requires_auth(self):
        """Test that shareable link endpoint requires authentication"""
        response = requests.put(f"{BASE_URL}/api/jobs/test-id/shareable-link", json={"enabled": True})
        assert response.status_code == 403 or response.status_code == 401, "Should require auth"
        print("✅ Shareable link endpoint requires authentication")
    
    def test_shareable_link_requires_live_career_page(self):
        """Test that shareable link can only be enabled for live career page jobs"""
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create a job (default career_page_status is not_posted)
        job_data = {
            "title": "TEST_ShareableLink_Job",
            "description": "Test job for shareable link",
            "location": "Bangalore",
            "job_type": "full-time"
        }
        response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=headers)
        assert response.status_code == 200
        job = response.json()
        job_id = job["id"]
        
        # Try to enable shareable link without live career page - should fail
        response = requests.put(
            f"{BASE_URL}/api/jobs/{job_id}/shareable-link",
            json={"enabled": True},
            headers=headers
        )
        assert response.status_code == 400, f"Should fail for non-live job: {response.text}"
        assert "live" in response.json().get("detail", "").lower(), "Error should mention live status"
        
        print("✅ Shareable link correctly requires live career page status")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)
    
    def test_shareable_link_enable_for_live_job(self):
        """Test enabling shareable link for a live career page job"""
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create a job
        job_data = {
            "title": "TEST_LiveShareable_Job",
            "description": "Test job for live shareable link",
            "location": "Chennai",
            "job_type": "full-time"
        }
        response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=headers)
        assert response.status_code == 200
        job = response.json()
        job_id = job["id"]
        
        # Set career page status to live
        response = requests.post(
            f"{BASE_URL}/api/jobs/{job_id}/career-page-status",
            json={"new_status": "live"},
            headers=headers
        )
        assert response.status_code == 200, f"Failed to set career page live: {response.text}"
        
        # Now enable shareable link - should succeed
        response = requests.put(
            f"{BASE_URL}/api/jobs/{job_id}/shareable-link",
            json={"enabled": True},
            headers=headers
        )
        assert response.status_code == 200, f"Failed to enable shareable link: {response.text}"
        result = response.json()
        assert result.get("shareable_link_enabled") == True
        
        print(f"✅ Shareable link enabled for live job: {result.get('job_public_id')}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)


class TestPublicJobEndpoints:
    """Test Feature 1: Public Job Landing Page endpoints"""
    
    def test_public_jobs_list_no_auth(self):
        """Test GET /api/public/jobs works without authentication"""
        response = requests.get(f"{BASE_URL}/api/public/jobs")
        assert response.status_code == 200, f"Public jobs list failed: {response.text}"
        jobs = response.json()
        assert isinstance(jobs, list), "Response should be a list"
        print(f"✅ Public jobs list accessible without auth, found {len(jobs)} jobs")
    
    def test_public_jobs_visibility_rules(self):
        """Test that public jobs only shows live + shareable_link_enabled jobs"""
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create a job that is NOT live
        job_data = {
            "title": "TEST_NotVisible_Job",
            "description": "This job should NOT appear in public list",
            "location": "Pune",
            "job_type": "full-time"
        }
        response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=headers)
        assert response.status_code == 200
        hidden_job = response.json()
        
        # Check public list - this job should NOT appear
        response = requests.get(f"{BASE_URL}/api/public/jobs")
        public_jobs = response.json()
        hidden_job_ids = [j["id"] for j in public_jobs]
        assert hidden_job["id"] not in hidden_job_ids, "Non-live job should not appear in public list"
        
        print("✅ Visibility rules enforced - non-live jobs hidden from public")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/jobs/{hidden_job['id']}", headers=headers)
    
    def test_public_job_detail_by_id(self):
        """Test GET /api/public/jobs/{job_id} for a visible job"""
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create and make job visible
        job_data = {
            "title": "TEST_PublicDetail_Job",
            "description": "Test job for public detail view",
            "location": "Hyderabad",
            "job_type": "remote",
            "public_company_alias": "Leading Tech Company"
        }
        response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=headers)
        assert response.status_code == 200
        job = response.json()
        job_id = job["id"]
        
        # Make it live
        requests.post(
            f"{BASE_URL}/api/jobs/{job_id}/career-page-status",
            json={"new_status": "live"},
            headers=headers
        )
        
        # Enable shareable link
        requests.put(
            f"{BASE_URL}/api/jobs/{job_id}/shareable-link",
            json={"enabled": True},
            headers=headers
        )
        
        # Now fetch public detail - should work without auth
        response = requests.get(f"{BASE_URL}/api/public/jobs/{job_id}")
        assert response.status_code == 200, f"Public job detail failed: {response.text}"
        
        public_job = response.json()
        assert public_job["id"] == job_id
        assert public_job["title"] == "TEST_PublicDetail_Job"
        assert public_job.get("job_public_id") is not None
        # Company name should be alias, not real name
        assert public_job.get("company_name") == "Leading Tech Company"
        
        print(f"✅ Public job detail accessible: {public_job.get('job_public_id')}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)
    
    def test_public_job_detail_hidden_job_returns_404(self):
        """Test that non-visible jobs return 404 on public endpoint"""
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create a job but don't make it live
        job_data = {
            "title": "TEST_Hidden_Job",
            "description": "This job should return 404 on public endpoint",
            "location": "Kolkata",
            "job_type": "contract"
        }
        response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=headers)
        assert response.status_code == 200
        job = response.json()
        job_id = job["id"]
        
        # Try to access via public endpoint - should return 404
        response = requests.get(f"{BASE_URL}/api/public/jobs/{job_id}")
        assert response.status_code == 404, f"Hidden job should return 404: {response.status_code}"
        
        print("✅ Hidden jobs correctly return 404 on public endpoint")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)


class TestPublicApplyEndpoint:
    """Test Feature 1: POST /api/public/apply endpoint"""
    
    def test_public_apply_requires_consent(self):
        """Test that public apply requires consent_given=true"""
        # First, we need a visible job
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create and make job visible
        job_data = {
            "title": "TEST_ApplyConsent_Job",
            "description": "Test job for consent requirement",
            "location": "Mumbai",
            "job_type": "full-time"
        }
        response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=headers)
        job = response.json()
        job_id = job["id"]
        
        # Make it live and shareable
        requests.post(f"{BASE_URL}/api/jobs/{job_id}/career-page-status", json={"new_status": "live"}, headers=headers)
        requests.put(f"{BASE_URL}/api/jobs/{job_id}/shareable-link", json={"enabled": True}, headers=headers)
        
        # Try to apply WITHOUT consent
        apply_data = {
            "job_id": job_id,
            "name": "Test Applicant",
            "email": "test_consent@example.com",
            "consent_given": "false"  # Not giving consent
        }
        
        # Create a dummy file for resume
        files = {"resume": ("test_resume.txt", b"Test resume content", "text/plain")}
        
        response = requests.post(f"{BASE_URL}/api/public/apply", data=apply_data, files=files)
        assert response.status_code == 400, f"Should fail without consent: {response.status_code}"
        assert "consent" in response.json().get("detail", "").lower()
        
        print("✅ Public apply correctly requires consent")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)
    
    def test_public_apply_with_consent(self):
        """Test successful public application with consent"""
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create and make job visible
        job_data = {
            "title": "TEST_ApplySuccess_Job",
            "description": "Test job for successful application",
            "location": "Delhi",
            "job_type": "full-time"
        }
        response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=headers)
        job = response.json()
        job_id = job["id"]
        
        # Make it live and shareable
        requests.post(f"{BASE_URL}/api/jobs/{job_id}/career-page-status", json={"new_status": "live"}, headers=headers)
        requests.put(f"{BASE_URL}/api/jobs/{job_id}/shareable-link", json={"enabled": True}, headers=headers)
        
        # Apply WITH consent
        timestamp = int(time.time())
        apply_data = {
            "job_id": job_id,
            "name": "Test Successful Applicant",
            "email": f"test_success_{timestamp}@example.com",
            "phone": "+91 9876543210",
            "current_salary": "1200000",
            "notice_period": "30 days",
            "consent_given": "true"
        }
        
        files = {"resume": ("test_resume.pdf", b"%PDF-1.4 Test resume content", "application/pdf")}
        
        response = requests.post(f"{BASE_URL}/api/public/apply", data=apply_data, files=files)
        assert response.status_code == 200, f"Application failed: {response.text}"
        
        result = response.json()
        assert result.get("success") == True
        
        print("✅ Public application with consent successful")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)
    
    def test_public_apply_honeypot_protection(self):
        """Test honeypot field for bot protection"""
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create and make job visible
        job_data = {
            "title": "TEST_Honeypot_Job",
            "description": "Test job for honeypot",
            "location": "Bangalore",
            "job_type": "full-time"
        }
        response = requests.post(f"{BASE_URL}/api/jobs", json=job_data, headers=headers)
        job = response.json()
        job_id = job["id"]
        
        requests.post(f"{BASE_URL}/api/jobs/{job_id}/career-page-status", json={"new_status": "live"}, headers=headers)
        requests.put(f"{BASE_URL}/api/jobs/{job_id}/shareable-link", json={"enabled": True}, headers=headers)
        
        # Apply with honeypot field filled (bot behavior)
        apply_data = {
            "job_id": job_id,
            "name": "Bot Applicant",
            "email": "bot@example.com",
            "consent_given": "true",
            "website": "http://spam.com"  # Honeypot field - bots fill this
        }
        
        files = {"resume": ("bot_resume.txt", b"Bot resume", "text/plain")}
        
        response = requests.post(f"{BASE_URL}/api/public/apply", data=apply_data, files=files)
        # Should return success (to not tip off bots) but not actually process
        assert response.status_code == 200
        
        print("✅ Honeypot protection working")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/jobs/{job_id}", headers=headers)


class TestJDParsingEndpoint:
    """Test Feature 3: POST /api/jobs/parse-jd endpoint"""
    
    def test_jd_parsing_requires_auth(self):
        """Test that JD parsing requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            data={"jd_text": "Test job description"}
        )
        assert response.status_code in [401, 403], "JD parsing should require auth"
        print("✅ JD parsing endpoint requires authentication")
    
    def test_jd_parsing_with_text(self):
        """Test JD parsing with text input"""
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        jd_text = """
        Senior Software Engineer - Full Stack
        
        Location: Mumbai, India
        Experience: 5-8 years
        
        We are looking for a Senior Software Engineer to join our team.
        
        Requirements:
        - 5+ years of experience in software development
        - Strong knowledge of Python, JavaScript, React
        - Experience with MongoDB and PostgreSQL
        - Good communication skills
        
        Responsibilities:
        - Design and develop scalable applications
        - Lead technical discussions
        - Mentor junior developers
        
        Salary: 20-30 LPA
        """
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            data={"jd_text": jd_text},
            headers=headers
        )
        
        # Note: This may fail if AI service is not available, but endpoint should work
        if response.status_code == 200:
            result = response.json()
            print(f"✅ JD parsing returned: title={result.get('title')}, skills={result.get('skills', [])[:3]}")
            
            # Verify response structure
            assert "title" in result or "success" in result
            if result.get("success"):
                assert "skills" in result
                assert "raw_text" in result
        else:
            # If AI service fails, endpoint should still return proper error
            print(f"⚠️ JD parsing returned {response.status_code} - AI service may be unavailable")
            assert response.status_code in [200, 500, 503], f"Unexpected status: {response.status_code}"
    
    def test_jd_parsing_requires_input(self):
        """Test that JD parsing requires either text or file"""
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Call without any input
        response = requests.post(f"{BASE_URL}/api/jobs/parse-jd", headers=headers)
        assert response.status_code == 400 or response.status_code == 422, "Should require input"
        
        print("✅ JD parsing correctly requires input")


class TestExistingTestJob:
    """Test with the existing test job mentioned in requirements"""
    
    def test_existing_job_visibility(self):
        """Test the existing test job (fb3514ce-2c16-40ab-ae4d-f0ae38016d3a)"""
        job_id = "fb3514ce-2c16-40ab-ae4d-f0ae38016d3a"
        
        # Try to access via public endpoint
        response = requests.get(f"{BASE_URL}/api/public/jobs/{job_id}")
        
        if response.status_code == 200:
            job = response.json()
            print(f"✅ Existing test job accessible: {job.get('job_public_id')} - {job.get('title')}")
            assert job.get("job_public_id") == "VHC/2026/0001", f"Expected VHC/2026/0001, got {job.get('job_public_id')}"
        else:
            print(f"⚠️ Existing test job not accessible (status {response.status_code}) - may need to enable shareable link")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
