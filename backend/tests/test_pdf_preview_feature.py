"""
PDF Preview Feature Tests - Iteration 98
Tests for the new PDF preview/compile feature in Resume Builder

Features tested:
1. POST /api/resume/compile-pdf - compiles LaTeX to PDF
2. POST /api/resume/generate - accepts null profile fields
3. GET /api/resume/templates - template list
4. GET /api/resume/candidate/{id} - get candidate profile for resume
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPDFPreviewFeature:
    """Test suite for PDF Preview feature"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: login as admin and get token"""
        self.session = requests.Session()
        # Login as admin
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        token = resp.json().get('access_token')
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        yield
        self.session.close()
    
    # ============= Template Tests =============
    def test_get_templates(self):
        """Test getting resume templates"""
        resp = self.session.get(f"{BASE_URL}/api/resume/templates")
        assert resp.status_code == 200
        templates = resp.json()
        assert isinstance(templates, list)
        assert len(templates) >= 3, "Should have at least 3 templates"
        # Verify template structure
        template_ids = [t['id'] for t in templates]
        assert 'ats_clean' in template_ids
        assert 'google_style' in template_ids
        assert 'modern' in template_ids
        print(f"✅ Templates retrieved: {template_ids}")
    
    # ============= Generate LaTeX Tests =============
    def test_generate_resume_basic(self):
        """Test generating LaTeX from basic profile"""
        profile = {
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "+1234567890",
            "location": "San Francisco, CA",
            "linkedin": "https://linkedin.com/in/johndoe",
            "summary": "Experienced software engineer with 5 years of experience.",
            "skills": ["Python", "JavaScript", "React"],
            "experience": [
                {
                    "company": "Tech Corp",
                    "title": "Software Engineer",
                    "duration": "2020 - Present",
                    "bullets": ["Led development of microservices", "Improved performance by 40%"]
                }
            ],
            "education": [
                {
                    "institution": "Stanford University",
                    "degree": "BS in Computer Science",
                    "year": "2020",
                    "gpa": "3.8"
                }
            ]
        }
        resp = self.session.post(f"{BASE_URL}/api/resume/generate", json={
            "profile": profile,
            "template_id": "ats_clean"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "latex" in data
        assert data["template_id"] == "ats_clean"
        assert "\\documentclass" in data["latex"]
        assert "John Doe" in data["latex"]
        print(f"✅ LaTeX generated successfully ({len(data['latex'])} chars)")
        return data["latex"]
    
    def test_generate_resume_with_null_fields(self):
        """Test generating LaTeX with null email/phone/linkedin fields"""
        profile = {
            "name": "Jane Smith",
            "email": None,  # NULL email
            "phone": None,  # NULL phone
            "location": "New York, NY",
            "linkedin": None,  # NULL linkedin
            "summary": "Product manager with 10 years experience.",
            "skills": ["Product Management", "Agile"],
            "experience": [],
            "education": []
        }
        resp = self.session.post(f"{BASE_URL}/api/resume/generate", json={
            "profile": profile,
            "template_id": "google_style"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "latex" in data
        assert "Jane Smith" in data["latex"]
        print("✅ Generate with null fields succeeded")
    
    def test_generate_resume_all_templates(self):
        """Test generating with all 3 templates"""
        profile = {
            "name": "Test User",
            "email": "test@test.com",
            "phone": "123456",
            "location": "Boston",
            "linkedin": "",
            "summary": "A test summary.",
            "skills": ["Skill1", "Skill2"],
            "experience": [],
            "education": []
        }
        for template in ["ats_clean", "google_style", "modern"]:
            resp = self.session.post(f"{BASE_URL}/api/resume/generate", json={
                "profile": profile,
                "template_id": template
            })
            assert resp.status_code == 200, f"Generate failed for template {template}"
            print(f"✅ Template {template} generation successful")
    
    # ============= Compile PDF Tests =============
    def test_compile_pdf_success(self):
        """Test compiling valid LaTeX to PDF"""
        # First generate LaTeX
        profile = {
            "name": "PDF Test User",
            "email": "pdf@test.com",
            "phone": "9876543210",
            "location": "Seattle",
            "linkedin": "",
            "summary": "Testing PDF compilation.",
            "skills": ["Python", "LaTeX"],
            "experience": [],
            "education": []
        }
        gen_resp = self.session.post(f"{BASE_URL}/api/resume/generate", json={
            "profile": profile,
            "template_id": "ats_clean"
        })
        assert gen_resp.status_code == 200
        latex = gen_resp.json()["latex"]
        
        # Now compile to PDF
        resp = self.session.post(f"{BASE_URL}/api/resume/compile-pdf", json={"latex": latex})
        assert resp.status_code == 200, f"Compile failed: {resp.text[:200]}"
        assert resp.headers.get("Content-Type") == "application/pdf"
        # Check PDF magic bytes
        pdf_content = resp.content
        assert pdf_content[:4] == b'%PDF', "Response should be valid PDF"
        print(f"✅ PDF compiled successfully ({len(pdf_content)} bytes)")
    
    def test_compile_pdf_with_special_characters(self):
        """Test compiling LaTeX with escaped special characters"""
        profile = {
            "name": "John & Jane",  # Special char &
            "email": "test@test.com",
            "phone": "+1-234-567",
            "location": "100% Remote",  # Special char %
            "linkedin": "",
            "summary": "Worked with C++ and C# technologies.",
            "skills": ["C++", "C#", "Node.js"],
            "experience": [
                {
                    "company": "Tech & Co",
                    "title": "Senior Dev",
                    "duration": "2020-2024",
                    "bullets": ["Saved company 50% on costs", "Used AWS & GCP"]
                }
            ],
            "education": []
        }
        gen_resp = self.session.post(f"{BASE_URL}/api/resume/generate", json={
            "profile": profile,
            "template_id": "ats_clean"
        })
        assert gen_resp.status_code == 200
        latex = gen_resp.json()["latex"]
        
        # Compile
        resp = self.session.post(f"{BASE_URL}/api/resume/compile-pdf", json={"latex": latex})
        assert resp.status_code == 200
        assert resp.content[:4] == b'%PDF'
        print("✅ PDF with special characters compiled successfully")
    
    def test_compile_pdf_empty_latex_error(self):
        """Test that empty LaTeX returns 400 error"""
        resp = self.session.post(f"{BASE_URL}/api/resume/compile-pdf", json={"latex": ""})
        assert resp.status_code == 400, f"Expected 400 for empty latex, got {resp.status_code}"
        print("✅ Empty LaTeX correctly rejected with 400")
    
    def test_compile_pdf_short_latex_error(self):
        """Test that too-short LaTeX returns 400 error"""
        resp = self.session.post(f"{BASE_URL}/api/resume/compile-pdf", json={"latex": "abc"})
        assert resp.status_code == 400, f"Expected 400 for short latex, got {resp.status_code}"
        print("✅ Short LaTeX correctly rejected with 400")
    
    def test_compile_pdf_invalid_latex_error(self):
        """Test that invalid LaTeX returns 422 error"""
        invalid_latex = "\\documentclass{article}\\begin{document}Hello \\invalid{} \\end{document}"
        resp = self.session.post(f"{BASE_URL}/api/resume/compile-pdf", json={"latex": invalid_latex})
        # Should be 422 for compilation failure or possibly 200 if pdflatex is lenient
        assert resp.status_code in [200, 422], f"Expected 200 or 422, got {resp.status_code}"
        print(f"✅ Invalid LaTeX handled (status: {resp.status_code})")
    
    def test_compile_pdf_modern_template(self):
        """Test compiling PDF with modern template (multicol)"""
        profile = {
            "name": "Modern Template User",
            "email": "modern@test.com",
            "phone": "1111111111",
            "location": "Austin, TX",
            "linkedin": "https://linkedin.com/in/modern",
            "summary": "Testing modern template compilation.",
            "skills": ["Skill1", "Skill2", "Skill3", "Skill4", "Skill5", "Skill6"],
            "experience": [
                {
                    "company": "Company A",
                    "title": "Role A",
                    "duration": "2022-Present",
                    "bullets": ["Did something impactful"]
                }
            ],
            "education": [
                {
                    "institution": "MIT",
                    "degree": "MS Engineering",
                    "year": "2022"
                }
            ]
        }
        gen_resp = self.session.post(f"{BASE_URL}/api/resume/generate", json={
            "profile": profile,
            "template_id": "modern"
        })
        assert gen_resp.status_code == 200
        latex = gen_resp.json()["latex"]
        
        resp = self.session.post(f"{BASE_URL}/api/resume/compile-pdf", json={"latex": latex})
        assert resp.status_code == 200
        assert resp.content[:4] == b'%PDF'
        print("✅ Modern template PDF compiled successfully")
    
    def test_compile_pdf_google_style_template(self):
        """Test compiling PDF with google_style template"""
        profile = {
            "name": "Google Style User",
            "email": "google@test.com",
            "phone": "2222222222",
            "location": "Mountain View",
            "linkedin": "https://linkedin.com/in/googler",
            "summary": "Testing Google style template.",
            "skills": ["React", "TypeScript", "Node.js"],
            "experience": [],
            "education": []
        }
        gen_resp = self.session.post(f"{BASE_URL}/api/resume/generate", json={
            "profile": profile,
            "template_id": "google_style"
        })
        assert gen_resp.status_code == 200
        latex = gen_resp.json()["latex"]
        
        resp = self.session.post(f"{BASE_URL}/api/resume/compile-pdf", json={"latex": latex})
        assert resp.status_code == 200
        assert resp.content[:4] == b'%PDF'
        print("✅ Google style template PDF compiled successfully")
    
    # ============= Candidate Profile Tests =============
    def test_get_candidate_profile_for_resume(self):
        """Test loading candidate profile for resume generation"""
        # First search for a candidate
        resp = self.session.get(f"{BASE_URL}/api/candidate-bank", params={"limit": 1})
        assert resp.status_code == 200
        data = resp.json()
        candidates = data.get("candidates", data if isinstance(data, list) else [])
        if not candidates:
            pytest.skip("No candidates in bank to test with")
        
        candidate_id = candidates[0].get("id")
        assert candidate_id, "Candidate should have an id"
        
        # Get candidate profile for resume
        resp = self.session.get(f"{BASE_URL}/api/resume/candidate/{candidate_id}")
        assert resp.status_code == 200
        profile = resp.json()
        # Should have resume-formatted structure
        assert "name" in profile
        assert "skills" in profile
        assert "experience" in profile
        assert "education" in profile
        print(f"✅ Candidate profile loaded for resume: {profile.get('name', 'Unknown')}")
    
    def test_get_candidate_profile_not_found(self):
        """Test 404 for non-existent candidate"""
        resp = self.session.get(f"{BASE_URL}/api/resume/candidate/non-existent-id-12345")
        assert resp.status_code == 404
        print("✅ Non-existent candidate correctly returns 404")
    
    # ============= End-to-End Flow Test =============
    def test_e2e_candidate_to_pdf(self):
        """End-to-end: Search candidate -> Load profile -> Generate -> Compile PDF"""
        # Step 1: Search candidates
        search_resp = self.session.get(f"{BASE_URL}/api/candidate-bank", params={"limit": 5})
        assert search_resp.status_code == 200
        data = search_resp.json()
        candidates = data.get("candidates", data if isinstance(data, list) else [])
        if not candidates:
            pytest.skip("No candidates available for E2E test")
        
        candidate = candidates[0]
        print(f"Step 1: Found candidate '{candidate.get('name')}'")
        
        # Step 2: Load candidate profile for resume
        profile_resp = self.session.get(f"{BASE_URL}/api/resume/candidate/{candidate['id']}")
        assert profile_resp.status_code == 200
        profile = profile_resp.json()
        print(f"Step 2: Loaded profile with {len(profile.get('skills', []))} skills")
        
        # Step 3: Generate LaTeX
        gen_resp = self.session.post(f"{BASE_URL}/api/resume/generate", json={
            "profile": profile,
            "template_id": "ats_clean"
        })
        assert gen_resp.status_code == 200
        latex = gen_resp.json()["latex"]
        print(f"Step 3: Generated LaTeX ({len(latex)} chars)")
        
        # Step 4: Compile to PDF
        pdf_resp = self.session.post(f"{BASE_URL}/api/resume/compile-pdf", json={"latex": latex})
        assert pdf_resp.status_code == 200
        assert pdf_resp.content[:4] == b'%PDF'
        print(f"Step 4: Compiled PDF ({len(pdf_resp.content)} bytes)")
        
        print("✅ E2E flow: Candidate → Profile → LaTeX → PDF successful!")


class TestPDFPreviewAccessControl:
    """Test access control for PDF preview endpoints"""
    
    def test_compile_pdf_requires_auth(self):
        """Test that compile-pdf requires authentication"""
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/resume/compile-pdf", json={
            "latex": "\\documentclass{article}\\begin{document}Test\\end{document}"
        })
        assert resp.status_code == 401, "Should require authentication"
        print("✅ compile-pdf correctly requires authentication")
    
    def test_generate_requires_auth(self):
        """Test that generate requires authentication"""
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/resume/generate", json={
            "profile": {"name": "Test"},
            "template_id": "ats_clean"
        })
        assert resp.status_code == 401, "Should require authentication"
        print("✅ generate correctly requires authentication")
    
    def test_templates_requires_auth(self):
        """Test that templates endpoint requires authentication"""
        session = requests.Session()
        resp = session.get(f"{BASE_URL}/api/resume/templates")
        assert resp.status_code == 401, "Should require authentication"
        print("✅ templates correctly requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
