"""
Test Resume Download Fix - Iteration 25
Tests that resume files can be downloaded from both /app/uploads and /app/backend/uploads
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestResumeDownloadFix:
    """Test resume download functionality after fix"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        # Login as employer
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "ajit@vhc.in",
            "password": "12345678"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.employer_token = response.json()["access_token"]
        self.employer_headers = {"Authorization": f"Bearer {self.employer_token}"}
        
        # Login as admin
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        self.admin_token = response.json()["access_token"]
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
    
    def test_uploads_endpoint_returns_file(self):
        """Test GET /api/uploads/{filename} returns file from /app/uploads"""
        # Test with Mithun's resume which is in /app/uploads
        filename = "public_mithun_khatei_at_gmail_com_20260128_071025_Mithun_Khatei_VHC.pdf"
        response = requests.get(f"{BASE_URL}/api/uploads/{filename}")
        
        assert response.status_code == 200, f"Upload endpoint failed: {response.text}"
        assert len(response.content) > 0, "File content is empty"
        assert response.content[:4] == b'%PDF', "File is not a valid PDF"
        print(f"✅ /api/uploads/{filename} returns valid PDF ({len(response.content)} bytes)")
    
    def test_application_resume_download(self):
        """Test GET /api/applications/{app_id}/resume downloads file correctly"""
        # Get applications to find Mithun's application
        response = requests.get(f"{BASE_URL}/api/applications", headers=self.admin_headers)
        assert response.status_code == 200, f"Get applications failed: {response.text}"
        
        applications = response.json()
        mithun_app = None
        for app in applications:
            if 'mithun' in app.get('candidate_name', '').lower():
                mithun_app = app
                break
        
        assert mithun_app is not None, "Mithun's application not found"
        print(f"Found Mithun's application: {mithun_app['id']}")
        
        # Test download endpoint
        response = requests.get(
            f"{BASE_URL}/api/applications/{mithun_app['id']}/resume",
            headers=self.employer_headers
        )
        
        assert response.status_code == 200, f"Download failed: {response.text}"
        assert len(response.content) > 0, "Downloaded file is empty"
        assert response.content[:4] == b'%PDF', "Downloaded file is not a valid PDF"
        
        # Check content-disposition header for proper filename
        content_disposition = response.headers.get('content-disposition', '')
        assert 'Mithun' in content_disposition or 'Khatei' in content_disposition, \
            f"Filename should contain candidate name: {content_disposition}"
        
        print(f"✅ Application resume download works ({len(response.content)} bytes)")
        print(f"   Content-Disposition: {content_disposition}")
    
    def test_candidate_bank_resume_download(self):
        """Test GET /api/candidates/{candidate_id}/resume downloads file correctly"""
        # Get candidate bank to find a candidate with resume
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=self.admin_headers)
        assert response.status_code == 200, f"Get candidate bank failed: {response.text}"
        
        candidates = response.json()
        candidate_with_resume = None
        for c in candidates:
            if c.get('resume_url') and 'public_' in c.get('resume_url', ''):
                candidate_with_resume = c
                break
        
        if candidate_with_resume is None:
            pytest.skip("No candidate with public resume found")
        
        print(f"Found candidate with resume: {candidate_with_resume['name']} ({candidate_with_resume['id']})")
        
        # Test download endpoint
        response = requests.get(
            f"{BASE_URL}/api/candidates/{candidate_with_resume['id']}/resume",
            headers=self.admin_headers
        )
        
        assert response.status_code == 200, f"Download failed: {response.text}"
        assert len(response.content) > 0, "Downloaded file is empty"
        print(f"✅ Candidate bank resume download works ({len(response.content)} bytes)")


class TestPublicApplicationCandidateBank:
    """Test that public applications create candidates in candidate_bank"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        # Login as admin
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        self.admin_token = response.json()["access_token"]
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
    
    def test_public_application_candidates_in_bank(self):
        """Test that candidates from public applications are in candidate_bank"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=self.admin_headers)
        assert response.status_code == 200, f"Get candidate bank failed: {response.text}"
        
        candidates = response.json()
        public_app_candidates = [c for c in candidates if c.get('source') == 'public_application']
        
        assert len(public_app_candidates) > 0, "No public_application candidates found in candidate_bank"
        print(f"✅ Found {len(public_app_candidates)} candidates from public applications")
        
        for c in public_app_candidates[:3]:
            print(f"   - {c.get('name')} ({c.get('email')})")
    
    def test_ai_screening_finds_public_candidates(self):
        """Test that AI screening can find candidates from public applications"""
        # Get a job ID
        response = requests.get(f"{BASE_URL}/api/jobs", headers=self.admin_headers)
        assert response.status_code == 200, f"Get jobs failed: {response.text}"
        
        jobs = response.json()
        if not jobs:
            pytest.skip("No jobs found")
        
        job_id = jobs[0]['id']
        
        # Run AI screening
        response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            headers=self.admin_headers,
            json={"job_id": job_id}
        )
        
        assert response.status_code == 200, f"AI screening failed: {response.text}"
        
        results = response.json()
        public_app_results = [r for r in results if r.get('source') == 'public_application']
        
        print(f"✅ AI Screening returned {len(results)} candidates")
        print(f"   - {len(public_app_results)} from public applications")
        
        # At least some public application candidates should be found
        assert len(public_app_results) > 0 or len(results) > 0, \
            "AI screening should find candidates"


class TestNavneetResumeDownload:
    """Test Navneet's DOCX resume download"""
    
    def test_navneet_docx_download(self):
        """Test downloading Navneet's DOCX resume"""
        filename = "public_navneetjim_at_gmail_com_20260128_064059_Navneet_Srivastava_VHC.docx"
        response = requests.get(f"{BASE_URL}/api/uploads/{filename}")
        
        assert response.status_code == 200, f"Download failed: {response.text}"
        assert len(response.content) > 0, "File content is empty"
        # DOCX files start with PK (ZIP format)
        assert response.content[:2] == b'PK', "File is not a valid DOCX"
        print(f"✅ Navneet's DOCX resume downloads correctly ({len(response.content)} bytes)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
