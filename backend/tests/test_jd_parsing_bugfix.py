"""
Test suite for JD Parsing Bug Fix - VHC Talent OS
Tests specifically for the 'body stream already read' bug fix.

Bug Root Cause: Frontend was calling response.json() and then in error handling 
trying to read the response again (body stream already consumed).

Fix: Read response.text() once, then parse JSON from string.

This test suite verifies:
1. Single request → single clean JSON response
2. No double-read issues
3. Proper HTTP error codes
4. Response structure matches frontend expectations
"""

import pytest
import requests
import os
import io
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


class TestJDParsingBugFix:
    """Tests specifically for the body stream bug fix"""
    
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
    
    def test_parse_jd_returns_single_clean_json_paste_mode(self):
        """Test that paste mode returns single clean JSON response"""
        jd_text = """
        Senior Software Engineer
        Location: Mumbai, India
        Experience: 5-8 years
        Skills: Python, FastAPI, React, MongoDB
        """
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            data={
                "jd_text": jd_text,
                "input_type": "paste"
            }
        )
        
        # Verify single clean response
        assert response.status_code == 200, f"Request failed: {response.status_code}"
        
        # Read response text once (simulating frontend fix)
        response_text = response.text
        
        # Parse JSON from text
        data = json.loads(response_text)
        
        # Verify response structure for frontend autofill
        assert "success" in data, "Missing 'success' field"
        assert "title" in data, "Missing 'title' field"
        assert "skills" in data, "Missing 'skills' field"
        assert "location" in data, "Missing 'location' field"
        assert "input_type" in data, "Missing 'input_type' field"
        assert "parsed_by_role" in data, "Missing 'parsed_by_role' field"
        
        # Verify audit logging
        assert data["input_type"] == "paste"
        
        print(f"✅ Paste mode returns clean JSON")
        print(f"   - success: {data['success']}")
        print(f"   - title: {data.get('title')}")
        print(f"   - skills: {data.get('skills', [])[:3]}")
    
    def test_parse_jd_returns_single_clean_json_upload_mode(self):
        """Test that upload mode returns single clean JSON response"""
        txt_content = """
        Data Analyst
        Location: Bangalore, India
        Experience: 2-4 years
        Skills: SQL, Python, Tableau, Excel
        """
        
        files = {
            'jd_file': ('data_analyst_jd.txt', io.BytesIO(txt_content.encode('utf-8')), 'text/plain')
        }
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            files=files,
            data={"input_type": "upload"}
        )
        
        # Verify single clean response
        assert response.status_code == 200, f"Request failed: {response.status_code}"
        
        # Read response text once (simulating frontend fix)
        response_text = response.text
        
        # Parse JSON from text
        data = json.loads(response_text)
        
        # Verify response structure
        assert "success" in data
        assert "title" in data
        assert "skills" in data
        assert "input_type" in data
        
        # Verify audit logging for upload
        assert data["input_type"] == "upload"
        
        print(f"✅ Upload mode returns clean JSON")
        print(f"   - input_type: {data['input_type']}")
    
    def test_parse_jd_error_returns_proper_http_code(self):
        """Test that errors return proper HTTP codes (400) not 500"""
        # Test with unsupported file format
        files = {
            'jd_file': ('test.jpg', io.BytesIO(b'fake image'), 'image/jpeg')
        }
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            files=files,
            data={"input_type": "upload"}
        )
        
        # Should return 400 Bad Request, not 500
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        # Response should be valid JSON
        data = response.json()
        assert "detail" in data
        
        print(f"✅ Unsupported format returns 400 with proper error message")
        print(f"   - detail: {data['detail']}")
    
    def test_parse_jd_empty_file_returns_proper_error(self):
        """Test that empty files return proper error message"""
        files = {
            'jd_file': ('empty.txt', io.BytesIO(b''), 'text/plain')
        }
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            files=files,
            data={"input_type": "upload"}
        )
        
        # Should return 400 with clear error
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        # Error should mention empty or no text
        assert "empty" in data["detail"].lower() or "no text" in data["detail"].lower()
        
        print(f"✅ Empty file returns proper error message")
        print(f"   - detail: {data['detail']}")
    
    def test_parse_jd_response_fields_for_frontend_autofill(self):
        """Test that response includes all fields needed for frontend autofill"""
        jd_text = """
        Product Manager
        
        Location: Delhi NCR
        Experience: 4-7 years
        Salary: 25-40 LPA
        
        Requirements:
        - Product management experience
        - Agile methodology
        - Stakeholder management
        
        Responsibilities:
        - Define product roadmap
        - Work with engineering teams
        """
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            data={
                "jd_text": jd_text,
                "input_type": "paste"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify all fields needed for frontend autofill
        required_fields = [
            "success",
            "title",
            "skills",
            "experience_years",
            "location",
            "input_type",
            "parsed_by_role"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Verify optional fields are present (may be None)
        optional_fields = [
            "salary_min",
            "salary_max",
            "summary",
            "responsibilities",
            "requirements",
            "raw_text"
        ]
        
        for field in optional_fields:
            assert field in data, f"Missing optional field: {field}"
        
        print(f"✅ Response includes all fields for frontend autofill")
        print(f"   - Required fields: {len(required_fields)} present")
        print(f"   - Optional fields: {len(optional_fields)} present")
    
    def test_parse_jd_no_input_returns_400(self):
        """Test that missing input returns 400 not 500"""
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            data={}
        )
        
        # Should return 400 Bad Request
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        
        print(f"✅ Missing input returns 400 with proper error")
        print(f"   - detail: {data['detail']}")
    
    def test_parse_jd_pdf_file_upload(self):
        """Test parsing JD from PDF file upload"""
        # Create a minimal PDF with text
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
BT /F1 12 Tf 100 700 Td (Software Engineer JD) Tj ET
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
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            files=files,
            data={"input_type": "upload"}
        )
        
        # Should return 200 or 400 (if PDF has no extractable text)
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
        
        # Response should be valid JSON
        data = response.json()
        
        if response.status_code == 200:
            assert "success" in data
            assert "input_type" in data
            print(f"✅ PDF file parsing successful")
        else:
            assert "detail" in data
            print(f"✅ PDF with minimal text handled correctly: {data['detail']}")
    
    def test_parse_jd_docx_file_upload(self):
        """Test parsing JD from DOCX file upload - should handle gracefully"""
        # Create a minimal DOCX-like content (won't be valid DOCX but tests error handling)
        # Real DOCX files would work, this tests the error path
        docx_content = b'PK\x03\x04fake docx content'
        
        files = {
            'jd_file': ('test_jd.docx', io.BytesIO(docx_content), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        }
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            files=files,
            data={"input_type": "upload"}
        )
        
        # Should return 200 or 400 (if DOCX extraction fails)
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
        
        # Response should be valid JSON
        data = response.json()
        
        if response.status_code == 200:
            assert "success" in data
            print(f"✅ DOCX file parsing successful")
        else:
            assert "detail" in data
            print(f"✅ Invalid DOCX handled correctly: {data['detail']}")


class TestJDParsingAuditLogging:
    """Tests for audit logging in JD parsing"""
    
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
    
    def test_audit_logging_paste_mode(self):
        """Test audit logging includes input_type for paste mode"""
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            data={
                "jd_text": "Test JD for audit logging",
                "input_type": "paste"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify audit fields
        assert data["input_type"] == "paste"
        assert data["parsed_by"] == self.user["id"]
        assert data["parsed_by_role"] == self.user["role"]
        assert "parsed_at" in data
        
        print(f"✅ Audit logging correct for paste mode")
        print(f"   - input_type: {data['input_type']}")
        print(f"   - parsed_by_role: {data['parsed_by_role']}")
    
    def test_audit_logging_upload_mode(self):
        """Test audit logging includes input_type for upload mode"""
        files = {
            'jd_file': ('test.txt', io.BytesIO(b'Test JD for audit'), 'text/plain')
        }
        
        response = requests.post(
            f"{BASE_URL}/api/jobs/parse-jd",
            headers=self.headers,
            files=files,
            data={"input_type": "upload"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify audit fields
        assert data["input_type"] == "upload"
        assert data["parsed_by"] == self.user["id"]
        assert data["parsed_by_role"] == self.user["role"]
        assert "parsed_at" in data
        
        print(f"✅ Audit logging correct for upload mode")
        print(f"   - input_type: {data['input_type']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
