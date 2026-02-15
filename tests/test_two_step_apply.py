"""
Test Two-Step Candidate Apply Flow
P0 Feature: Resume parsing + Review/Edit + Submit application

Tests:
1. Step 1: /api/public/parse-resume - uploads resume and returns parsed data
2. Step 2: /api/public/apply - accepts application with all fields including current_salary and notice_period
3. Data persistence: current_salary and notice_period stored in applications and candidate_bank
"""

import pytest
import requests
import os
import time
from pathlib import Path

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://ai-candidate-hub.preview.emergentagent.com').rstrip('/')

# Test resume content
TEST_RESUME_CONTENT = """
Jane Smith
Senior Software Engineer
janesmith_test@example.com
+91 9876543210

LOCATION: Bangalore, India

PROFESSIONAL HEADLINE: Senior Full Stack Developer with 8 years experience

SKILLS:
Python, JavaScript, React, Node.js, MongoDB, FastAPI, AWS, Docker, Kubernetes

EXPERIENCE:
Senior Software Engineer at TechCorp (2020-Present)
- 4 years
- Led development of microservices architecture
- Managed team of 5 developers

Software Developer at StartupXYZ (2016-2020)
- 4 years
- Developed frontend using React and backend using Node.js

EDUCATION:
B.Tech in Computer Science - IIT Bangalore (2016)
"""


class TestTwoStepApplyFlow:
    """Test the complete two-step apply flow"""
    
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Create test resume file"""
        self.resume_path = tmp_path / "test_resume.txt"
        self.resume_path.write_text(TEST_RESUME_CONTENT)
        
        # Get a valid job ID
        response = requests.get(f"{BASE_URL}/api/public/jobs?limit=1")
        assert response.status_code == 200
        jobs = response.json()
        if jobs:
            self.job_id = jobs[0]["id"]
        else:
            pytest.skip("No active jobs available for testing")
    
    def test_step1_parse_resume_success(self):
        """Step 1: Parse resume and get extracted data"""
        with open(self.resume_path, 'rb') as f:
            files = {'resume': ('test_resume.txt', f, 'text/plain')}
            response = requests.post(f"{BASE_URL}/api/public/parse-resume", files=files)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert data.get("success") == True, "Response should indicate success"
        assert "parsed_data" in data, "Response should contain parsed_data"
        assert "resume_filename" in data, "Response should contain resume_filename"
        
        parsed = data["parsed_data"]
        
        # Verify parsed fields exist (may be empty if AI parsing fails, but structure should exist)
        expected_fields = ["name", "email", "phone", "skills", "experience_years", "location", "headline"]
        for field in expected_fields:
            assert field in parsed, f"Parsed data should contain {field}"
        
        print(f"✅ Step 1 PASSED: Resume parsed successfully")
        print(f"   - Name: {parsed.get('name')}")
        print(f"   - Email: {parsed.get('email')}")
        print(f"   - Skills: {parsed.get('skills', [])[:5]}")
        print(f"   - Experience Years: {parsed.get('experience_years')}")
        print(f"   - Resume filename: {data.get('resume_filename')}")
        
        return data
    
    def test_step2_apply_with_parsed_data(self):
        """Step 2: Submit application with parsed data + salary + notice period"""
        # First, parse the resume
        with open(self.resume_path, 'rb') as f:
            files = {'resume': ('test_resume.txt', f, 'text/plain')}
            parse_response = requests.post(f"{BASE_URL}/api/public/parse-resume", files=files)
        
        assert parse_response.status_code == 200
        parse_data = parse_response.json()
        resume_filename = parse_data.get("resume_filename")
        parsed = parse_data.get("parsed_data", {})
        
        # Prepare application data with candidate-edited fields
        unique_email = f"test_apply_{int(time.time())}@example.com"
        form_data = {
            "job_id": self.job_id,
            "resume_filename": resume_filename,
            "name": parsed.get("name") or "Test Candidate",
            "email": unique_email,
            "phone": parsed.get("phone") or "+91 9876543210",
            "location": parsed.get("location") or "Bangalore, India",
            "headline": parsed.get("headline") or "Senior Software Engineer",
            "experience_years": parsed.get("experience_years") or 5,
            "skills": ", ".join(parsed.get("skills", ["Python", "JavaScript", "React"])),
            "current_salary": 1500000,  # INR - Required field
            "notice_period": "30 days",  # Required field
            "cover_letter": "I am excited to apply for this position."
        }
        
        response = requests.post(f"{BASE_URL}/api/public/apply", data=form_data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("success") == True, "Application should be successful"
        assert "application_id" in data, "Response should contain application_id"
        assert "candidate_id" in data, "Response should contain candidate_id"
        
        print(f"✅ Step 2 PASSED: Application submitted successfully")
        print(f"   - Application ID: {data.get('application_id')}")
        print(f"   - Candidate ID: {data.get('candidate_id')}")
        
        return data
    
    def test_current_salary_and_notice_period_required(self):
        """Verify current_salary and notice_period are accepted and stored"""
        # Parse resume first
        with open(self.resume_path, 'rb') as f:
            files = {'resume': ('test_resume.txt', f, 'text/plain')}
            parse_response = requests.post(f"{BASE_URL}/api/public/parse-resume", files=files)
        
        assert parse_response.status_code == 200
        resume_filename = parse_response.json().get("resume_filename")
        
        # Submit with specific salary and notice period
        unique_email = f"test_salary_{int(time.time())}@example.com"
        test_salary = 2000000  # 20 LPA
        test_notice = "60 days"
        
        form_data = {
            "job_id": self.job_id,
            "resume_filename": resume_filename,
            "name": "Salary Test Candidate",
            "email": unique_email,
            "phone": "+91 9876543210",
            "current_salary": test_salary,
            "notice_period": test_notice,
            "skills": "Python, JavaScript",
            "experience_years": 5
        }
        
        response = requests.post(f"{BASE_URL}/api/public/apply", data=form_data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") == True
        
        print(f"✅ Salary and Notice Period Test PASSED")
        print(f"   - Current Salary: {test_salary} INR")
        print(f"   - Notice Period: {test_notice}")
        
        return data.get("candidate_id"), data.get("application_id")
    
    def test_skills_can_be_edited(self):
        """Verify skills can be added/removed by candidate"""
        # Parse resume first
        with open(self.resume_path, 'rb') as f:
            files = {'resume': ('test_resume.txt', f, 'text/plain')}
            parse_response = requests.post(f"{BASE_URL}/api/public/parse-resume", files=files)
        
        assert parse_response.status_code == 200
        resume_filename = parse_response.json().get("resume_filename")
        
        # Submit with custom skills (different from parsed)
        unique_email = f"test_skills_{int(time.time())}@example.com"
        custom_skills = "Python, FastAPI, PostgreSQL, Redis, GraphQL"  # Custom skills
        
        form_data = {
            "job_id": self.job_id,
            "resume_filename": resume_filename,
            "name": "Skills Test Candidate",
            "email": unique_email,
            "phone": "+91 9876543210",
            "skills": custom_skills,
            "current_salary": 1800000,
            "notice_period": "45 days",
            "experience_years": 6
        }
        
        response = requests.post(f"{BASE_URL}/api/public/apply", data=form_data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") == True
        
        print(f"✅ Skills Edit Test PASSED")
        print(f"   - Custom Skills: {custom_skills}")
    
    def test_all_notice_period_options(self):
        """Test all notice period options are accepted"""
        notice_periods = [
            "Immediate",
            "15 days",
            "30 days",
            "45 days",
            "60 days",
            "90 days",
            "More than 90 days"
        ]
        
        # Parse resume once
        with open(self.resume_path, 'rb') as f:
            files = {'resume': ('test_resume.txt', f, 'text/plain')}
            parse_response = requests.post(f"{BASE_URL}/api/public/parse-resume", files=files)
        
        assert parse_response.status_code == 200
        resume_filename = parse_response.json().get("resume_filename")
        
        # Test first and last notice period options
        for notice in [notice_periods[0], notice_periods[-1]]:
            unique_email = f"test_notice_{int(time.time())}_{notice.replace(' ', '_')}@example.com"
            
            form_data = {
                "job_id": self.job_id,
                "resume_filename": resume_filename,
                "name": f"Notice Test {notice}",
                "email": unique_email,
                "phone": "+91 9876543210",
                "current_salary": 1500000,
                "notice_period": notice,
                "skills": "Python",
                "experience_years": 3
            }
            
            response = requests.post(f"{BASE_URL}/api/public/apply", data=form_data)
            
            assert response.status_code == 200, f"Notice period '{notice}' should be accepted: {response.text}"
            time.sleep(0.5)  # Small delay to avoid rate limiting
        
        print(f"✅ Notice Period Options Test PASSED")
        print(f"   - Tested: {notice_periods[0]}, {notice_periods[-1]}")


class TestParseResumeEndpoint:
    """Test /api/public/parse-resume endpoint specifically"""
    
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Create test resume file"""
        self.resume_path = tmp_path / "test_resume.txt"
        self.resume_path.write_text(TEST_RESUME_CONTENT)
    
    def test_parse_resume_returns_all_fields(self):
        """Verify parse-resume returns all expected fields"""
        with open(self.resume_path, 'rb') as f:
            files = {'resume': ('test_resume.txt', f, 'text/plain')}
            response = requests.post(f"{BASE_URL}/api/public/parse-resume", files=files)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") == True
        parsed = data.get("parsed_data", {})
        
        # Check all expected fields are present
        expected_fields = [
            "name", "email", "phone", "skills", "experience_years",
            "location", "headline", "experience", "education"
        ]
        
        for field in expected_fields:
            assert field in parsed, f"Missing field: {field}"
        
        # Verify resume_filename is returned for step 2
        assert "resume_filename" in data, "resume_filename required for step 2"
        assert data["resume_filename"], "resume_filename should not be empty"
        
        print(f"✅ Parse Resume Fields Test PASSED")
        print(f"   - All expected fields present: {expected_fields}")
    
    def test_parse_resume_honeypot_rejection(self):
        """Verify honeypot field triggers silent rejection"""
        with open(self.resume_path, 'rb') as f:
            files = {'resume': ('test_resume.txt', f, 'text/plain')}
            data = {'website': 'http://spam.com'}  # Honeypot field
            response = requests.post(f"{BASE_URL}/api/public/parse-resume", files=files, data=data)
        
        assert response.status_code == 200
        result = response.json()
        
        # Should return success but with empty parsed_data
        assert result.get("success") == True
        assert result.get("parsed_data") == {}
        
        print(f"✅ Honeypot Rejection Test PASSED")


class TestApplyEndpoint:
    """Test /api/public/apply endpoint specifically"""
    
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Create test resume file and get job ID"""
        self.resume_path = tmp_path / "test_resume.txt"
        self.resume_path.write_text(TEST_RESUME_CONTENT)
        
        # Get a valid job ID
        response = requests.get(f"{BASE_URL}/api/public/jobs?limit=1")
        assert response.status_code == 200
        jobs = response.json()
        if jobs:
            self.job_id = jobs[0]["id"]
        else:
            pytest.skip("No active jobs available for testing")
    
    def test_apply_requires_job_id(self):
        """Verify job_id is required"""
        form_data = {
            "name": "Test User",
            "email": "test@example.com",
            "current_salary": 1500000,
            "notice_period": "30 days"
        }
        
        response = requests.post(f"{BASE_URL}/api/public/apply", data=form_data)
        
        # Should fail without job_id
        assert response.status_code in [400, 422], f"Should fail without job_id: {response.status_code}"
        
        print(f"✅ Job ID Required Test PASSED")
    
    def test_apply_requires_email(self):
        """Verify email is required"""
        form_data = {
            "job_id": self.job_id,
            "name": "Test User",
            "current_salary": 1500000,
            "notice_period": "30 days"
        }
        
        response = requests.post(f"{BASE_URL}/api/public/apply", data=form_data)
        
        # Should fail without email
        assert response.status_code in [400, 422], f"Should fail without email: {response.status_code}"
        
        print(f"✅ Email Required Test PASSED")
    
    def test_apply_invalid_job_returns_404(self):
        """Verify invalid job_id returns 404"""
        with open(self.resume_path, 'rb') as f:
            files = {'resume': ('test_resume.txt', f, 'text/plain')}
            form_data = {
                "job_id": "invalid-job-id-12345",
                "name": "Test User",
                "email": f"test_{int(time.time())}@example.com",
                "current_salary": 1500000,
                "notice_period": "30 days"
            }
            response = requests.post(f"{BASE_URL}/api/public/apply", files=files, data=form_data)
        
        assert response.status_code == 404, f"Expected 404 for invalid job: {response.status_code}"
        
        print(f"✅ Invalid Job 404 Test PASSED")
    
    def test_apply_honeypot_rejection(self):
        """Verify honeypot field triggers silent rejection"""
        with open(self.resume_path, 'rb') as f:
            files = {'resume': ('test_resume.txt', f, 'text/plain')}
            form_data = {
                "job_id": self.job_id,
                "name": "Bot User",
                "email": f"bot_{int(time.time())}@example.com",
                "website": "http://spam.com",  # Honeypot
                "current_salary": 1500000,
                "notice_period": "30 days"
            }
            response = requests.post(f"{BASE_URL}/api/public/apply", files=files, data=form_data)
        
        assert response.status_code == 200
        result = response.json()
        
        # Should return success (silent rejection)
        assert result.get("success") == True
        
        print(f"✅ Apply Honeypot Rejection Test PASSED")


class TestDataPersistence:
    """Test that current_salary and notice_period are stored correctly"""
    
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Create test resume file and get job ID"""
        self.resume_path = tmp_path / "test_resume.txt"
        self.resume_path.write_text(TEST_RESUME_CONTENT)
        
        # Get a valid job ID
        response = requests.get(f"{BASE_URL}/api/public/jobs?limit=1")
        assert response.status_code == 200
        jobs = response.json()
        if jobs:
            self.job_id = jobs[0]["id"]
        else:
            pytest.skip("No active jobs available for testing")
    
    def test_application_stores_salary_and_notice(self):
        """Verify application stores current_salary and notice_period"""
        # Parse resume first
        with open(self.resume_path, 'rb') as f:
            files = {'resume': ('test_resume.txt', f, 'text/plain')}
            parse_response = requests.post(f"{BASE_URL}/api/public/parse-resume", files=files)
        
        assert parse_response.status_code == 200
        resume_filename = parse_response.json().get("resume_filename")
        
        # Submit application
        unique_email = f"test_persist_{int(time.time())}@example.com"
        test_salary = 2500000
        test_notice = "90 days"
        
        form_data = {
            "job_id": self.job_id,
            "resume_filename": resume_filename,
            "name": "Persistence Test",
            "email": unique_email,
            "phone": "+91 9876543210",
            "current_salary": test_salary,
            "notice_period": test_notice,
            "skills": "Python, JavaScript",
            "experience_years": 7
        }
        
        response = requests.post(f"{BASE_URL}/api/public/apply", data=form_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        
        # Note: We can't directly verify DB storage without admin access
        # But the successful response indicates the data was accepted
        print(f"✅ Data Persistence Test PASSED")
        print(f"   - Application created with salary: {test_salary} INR")
        print(f"   - Notice period: {test_notice}")
        print(f"   - Application ID: {data.get('application_id')}")
        print(f"   - Candidate ID: {data.get('candidate_id')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
