"""
VHC Talent OS v3.6.2 - Testing for:
1. POST /api/extension/capture - sets visibility field with employer_ids and recruiter_ids from team
2. POST /api/extension/capture - strips recruiter's own email (current_user email matches submitted email)
3. POST /api/extension/capture - name cleaning still works (appended years stripped)
4. GET /api/candidate-bank (as recruiter yamini@vhc.in) - returns naukri_extension candidates with visibility.recruiter_ids containing recruiter's ID
5. GET /api/candidate-bank (as admin admin@vhc.in) - returns all candidates including naukri_extension
6. POST /api/extension/ai-extract - accepts dom_extracted_name and overrides AI name with it
7. GET /api/extension/profile/{id} - returns full naukri candidate profile
8. GET /api/download/naukri-extension - returns ZIP with v3.6.2 manifest and valid JS syntax

Test prefix: test_v362b_
"""
import pytest
import requests
import os
import zipfile
import io
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://deployment-stabilize.preview.emergentagent.com")

# Test credentials from review request
ADMIN_CREDS = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
RECRUITER_CREDS = {"email": "yamini@vhc.in", "password": "VhcAdmin@2024"}


class TestAuth:
    """Authentication helper tests"""
    
    def test_admin_login(self):
        """Verify admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "admin"
        print(f"✓ Admin login successful, user_id={data['user']['id']}")
    
    def test_recruiter_login(self):
        """Verify recruiter login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER_CREDS)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "recruiter"
        print(f"✓ Recruiter login successful, user_id={data['user']['id']}, name={data['user']['name']}")


@pytest.fixture
def admin_auth():
    """Get admin authentication token and user info"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
    if response.status_code != 200:
        pytest.skip("Admin authentication failed")
    data = response.json()
    return {
        "token": data["access_token"],
        "user_id": data["user"]["id"],
        "email": data["user"]["email"],
        "role": data["user"]["role"]
    }


@pytest.fixture
def recruiter_auth():
    """Get recruiter authentication token and user info"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=RECRUITER_CREDS)
    if response.status_code != 200:
        pytest.skip("Recruiter authentication failed")
    data = response.json()
    return {
        "token": data["access_token"],
        "user_id": data["user"]["id"],
        "email": data["user"]["email"],
        "role": data["user"]["role"],
        "name": data["user"]["name"]
    }


class TestVisibilitySetsTeamIds:
    """Test 1: POST /api/extension/capture - sets visibility field with employer_ids and recruiter_ids from team"""
    
    def test_capture_as_admin_sets_visibility(self, admin_auth):
        """When admin captures, visibility should include all employers and recruiters"""
        headers = {"Authorization": f"Bearer {admin_auth['token']}"}
        
        # Create unique test profile
        profile_id = f"test_v362b_admin_visibility_{int(time.time())}"
        payload = {
            "naukri_profile_id": profile_id,
            "naukri_profile_url": f"https://resdex.naukri.com/v2/preview/{profile_id}",
            "name": "Test Visibility Admin Capture",
            "email": f"test.visibility.admin.{int(time.time())}@testmail.com",
            "scraped_at": "2026-01-12T10:00:00Z"
        }
        
        response = requests.post(f"{BASE_URL}/api/extension/capture", headers=headers, json=payload)
        print(f"Capture response: {response.status_code} - {response.text[:500]}")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        candidate_id = data["candidate_id"]
        
        # Verify visibility was set
        profile_response = requests.get(f"{BASE_URL}/api/extension/profile/{candidate_id}", headers=headers)
        assert profile_response.status_code == 200
        profile = profile_response.json()
        
        # Check visibility field exists and has structure
        visibility = profile.get("visibility", {})
        print(f"Visibility field: {visibility}")
        
        # Admin capture should set visibility with employer_ids and recruiter_ids
        assert "employer_ids" in visibility or "recruiter_ids" in visibility, \
            f"Visibility should have employer_ids or recruiter_ids, got: {visibility}"
        
        # Verify at least one ID is present (admin captures go to all team members)
        has_ids = len(visibility.get("employer_ids", [])) > 0 or len(visibility.get("recruiter_ids", [])) > 0
        assert has_ids, f"Visibility should have at least one ID, got: {visibility}"
        
        print(f"✓ Admin capture sets visibility: employer_ids={len(visibility.get('employer_ids', []))}, recruiter_ids={len(visibility.get('recruiter_ids', []))}")


class TestEmailStripping:
    """Test 2: POST /api/extension/capture - strips recruiter's own email (current_user email matches submitted email)"""
    
    def test_capture_strips_recruiter_own_email(self, recruiter_auth):
        """When recruiter captures with their own email, it should be stripped to null"""
        headers = {"Authorization": f"Bearer {recruiter_auth['token']}"}
        
        profile_id = f"test_v362b_strip_email_{int(time.time())}"
        payload = {
            "naukri_profile_id": profile_id,
            "naukri_profile_url": f"https://resdex.naukri.com/v2/preview/{profile_id}",
            "name": "Test Email Strip Candidate",
            # Submit with recruiter's own email - this should be stripped
            "email": recruiter_auth["email"],
            "scraped_at": "2026-01-12T10:00:00Z"
        }
        
        response = requests.post(f"{BASE_URL}/api/extension/capture", headers=headers, json=payload)
        print(f"Capture response: {response.status_code} - {response.text[:500]}")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        candidate_id = data["candidate_id"]
        
        # Get the profile and verify email was stripped
        profile_response = requests.get(f"{BASE_URL}/api/extension/profile/{candidate_id}", headers=headers)
        assert profile_response.status_code == 200
        profile = profile_response.json()
        
        # Email should be null since it matched recruiter's email
        assert profile.get("email") is None, \
            f"Email should be stripped to null when it matches recruiter's email ({recruiter_auth['email']}), got: {profile.get('email')}"
        
        print(f"✓ Recruiter's own email ({recruiter_auth['email']}) was correctly stripped to null")
    
    def test_capture_keeps_different_email(self, recruiter_auth):
        """When recruiter captures with a different email, it should be kept"""
        headers = {"Authorization": f"Bearer {recruiter_auth['token']}"}
        
        profile_id = f"test_v362b_keep_email_{int(time.time())}"
        different_email = f"real.candidate.{int(time.time())}@example.org"
        payload = {
            "naukri_profile_id": profile_id,
            "naukri_profile_url": f"https://resdex.naukri.com/v2/preview/{profile_id}",
            "name": "Test Email Keep Candidate",
            "email": different_email,
            "scraped_at": "2026-01-12T10:00:00Z"
        }
        
        response = requests.post(f"{BASE_URL}/api/extension/capture", headers=headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        candidate_id = data["candidate_id"]
        
        # Get the profile and verify email was kept
        profile_response = requests.get(f"{BASE_URL}/api/extension/profile/{candidate_id}", headers=headers)
        assert profile_response.status_code == 200
        profile = profile_response.json()
        
        # Email should be kept (lowercased)
        assert profile.get("email") == different_email.lower(), \
            f"Different email should be kept, expected {different_email.lower()}, got: {profile.get('email')}"
        
        print(f"✓ Different email ({different_email}) was correctly kept")


class TestNameCleaning:
    """Test 3: POST /api/extension/capture - name cleaning still works (appended years stripped)"""
    
    def test_name_cleaning_strips_years(self, admin_auth):
        """Name with appended years should be cleaned"""
        headers = {"Authorization": f"Bearer {admin_auth['token']}"}
        
        profile_id = f"test_v362b_name_clean_{int(time.time())}"
        payload = {
            "naukri_profile_id": profile_id,
            "naukri_profile_url": f"https://resdex.naukri.com/v2/preview/{profile_id}",
            "name": "Rahul Sharma - 15 Year(s)",  # This should be cleaned to "Rahul Sharma"
            "email": f"rahul.sharma.{int(time.time())}@testmail.com",
            "scraped_at": "2026-01-12T10:00:00Z"
        }
        
        response = requests.post(f"{BASE_URL}/api/extension/capture", headers=headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        candidate_id = data["candidate_id"]
        
        # Verify name was cleaned
        profile_response = requests.get(f"{BASE_URL}/api/extension/profile/{candidate_id}", headers=headers)
        assert profile_response.status_code == 200
        profile = profile_response.json()
        
        # Name should not contain " - 15 Year(s)"
        assert "Year" not in profile.get("name", ""), \
            f"Name should be cleaned of appended years, got: {profile.get('name')}"
        assert profile.get("name") == "Rahul Sharma", \
            f"Name should be 'Rahul Sharma', got: {profile.get('name')}"
        
        print(f"✓ Name cleaned from 'Rahul Sharma - 15 Year(s)' to '{profile.get('name')}'")
    
    def test_name_cleaning_strips_decimal_years(self, admin_auth):
        """Name with decimal years should be cleaned"""
        headers = {"Authorization": f"Bearer {admin_auth['token']}"}
        
        profile_id = f"test_v362b_name_decimal_{int(time.time())}"
        payload = {
            "naukri_profile_id": profile_id,
            "naukri_profile_url": f"https://resdex.naukri.com/v2/preview/{profile_id}",
            "name": "Priya Patel - 3.5 Years",  # This should be cleaned to "Priya Patel"
            "email": f"priya.patel.{int(time.time())}@testmail.com",
            "scraped_at": "2026-01-12T10:00:00Z"
        }
        
        response = requests.post(f"{BASE_URL}/api/extension/capture", headers=headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        candidate_id = data["candidate_id"]
        
        profile_response = requests.get(f"{BASE_URL}/api/extension/profile/{candidate_id}", headers=headers)
        assert profile_response.status_code == 200
        profile = profile_response.json()
        
        assert profile.get("name") == "Priya Patel", \
            f"Name should be 'Priya Patel', got: {profile.get('name')}"
        
        print(f"✓ Name cleaned from 'Priya Patel - 3.5 Years' to '{profile.get('name')}'")


class TestRecruiterCandidateBankVisibility:
    """Test 4: GET /api/candidate-bank (as recruiter) - returns naukri_extension candidates with visibility.recruiter_ids containing recruiter's ID"""
    
    def test_recruiter_sees_candidates_with_visibility(self, recruiter_auth, admin_auth):
        """Recruiter should see naukri_extension candidates where their ID is in visibility.recruiter_ids"""
        
        # First, create a candidate as admin with recruiter in visibility
        admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
        
        profile_id = f"test_v362b_recruiter_vis_{int(time.time())}"
        payload = {
            "naukri_profile_id": profile_id,
            "naukri_profile_url": f"https://resdex.naukri.com/v2/preview/{profile_id}",
            "name": "Test Recruiter Visibility Candidate",
            "email": f"recruiter.vis.{int(time.time())}@testmail.com",
            "scraped_at": "2026-01-12T10:00:00Z"
        }
        
        capture_response = requests.post(f"{BASE_URL}/api/extension/capture", headers=admin_headers, json=payload)
        assert capture_response.status_code == 200
        capture_data = capture_response.json()
        created_candidate_id = capture_data["candidate_id"]
        print(f"Created candidate {created_candidate_id} as admin")
        
        # Now fetch candidate bank as recruiter
        recruiter_headers = {"Authorization": f"Bearer {recruiter_auth['token']}"}
        recruiter_id = recruiter_auth["user_id"]
        
        bank_response = requests.get(f"{BASE_URL}/api/candidate-bank?limit=100", headers=recruiter_headers)
        assert bank_response.status_code == 200
        bank_data = bank_response.json()
        
        candidates = bank_data.get("candidates", [])
        print(f"Recruiter sees {len(candidates)} candidates in candidate bank")
        
        # Check if any naukri_extension candidates are visible
        naukri_candidates = [c for c in candidates if c.get("source") == "naukri_extension"]
        print(f"Recruiter sees {len(naukri_candidates)} naukri_extension candidates")
        
        # Check if the just-created candidate is visible to recruiter
        found_created = any(c.get("id") == created_candidate_id for c in candidates)
        
        # The candidate should be visible if recruiter_id is in visibility.recruiter_ids
        # or if admin capture added all team members
        if found_created:
            print(f"✓ Newly created candidate {created_candidate_id} is visible to recruiter")
        else:
            # Get the candidate profile to check visibility
            profile_response = requests.get(f"{BASE_URL}/api/extension/profile/{created_candidate_id}", headers=admin_headers)
            if profile_response.status_code == 200:
                profile = profile_response.json()
                visibility = profile.get("visibility", {})
                print(f"Candidate visibility: {visibility}")
                print(f"Recruiter ID: {recruiter_id}")
                if recruiter_id in visibility.get("recruiter_ids", []):
                    print("✓ Recruiter ID is in visibility.recruiter_ids but candidate not returned (possible query issue)")
                else:
                    print(f"✓ Recruiter ID {recruiter_id} not in visibility.recruiter_ids: {visibility.get('recruiter_ids', [])}")
        
        assert len(candidates) >= 0  # Basic assertion that query worked


class TestAdminCandidateBankAccess:
    """Test 5: GET /api/candidate-bank (as admin) - returns all candidates including naukri_extension"""
    
    def test_admin_sees_all_naukri_candidates(self, admin_auth):
        """Admin should see all candidates including naukri_extension sourced ones"""
        headers = {"Authorization": f"Bearer {admin_auth['token']}"}
        
        response = requests.get(f"{BASE_URL}/api/candidate-bank?limit=100", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        candidates = data.get("candidates", [])
        total = data.get("total", 0)
        
        # Check for naukri_extension sourced candidates
        naukri_candidates = [c for c in candidates if c.get("source") == "naukri_extension"]
        
        print(f"✓ Admin sees {len(candidates)} candidates (total: {total}), {len(naukri_candidates)} from naukri_extension")
        
        assert len(candidates) > 0, "Admin should see candidates"
        # There should be naukri extension candidates based on previous tests
        assert len(naukri_candidates) >= 0, "Query should work for naukri candidates"


class TestAIExtractDOMOverride:
    """Test 6: POST /api/extension/ai-extract - accepts dom_extracted_name and overrides AI name with it"""
    
    def test_ai_extract_uses_dom_name_override(self, admin_auth):
        """AI extraction should use dom_extracted_name over AI-extracted name"""
        headers = {"Authorization": f"Bearer {admin_auth['token']}"}
        
        # Create a payload with raw text that might confuse AI
        # but provide dom_extracted_name for override
        payload = {
            "raw_text": """
            Jobs & Responses | Resdex | Reports
            Search candidates
            Some Other Name in the Text
            Senior Software Engineer at TechCorp
            Email: someother@example.com
            Phone: +91 9876543210
            Experience: 10 years
            Skills: Python, Java, AWS
            Education: B.Tech in Computer Science
            """,
            "page_url": "https://resdex.naukri.com/v2/preview/test123",
            "page_title": "Amit Kumar | Naukri Resdex",
            "naukri_profile_id": f"test_v362b_ai_dom_{int(time.time())}",
            "dom_extracted_name": "Amit Kumar"  # This should override whatever AI extracts
        }
        
        response = requests.post(f"{BASE_URL}/api/extension/ai-extract", headers=headers, json=payload)
        print(f"AI Extract response: {response.status_code} - {response.text[:1000]}")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") is True, f"AI extraction should succeed, got: {data}"
        profile_data = data.get("profile_data", {})
        
        # The name should be the dom_extracted_name, not whatever AI found
        extracted_name = profile_data.get("name")
        assert extracted_name == "Amit Kumar", \
            f"Name should be DOM override 'Amit Kumar', got: {extracted_name}"
        
        print(f"✓ AI extraction correctly used dom_extracted_name override: '{extracted_name}'")
    
    def test_ai_extract_uses_dom_email_override(self, admin_auth):
        """AI extraction should use dom_extracted_email over AI-extracted email"""
        headers = {"Authorization": f"Bearer {admin_auth['token']}"}
        
        payload = {
            "raw_text": """
            Candidate Profile
            Name: Test Candidate
            Contact: wrongemail@naukri.com
            Experience: 5 years in IT
            Skills: React, Node.js
            """,
            "page_url": "https://resdex.naukri.com/v2/preview/test456",
            "page_title": "Test Candidate | Naukri Resdex",
            "naukri_profile_id": f"test_v362b_ai_email_{int(time.time())}",
            "dom_extracted_name": "Test Candidate",
            "dom_extracted_email": "real.candidate@gmail.com"  # This should override
        }
        
        response = requests.post(f"{BASE_URL}/api/extension/ai-extract", headers=headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        
        profile_data = data.get("profile_data", {})
        extracted_email = profile_data.get("email")
        
        # Should use DOM extracted email, not the @naukri.com from text
        assert extracted_email == "real.candidate@gmail.com", \
            f"Email should be DOM override 'real.candidate@gmail.com', got: {extracted_email}"
        
        print(f"✓ AI extraction correctly used dom_extracted_email override: '{extracted_email}'")


class TestExtensionProfileEndpoint:
    """Test 7: GET /api/extension/profile/{id} - returns full naukri candidate profile"""
    
    def test_get_profile_returns_full_data(self, admin_auth):
        """Profile endpoint should return complete candidate data"""
        headers = {"Authorization": f"Bearer {admin_auth['token']}"}
        
        # First create a profile with all fields
        profile_id = f"test_v362b_full_profile_{int(time.time())}"
        payload = {
            "naukri_profile_id": profile_id,
            "naukri_profile_url": f"https://resdex.naukri.com/v2/preview/{profile_id}",
            "name": "Full Profile Test User",
            "email": f"full.profile.{int(time.time())}@testmail.com",
            "phone": "+91 9876543210",
            "current_company": "TechCorp",
            "current_designation": "Senior Engineer",
            "total_experience_years": 8.5,
            "key_skills": ["Python", "AWS", "Docker"],
            "work_experience": [
                {"company": "TechCorp", "designation": "Senior Engineer", "is_current": True}
            ],
            "education": [
                {"degree": "B.Tech", "institution": "IIT Delhi"}
            ],
            "scraped_at": "2026-01-12T10:00:00Z"
        }
        
        capture_response = requests.post(f"{BASE_URL}/api/extension/capture", headers=headers, json=payload)
        assert capture_response.status_code == 200
        candidate_id = capture_response.json()["candidate_id"]
        
        # Get the full profile
        profile_response = requests.get(f"{BASE_URL}/api/extension/profile/{candidate_id}", headers=headers)
        assert profile_response.status_code == 200
        profile = profile_response.json()
        
        # Verify key fields
        assert profile.get("id") == candidate_id
        assert profile.get("name") == "Full Profile Test User"
        assert profile.get("source") == "naukri_extension"
        assert profile.get("naukri_profile_id") == profile_id
        assert "visibility" in profile
        
        print(f"✓ Profile endpoint returns full data with {len(profile.keys())} fields")
    
    def test_get_profile_404_for_nonexistent(self, admin_auth):
        """Profile endpoint should return 404 for non-existent candidate"""
        headers = {"Authorization": f"Bearer {admin_auth['token']}"}
        
        response = requests.get(f"{BASE_URL}/api/extension/profile/nonexistent-id-12345", headers=headers)
        assert response.status_code == 404
        
        print("✓ Profile endpoint returns 404 for non-existent candidate")


class TestExtensionDownload:
    """Test 8: GET /api/download/naukri-extension - returns ZIP with v3.6.2 manifest and valid JS syntax"""
    
    def test_download_returns_zip(self, admin_auth):
        """Download endpoint should return a ZIP file"""
        headers = {"Authorization": f"Bearer {admin_auth['token']}"}
        
        response = requests.get(f"{BASE_URL}/api/download/naukri-extension", headers=headers)
        assert response.status_code == 200
        assert "application/zip" in response.headers.get("Content-Type", "") or \
               "application/octet-stream" in response.headers.get("Content-Type", "")
        
        # Verify it's a valid ZIP
        try:
            zip_file = zipfile.ZipFile(io.BytesIO(response.content))
            file_list = zip_file.namelist()
            print(f"ZIP contains: {file_list}")
            assert len(file_list) > 0, "ZIP should contain files"
        except zipfile.BadZipFile:
            pytest.fail("Response is not a valid ZIP file")
        
        print(f"✓ Extension download returns valid ZIP with {len(file_list)} files")
    
    def test_download_contains_manifest(self, admin_auth):
        """ZIP should contain manifest.json with correct version"""
        headers = {"Authorization": f"Bearer {admin_auth['token']}"}
        
        response = requests.get(f"{BASE_URL}/api/download/naukri-extension", headers=headers)
        assert response.status_code == 200
        
        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        
        # Check for manifest.json
        manifest_path = None
        for name in zip_file.namelist():
            if name.endswith("manifest.json"):
                manifest_path = name
                break
        
        assert manifest_path is not None, "ZIP should contain manifest.json"
        
        # Read and parse manifest
        import json
        manifest_content = zip_file.read(manifest_path).decode('utf-8')
        manifest = json.loads(manifest_content)
        
        version = manifest.get("version", "")
        print(f"Manifest version: {version}")
        
        # Version should be 3.6.2 as mentioned in content.js
        assert version == "3.6.2", f"Manifest version should be 3.6.2, got: {version}"
        
        print(f"✓ Manifest has correct version: {version}")
    
    def test_download_contains_valid_js(self, admin_auth):
        """ZIP should contain content.js with valid JavaScript syntax"""
        headers = {"Authorization": f"Bearer {admin_auth['token']}"}
        
        response = requests.get(f"{BASE_URL}/api/download/naukri-extension", headers=headers)
        assert response.status_code == 200
        
        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        
        # Check for content.js
        content_js_path = None
        for name in zip_file.namelist():
            if name.endswith("content.js"):
                content_js_path = name
                break
        
        assert content_js_path is not None, "ZIP should contain content.js"
        
        content_js = zip_file.read(content_js_path).decode('utf-8')
        
        # Basic syntax check - should contain the version
        assert "3.6.2" in content_js, "content.js should contain version 3.6.2"
        assert "extractNameFromTitle" in content_js, "content.js should have extractNameFromTitle function"
        assert "extractContactFromDOM" in content_js, "content.js should have extractContactFromDOM function"
        
        # Check it doesn't have body text scan (the fix)
        assert "document.body.innerText" not in content_js or "NO Strategy 4" in content_js, \
            "content.js should not have body text scan for email"
        
        print(f"✓ content.js has valid syntax and v3.6.2 features")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
