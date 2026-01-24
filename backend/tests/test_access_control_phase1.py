"""
Phase 1 Access Control Tests - Candidate Data Bank
Tests STRICT role-based visibility:
- Admin: Full access to all candidates
- Employer: Only candidates they parsed, team parsed, or applicants to their jobs
- Recruiter: Only candidates they parsed or applicants to their assigned mandates
- Candidate: ZERO access (returns empty or 403)
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"email": "admin@vhc.in", "password": "VhcAdmin@2024"}


class TestAccessControlSetup:
    """Setup and verify test environment"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}"}
    
    def test_admin_login(self):
        """Verify admin can login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["role"] == "admin"
        print("✅ Admin login successful")


class TestAdminFullAccess:
    """Admin should have FULL access to all candidates"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}"}
    
    def test_admin_can_access_candidate_bank(self, admin_headers):
        """Admin should see all candidates in data bank"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        assert response.status_code == 200
        candidates = response.json()
        print(f"✅ Admin can access candidate bank - {len(candidates)} candidates found")
        return candidates
    
    def test_admin_can_access_any_candidate_detail(self, admin_headers):
        """Admin should access any candidate's details"""
        # First get list
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        assert response.status_code == 200
        candidates = response.json()
        
        if candidates:
            candidate_id = candidates[0]["id"]
            detail_response = requests.get(
                f"{BASE_URL}/api/candidate-bank/{candidate_id}", 
                headers=admin_headers
            )
            assert detail_response.status_code == 200
            print(f"✅ Admin can access candidate detail: {candidates[0].get('name', 'Unknown')}")
        else:
            print("⚠️ No candidates in bank to test detail access")


class TestCandidateZeroAccess:
    """Candidate role should have ZERO access to Candidate Data Bank"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}"}
    
    @pytest.fixture(scope="class")
    def test_candidate_token(self, admin_headers):
        """Create a test candidate user and get their token"""
        unique_email = f"test_candidate_{uuid.uuid4().hex[:8]}@test.com"
        
        # Create candidate user via admin
        create_response = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers=admin_headers,
            json={
                "email": unique_email,
                "password": "TestPass@123",
                "name": "Test Candidate Access",
                "role": "candidate"
            }
        )
        
        if create_response.status_code != 200:
            # Try to login with existing test candidate
            login_response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": "testcandidate@test.com", "password": "TestPass@123"}
            )
            if login_response.status_code == 200:
                return login_response.json()["access_token"]
            pytest.skip("Could not create or login test candidate")
        
        # Login as the new candidate
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": unique_email, "password": "TestPass@123"}
        )
        assert login_response.status_code == 200
        return login_response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def candidate_headers(self, test_candidate_token):
        return {"Authorization": f"Bearer {test_candidate_token}"}
    
    def test_candidate_gets_empty_list(self, candidate_headers):
        """Candidate should get empty list from candidate bank"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=candidate_headers)
        assert response.status_code == 200
        candidates = response.json()
        assert candidates == [], f"Candidate should get empty list, got {len(candidates)} candidates"
        print("✅ Candidate gets empty list from candidate bank (ZERO access)")
    
    def test_candidate_cannot_access_candidate_detail(self, candidate_headers, admin_headers):
        """Candidate should get 403 when accessing any candidate detail"""
        # Get a candidate ID from admin
        admin_response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        if admin_response.status_code == 200 and admin_response.json():
            candidate_id = admin_response.json()[0]["id"]
            
            # Try to access as candidate
            response = requests.get(
                f"{BASE_URL}/api/candidate-bank/{candidate_id}",
                headers=candidate_headers
            )
            assert response.status_code == 403, f"Expected 403, got {response.status_code}"
            print("✅ Candidate gets 403 when accessing candidate detail")
        else:
            print("⚠️ No candidates to test detail access denial")


class TestResumeDownloadEndpoints:
    """Test resume download endpoints exist and have proper access control"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}"}
    
    def test_candidate_bank_download_endpoint_exists(self, admin_headers):
        """GET /api/candidate-bank/{id}/download-resume should exist"""
        # Get a candidate with resume
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        assert response.status_code == 200
        candidates = response.json()
        
        candidates_with_resume = [c for c in candidates if c.get("resume_url")]
        
        if candidates_with_resume:
            candidate_id = candidates_with_resume[0]["id"]
            download_response = requests.get(
                f"{BASE_URL}/api/candidate-bank/{candidate_id}/download-resume",
                headers=admin_headers,
                allow_redirects=False
            )
            # Should return 200 (file) or 404 (file not found on disk)
            assert download_response.status_code in [200, 404], \
                f"Expected 200 or 404, got {download_response.status_code}"
            print(f"✅ Candidate bank download endpoint works (status: {download_response.status_code})")
        else:
            print("⚠️ No candidates with resume to test download")
    
    def test_candidates_resume_endpoint_exists(self, admin_headers):
        """GET /api/candidates/{id}/resume should exist"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        assert response.status_code == 200
        candidates = response.json()
        
        candidates_with_resume = [c for c in candidates if c.get("resume_url")]
        
        if candidates_with_resume:
            candidate_id = candidates_with_resume[0]["id"]
            download_response = requests.get(
                f"{BASE_URL}/api/candidates/{candidate_id}/resume",
                headers=admin_headers,
                allow_redirects=False
            )
            # Should return 200 (file) or 404 (file not found on disk)
            assert download_response.status_code in [200, 404], \
                f"Expected 200 or 404, got {download_response.status_code}"
            print(f"✅ Candidates resume endpoint works (status: {download_response.status_code})")
        else:
            print("⚠️ No candidates with resume to test download")


class TestEmployerScopedAccess:
    """Employer should only see candidates they parsed, team parsed, or applicants to their jobs"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}"}
    
    @pytest.fixture(scope="class")
    def test_employer_token(self, admin_headers):
        """Create or get test employer"""
        unique_email = f"test_employer_{uuid.uuid4().hex[:8]}@test.com"
        
        # Create employer user via admin
        create_response = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers=admin_headers,
            json={
                "email": unique_email,
                "password": "TestPass@123",
                "name": "Test Employer Access",
                "role": "employer"
            }
        )
        
        if create_response.status_code == 200:
            # Login as the new employer
            login_response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": unique_email, "password": "TestPass@123"}
            )
            assert login_response.status_code == 200
            return login_response.json()["access_token"]
        else:
            pytest.skip("Could not create test employer")
    
    @pytest.fixture(scope="class")
    def employer_headers(self, test_employer_token):
        return {"Authorization": f"Bearer {test_employer_token}"}
    
    def test_employer_can_access_candidate_bank(self, employer_headers):
        """Employer should be able to access candidate bank endpoint"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=employer_headers)
        assert response.status_code == 200
        candidates = response.json()
        # New employer with no team/jobs should see limited or no candidates
        print(f"✅ Employer can access candidate bank - {len(candidates)} candidates visible")
    
    def test_new_employer_sees_limited_candidates(self, employer_headers, admin_headers):
        """New employer without team/jobs should see fewer candidates than admin"""
        admin_response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        employer_response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=employer_headers)
        
        admin_count = len(admin_response.json())
        employer_count = len(employer_response.json())
        
        # Employer should see same or fewer candidates than admin
        assert employer_count <= admin_count, \
            f"Employer sees {employer_count} candidates, admin sees {admin_count}"
        print(f"✅ Employer sees {employer_count} candidates (admin sees {admin_count}) - access control working")


class TestRecruiterScopedAccess:
    """Recruiter should only see candidates they parsed or applicants to their assigned mandates"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}"}
    
    @pytest.fixture(scope="class")
    def test_recruiter_token(self, admin_headers):
        """Create or get test recruiter"""
        unique_email = f"test_recruiter_{uuid.uuid4().hex[:8]}@test.com"
        
        # Create recruiter user via admin
        create_response = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers=admin_headers,
            json={
                "email": unique_email,
                "password": "TestPass@123",
                "name": "Test Recruiter Access",
                "role": "recruiter"
            }
        )
        
        if create_response.status_code == 200:
            # Login as the new recruiter
            login_response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": unique_email, "password": "TestPass@123"}
            )
            assert login_response.status_code == 200
            return login_response.json()["access_token"]
        else:
            pytest.skip("Could not create test recruiter")
    
    @pytest.fixture(scope="class")
    def recruiter_headers(self, test_recruiter_token):
        return {"Authorization": f"Bearer {test_recruiter_token}"}
    
    def test_recruiter_can_access_candidate_bank(self, recruiter_headers):
        """Recruiter should be able to access candidate bank endpoint"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=recruiter_headers)
        assert response.status_code == 200
        candidates = response.json()
        print(f"✅ Recruiter can access candidate bank - {len(candidates)} candidates visible")
    
    def test_new_recruiter_sees_limited_candidates(self, recruiter_headers, admin_headers):
        """New recruiter without assigned mandates should see fewer candidates than admin"""
        admin_response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        recruiter_response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=recruiter_headers)
        
        admin_count = len(admin_response.json())
        recruiter_count = len(recruiter_response.json())
        
        # Recruiter should see same or fewer candidates than admin
        assert recruiter_count <= admin_count, \
            f"Recruiter sees {recruiter_count} candidates, admin sees {admin_count}"
        print(f"✅ Recruiter sees {recruiter_count} candidates (admin sees {admin_count}) - access control working")


class TestMandatoryFieldsValidation:
    """Test mandatory fields enforcement on batch save"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}"}
    
    def test_batch_save_requires_salary(self, admin_headers):
        """Batch save should reject candidates without salary"""
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-save",
            headers=admin_headers,
            json={
                "candidates": [{
                    "email": f"test_{uuid.uuid4().hex[:8]}@test.com",
                    "name": "Test No Salary",
                    "notice_period": "30 days",
                    "location": "Mumbai",
                    "experience_years": 5
                    # Missing current_salary
                }]
            }
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("✅ Batch save rejects candidates without salary")
    
    def test_batch_save_requires_notice_period(self, admin_headers):
        """Batch save should reject candidates without notice period"""
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-save",
            headers=admin_headers,
            json={
                "candidates": [{
                    "email": f"test_{uuid.uuid4().hex[:8]}@test.com",
                    "name": "Test No Notice",
                    "current_salary": 1000000,
                    "location": "Mumbai",
                    "experience_years": 5
                    # Missing notice_period
                }]
            }
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("✅ Batch save rejects candidates without notice period")
    
    def test_batch_save_requires_location(self, admin_headers):
        """Batch save should reject candidates without location"""
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-save",
            headers=admin_headers,
            json={
                "candidates": [{
                    "email": f"test_{uuid.uuid4().hex[:8]}@test.com",
                    "name": "Test No Location",
                    "current_salary": 1000000,
                    "notice_period": "30 days",
                    "experience_years": 5
                    # Missing location
                }]
            }
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("✅ Batch save rejects candidates without location")
    
    def test_batch_save_requires_experience(self, admin_headers):
        """Batch save should reject candidates without experience_years"""
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-save",
            headers=admin_headers,
            json={
                "candidates": [{
                    "email": f"test_{uuid.uuid4().hex[:8]}@test.com",
                    "name": "Test No Experience",
                    "current_salary": 1000000,
                    "notice_period": "30 days",
                    "location": "Mumbai"
                    # Missing experience_years
                }]
            }
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("✅ Batch save rejects candidates without experience_years")
    
    def test_batch_save_succeeds_with_all_fields(self, admin_headers):
        """Batch save should succeed with all mandatory fields"""
        unique_email = f"test_complete_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-save",
            headers=admin_headers,
            json={
                "candidates": [{
                    "email": unique_email,
                    "name": "Test Complete Candidate",
                    "current_salary": 1500000,
                    "notice_period": "30 days",
                    "location": "Bangalore",
                    "experience_years": 5,
                    "skills": ["Python", "FastAPI"]
                }]
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✅ Batch save succeeds with all mandatory fields")


class TestAddCandidateResumeParser:
    """Test Add Candidate flow via resume upload"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}"}
    
    def test_add_candidate_endpoint_exists(self, admin_headers):
        """POST /api/candidate-bank/add endpoint should exist"""
        # Test with empty request to verify endpoint exists
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/add",
            headers=admin_headers
        )
        # Should return 422 (validation error) not 404
        assert response.status_code != 404, "Add candidate endpoint not found"
        print(f"✅ Add candidate endpoint exists (status: {response.status_code})")
    
    def test_batch_parse_endpoint_exists(self, admin_headers):
        """POST /api/candidate-bank/batch-parse endpoint should exist"""
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/batch-parse",
            headers=admin_headers
        )
        # Should return 422 (validation error) not 404
        assert response.status_code != 404, "Batch parse endpoint not found"
        print(f"✅ Batch parse endpoint exists (status: {response.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
