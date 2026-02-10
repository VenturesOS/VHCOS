"""
Test VHC Talent OS v3.6.0 - NEW Validation Logic Tests

Tests:
1. Invalid name rejection (Search candidates, Decode India, empty, too long)
2. Name cleaning (removes appended years like "Puja Gupta Basu - 15 Year(s)")
3. Email stripping (@naukri.com, @placeholder.com emails become null)
4. Valid profile acceptance
5. Deduplication by naukri_profile_id
6. AI extraction from noisy text
7. Extension download ZIP manifest version
"""
import pytest
import requests
import os
import uuid
import zipfile
import io
import json
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


class TestV36NameValidation:
    """Test v3.6.0 name validation and cleaning logic"""
    
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
        
        # Generate unique test identifiers with v36 prefix
        self.test_id = f"test_v36_{uuid.uuid4().hex[:8]}"
        self.created_candidates = []
        
    def teardown_method(self, method):
        """Cleanup test candidates after each test"""
        for candidate_id in self.created_candidates:
            try:
                # Note: There's no delete endpoint, so we'll just leave them
                pass
            except:
                pass
    
    # ================== INVALID NAME REJECTION TESTS ==================
    
    def test_reject_invalid_name_search_candidates(self):
        """Test capture rejects 'Search candidates' as invalid name"""
        profile_data = {
            "naukri_profile_id": f"{self.test_id}_search",
            "naukri_profile_url": f"https://www.naukri.com/profile/{self.test_id}",
            "name": "Search candidates",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        assert data["success"] == False, "Expected rejection"
        assert data["action"] == "rejected", f"Expected action='rejected', got '{data['action']}'"
        assert "Search candidates" in data.get("message", "")
        print("✅ 'Search candidates' correctly rejected")
    
    def test_reject_invalid_name_decode_india(self):
        """Test capture rejects 'Decode India' as invalid name"""
        profile_data = {
            "naukri_profile_id": f"{self.test_id}_decode",
            "naukri_profile_url": f"https://www.naukri.com/profile/{self.test_id}",
            "name": "Decode India",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == False, "Expected rejection"
        assert data["action"] == "rejected"
        print("✅ 'Decode India' correctly rejected")
    
    def test_reject_invalid_name_empty(self):
        """Test capture rejects empty name"""
        profile_data = {
            "naukri_profile_id": f"{self.test_id}_empty",
            "naukri_profile_url": f"https://www.naukri.com/profile/{self.test_id}",
            "name": "",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == False, "Expected rejection for empty name"
        assert data["action"] == "rejected"
        print("✅ Empty name correctly rejected")
    
    def test_reject_invalid_name_whitespace_only(self):
        """Test capture rejects whitespace-only name"""
        profile_data = {
            "naukri_profile_id": f"{self.test_id}_whitespace",
            "naukri_profile_url": f"https://www.naukri.com/profile/{self.test_id}",
            "name": "   ",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == False, "Expected rejection for whitespace name"
        assert data["action"] == "rejected"
        print("✅ Whitespace-only name correctly rejected")
    
    def test_reject_invalid_name_too_short(self):
        """Test capture rejects name shorter than 2 characters"""
        profile_data = {
            "naukri_profile_id": f"{self.test_id}_short",
            "naukri_profile_url": f"https://www.naukri.com/profile/{self.test_id}",
            "name": "A",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == False, "Expected rejection for too-short name"
        assert data["action"] == "rejected"
        print("✅ Too-short name correctly rejected")
    
    def test_reject_invalid_name_too_long(self):
        """Test capture rejects name longer than 80 characters"""
        long_name = "A" * 100  # 100 chars
        profile_data = {
            "naukri_profile_id": f"{self.test_id}_long",
            "naukri_profile_url": f"https://www.naukri.com/profile/{self.test_id}",
            "name": long_name,
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == False, "Expected rejection for too-long name"
        assert data["action"] == "rejected"
        print("✅ Too-long name correctly rejected")
    
    def test_reject_invalid_name_profiles_found(self):
        """Test capture rejects 'profiles found' as invalid name"""
        profile_data = {
            "naukri_profile_id": f"{self.test_id}_profilesfound",
            "naukri_profile_url": f"https://www.naukri.com/profile/{self.test_id}",
            "name": "profiles found",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == False, "Expected rejection"
        assert data["action"] == "rejected"
        print("✅ 'profiles found' correctly rejected")
    
    # ================== NAME CLEANING TESTS ==================
    
    def test_clean_name_removes_experience_years(self):
        """Test capture cleans name by removing appended experience years"""
        profile_data = {
            "naukri_profile_id": f"{self.test_id}_yearsclean",
            "naukri_profile_url": f"https://www.naukri.com/profile/{self.test_id}",
            "name": "Puja Gupta Basu - 15 Year(s)",
            "email": f"{self.test_id}_clean@example.com",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        assert data["success"] == True, f"Expected success, got: {data}"
        candidate_id = data["candidate_id"]
        self.created_candidates.append(candidate_id)
        
        # Verify name was cleaned by fetching profile
        profile_response = self.session.get(f"{BASE_URL}/api/extension/profile/{candidate_id}")
        assert profile_response.status_code == 200
        
        profile = profile_response.json()
        assert profile["name"] == "Puja Gupta Basu", f"Expected 'Puja Gupta Basu', got '{profile['name']}'"
        print(f"✅ Name cleaned from 'Puja Gupta Basu - 15 Year(s)' to '{profile['name']}'")
    
    def test_clean_name_removes_decimal_years(self):
        """Test capture cleans name with decimal experience years"""
        profile_data = {
            "naukri_profile_id": f"{self.test_id}_decimalyears",
            "naukri_profile_url": f"https://www.naukri.com/profile/{self.test_id}",
            "name": "Vikrant Kumar - 3.5 Years",
            "email": f"{self.test_id}_decimal@example.com",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == True
        candidate_id = data["candidate_id"]
        self.created_candidates.append(candidate_id)
        
        profile_response = self.session.get(f"{BASE_URL}/api/extension/profile/{candidate_id}")
        profile = profile_response.json()
        assert profile["name"] == "Vikrant Kumar", f"Expected 'Vikrant Kumar', got '{profile['name']}'"
        print(f"✅ Name cleaned from 'Vikrant Kumar - 3.5 Years' to '{profile['name']}'")


class TestV36EmailValidation:
    """Test v3.6.0 email stripping logic"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token for admin"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200
        self.token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        self.test_id = f"test_v36_{uuid.uuid4().hex[:8]}"
        self.created_candidates = []
    
    def test_strip_naukri_email(self):
        """Test capture strips @naukri.com emails to null"""
        profile_data = {
            "naukri_profile_id": f"{self.test_id}_naukriemail",
            "naukri_profile_url": f"https://www.naukri.com/profile/{self.test_id}",
            "name": "Valid User Naukri Email",
            "email": "user123@naukri.com",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == True
        candidate_id = data["candidate_id"]
        self.created_candidates.append(candidate_id)
        
        profile_response = self.session.get(f"{BASE_URL}/api/extension/profile/{candidate_id}")
        profile = profile_response.json()
        assert profile["email"] is None, f"Expected email to be null, got '{profile['email']}'"
        print("✅ @naukri.com email correctly stripped to null")
    
    def test_strip_placeholder_email(self):
        """Test capture strips @placeholder.com emails to null"""
        profile_data = {
            "naukri_profile_id": f"{self.test_id}_placeholderemail",
            "naukri_profile_url": f"https://www.naukri.com/profile/{self.test_id}",
            "name": "Valid User Placeholder Email",
            "email": "hidden@placeholder.com",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == True
        candidate_id = data["candidate_id"]
        self.created_candidates.append(candidate_id)
        
        profile_response = self.session.get(f"{BASE_URL}/api/extension/profile/{candidate_id}")
        profile = profile_response.json()
        assert profile["email"] is None, f"Expected email to be null, got '{profile['email']}'"
        print("✅ @placeholder.com email correctly stripped to null")
    
    def test_strip_support_naukri_email(self):
        """Test capture strips support@naukri type emails"""
        profile_data = {
            "naukri_profile_id": f"{self.test_id}_supportemail",
            "naukri_profile_url": f"https://www.naukri.com/profile/{self.test_id}",
            "name": "Valid User Support Email",
            "email": "support@domain.com",
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == True
        candidate_id = data["candidate_id"]
        self.created_candidates.append(candidate_id)
        
        profile_response = self.session.get(f"{BASE_URL}/api/extension/profile/{candidate_id}")
        profile = profile_response.json()
        assert profile["email"] is None, f"Expected email to be null, got '{profile['email']}'"
        print("✅ support@ email correctly stripped to null")
    
    def test_keep_valid_email(self):
        """Test capture keeps valid personal/work emails"""
        valid_email = f"{self.test_id}_valid@gmail.com"
        profile_data = {
            "naukri_profile_id": f"{self.test_id}_validemail",
            "naukri_profile_url": f"https://www.naukri.com/profile/{self.test_id}",
            "name": "Valid User Real Email",
            "email": valid_email,
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == True
        candidate_id = data["candidate_id"]
        self.created_candidates.append(candidate_id)
        
        profile_response = self.session.get(f"{BASE_URL}/api/extension/profile/{candidate_id}")
        profile = profile_response.json()
        assert profile["email"] == valid_email.lower(), f"Expected '{valid_email.lower()}', got '{profile['email']}'"
        print(f"✅ Valid email '{valid_email}' correctly preserved")


class TestV36ValidProfileCapture:
    """Test v3.6.0 accepts valid profiles"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200
        self.token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        self.test_id = f"test_v36_{uuid.uuid4().hex[:8]}"
        self.created_candidates = []
    
    def test_accept_valid_profile_with_clean_data(self):
        """Test capture accepts valid profile with all fields correctly"""
        valid_email = f"{self.test_id}_complete@example.com"
        profile_data = {
            "naukri_profile_id": f"{self.test_id}_valid_complete",
            "naukri_profile_url": f"https://www.naukri.com/profile/{self.test_id}",
            "name": "Rajiv Mathur",
            "email": valid_email,
            "phone": "9876543210",
            "headline": "Senior Software Engineer at TechCorp",
            "current_company": "TechCorp India",
            "current_designation": "Senior Engineer",
            "total_experience_years": 8.5,
            "key_skills": ["Python", "React", "AWS", "MongoDB"],
            "work_experience": [
                {
                    "company": "TechCorp India",
                    "designation": "Senior Engineer",
                    "is_current": True
                }
            ],
            "education": [
                {
                    "degree": "B.Tech Computer Science",
                    "institution": "IIT Bombay",
                    "year_of_passing": "2015"
                }
            ],
            "career_preferences": {
                "current_salary": 2000000,
                "expected_salary": 3000000,
                "notice_period": "30 days"
            },
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data)
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        assert data["success"] == True
        assert data["action"] in ["created", "updated"], f"Expected created/updated, got '{data['action']}'"
        candidate_id = data["candidate_id"]
        self.created_candidates.append(candidate_id)
        
        # Verify all data stored
        profile_response = self.session.get(f"{BASE_URL}/api/extension/profile/{candidate_id}")
        assert profile_response.status_code == 200
        
        profile = profile_response.json()
        assert profile["name"] == "Rajiv Mathur"
        assert profile["email"] == valid_email.lower()
        assert profile["source"] == "naukri_extension"
        assert len(profile.get("skills", [])) == 4
        print(f"✅ Valid complete profile captured: {candidate_id}")
    
    def test_deduplication_by_naukri_profile_id(self):
        """Test capture deduplicates by naukri_profile_id (returns updated)"""
        profile_id = f"{self.test_id}_dedup"
        
        # First capture
        profile_data1 = {
            "naukri_profile_id": profile_id,
            "naukri_profile_url": f"https://www.naukri.com/profile/{profile_id}",
            "name": "Dedup Test User",
            "email": f"{self.test_id}_dedup@example.com",
            "total_experience_years": 5,
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response1 = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data1)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["success"] == True
        assert data1["action"] == "created"
        first_candidate_id = data1["candidate_id"]
        self.created_candidates.append(first_candidate_id)
        
        # Second capture with same naukri_profile_id
        profile_data2 = {
            "naukri_profile_id": profile_id,  # Same ID
            "naukri_profile_url": f"https://www.naukri.com/profile/{profile_id}",
            "name": "Dedup Test User",
            "email": f"{self.test_id}_dedup@example.com",
            "total_experience_years": 6,  # Updated
            "current_designation": "Tech Lead",  # New
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        response2 = self.session.post(f"{BASE_URL}/api/extension/capture", json=profile_data2)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["success"] == True
        assert data2["action"] == "updated", f"Expected 'updated', got '{data2['action']}'"
        assert data2["candidate_id"] == first_candidate_id
        print(f"✅ Deduplication by naukri_profile_id works correctly")


class TestV36AIExtraction:
    """Test v3.6.0 AI extraction from noisy text"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200
        self.token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_ai_extract_from_noisy_text_with_nav(self):
        """Test AI extraction ignores nav items and extracts only candidate data"""
        # Realistic noisy text with nav items, profile data, and marketing text
        noisy_text = """Jobs & Responses
Resdex
Reports
Recent
Search
Decode India's largest talent pool

15 profiles found

Rajiv Sharma
Senior Software Engineer at Infosys
10.5 Years Experience

Profile Summary: Experienced full-stack developer specializing in Java, Python, and cloud technologies. Led multiple enterprise projects with teams of 10+ engineers.

Contact: rajiv.sharma.work@gmail.com
Phone: +91 9876543210

Current CTC: 25 Lacs
Expected CTC: 35 Lacs
Notice Period: 30 Days

Location: Bangalore, Karnataka
Preferred: Bangalore, Hyderabad, Remote

Skills: Java, Python, Spring Boot, AWS, Docker, Kubernetes, MongoDB, React

Work Experience:
- Infosys (Current) - Senior Engineer - 5 Years
- TCS - Software Engineer - 3 Years
- Wipro - Junior Engineer - 2 Years

Education:
- B.Tech Computer Science - IIT Delhi - 2013

Certifications:
- AWS Solutions Architect
- Java SE 11 Developer

AI matched similar profiles
Save for later
Add to folder
Report profile

Similar profiles you might like:
Profile 1 - Different candidate
Profile 2 - Another candidate"""

        response = self.session.post(f"{BASE_URL}/api/extension/ai-extract", json={
            "raw_text": noisy_text,
            "page_url": "https://resdex.naukri.com/profile/12345",
            "naukri_profile_id": "naukri_test_ai"
        })
        
        assert response.status_code == 200, f"AI extract failed: {response.text}"
        
        data = response.json()
        assert data["success"] == True, f"AI extraction failed: {data.get('error')}"
        assert data["profile_data"] is not None
        
        profile = data["profile_data"]
        
        # Name should be clean, NOT include nav items
        name = profile.get("name", "")
        assert name is not None, "Name should not be null"
        # Name should NOT contain nav items
        invalid_in_name = ["Jobs", "Resdex", "Reports", "Search", "Decode", "AI matched", "Similar"]
        for invalid in invalid_in_name:
            assert invalid not in name, f"Name '{name}' should not contain '{invalid}'"
        
        # Should extract the actual candidate's data
        print(f"✅ AI extracted name: '{name}'")
        print(f"✅ AI extracted email: '{profile.get('email')}'")
        print(f"✅ AI extracted skills: {len(profile.get('key_skills', []))} skills")
    
    def test_ai_extract_does_not_include_nav_in_name(self):
        """Test AI extraction name field never includes nav/marketing text"""
        nav_heavy_text = """Home
Dashboard
Jobs & Responses
Resdex
Reports
Recent
Search candidates
Notifications
Settings

Ashwin Mehta
Product Manager at Google
Experience: 8 years

Summary: Product management expert with experience in consumer tech.
Email: ashwin.mehta.pm@outlook.com
Skills: Product Management, Agile, Data Analysis

Next
Prev
Print
Back to search
Save for later"""

        response = self.session.post(f"{BASE_URL}/api/extension/ai-extract", json={
            "raw_text": nav_heavy_text,
            "page_url": "https://resdex.naukri.com/test"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        if data["success"]:
            profile = data["profile_data"]
            name = profile.get("name", "")
            
            # Name must not be navigation text
            nav_items = ["Home", "Dashboard", "Jobs", "Resdex", "Reports", "Search candidates", 
                        "Notifications", "Settings", "Next", "Prev", "Print", "Save for later"]
            
            for nav in nav_items:
                assert nav not in str(name), f"Name '{name}' should not contain nav item '{nav}'"
            
            print(f"✅ AI correctly extracted name without nav items: '{name}'")


class TestV36ExtensionDownload:
    """Test v3.6.0 extension download"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200
        self.token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_download_returns_zip_file(self):
        """Test GET /api/download/naukri-extension returns ZIP file"""
        response = self.session.get(f"{BASE_URL}/api/download/naukri-extension")
        
        assert response.status_code == 200, f"Download failed: {response.status_code}"
        
        # Verify it's a ZIP file (PK signature)
        assert response.content[:2] == b'PK', "Response is not a valid ZIP file"
        print(f"✅ Extension download returns valid ZIP ({len(response.content)} bytes)")
    
    def test_download_zip_contains_manifest(self):
        """Test downloaded ZIP contains manifest.json"""
        response = self.session.get(f"{BASE_URL}/api/download/naukri-extension")
        assert response.status_code == 200
        
        # Parse ZIP and check for manifest.json
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, 'r') as zip_file:
            file_list = zip_file.namelist()
            
            # Find manifest.json (may be in root or subdirectory)
            manifest_files = [f for f in file_list if f.endswith('manifest.json')]
            assert len(manifest_files) > 0, f"No manifest.json found in ZIP. Files: {file_list}"
            
            # Read manifest
            manifest_content = zip_file.read(manifest_files[0])
            manifest = json.loads(manifest_content)
            
            assert "version" in manifest, "Manifest missing version field"
            version = manifest["version"]
            print(f"✅ Extension ZIP contains manifest.json with version: {version}")


class TestV36Stats:
    """Test v3.6.0 stats endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200
        self.token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_stats_returns_capture_statistics(self):
        """Test GET /api/extension/stats returns capture statistics"""
        response = self.session.get(f"{BASE_URL}/api/extension/stats")
        
        assert response.status_code == 200, f"Stats failed: {response.text}"
        
        data = response.json()
        assert "total_captured" in data
        assert "user_captured" in data
        assert "today_captured" in data
        assert isinstance(data["total_captured"], int)
        print(f"✅ Stats: total={data['total_captured']}, user={data['user_captured']}, today={data['today_captured']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
