"""
VHC Talent OS - AI Matching Engine API Tests
Tests for Phase-2b AI-powered candidate-to-job matching using GPT-5.2

Endpoints tested:
- /api/ai/parse-jd - Parse job descriptions
- /api/ai/parse-resume - Parse resume files
- /api/matching/find-candidates - Match candidates to JD
- /api/candidate-bank/add - Add candidates via resume upload
- /api/candidate-bank - List candidates in data bank
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://seo-pillar.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "vhc@123"


class TestAuthAndSetup:
    """Authentication tests - run first to get tokens"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        return data["access_token"]
    
    def test_admin_login(self, admin_token):
        """Test admin login works"""
        assert admin_token is not None
        assert len(admin_token) > 20
        print(f"✅ Admin login successful, token: {admin_token[:30]}...")
    
    def test_admin_me_endpoint(self, admin_token):
        """Verify admin token works with /auth/me"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        print(f"✅ Admin user verified: {data['name']}")


class TestAIParseJD:
    """Tests for /api/ai/parse-jd endpoint - Job Description parsing"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token for AI endpoints"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        return response.json()["access_token"]
    
    def test_parse_jd_with_text(self, admin_token):
        """Test parsing JD from text input"""
        jd_text = """
        Senior Python Developer
        
        We are looking for a Senior Python Developer with 5+ years of experience.
        
        Requirements:
        - Python, Django, FastAPI
        - React or Vue.js frontend experience
        - PostgreSQL and MongoDB
        - AWS or GCP cloud experience
        - Docker and Kubernetes
        
        Location: Remote
        Salary: $120,000 - $160,000
        
        Responsibilities:
        - Design and implement scalable backend services
        - Lead code reviews and mentor junior developers
        - Collaborate with product team on feature development
        """
        
        response = requests.post(
            f"{BASE_URL}/api/ai/parse-jd",
            data={"jd_text": jd_text},
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=60  # AI calls can take time
        )
        
        assert response.status_code == 200, f"Parse JD failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert data.get("success") == True, f"Parse JD not successful: {data}"
        assert "parsed_data" in data, "No parsed_data in response"
        
        parsed = data["parsed_data"]
        print(f"✅ JD Parsed successfully. Title: {parsed.get('title')}")
        
        # Verify key fields are extracted
        assert "title" in parsed, "Missing title in parsed JD"
        assert "required_skills" in parsed, "Missing required_skills in parsed JD"
        assert isinstance(parsed.get("required_skills", []), list), "required_skills should be a list"
        
        # Verify skills were extracted
        skills = parsed.get("required_skills", [])
        print(f"   Extracted skills: {skills}")
        assert len(skills) > 0, "No skills extracted from JD"
    
    def test_parse_jd_empty_text_fails(self, admin_token):
        """Test that empty JD text returns error"""
        response = requests.post(
            f"{BASE_URL}/api/ai/parse-jd",
            data={"jd_text": ""},
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30
        )
        
        # Should return 400 for empty text
        assert response.status_code == 400, f"Expected 400 for empty JD, got {response.status_code}"
        print("✅ Empty JD text correctly rejected")
    
    def test_parse_jd_requires_auth(self):
        """Test that parse-jd requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/ai/parse-jd",
            data={"jd_text": "Test JD"},
            timeout=10
        )
        
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print("✅ Parse JD correctly requires authentication")


class TestAIParseResume:
    """Tests for /api/ai/parse-resume endpoint - Resume parsing"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        return response.json()["access_token"]
    
    def test_parse_resume_with_txt_file(self, admin_token):
        """Test parsing resume from TXT file"""
        resume_content = """
        Jane Doe
        Email: jane.doe@email.com
        Phone: 555-987-6543
        Location: San Francisco, CA
        
        PROFESSIONAL SUMMARY
        Full-stack developer with 6 years of experience in web application development.
        Specialized in Python, JavaScript, and cloud technologies.
        
        SKILLS
        Python, JavaScript, TypeScript, React, Node.js, Django, FastAPI, 
        PostgreSQL, MongoDB, Redis, AWS, Docker, Kubernetes, Git
        
        EXPERIENCE
        
        Senior Software Engineer - Stripe (2021-Present)
        - Built payment processing microservices handling $1B+ transactions
        - Led migration from monolith to microservices architecture
        - Mentored team of 4 junior developers
        
        Software Engineer - Airbnb (2018-2021)
        - Developed booking system features using Python and React
        - Implemented real-time notification system
        - Improved API response times by 40%
        
        EDUCATION
        BS Computer Science - UC Berkeley (2018)
        
        CERTIFICATIONS
        - AWS Solutions Architect
        - Google Cloud Professional
        """
        
        # Create a temporary file-like object
        files = {
            'file': ('test_resume.txt', resume_content, 'text/plain')
        }
        
        response = requests.post(
            f"{BASE_URL}/api/ai/parse-resume",
            files=files,
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=60
        )
        
        assert response.status_code == 200, f"Parse resume failed: {response.text}"
        data = response.json()
        
        assert data.get("success") == True, f"Parse resume not successful: {data}"
        assert "parsed_data" in data, "No parsed_data in response"
        
        parsed = data["parsed_data"]
        print(f"✅ Resume parsed successfully. Name: {parsed.get('name')}")
        
        # Verify key fields
        assert "name" in parsed, "Missing name in parsed resume"
        assert "skills" in parsed, "Missing skills in parsed resume"
        assert "experience" in parsed or "experience_years" in parsed, "Missing experience info"
        
        skills = parsed.get("skills", [])
        print(f"   Extracted skills: {skills[:5]}...")  # Show first 5
        assert len(skills) > 0, "No skills extracted from resume"
    
    def test_parse_resume_requires_file(self, admin_token):
        """Test that parse-resume requires a file"""
        response = requests.post(
            f"{BASE_URL}/api/ai/parse-resume",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10
        )
        
        # Should return 422 for missing file
        assert response.status_code == 422, f"Expected 422 for missing file, got {response.status_code}"
        print("✅ Parse resume correctly requires file upload")
    
    def test_parse_resume_requires_auth(self):
        """Test that parse-resume requires authentication"""
        files = {'file': ('test.txt', 'Test content', 'text/plain')}
        response = requests.post(
            f"{BASE_URL}/api/ai/parse-resume",
            files=files,
            timeout=10
        )
        
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print("✅ Parse resume correctly requires authentication")


class TestCandidateBank:
    """Tests for /api/candidate-bank endpoints"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        return response.json()["access_token"]
    
    def test_get_candidate_bank_list(self, admin_token):
        """Test listing candidates in data bank"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30
        )
        
        assert response.status_code == 200, f"Get candidate bank failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ Candidate bank retrieved. Count: {len(data)}")
        
        if len(data) > 0:
            candidate = data[0]
            # Verify candidate structure
            assert "id" in candidate, "Candidate missing id"
            assert "name" in candidate, "Candidate missing name"
            assert "email" in candidate, "Candidate missing email"
            print(f"   First candidate: {candidate.get('name')} ({candidate.get('email')})")
    
    def test_add_candidate_via_resume_upload(self, admin_token):
        """Test adding candidate to data bank via resume upload"""
        resume_content = f"""
        Test Candidate {int(time.time())}
        Email: test_candidate_{int(time.time())}@testbank.com
        Phone: 555-111-2222
        
        SKILLS
        Java, Spring Boot, Microservices, AWS, Docker
        
        EXPERIENCE
        Software Engineer - Amazon (2020-Present)
        - Built scalable services
        
        EDUCATION
        MS Computer Science - MIT (2020)
        """
        
        files = {
            'file': ('candidate_resume.txt', resume_content, 'text/plain')
        }
        
        response = requests.post(
            f"{BASE_URL}/api/candidate-bank/add",
            files=files,
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=60
        )
        
        assert response.status_code == 200, f"Add candidate failed: {response.text}"
        data = response.json()
        
        assert "action" in data, "Response missing action field"
        assert data["action"] in ["created", "updated"], f"Unexpected action: {data['action']}"
        assert "candidate_id" in data, "Response missing candidate_id"
        
        print(f"✅ Candidate added to bank. Action: {data['action']}, ID: {data['candidate_id']}")
        
        # Verify candidate appears in list
        list_response = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30
        )
        assert list_response.status_code == 200
        candidates = list_response.json()
        
        # Find the added candidate
        found = any(c["id"] == data["candidate_id"] for c in candidates)
        assert found, "Added candidate not found in candidate bank list"
        print("✅ Candidate verified in data bank list")
    
    def test_candidate_bank_requires_auth(self):
        """Test that candidate-bank requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            timeout=10
        )
        
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print("✅ Candidate bank correctly requires authentication")


class TestMatchingEngine:
    """Tests for /api/matching/* endpoints - AI-powered matching"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        return response.json()["access_token"]
    
    def test_find_candidates_with_jd_text(self, admin_token):
        """Test finding matching candidates using JD text"""
        match_request = {
            "jd_text": """
            Senior Python Developer
            
            Requirements:
            - 5+ years Python experience
            - Django or FastAPI
            - React frontend
            - AWS cloud experience
            - PostgreSQL database
            
            Location: Remote
            """
        }
        
        response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            json=match_request,
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            timeout=120  # AI matching can take time
        )
        
        assert response.status_code == 200, f"Find candidates failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list of match results"
        print(f"✅ Matching completed. Found {len(data)} candidates")
        
        if len(data) > 0:
            match = data[0]
            # Verify match result structure
            assert "candidate_id" in match, "Match missing candidate_id"
            assert "candidate_name" in match, "Match missing candidate_name"
            assert "score" in match, "Match missing score"
            assert "explanation" in match, "Match missing explanation"
            
            print(f"   Top match: {match.get('candidate_name')} - Score: {match.get('score')}")
            print(f"   Explanation: {match.get('explanation', '')[:100]}...")
            
            # Verify score is in valid range
            assert 0 <= match["score"] <= 100, f"Invalid score: {match['score']}"
    
    def test_find_candidates_with_filters(self, admin_token):
        """Test finding candidates with must-have filters"""
        match_request = {
            "jd_text": "Python Developer with AWS experience",
            "min_experience": 3,
            "must_have_skills": ["Python"]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            json=match_request,
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            timeout=120
        )
        
        assert response.status_code == 200, f"Find candidates with filters failed: {response.text}"
        data = response.json()
        
        print(f"✅ Filtered matching completed. Found {len(data)} candidates")
        
        # Check that filtered_out candidates are marked
        for match in data:
            if match.get("filtered_out"):
                assert "filter_reason" in match, "Filtered candidate missing filter_reason"
                print(f"   Filtered out: {match.get('candidate_name')} - Reason: {match.get('filter_reason')}")
    
    def test_find_candidates_requires_jd(self, admin_token):
        """Test that find-candidates requires job description"""
        response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            json={},  # Empty request
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            timeout=30
        )
        
        # Should return 400 for missing JD
        assert response.status_code == 400, f"Expected 400 for missing JD, got {response.status_code}"
        print("✅ Find candidates correctly requires JD text or job_id")
    
    def test_find_candidates_requires_auth(self):
        """Test that find-candidates requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            json={"jd_text": "Test JD"},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print("✅ Find candidates correctly requires authentication")


class TestJobsEndpoint:
    """Tests for /api/jobs endpoint - needed for matching with job_id"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        return response.json()["access_token"]
    
    def test_get_jobs_list(self, admin_token):
        """Test getting list of jobs"""
        response = requests.get(
            f"{BASE_URL}/api/jobs",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30
        )
        
        assert response.status_code == 200, f"Get jobs failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ Jobs retrieved. Count: {len(data)}")
        
        if len(data) > 0:
            job = data[0]
            assert "id" in job, "Job missing id"
            assert "title" in job, "Job missing title"
            print(f"   First job: {job.get('title')}")
    
    def test_browse_jobs_public(self):
        """Test public job browsing endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/jobs/browse",
            timeout=30
        )
        
        assert response.status_code == 200, f"Browse jobs failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ Public job browse works. Active jobs: {len(data)}")


class TestAdminDashboard:
    """Tests for admin dashboard functionality"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        return response.json()["access_token"]
    
    def test_admin_stats(self, admin_token):
        """Test admin dashboard stats endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/stats/admin",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30
        )
        
        assert response.status_code == 200, f"Admin stats failed: {response.text}"
        data = response.json()
        
        # Verify required stats fields
        required_fields = ["total_users", "total_jobs", "total_applications", "total_companies"]
        for field in required_fields:
            assert field in data, f"Missing stat field: {field}"
        
        print(f"✅ Admin stats retrieved:")
        print(f"   Users: {data.get('total_users')}")
        print(f"   Jobs: {data.get('total_jobs')}")
        print(f"   Applications: {data.get('total_applications')}")
        print(f"   Companies: {data.get('total_companies')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
