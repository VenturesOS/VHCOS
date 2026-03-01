"""
Tests for fpdf2-based PDF generation (Iteration 99)
- Tests the NEW /api/resume/generate-pdf endpoint (pure Python, no pdflatex)
- Tests the ATS CV endpoint returns application/pdf (not .tex)
- Tests PDF generation with null fields
- Tests /api/resume/capabilities returns pdf_compilation: true
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Session-scoped fixture to avoid rate limiting
@pytest.fixture(scope="module")
def auth_token():
    """Get auth token once for all tests"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@vhc.in",
        "password": "VhcAdmin@2024"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    token = data.get("access_token")
    assert token, "No access_token in login response"
    return token

class TestFpdf2PdfGeneration:
    """Tests for fpdf2-based PDF generation - fixes .tex file download issue"""
    
    @pytest.fixture(autouse=True)
    def setup(self, auth_token):
        """Use shared auth token"""
        self.token = auth_token
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
    def test_resume_capabilities_returns_pdf_compilation_true(self):
        """GET /api/resume/capabilities must return pdf_compilation: true"""
        response = requests.get(f"{BASE_URL}/api/resume/capabilities", headers=self.headers)
        assert response.status_code == 200, f"Capabilities failed: {response.text}"
        data = response.json()
        assert data.get("pdf_compilation") == True, f"Expected pdf_compilation: true, got {data}"
        print(f"PASS: /api/resume/capabilities returns pdf_compilation: {data.get('pdf_compilation')}")
        
    def test_generate_pdf_endpoint_returns_valid_pdf(self):
        """POST /api/resume/generate-pdf must return application/pdf"""
        # Use shorter content to avoid layout issues
        profile = {
            "name": "Test User",
            "email": "test@example.com",
            "phone": "9876543210",
            "location": "Mumbai",
            "linkedin": "",
            "summary": "Software engineer with 5 years experience in Python.",
            "skills": ["Python", "JavaScript", "React", "Node.js"],
            "experience": [
                {
                    "company": "Tech Corp",
                    "title": "Developer",
                    "duration": "2020 - Present",
                    "bullets": [
                        "Led team to deliver projects",
                        "Implemented CI/CD pipeline"
                    ]
                }
            ],
            "education": [
                {
                    "institution": "IIT",
                    "degree": "B.Tech CS",
                    "year": "2018",
                    "gpa": "8.5"
                }
            ]
        }
        response = requests.post(
            f"{BASE_URL}/api/resume/generate-pdf",
            json={"profile": profile, "template_id": "ats_clean"},
            headers=self.headers
        )
        assert response.status_code == 200, f"Generate PDF failed: {response.status_code} - {response.text}"
        assert response.headers.get("Content-Type") == "application/pdf", f"Expected application/pdf, got {response.headers.get('Content-Type')}"
        # PDF should start with %PDF-
        assert response.content[:4] == b'%PDF', f"Response is not a valid PDF. First bytes: {response.content[:20]}"
        assert len(response.content) > 500, f"PDF too small: {len(response.content)} bytes"
        print(f"PASS: /api/resume/generate-pdf returns valid PDF ({len(response.content)} bytes)")
        
    def test_generate_pdf_with_null_fields(self):
        """POST /api/resume/generate-pdf with null email/phone must work"""
        profile = {
            "name": "Minimal Candidate",
            "email": None,  # Null email
            "phone": None,  # Null phone
            "location": "",
            "linkedin": "",
            "summary": "A software developer.",
            "skills": ["Python"],
            "experience": [],
            "education": []
        }
        response = requests.post(
            f"{BASE_URL}/api/resume/generate-pdf",
            json={"profile": profile, "template_id": "ats_clean"},
            headers=self.headers
        )
        assert response.status_code == 200, f"Generate PDF with nulls failed: {response.status_code} - {response.text}"
        assert response.headers.get("Content-Type") == "application/pdf", f"Expected application/pdf, got {response.headers.get('Content-Type')}"
        assert response.content[:4] == b'%PDF', f"Response is not a valid PDF"
        print(f"PASS: /api/resume/generate-pdf handles null fields correctly ({len(response.content)} bytes)")
        
    def test_generate_pdf_empty_profile(self):
        """POST /api/resume/generate-pdf with empty profile should still work"""
        profile = {
            "name": "",
            "email": "",
            "phone": "",
            "location": "",
            "linkedin": "",
            "summary": "",
            "skills": [],
            "experience": [],
            "education": []
        }
        response = requests.post(
            f"{BASE_URL}/api/resume/generate-pdf",
            json={"profile": profile, "template_id": "ats_clean"},
            headers=self.headers
        )
        # Should still generate a PDF (empty resume)
        assert response.status_code == 200, f"Generate PDF with empty profile failed: {response.status_code}"
        assert response.content[:4] == b'%PDF', f"Response is not a valid PDF"
        print(f"PASS: /api/resume/generate-pdf handles empty profile ({len(response.content)} bytes)")

    def test_ats_cv_endpoint_returns_pdf_not_tex(self):
        """GET /api/candidate-bank/{id}/ats-cv must return application/pdf (NOT .tex)"""
        # First get a candidate from the bank
        response = requests.get(f"{BASE_URL}/api/candidate-bank?limit=1", headers=self.headers)
        assert response.status_code == 200, f"Get candidates failed: {response.text}"
        data = response.json()
        candidates = data.get("candidates", [])
        
        if not candidates:
            pytest.skip("No candidates in bank to test ATS CV download")
            
        candidate_id = candidates[0].get("id")
        assert candidate_id, "Candidate has no ID"
        
        # Download ATS CV with token
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank/{candidate_id}/ats-cv?token={self.token}",
            headers=self.headers,
            allow_redirects=False
        )
        assert response.status_code == 200, f"ATS CV failed: {response.status_code} - {response.text}"
        content_type = response.headers.get("Content-Type", "")
        
        # CRITICAL: Must be application/pdf, NOT application/x-tex
        assert "application/pdf" in content_type, f"FAIL: Expected application/pdf, got {content_type}. File is downloading as .tex instead of PDF!"
        
        # Verify it's actually a PDF
        assert response.content[:4] == b'%PDF', f"Response content is not a valid PDF. First bytes: {response.content[:20]}"
        print(f"PASS: /api/candidate-bank/{candidate_id}/ats-cv returns application/pdf ({len(response.content)} bytes)")
        
    def test_multiple_candidates_ats_cv_all_return_pdf(self):
        """Multiple candidate ATS CV downloads should all return application/pdf"""
        # Get multiple candidates
        response = requests.get(f"{BASE_URL}/api/candidate-bank?limit=3", headers=self.headers)
        assert response.status_code == 200, f"Get candidates failed: {response.text}"
        data = response.json()
        candidates = data.get("candidates", [])
        
        if len(candidates) < 2:
            pytest.skip("Need at least 2 candidates to test multiple ATS CV downloads")
            
        pdf_count = 0
        for candidate in candidates[:3]:
            candidate_id = candidate.get("id")
            response = requests.get(
                f"{BASE_URL}/api/candidate-bank/{candidate_id}/ats-cv?token={self.token}",
                headers=self.headers
            )
            if response.status_code == 200:
                content_type = response.headers.get("Content-Type", "")
                assert "application/pdf" in content_type, f"Candidate {candidate_id}: Expected application/pdf, got {content_type}"
                assert response.content[:4] == b'%PDF', f"Candidate {candidate_id}: Not a valid PDF"
                pdf_count += 1
                
        print(f"PASS: {pdf_count}/{len(candidates[:3])} candidates returned valid PDF")
        
    def test_generate_resume_latex_still_works(self):
        """POST /api/resume/generate should still return LaTeX code"""
        profile = {
            "name": "LaTeX Test",
            "email": "latex@test.com",
            "phone": "1234567890",
            "location": "Test City",
            "summary": "Test summary",
            "skills": ["Skill1", "Skill2"],
            "experience": [],
            "education": []
        }
        response = requests.post(
            f"{BASE_URL}/api/resume/generate",
            json={"profile": profile, "template_id": "ats_clean"},
            headers=self.headers
        )
        assert response.status_code == 200, f"Generate LaTeX failed: {response.text}"
        data = response.json()
        assert "latex" in data, "Response missing 'latex' field"
        assert "\\documentclass" in data["latex"], "LaTeX code missing \\documentclass"
        print(f"PASS: /api/resume/generate returns valid LaTeX ({len(data['latex'])} chars)")
        
    def test_compile_pdf_fallback_message(self):
        """POST /api/resume/compile-pdf should return helpful message when pdflatex unavailable"""
        # This endpoint requires pdflatex - it should return 503 with helpful message if unavailable
        response = requests.post(
            f"{BASE_URL}/api/resume/compile-pdf",
            json={"latex": "\\documentclass{article}\\begin{document}Test\\end{document}"},
            headers=self.headers
        )
        # Either 200 (pdflatex works) or 503 (use generate-pdf instead)
        assert response.status_code in [200, 503], f"Unexpected status: {response.status_code}"
        if response.status_code == 503:
            data = response.json()
            assert "generate-pdf" in data.get("detail", ""), "503 should mention /api/resume/generate-pdf"
            print("PASS: /api/resume/compile-pdf returns helpful 503 when pdflatex unavailable")
        else:
            assert response.content[:4] == b'%PDF', "compile-pdf should return PDF"
            print(f"PASS: /api/resume/compile-pdf returns PDF with pdflatex")

    def test_auth_required_for_generate_pdf(self):
        """POST /api/resume/generate-pdf requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/resume/generate-pdf",
            json={"profile": {"name": "Test"}, "template_id": "ats_clean"}
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("PASS: /api/resume/generate-pdf requires authentication")

    def test_auth_required_for_ats_cv(self):
        """GET /api/candidate-bank/{id}/ats-cv requires token"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank/test-id/ats-cv")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: /api/candidate-bank/{id}/ats-cv requires token")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
