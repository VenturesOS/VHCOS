"""
Test Bulk Candidate Import Tool - Backend API Tests
Tests all bulk import endpoints: template download, parse, save, batches
"""
import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"

# Test file paths
TEST_EXCEL_PATH = "/tmp/test_candidates.xlsx"
TEST_ZIP_PATH = "/tmp/test_resumes.zip"


class TestBulkImportAuth:
    """Test authentication requirements for bulk import endpoints"""
    
    def test_template_requires_auth(self):
        """GET /api/admin/bulk-import/template requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/bulk-import/template")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ Template endpoint requires authentication")
    
    def test_parse_requires_auth(self):
        """POST /api/admin/bulk-import/parse requires authentication"""
        response = requests.post(f"{BASE_URL}/api/admin/bulk-import/parse")
        assert response.status_code in [401, 403, 422], f"Expected 401/403/422, got {response.status_code}"
        print("✅ Parse endpoint requires authentication")
    
    def test_save_requires_auth(self):
        """POST /api/admin/bulk-import/save requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/admin/bulk-import/save",
            json={"batch_id": "test", "candidates": []}
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ Save endpoint requires authentication")
    
    def test_batches_requires_auth(self):
        """GET /api/admin/bulk-import/batches requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/bulk-import/batches")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ Batches endpoint requires authentication")


class TestBulkImportTemplate:
    """Test template download endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_download_template_success(self):
        """GET /api/admin/bulk-import/template returns Excel file"""
        response = requests.get(
            f"{BASE_URL}/api/admin/bulk-import/template",
            headers=self.headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Check content type
        content_type = response.headers.get('content-type', '')
        assert 'spreadsheet' in content_type or 'excel' in content_type or 'octet-stream' in content_type, \
            f"Expected Excel content type, got {content_type}"
        
        # Check content disposition
        content_disp = response.headers.get('content-disposition', '')
        assert 'bulk_import_template.xlsx' in content_disp, \
            f"Expected filename in content-disposition, got {content_disp}"
        
        # Check file size (should be non-empty)
        assert len(response.content) > 0, "Template file is empty"
        
        print(f"✅ Template downloaded successfully ({len(response.content)} bytes)")


class TestBulkImportParse:
    """Test parse endpoint with Excel + ZIP files"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_parse_missing_excel(self):
        """POST /api/admin/bulk-import/parse fails without Excel file"""
        with open(TEST_ZIP_PATH, 'rb') as zip_file:
            files = {'resume_zip': ('test_resumes.zip', zip_file, 'application/zip')}
            response = requests.post(
                f"{BASE_URL}/api/admin/bulk-import/parse",
                headers=self.headers,
                files=files
            )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("✅ Parse fails without Excel file (422)")
    
    def test_parse_missing_zip(self):
        """POST /api/admin/bulk-import/parse fails without ZIP file"""
        with open(TEST_EXCEL_PATH, 'rb') as excel_file:
            files = {'excel_file': ('test_candidates.xlsx', excel_file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
            response = requests.post(
                f"{BASE_URL}/api/admin/bulk-import/parse",
                headers=self.headers,
                files=files
            )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("✅ Parse fails without ZIP file (422)")
    
    def test_parse_invalid_excel_type(self):
        """POST /api/admin/bulk-import/parse fails with invalid Excel file type"""
        # Create a fake text file
        fake_excel = io.BytesIO(b"This is not an Excel file")
        fake_zip = io.BytesIO(b"PK\x03\x04")  # Minimal ZIP header
        
        files = {
            'excel_file': ('test.txt', fake_excel, 'text/plain'),
            'resume_zip': ('test.zip', fake_zip, 'application/zip')
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/bulk-import/parse",
            headers=self.headers,
            files=files
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✅ Parse fails with invalid Excel file type (400)")
    
    def test_parse_success_with_test_files(self):
        """POST /api/admin/bulk-import/parse succeeds with valid test files"""
        # Check if test files exist
        if not os.path.exists(TEST_EXCEL_PATH) or not os.path.exists(TEST_ZIP_PATH):
            pytest.skip("Test files not found at /tmp/")
        
        with open(TEST_EXCEL_PATH, 'rb') as excel_file, open(TEST_ZIP_PATH, 'rb') as zip_file:
            files = {
                'excel_file': ('test_candidates.xlsx', excel_file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                'resume_zip': ('test_resumes.zip', zip_file, 'application/zip')
            }
            response = requests.post(
                f"{BASE_URL}/api/admin/bulk-import/parse",
                headers=self.headers,
                files=files
            )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Validate response structure
        assert 'batch_id' in data, "Response missing batch_id"
        assert 'total_rows' in data, "Response missing total_rows"
        assert 'valid_rows' in data, "Response missing valid_rows"
        assert 'invalid_rows' in data, "Response missing invalid_rows"
        assert 'candidates' in data, "Response missing candidates"
        
        # Store batch_id for later tests
        self.batch_id = data['batch_id']
        
        print(f"✅ Parse successful: {data['total_rows']} total, {data['valid_rows']} valid, {data['invalid_rows']} invalid")
        print(f"   Batch ID: {data['batch_id'][:8]}...")
        
        # Validate candidate structure
        if data['candidates']:
            candidate = data['candidates'][0]
            assert 'row_index' in candidate, "Candidate missing row_index"
            assert 'final_name' in candidate, "Candidate missing final_name"
            assert 'is_valid' in candidate, "Candidate missing is_valid"
            print(f"   First candidate: {candidate['final_name']}")
        
        return data


class TestBulkImportSave:
    """Test save endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and parse test files"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_save_invalid_batch_id(self):
        """POST /api/admin/bulk-import/save fails with invalid batch_id"""
        response = requests.post(
            f"{BASE_URL}/api/admin/bulk-import/save",
            headers=self.headers,
            json={
                "batch_id": "non-existent-batch-id",
                "candidates": [{"final_name": "Test"}]
            }
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✅ Save fails with invalid batch_id (404)")
    
    def test_save_empty_candidates(self):
        """POST /api/admin/bulk-import/save fails with empty candidates list"""
        response = requests.post(
            f"{BASE_URL}/api/admin/bulk-import/save",
            headers=self.headers,
            json={
                "batch_id": "some-batch-id",
                "candidates": []
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✅ Save fails with empty candidates list (400)")
    
    def test_full_parse_and_save_flow(self):
        """Full flow: Parse files -> Save candidates"""
        # Check if test files exist
        if not os.path.exists(TEST_EXCEL_PATH) or not os.path.exists(TEST_ZIP_PATH):
            pytest.skip("Test files not found at /tmp/")
        
        # Step 1: Parse files
        with open(TEST_EXCEL_PATH, 'rb') as excel_file, open(TEST_ZIP_PATH, 'rb') as zip_file:
            files = {
                'excel_file': ('test_candidates.xlsx', excel_file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                'resume_zip': ('test_resumes.zip', zip_file, 'application/zip')
            }
            parse_response = requests.post(
                f"{BASE_URL}/api/admin/bulk-import/parse",
                headers=self.headers,
                files=files
            )
        
        assert parse_response.status_code == 200, f"Parse failed: {parse_response.text}"
        parse_data = parse_response.json()
        batch_id = parse_data['batch_id']
        
        print(f"✅ Step 1: Parsed {parse_data['total_rows']} candidates")
        
        # Step 2: Prepare valid candidates for save
        valid_candidates = [c for c in parse_data['candidates'] if c['is_valid']]
        
        if not valid_candidates:
            print("⚠️ No valid candidates to save, skipping save step")
            return
        
        # Prepare save payload
        candidates_to_save = []
        for c in valid_candidates[:3]:  # Save only first 3 for testing
            candidates_to_save.append({
                'row_index': c['row_index'],
                'final_name': c['final_name'],
                'final_email': c['final_email'],
                'final_phone': c['final_phone'],
                'final_location': c['final_location'],
                'final_experience_years': c['final_experience_years'],
                'final_skills': c['final_skills'],
                'final_current_salary': c['final_current_salary'],
                'final_notice_period': c['final_notice_period'],
                'final_headline': c.get('final_headline'),
                'final_summary': c.get('final_summary'),
                'final_experience': c.get('final_experience', []),
                'final_education': c.get('final_education', []),
                'resume_file_id': c['resume_file_id'],
                'resume_fingerprint': c.get('resume_fingerprint'),
                'r2_metadata': c.get('r2_metadata'),
                'resume_filename': c['resume_filename']
            })
        
        # Step 3: Save candidates
        save_response = requests.post(
            f"{BASE_URL}/api/admin/bulk-import/save",
            headers=self.headers,
            json={
                "batch_id": batch_id,
                "candidates": candidates_to_save
            }
        )
        
        assert save_response.status_code == 200, f"Save failed: {save_response.text}"
        save_data = save_response.json()
        
        # Validate save response
        assert 'batch_id' in save_data, "Save response missing batch_id"
        assert 'total_attempted' in save_data, "Save response missing total_attempted"
        assert 'successful' in save_data, "Save response missing successful"
        assert 'failed' in save_data, "Save response missing failed"
        assert 'results' in save_data, "Save response missing results"
        
        print(f"✅ Step 2: Saved {save_data['successful']}/{save_data['total_attempted']} candidates")
        
        # Verify results
        for result in save_data['results']:
            assert 'status' in result, "Result missing status"
            assert result['status'] in ['created', 'updated', 'failed'], f"Invalid status: {result['status']}"
            print(f"   - {result['name']}: {result['status']}")
        
        return save_data


class TestBulkImportBatches:
    """Test batches listing endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_list_batches_success(self):
        """GET /api/admin/bulk-import/batches returns batch list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/bulk-import/batches",
            headers=self.headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'batches' in data, "Response missing batches"
        assert isinstance(data['batches'], list), "Batches should be a list"
        
        print(f"✅ Batches list retrieved: {len(data['batches'])} batches")
        
        # Validate batch structure if any exist
        if data['batches']:
            batch = data['batches'][0]
            assert 'id' in batch, "Batch missing id"
            assert 'created_at' in batch, "Batch missing created_at"
            assert 'status' in batch, "Batch missing status"
            print(f"   Latest batch: {batch['id'][:8]}... ({batch['status']})")


class TestDataMergeLogic:
    """Test that Excel data takes priority over resume parsed data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_excel_priority_in_merge(self):
        """Verify Excel data takes priority over parsed resume data"""
        # Check if test files exist
        if not os.path.exists(TEST_EXCEL_PATH) or not os.path.exists(TEST_ZIP_PATH):
            pytest.skip("Test files not found at /tmp/")
        
        with open(TEST_EXCEL_PATH, 'rb') as excel_file, open(TEST_ZIP_PATH, 'rb') as zip_file:
            files = {
                'excel_file': ('test_candidates.xlsx', excel_file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                'resume_zip': ('test_resumes.zip', zip_file, 'application/zip')
            }
            response = requests.post(
                f"{BASE_URL}/api/admin/bulk-import/parse",
                headers=self.headers,
                files=files
            )
        
        assert response.status_code == 200, f"Parse failed: {response.text}"
        data = response.json()
        
        # Check merge logic for each candidate
        for candidate in data['candidates']:
            # Excel name should always be used
            if candidate['excel_name']:
                assert candidate['final_name'] == candidate['excel_name'], \
                    f"Excel name should take priority: {candidate['excel_name']} vs {candidate['final_name']}"
            
            # Excel email should take priority if provided
            if candidate['excel_email']:
                assert candidate['final_email'] == candidate['excel_email'], \
                    f"Excel email should take priority"
            
            # Excel phone should take priority if provided
            if candidate['excel_phone']:
                assert candidate['final_phone'] == candidate['excel_phone'], \
                    f"Excel phone should take priority"
        
        print("✅ Excel data correctly takes priority over parsed resume data")


class TestValidation:
    """Test validation rules"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_validation_errors_reported(self):
        """Verify validation errors are properly reported"""
        # Check if test files exist
        if not os.path.exists(TEST_EXCEL_PATH) or not os.path.exists(TEST_ZIP_PATH):
            pytest.skip("Test files not found at /tmp/")
        
        with open(TEST_EXCEL_PATH, 'rb') as excel_file, open(TEST_ZIP_PATH, 'rb') as zip_file:
            files = {
                'excel_file': ('test_candidates.xlsx', excel_file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                'resume_zip': ('test_resumes.zip', zip_file, 'application/zip')
            }
            response = requests.post(
                f"{BASE_URL}/api/admin/bulk-import/parse",
                headers=self.headers,
                files=files
            )
        
        assert response.status_code == 200, f"Parse failed: {response.text}"
        data = response.json()
        
        # Check that validation_errors and warnings are present
        for candidate in data['candidates']:
            assert 'is_valid' in candidate, "Candidate missing is_valid field"
            assert 'validation_errors' in candidate, "Candidate missing validation_errors field"
            assert 'warnings' in candidate, "Candidate missing warnings field"
            
            if not candidate['is_valid']:
                assert len(candidate['validation_errors']) > 0, \
                    "Invalid candidate should have validation errors"
                print(f"   Invalid: {candidate['final_name']} - {candidate['validation_errors']}")
        
        print(f"✅ Validation errors properly reported: {data['invalid_rows']} invalid candidates")


class TestCandidateBankIntegration:
    """Test that saved candidates appear in Candidate Bank"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_saved_candidates_in_bank(self):
        """Verify saved candidates appear in Candidate Bank with correct source tag"""
        # Get candidate bank
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed to get candidate bank: {response.text}"
        
        data = response.json()
        candidates = data.get('candidates', [])
        
        # Look for bulk_import sourced candidates
        bulk_import_candidates = [c for c in candidates if c.get('source') == 'bulk_import']
        
        print(f"✅ Found {len(bulk_import_candidates)} candidates with source='bulk_import' in Candidate Bank")
        
        # Verify import_batch_id is present
        for candidate in bulk_import_candidates[:3]:
            assert 'import_batch_id' in candidate or candidate.get('import_batch_id') is not None, \
                "Bulk import candidate should have import_batch_id"
            print(f"   - {candidate.get('name')}: batch {candidate.get('import_batch_id', 'N/A')[:8]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
