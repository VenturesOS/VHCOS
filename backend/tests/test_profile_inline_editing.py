"""
Test Suite for Profile Inline Editing and Excel Import Contact Number Parsing
Tests:
1. Excel import correctly parses Contact No. column with phone numbers
2. Profile inline editing - update current_employer, designation, industry
3. Profile dialog shows all mandatory fields
"""
import pytest
import requests
import os
import io
import pandas as pd

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


class TestExcelImportContactNumber:
    """Test Excel import correctly parses Contact No. column"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_excel_import_parses_contact_no(self):
        """Excel import correctly parses Contact No.* column"""
        # Create test Excel file with Contact No. column
        test_data = {
            'Candidate Name*': ['Test Contact 1', 'Test Contact 2'],
            'Contact No.*': ['9876543210', '9876543211'],
            'Email*': ['test.contact1@test.com', 'test.contact2@test.com'],
            'Work Exp*': ['5Y 0 M', '3Y 6 M'],
            'Annual Salary*': ['12.0 L', '15.5 L'],
            'Current Location*': ['Bangalore', 'Mumbai'],
            'Current Employer*': ['Test Company 1', 'Test Company 2'],
            'Designation*': ['Software Engineer', 'Business Analyst'],
            'U.G. Course*': ['B.Tech', 'BBA'],
            'Industry*': ['IT', 'Finance'],
            'Age/Date of Birth*': ['28', '30']
        }
        
        df = pd.DataFrame(test_data)
        excel_buffer = io.BytesIO()
        df.to_excel(excel_buffer, index=False)
        excel_buffer.seek(0)
        
        # Upload Excel file
        files = {"excel_file": ("test_contact.xlsx", excel_buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        response = requests.post(
            f"{BASE_URL}/api/admin/bulk-import/excel",
            headers=self.headers,
            files=files
        )
        
        assert response.status_code == 200, f"Excel parse failed: {response.text}"
        data = response.json()
        
        # Verify contact numbers are parsed
        assert len(data['candidates']) == 2
        
        for candidate in data['candidates']:
            assert candidate['contact_no'] is not None, f"Contact No. not parsed for {candidate['candidate_name']}"
            assert candidate['phone_normalized'] is not None, f"Phone not normalized for {candidate['candidate_name']}"
            assert len(candidate['phone_normalized']) == 10, f"Phone should be 10 digits for {candidate['candidate_name']}"
            print(f"✅ {candidate['candidate_name']}: Contact={candidate['contact_no']}, Normalized={candidate['phone_normalized']}")
        
        print(f"✅ Excel import correctly parsed Contact No. column for {len(data['candidates'])} candidates")


class TestProfileInlineEditing:
    """Test profile inline editing functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_update_current_employer(self):
        """Update current_employer field via inline editing"""
        # Get a candidate
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=self.headers)
        assert response.status_code == 200
        candidates = response.json()
        assert len(candidates) > 0, "No candidates found"
        
        candidate = candidates[0]
        original_employer = candidate.get('current_employer')
        
        # Update current_employer
        update_data = {"current_employer": "Test Employer Updated"}
        update_response = requests.put(
            f"{BASE_URL}/api/candidate-bank/{candidate['id']}",
            headers=self.headers,
            json=update_data
        )
        assert update_response.status_code == 200
        
        # Verify update
        verify_response = requests.get(f"{BASE_URL}/api/candidate-bank/{candidate['id']}", headers=self.headers)
        assert verify_response.status_code == 200
        updated = verify_response.json()
        assert updated.get('current_employer') == "Test Employer Updated"
        print(f"✅ current_employer updated successfully")
        
        # Revert
        requests.put(
            f"{BASE_URL}/api/candidate-bank/{candidate['id']}",
            headers=self.headers,
            json={"current_employer": original_employer}
        )
    
    def test_update_designation(self):
        """Update designation field via inline editing"""
        # Get a candidate
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=self.headers)
        assert response.status_code == 200
        candidates = response.json()
        assert len(candidates) > 0, "No candidates found"
        
        candidate = candidates[0]
        original_designation = candidate.get('designation')
        
        # Update designation
        update_data = {"designation": "Test Designation Updated"}
        update_response = requests.put(
            f"{BASE_URL}/api/candidate-bank/{candidate['id']}",
            headers=self.headers,
            json=update_data
        )
        assert update_response.status_code == 200
        
        # Verify update
        verify_response = requests.get(f"{BASE_URL}/api/candidate-bank/{candidate['id']}", headers=self.headers)
        assert verify_response.status_code == 200
        updated = verify_response.json()
        assert updated.get('designation') == "Test Designation Updated"
        print(f"✅ designation updated successfully")
        
        # Revert
        requests.put(
            f"{BASE_URL}/api/candidate-bank/{candidate['id']}",
            headers=self.headers,
            json={"designation": original_designation}
        )
    
    def test_update_industry(self):
        """Update industry field via inline editing"""
        # Get a candidate
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=self.headers)
        assert response.status_code == 200
        candidates = response.json()
        assert len(candidates) > 0, "No candidates found"
        
        candidate = candidates[0]
        original_industry = candidate.get('industry')
        
        # Update industry
        update_data = {"industry": "Test Industry Updated"}
        update_response = requests.put(
            f"{BASE_URL}/api/candidate-bank/{candidate['id']}",
            headers=self.headers,
            json=update_data
        )
        assert update_response.status_code == 200
        
        # Verify update
        verify_response = requests.get(f"{BASE_URL}/api/candidate-bank/{candidate['id']}", headers=self.headers)
        assert verify_response.status_code == 200
        updated = verify_response.json()
        assert updated.get('industry') == "Test Industry Updated"
        print(f"✅ industry updated successfully")
        
        # Revert
        requests.put(
            f"{BASE_URL}/api/candidate-bank/{candidate['id']}",
            headers=self.headers,
            json={"industry": original_industry}
        )
    
    def test_update_multiple_fields(self):
        """Update multiple profile fields at once"""
        # Get a candidate
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=self.headers)
        assert response.status_code == 200
        candidates = response.json()
        assert len(candidates) > 0, "No candidates found"
        
        candidate = candidates[0]
        original_values = {
            'current_employer': candidate.get('current_employer'),
            'designation': candidate.get('designation'),
            'industry': candidate.get('industry')
        }
        
        # Update multiple fields
        update_data = {
            "current_employer": "Multi Update Employer",
            "designation": "Multi Update Designation",
            "industry": "Multi Update Industry"
        }
        update_response = requests.put(
            f"{BASE_URL}/api/candidate-bank/{candidate['id']}",
            headers=self.headers,
            json=update_data
        )
        assert update_response.status_code == 200
        
        # Verify all updates
        verify_response = requests.get(f"{BASE_URL}/api/candidate-bank/{candidate['id']}", headers=self.headers)
        assert verify_response.status_code == 200
        updated = verify_response.json()
        
        assert updated.get('current_employer') == "Multi Update Employer"
        assert updated.get('designation') == "Multi Update Designation"
        assert updated.get('industry') == "Multi Update Industry"
        print(f"✅ Multiple fields updated successfully")
        
        # Revert
        requests.put(
            f"{BASE_URL}/api/candidate-bank/{candidate['id']}",
            headers=self.headers,
            json=original_values
        )


class TestCandidateBankMandatoryFields:
    """Test Candidate Bank API returns all mandatory fields"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_candidate_bank_returns_mandatory_fields(self):
        """Candidate Bank API returns all mandatory fields"""
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=self.headers)
        assert response.status_code == 200
        candidates = response.json()
        assert len(candidates) > 0, "No candidates found"
        
        # Check first candidate has all mandatory fields
        candidate = candidates[0]
        mandatory_fields = [
            'name', 'email', 'phone', 'experience_years', 'current_salary',
            'location', 'notice_period', 'current_employer', 'designation', 'industry'
        ]
        
        for field in mandatory_fields:
            assert field in candidate, f"Missing mandatory field: {field}"
        
        print(f"✅ Candidate Bank returns all mandatory fields")
        print(f"   Name: {candidate.get('name')}")
        print(f"   Email: {candidate.get('email')}")
        print(f"   Phone: {candidate.get('phone')}")
        print(f"   Experience: {candidate.get('experience_years')} years")
        print(f"   Salary: {candidate.get('current_salary')}")
        print(f"   Location: {candidate.get('location')}")
        print(f"   Notice: {candidate.get('notice_period')}")
        print(f"   Employer: {candidate.get('current_employer')}")
        print(f"   Designation: {candidate.get('designation')}")
        print(f"   Industry: {candidate.get('industry')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
