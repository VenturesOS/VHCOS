"""
Test suite for JD Parsing Feature - VHC Talent OS
Tests:
1. POST /api/jobs/extract-jd-text - Text extraction from uploaded files
2. POST /api/jobs/parse-jd - JD parsing with AI (GPT-5.2 via Emergent LLM Key)

Features tested:
- Extract text from PDF, DOC, DOCX, TXT files
- Reject unsupported file formats
- Handle empty/image-only files
- Parse JD with input_type parameter (paste/upload)
- Audit metadata in parse response
- Role-based access (admin/employer/recruiter only)
"""

import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


class TestJDExtraction:
    """Tests for POST /api/jobs/extract-jd-text endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_extract_text_from_txt_file(self):
        """Test extracting text from a TXT file"""
        # Create a sample TXT file
        txt_content = """Senior Software Engineer - Job Description
        
We are looking for a Senior Software Engineer to join our team.

Requirements:
- 5+ years of experience in Python
- Experience with FastAPI and React
- Strong problem-solving skills

Location: Mumbai, India
Salary: 15-25 LPA
"""
        files = {
            'jd_file': ('test_jd.txt', io.BytesIO(txt_content.encode('utf-8')), 'text/plain')
        }
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/extract-jd-text",
            headers=self.headers,
            files=files
        )
        
        assert response.status_code == 200, f"Extract failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert data.get("success") == True
        assert "extracted_text" in data
        assert "filename" in data
        assert "char_count" in data
        assert "extraction_method" in data
        
        # Verify content
        assert "Senior Software Engineer" in data["extracted_text"]
        assert data["filename"] == "test_jd.txt"
        assert data["file_type"] == "txt"
        assert data["char_count"] > 0
        assert data["extraction_method"] == "txt_read"
        
        # Verify audit metadata
        assert "extracted_by" in data
        assert "extracted_by_role" in data
        assert "extracted_at" in data
        
        print(f"✅ TXT extraction successful - {data['char_count']} characters extracted")
    
    def test_extract_text_from_pdf_file(self):
        """Test extracting text from a PDF file (using a minimal PDF)"""
        # Create a minimal PDF with text
        # This is a simple PDF structure with text
        pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Test JD Content) Tj ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000359 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
434
%%EOF"""
        
        files = {
            'jd_file': ('test_jd.pdf', io.BytesIO(pdf_content), 'application/pdf')
        }
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/extract-jd-text",
            headers=self.headers,
            files=files
        )
        
        # PDF extraction should work (may have minimal text)
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert data.get("success") == True
            assert data["file_type"] == "pdf"
            assert data["extraction_method"] == "pdf_fitz"
            print(f"✅ PDF extraction successful - {data.get('char_count', 0)} characters")
        else:
            # If PDF has no extractable text, should return 400
            data = response.json()
            assert "empty" in data.get("detail", "").lower() or "no text" in data.get("detail", "").lower()
            print("✅ PDF with no text correctly rejected")
    
    def test_reject_unsupported_file_format(self):
        """Test that unsupported file formats are rejected"""
        # Try to upload an image file
        files = {
            'jd_file': ('test.jpg', io.BytesIO(b'fake image content'), 'image/jpeg')
        }
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/extract-jd-text",
            headers=self.headers,
            files=files
        )
        
        assert response.status_code == 400, f"Should reject unsupported format: {response.text}"
        data = response.json()
        assert "unsupported" in data.get("detail", "").lower() or "format" in data.get("detail", "").lower()
        print("✅ Unsupported file format correctly rejected")
    
    def test_reject_empty_file(self):
        """Test that empty files are rejected"""
        files = {
            'jd_file': ('empty.txt', io.BytesIO(b''), 'text/plain')
        }
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/extract-jd-text",
            headers=self.headers,
            files=files
        )
        
        assert response.status_code == 400, f"Should reject empty file: {response.text}"
        data = response.json()
        assert "empty" in data.get("detail", "").lower() or "no text" in data.get("detail", "").lower()
        print("✅ Empty file correctly rejected")
    
    def test_extract_requires_authentication(self):
        """Test that extract endpoint requires authentication"""
        files = {
            'jd_file': ('test.txt', io.BytesIO(b'test content'), 'text/plain')
        }
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/extract-jd-text",
            files=files
        )
        
        assert response.status_code in [401, 403], f"Should require auth: {response.status_code}"
        print("✅ Extract endpoint correctly requires authentication")


class TestJDParsing:
    """Tests for POST /api/jobs/parse-jd endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.user = response.json()["user"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_parse_jd_with_paste_input(self):
        """Test parsing JD with pasted text input"""
        jd_text = """
        Senior Python Developer
        
        Location: Bangalore, India
        Experience: 5-8 years
        
        We are looking for a Senior Python Developer to join our engineering team.
        
        Requirements:
        - 5+ years of Python experience
        - Experience with Django or FastAPI
        - Knowledge of PostgreSQL and MongoDB
        - Strong problem-solving skills
        
        Responsibilities:
        - Design and develop backend services
        - Write clean, maintainable code
        - Mentor junior developers
        
        Salary: 20-30 LPA
        """
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            data={
                "jd_text": jd_text,
                "input_type": "paste"
            }
        )
        
        assert response.status_code == 200, f"Parse failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "title" in data
        assert "skills" in data
        assert "location" in data
        assert "raw_text" in data
        
        # Verify audit metadata
        assert data.get("input_type") == "paste"
        assert "parsed_by" in data
        assert "parsed_by_role" in data
        assert "parsed_at" in data
        
        print(f"✅ JD parsing with paste input successful")
        print(f"   - Title: {data.get('title')}")
        print(f"   - Skills: {data.get('skills', [])[:5]}")
        print(f"   - Location: {data.get('location')}")
        print(f"   - Input type: {data.get('input_type')}")
        print(f"   - Parsed by role: {data.get('parsed_by_role')}")
    
    def test_parse_jd_with_upload_input_type(self):
        """Test parsing JD with upload input type (text provided)"""
        jd_text = """
        Data Scientist
        
        Location: Mumbai, India
        Experience: 3-5 years
        
        Skills Required:
        - Python, R
        - Machine Learning
        - TensorFlow, PyTorch
        - SQL
        """
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            data={
                "jd_text": jd_text,
                "input_type": "upload"
            }
        )
        
        assert response.status_code == 200, f"Parse failed: {response.text}"
        data = response.json()
        
        # Verify input_type is recorded correctly
        assert data.get("input_type") == "upload"
        assert "parsed_by" in data
        assert "parsed_by_role" in data
        
        print(f"✅ JD parsing with upload input type successful")
        print(f"   - Input type: {data.get('input_type')}")
    
    def test_parse_jd_requires_input(self):
        """Test that parse endpoint requires either jd_text or jd_file"""
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            data={}
        )
        
        assert response.status_code == 400, f"Should require input: {response.status_code}"
        data = response.json()
        assert "provide" in data.get("detail", "").lower() or "jd_text" in data.get("detail", "").lower()
        print("✅ Parse endpoint correctly requires input")
    
    def test_parse_jd_requires_authentication(self):
        """Test that parse endpoint requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            data={"jd_text": "Test JD"}
        )
        
        assert response.status_code in [401, 403], f"Should require auth: {response.status_code}"
        print("✅ Parse endpoint correctly requires authentication")
    
    def test_parse_jd_with_file_upload(self):
        """Test parsing JD with file upload"""
        txt_content = """
        Product Manager
        
        Location: Delhi NCR
        Experience: 4-7 years
        
        Requirements:
        - Product management experience
        - Agile methodology
        - Stakeholder management
        - Data analysis skills
        """
        
        files = {
            'jd_file': ('product_manager_jd.txt', io.BytesIO(txt_content.encode('utf-8')), 'text/plain')
        }
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            files=files,
            data={"input_type": "upload"}
        )
        
        assert response.status_code == 200, f"Parse with file failed: {response.text}"
        data = response.json()
        
        # Verify response
        assert "title" in data
        assert "skills" in data
        assert "raw_text" in data
        
        print(f"✅ JD parsing with file upload successful")
        print(f"   - Title: {data.get('title')}")
    
    def test_parse_jd_audit_metadata_complete(self):
        """Test that parse response includes complete audit metadata"""
        jd_text = "Software Engineer - Test JD for audit verification"
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            data={
                "jd_text": jd_text,
                "input_type": "paste"
            }
        )
        
        assert response.status_code == 200, f"Parse failed: {response.text}"
        data = response.json()
        
        # Verify all audit fields
        assert "input_type" in data, "Missing input_type in audit"
        assert "parsed_by" in data, "Missing parsed_by in audit"
        assert "parsed_by_role" in data, "Missing parsed_by_role in audit"
        assert "parsed_at" in data, "Missing parsed_at in audit"
        
        # Verify values
        assert data["input_type"] == "paste"
        assert data["parsed_by"] == self.user["id"]
        assert data["parsed_by_role"] == self.user["role"]
        
        print("✅ Audit metadata complete and correct")
        print(f"   - input_type: {data['input_type']}")
        print(f"   - parsed_by: {data['parsed_by']}")
        print(f"   - parsed_by_role: {data['parsed_by_role']}")
        print(f"   - parsed_at: {data['parsed_at']}")


class TestRoleBasedAccess:
    """Tests for role-based access control on JD parsing endpoints"""
    
    def test_candidate_cannot_access_extract(self):
        """Test that candidates cannot access extract endpoint"""
        # First create a candidate user
        candidate_email = f"test_candidate_{os.urandom(4).hex()}@test.com"
        
        # Register as candidate
        reg_response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": candidate_email,
            "password": "TestPass123!",
            "name": "Test Candidate",
            "role": "candidate"
        })
        
        if reg_response.status_code == 200:
            token = reg_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            
            files = {
                'jd_file': ('test.txt', io.BytesIO(b'test content'), 'text/plain')
            }
            
            response = requests.post(
                f"{BASE_URL}/api/jobs/extract-jd-text",
                headers=headers,
                files=files
            )
            
            assert response.status_code == 403, f"Candidate should not access extract: {response.status_code}"
            print("✅ Candidate correctly denied access to extract endpoint")
        else:
            print("⚠️ Could not create test candidate, skipping role test")
    
    def test_admin_can_access_both_endpoints(self):
        """Test that admin can access both extract and parse endpoints"""
        # Login as admin
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test extract
        files = {
            'jd_file': ('test.txt', io.BytesIO(b'Admin test content'), 'text/plain')
        }
        extract_response = requests.post(
            f"{BASE_URL}/api/jobs/extract-jd-text",
            headers=headers,
            files=files
        )
        # Should be 200 or 400 (if empty), not 403
        assert extract_response.status_code != 403, "Admin should have access to extract"
        
        # Test parse
        parse_response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=headers,
            data={"jd_text": "Admin test JD", "input_type": "paste"}
        )
        assert parse_response.status_code == 200, f"Admin should access parse: {parse_response.status_code}"
        
        print("✅ Admin has access to both extract and parse endpoints")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
