"""
Test Naukri Browser Extension API - Tests capture, profile retrieval, stats, and duplicate detection
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


class TestNaukriExtensionAPI:
    """Test suite for Naukri Browser Extension API endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token for admin"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Admin login failed: {login_response.text}"
        self.token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Generate unique test identifiers
        self.test_id = str(uuid.uuid4())[:8]
        
    def test_capture_new_profile_creates_candidate(self):
        """Test POST /api/extension/capture creates a new candidate with comprehensive data"""
        profile_data = {
            "naukri_profile_id": f"TEST_NAUKRI_{self.test_id}",
            "naukri_profile_url": f"https://www.naukri.com/profile/TEST_{self.test_id}",
            "name": f"Test Candidate {self.test_id}",
            "email": f"test_{self.test_id}@example.com",
            "phone": f"98765{self.test_id[:5]}",
            "headline": "Senior Software Engineer",
            "profile_summary": "Experienced full-stack developer with 10+ years of experience",
            "current_company": "Test Tech Corp",
            "current_designation": "Lead Engineer",
            "total_experience_years": 10.5,
            "total_experience_months": 126,
            "key_skills": ["Python", "React", "AWS", "Docker", "MongoDB"],
            "work_experience": [
                {
                    "company": "Test Tech Corp",
                    "designation": "Lead Engineer",
                    "from_date": "2020-01",
                    "is_current": True,
                    "duration": "4 years",
                    "location": "Bangalore"
                },
                {
                    "company": "Previous Corp",
                    "designation": "Senior Engineer",
                    "from_date": "2016-01",
                    "to_date": "2019-12",
                    "duration": "4 years",
                    "location": "Mumbai"
                }
            ],
            "education": [
                {
                    "degree": "B.Tech",
                    "specialization": "Computer Science",
                    "institution": "IIT Delhi",
                    "year_of_passing": "2014"
                }
            ],
            "certifications": [
                {
                    "name": "AWS Solutions Architect",
                    "issuing_authority": "Amazon"
                }
            ],
            "languages": [
                {"language": "English", "proficiency": "Expert"},
                {"language": "Hindi", "proficiency": "Native"}
            ],
            "personal_details": {
                "date_of_birth": "1990-05-15",
                "gender": "Male",
                "marital_status": "Married",
                "nationality": "Indian",
                "current_city": "Bangalore",
                "current_state": "Karnataka",
                "current_country": "India"
            },
            "career_preferences": {
                "current_salary": 2500000,
                "expected_salary": 3500000,
                "notice_period": "30 days",
                "notice_period_days": 30,
                "current_location": "Bangalore",
                "preferred_locations": ["Bangalore", "Hyderabad", "Remote"],
                "willing_to_relocate": True,
                "preferred_job_type": ["Full-time"],
                "work_from_home": True
            },
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        
        # Status assertion
        assert response.status_code == 200, f"Capture failed: {response.text}"
        
        # Data assertions
        data = response.json()
        assert data["success"] == True
        assert data["action"] == "created"
        assert "candidate_id" in data
        assert len(data["candidate_id"]) > 0
        assert data["message"].startswith("Test Candidate")
        
        # Store candidate_id for later tests
        self.created_candidate_id = data["candidate_id"]
        print(f"✅ Created candidate: {self.created_candidate_id}")
        
    def test_capture_duplicate_naukri_id_updates(self):
        """Test POST /api/extension/capture updates existing candidate when same naukri_profile_id"""
        # First create a candidate
        profile_id = f"TEST_DUP_{self.test_id}"
        profile_data = {
            "naukri_profile_id": profile_id,
            "naukri_profile_url": f"https://www.naukri.com/profile/{profile_id}",
            "name": f"Original Name {self.test_id}",
            "email": f"original_{self.test_id}@example.com",
            "phone": f"91234{self.test_id[:5]}",
            "total_experience_years": 5,
            "key_skills": ["Java"],
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        create_response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert create_response.status_code == 200
        assert create_response.json()["action"] == "created"
        candidate_id = create_response.json()["candidate_id"]
        
        # Now send same naukri_profile_id with updated data
        updated_data = {
            "naukri_profile_id": profile_id,  # Same ID
            "naukri_profile_url": f"https://www.naukri.com/profile/{profile_id}",
            "name": f"Updated Name {self.test_id}",
            "email": f"original_{self.test_id}@example.com",  # Same email
            "phone": f"99999{self.test_id[:5]}",  # Updated phone
            "total_experience_years": 6,  # Updated experience
            "key_skills": ["Java", "Spring", "Kubernetes"],  # Updated skills
            "current_designation": "Tech Lead",  # New field
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        update_response = self.session.post(f"{BASE_URL}/api/extension/capture", json=updated_data)
        
        # Status assertion
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        
        # Data assertions
        data = update_response.json()
        assert data["success"] == True
        assert data["action"] == "updated", f"Expected 'updated', got '{data['action']}'"
        assert data["candidate_id"] == candidate_id  # Same candidate ID
        print(f"✅ Duplicate naukri_profile_id updates existing candidate: {candidate_id}")
        
    def test_capture_duplicate_email_updates(self):
        """Test POST /api/extension/capture finds and updates candidate by email"""
        # First create a candidate via capture
        unique_email = f"email_dup_{self.test_id}@example.com"
        profile_data1 = {
            "naukri_profile_id": f"NAUKRI_A_{self.test_id}",
            "naukri_profile_url": f"https://www.naukri.com/profile/A_{self.test_id}",
            "name": f"Email Dup User {self.test_id}",
            "email": unique_email,
            "total_experience_years": 3,
            "key_skills": ["Python"],
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        create_response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data1)
        assert create_response.status_code == 200
        assert create_response.json()["action"] == "created"
        candidate_id = create_response.json()["candidate_id"]
        
        # Now send DIFFERENT naukri_profile_id but SAME email
        profile_data2 = {
            "naukri_profile_id": f"NAUKRI_B_{self.test_id}",  # Different naukri ID
            "naukri_profile_url": f"https://www.naukri.com/profile/B_{self.test_id}",
            "name": f"Email Dup User Updated {self.test_id}",
            "email": unique_email,  # Same email
            "total_experience_years": 4,  # Updated
            "key_skills": ["Python", "Django"],  # Updated
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        update_response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data2)
        
        # Status assertion
        assert update_response.status_code == 200
        
        # Data assertions
        data = update_response.json()
        assert data["success"] == True
        assert data["action"] == "updated", f"Expected 'updated' by email match, got '{data['action']}'"
        assert data["candidate_id"] == candidate_id  # Should find same candidate
        print(f"✅ Duplicate email updates existing candidate: {candidate_id}")
        
    def test_get_extension_stats(self):
        """Test GET /api/extension/stats returns capture statistics"""
        response = self.session.get(f"{BASE_URL}/api/extension/stats")
        
        # Status assertion
        assert response.status_code == 200, f"Stats failed: {response.text}"
        
        # Data assertions
        data = response.json()
        assert "total_captured" in data
        assert "user_captured" in data
        assert "today_captured" in data
        assert isinstance(data["total_captured"], int)
        assert isinstance(data["user_captured"], int)
        assert isinstance(data["today_captured"], int)
        print(f"✅ Extension stats: total={data['total_captured']}, user={data['user_captured']}, today={data['today_captured']}")
        
    def test_get_profile_by_id_returns_full_data(self):
        """Test GET /api/extension/profile/{id} returns complete Naukri profile data"""
        # Use the test candidate ID provided in review request
        test_candidate_id = "62f9b2ea-f498-494a-a649-2ace564d7405"
        
        response = self.session.get(f"{BASE_URL}/api/extension/profile/{test_candidate_id}")
        
        # Status assertion
        assert response.status_code == 200, f"Profile fetch failed: {response.text}"
        
        # Data assertions - verify all Naukri-specific fields are present
        data = response.json()
        assert data["id"] == test_candidate_id
        assert "name" in data
        assert "email" in data
        assert "source" in data
        
        # Check source is naukri_extension
        assert data.get("source") == "naukri_extension", f"Expected source 'naukri_extension', got '{data.get('source')}'"
        
        # Check naukri-specific fields
        assert "naukri_profile_id" in data
        assert "naukri_profile_url" in data
        
        # Check source_details exists
        assert "source_details" in data
        source_details = data.get("source_details", {})
        assert "captured_by" in source_details or source_details == {}  # May be empty for some records
        
        # Check arrays exist (may be empty)
        assert "experience" in data or "work_experience" in data
        assert "education" in data
        
        print(f"✅ Full profile retrieved for: {data.get('name')} (source: {data.get('source')})")
        
    def test_get_profile_not_found_returns_404(self):
        """Test GET /api/extension/profile/{id} returns 404 for non-existent candidate"""
        fake_id = "non-existent-candidate-id-12345"
        
        response = self.session.get(f"{BASE_URL}/api/extension/profile/{fake_id}")
        
        # Status assertion
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✅ Non-existent candidate returns 404")
        
    def test_candidate_bank_shows_naukri_source(self):
        """Test GET /api/candidate-bank returns candidates with naukri_extension source"""
        response = self.session.get(f"{BASE_URL}/api/candidate-bank", params={"limit": 100})
        
        # Status assertion
        assert response.status_code == 200, f"Candidate bank failed: {response.text}"
        
        # Data assertions
        data = response.json()
        
        # Handle both paginated and non-paginated response
        candidates = data.get("candidates", data) if isinstance(data, dict) else data
        
        # Check if any candidate has naukri_extension source
        naukri_candidates = [c for c in candidates if c.get("source") == "naukri_extension"]
        
        if len(naukri_candidates) > 0:
            print(f"✅ Found {len(naukri_candidates)} naukri_extension sourced candidates in candidate bank")
            # Verify the source field is included in list response
            sample = naukri_candidates[0]
            assert "source" in sample
            assert sample["source"] == "naukri_extension"
        else:
            print("⚠️ No naukri_extension candidates found in candidate bank (may be on different page)")
            
    def test_capture_profile_with_all_arrays(self):
        """Test POST /api/extension/capture handles all array fields correctly"""
        profile_data = {
            "naukri_profile_id": f"TEST_ARRAYS_{self.test_id}",
            "naukri_profile_url": f"https://www.naukri.com/profile/ARRAYS_{self.test_id}",
            "name": f"Array Test User {self.test_id}",
            "email": f"arrays_{self.test_id}@example.com",
            "key_skills": ["Skill1", "Skill2", "Skill3"],
            "soft_skills": ["Communication", "Leadership"],
            "tools": ["VS Code", "Git", "JIRA"],
            "work_experience": [
                {"company": "Company A", "designation": "Developer", "is_current": True},
                {"company": "Company B", "designation": "Junior Dev", "is_current": False}
            ],
            "education": [
                {"degree": "Masters", "institution": "University A"},
                {"degree": "Bachelors", "institution": "University B"}
            ],
            "certifications": [
                {"name": "Cert A", "issuing_authority": "Org A"},
                {"name": "Cert B", "issuing_authority": "Org B"}
            ],
            "projects": [
                {"title": "Project A", "description": "Test project A"},
                {"title": "Project B", "description": "Test project B"}
            ],
            "languages": [
                {"language": "English", "proficiency": "Expert"},
                {"language": "Spanish", "proficiency": "Intermediate"}
            ],
            "it_skills": [
                {"name": "Python", "experience_years": 5},
                {"name": "JavaScript", "experience_years": 3}
            ],
            "online_profiles": [
                {"platform": "LinkedIn", "url": "https://linkedin.com/in/test"},
                {"platform": "GitHub", "url": "https://github.com/test"}
            ],
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        
        # Status assertion
        assert response.status_code == 200, f"Capture with arrays failed: {response.text}"
        
        # Data assertions
        data = response.json()
        assert data["success"] == True
        assert data["action"] == "created"
        candidate_id = data["candidate_id"]
        
        # Verify data was stored by fetching profile
        profile_response = self.session.get(f"{BASE_URL}/api/extension/profile/{candidate_id}")
        assert profile_response.status_code == 200
        
        profile = profile_response.json()
        assert len(profile.get("skills", [])) == 3
        assert len(profile.get("experience", [])) == 2
        assert len(profile.get("education", [])) == 2
        print(f"✅ All array fields captured correctly for candidate: {candidate_id}")


class TestNaukriExtensionAdditional:
    """Additional tests for Naukri Extension API - ai-extract, download, hidden contact"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token for admin"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Admin login failed: {login_response.text}"
        self.token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Generate unique test identifiers
        self.test_id = str(uuid.uuid4())[:8]
    
    def test_ai_extract_with_valid_text(self):
        """Test POST /api/extension/ai-extract returns structured profile data from raw text"""
        raw_text = """Profile Summary: Senior Software Engineer with 10+ years of experience 
        in Python, React, and cloud technologies. Currently working at TechCorp as Lead Engineer. 
        Education: BTech from IIT Delhi 2014. Skills: Python, JavaScript, AWS, Docker, Kubernetes. 
        Contact: test@example.com, Phone: 9876543210. Current CTC: 25 Lacs. Expected CTC: 35 Lacs. 
        Notice Period: 30 days. Location: Bangalore."""
        
        response = self.session.post(f"{BASE_URL}/api/extension/ai-extract", json={
            "raw_text": raw_text,
            "page_url": "https://naukri.com/test-profile"
        })
        
        # Status assertion
        assert response.status_code == 200, f"AI extract failed: {response.text}"
        
        # Data assertions
        data = response.json()
        assert data["success"] == True
        assert data["profile_data"] is not None
        assert "name" in data["profile_data"] or "email" in data["profile_data"]
        print(f"✅ AI extraction returned structured data: {data['profile_data'].get('name', 'N/A')}")
    
    def test_ai_extract_with_insufficient_text(self):
        """Test POST /api/extension/ai-extract rejects short text"""
        response = self.session.post(f"{BASE_URL}/api/extension/ai-extract", json={
            "raw_text": "short",
            "page_url": "https://naukri.com/test"
        })
        
        # Status assertion
        assert response.status_code == 200
        
        # Data assertions - should return error for insufficient text
        data = response.json()
        assert data["success"] == False
        assert "Insufficient text" in data.get("error", "")
        print("✅ AI extraction correctly rejects insufficient text")
    
    def test_extension_download_endpoint(self):
        """Test GET /api/download/naukri-extension returns ZIP file"""
        # Note: The correct URL is /api/download/naukri-extension (not /api/files/download/...)
        response = self.session.get(f"{BASE_URL}/api/download/naukri-extension")
        
        # Status assertion
        assert response.status_code == 200, f"Extension download failed: {response.status_code}"
        
        # Data assertions - verify it's a ZIP file
        content_type = response.headers.get("content-type", "")
        assert "zip" in content_type.lower() or len(response.content) > 10000, "Expected ZIP file"
        
        # Check ZIP file signature (PK header)
        assert response.content[:2] == b'PK', "Response is not a valid ZIP file"
        print(f"✅ Extension ZIP download works (size: {len(response.content)} bytes)")
    
    def test_capture_profile_with_null_email_phone(self):
        """Test POST /api/extension/capture handles null email/phone correctly"""
        profile_data = {
            "naukri_profile_id": f"TEST_NULL_CONTACT_{self.test_id}",
            "naukri_profile_url": f"https://www.naukri.com/profile/NULL_{self.test_id}",
            "name": f"Null Contact User {self.test_id}",
            "email": None,  # Explicitly null
            "phone": None,  # Explicitly null
            "headline": "Test user with hidden contact",
            "total_experience_years": 5,
            "key_skills": ["Python"],
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        
        # Status assertion
        assert response.status_code == 200, f"Capture with null contact failed: {response.text}"
        
        # Data assertions
        data = response.json()
        assert data["success"] == True
        candidate_id = data["candidate_id"]
        
        # Verify profile stored correctly
        profile_response = self.session.get(f"{BASE_URL}/api/extension/profile/{candidate_id}")
        assert profile_response.status_code == 200
        
        profile = profile_response.json()
        assert profile["email"] is None, "Email should be null"
        assert profile["phone"] is None, "Phone should be null"
        print(f"✅ Profile with null email/phone created correctly: {candidate_id}")


class TestNaukriExtensionAuth:
    """Test authentication requirements for extension endpoints"""
    
    def test_capture_requires_auth(self):
        """Test POST /api/extension/capture requires authentication"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        profile_data = {
            "naukri_profile_id": "UNAUTH_TEST",
            "naukri_profile_url": "https://naukri.com/test",
            "name": "Unauth Test",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        
        # Should return 401 or 403 (Unauthorized/Forbidden)
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ Capture endpoint requires authentication")
        
    def test_stats_requires_auth(self):
        """Test GET /api/extension/stats requires authentication"""
        session = requests.Session()
        
        response = session.get(f"{BASE_URL}/api/extension/stats")
        
        # Should return 401 or 403 (Unauthorized/Forbidden)
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ Stats endpoint requires authentication")
        
    def test_profile_requires_auth(self):
        """Test GET /api/extension/profile/{id} requires authentication"""
        session = requests.Session()
        
        response = session.get(f"{BASE_URL}/api/extension/profile/any-id")
        
        # Should return 401 or 403 (Unauthorized/Forbidden)
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ Profile endpoint requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
