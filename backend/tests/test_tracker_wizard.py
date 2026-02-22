"""
Test suite for Tracker Creation Wizard APIs
Tests: parse-template-file endpoint, template creation with custom columns, tracker creation
"""
import pytest
import requests
import os
import io
import csv

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://portal-training-docs.preview.emergentagent.com').rstrip('/')


class TestTrackerWizardAPIs:
    """Tests for Tracker Creation Wizard backend APIs"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        # Get jobs for mandate selection
        jobs_resp = requests.get(f"{BASE_URL}/api/jobs", headers=self.headers)
        self.jobs = jobs_resp.json() if jobs_resp.status_code == 200 else []
        if self.jobs:
            self.job_id = self.jobs[0].get("id")
        yield
        # Cleanup any test resources
    
    # ── Master Columns API ──
    
    def test_get_master_columns(self):
        """GET /api/tracker/columns - should return 58 columns in 11 categories"""
        resp = requests.get(f"{BASE_URL}/api/tracker/columns", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        assert "columns" in data
        assert "categories" in data
        assert "field_types" in data
        
        assert len(data["columns"]) == 58, f"Expected 58 columns, got {len(data['columns'])}"
        assert len(data["categories"]) == 11, f"Expected 11 categories, got {len(data['categories'])}"
        assert set(data["field_types"]) == {"text", "number", "currency", "date", "dropdown"}
        
        # Verify column structure
        col = data["columns"][0]
        assert "key" in col
        assert "label" in col
        assert "category" in col
        assert "field_type" in col
        print(f"✓ Master columns API: {len(data['columns'])} columns, {len(data['categories'])} categories")
    
    # ── Parse Template File API ──
    
    def test_parse_template_file_csv(self):
        """POST /api/tracker/parse-template-file - should parse CSV and match columns"""
        # Create CSV content
        csv_content = "Full Name,Email,Mobile Number,Current Company,Custom Field\n"
        csv_content += "John Doe,john@test.com,9876543210,TechCorp,Value1\n"
        csv_content += "Jane Smith,jane@test.com,9876543211,FinCorp,Value2\n"
        
        files = {"file": ("test_template.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        auth_headers = {"Authorization": f"Bearer {self.token}"}
        
        resp = requests.post(f"{BASE_URL}/api/tracker/parse-template-file", 
                            headers=auth_headers, files=files)
        
        assert resp.status_code == 200, f"Parse failed: {resp.text}"
        data = resp.json()
        
        assert "headers" in data
        assert "mapping" in data
        assert "total_headers" in data
        assert "matched_count" in data
        
        assert data["total_headers"] == 5
        assert data["matched_count"] >= 4  # Full Name, Email, Mobile Number, Current Company should match
        
        # Verify mapping structure
        for m in data["mapping"]:
            assert "index" in m
            assert "header" in m
            assert "matched" in m
            if m["matched"]:
                assert m["master_column"] is not None
        
        print(f"✓ Parse template file: {data['total_headers']} headers, {data['matched_count']} matched")
    
    def test_parse_template_file_invalid_format(self):
        """POST /api/tracker/parse-template-file - should reject invalid file formats"""
        files = {"file": ("test.txt", io.BytesIO(b"invalid content"), "text/plain")}
        auth_headers = {"Authorization": f"Bearer {self.token}"}
        
        resp = requests.post(f"{BASE_URL}/api/tracker/parse-template-file",
                            headers=auth_headers, files=files)
        
        assert resp.status_code == 400
        print("✓ Parse template file rejects invalid formats")
    
    # ── Template Creation with Custom Columns ──
    
    def test_create_template_with_custom_columns(self):
        """POST /api/tracker/templates - should create template with mixed master + custom columns"""
        template_data = {
            "name": "TEST_Wizard_Template",
            "description": "Test template with custom columns",
            "columns": [
                {"key": "full_name", "label": "Full Name", "category": "Basic Info", "field_type": "text", "required": True, "order": 0},
                {"key": "email", "label": "Email", "category": "Contact Details", "field_type": "text", "required": True, "order": 1},
                {"key": "custom_interview_score", "label": "Interview Score", "category": "Custom", "field_type": "dropdown", "required": False, "order": 2, "is_custom": True, "dropdown_options": ["Excellent", "Good", "Average"]}
            ]
        }
        
        resp = requests.post(f"{BASE_URL}/api/tracker/templates", 
                            headers=self.headers, json=template_data)
        
        assert resp.status_code == 200, f"Create template failed: {resp.text}"
        data = resp.json()
        
        assert "id" in data
        assert data["name"] == "TEST_Wizard_Template"
        assert len(data["columns"]) == 3
        
        # Verify custom column
        custom_cols = [c for c in data["columns"] if c.get("is_custom")]
        assert len(custom_cols) == 1
        assert custom_cols[0]["key"] == "custom_interview_score"
        assert custom_cols[0]["dropdown_options"] == ["Excellent", "Good", "Average"]
        
        self.template_id = data["id"]
        print(f"✓ Created template with custom columns: {data['id']}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tracker/templates/{data['id']}", headers=self.headers)
    
    # ── Full Wizard Flow: Template + Tracker Creation ──
    
    def test_wizard_full_create_flow(self):
        """Test complete wizard flow: create template -> create tracker"""
        if not hasattr(self, 'job_id') or not self.job_id:
            pytest.skip("No jobs available for testing")
        
        # Step 1: Create template (simulating wizard Step 2-4)
        template_data = {
            "name": "TEST_Wizard_Full_Flow_Template",
            "description": "Auto-created for wizard flow test",
            "columns": [
                {"key": "full_name", "label": "Full Name", "category": "Basic Info", "field_type": "text", "required": True, "order": 0},
                {"key": "email", "label": "Email", "category": "Contact Details", "field_type": "text", "required": True, "order": 1},
                {"key": "current_company", "label": "Current Company", "category": "Employment", "field_type": "text", "required": False, "order": 2},
                {"key": "current_ctc", "label": "Current CTC", "category": "Compensation", "field_type": "currency", "required": True, "order": 3}
            ]
        }
        
        template_resp = requests.post(f"{BASE_URL}/api/tracker/templates",
                                     headers=self.headers, json=template_data)
        assert template_resp.status_code == 200, f"Template creation failed: {template_resp.text}"
        template_id = template_resp.json()["id"]
        
        # Step 2: Create tracker using the template
        tracker_data = {
            "name": "TEST_Wizard_Full_Flow_Tracker",
            "mandate_id": self.job_id,
            "template_id": template_id
        }
        
        tracker_resp = requests.post(f"{BASE_URL}/api/tracker/trackers",
                                    headers=self.headers, json=tracker_data)
        assert tracker_resp.status_code == 200, f"Tracker creation failed: {tracker_resp.text}"
        tracker = tracker_resp.json()
        
        assert "id" in tracker
        assert tracker["name"] == "TEST_Wizard_Full_Flow_Tracker"
        assert len(tracker["columns"]) == 4
        assert tracker["mandate_id"] == self.job_id
        
        # Step 3: Verify tracker is accessible
        get_resp = requests.get(f"{BASE_URL}/api/tracker/trackers/{tracker['id']}", headers=self.headers)
        assert get_resp.status_code == 200
        
        print(f"✓ Full wizard flow: template {template_id} -> tracker {tracker['id']}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tracker/trackers/{tracker['id']}", headers=self.headers)
        requests.delete(f"{BASE_URL}/api/tracker/templates/{template_id}", headers=self.headers)
    
    # ── Use Existing Template Flow ──
    
    def test_use_existing_template_flow(self):
        """Test 'Use Existing Template' mode - create tracker directly from existing template"""
        if not hasattr(self, 'job_id') or not self.job_id:
            pytest.skip("No jobs available for testing")
        
        # Get existing templates
        templates_resp = requests.get(f"{BASE_URL}/api/tracker/templates", headers=self.headers)
        assert templates_resp.status_code == 200
        templates = templates_resp.json().get("templates", [])
        
        if not templates:
            pytest.skip("No existing templates for testing")
        
        existing_template = templates[0]
        
        # Create tracker using existing template
        tracker_data = {
            "name": "TEST_Use_Existing_Template_Tracker",
            "mandate_id": self.job_id,
            "template_id": existing_template["id"]
        }
        
        tracker_resp = requests.post(f"{BASE_URL}/api/tracker/trackers",
                                    headers=self.headers, json=tracker_data)
        assert tracker_resp.status_code == 200, f"Tracker creation failed: {tracker_resp.text}"
        tracker = tracker_resp.json()
        
        assert tracker["template_id"] == existing_template["id"]
        assert len(tracker["columns"]) == len(existing_template["columns"])
        
        print(f"✓ Use existing template: {existing_template['name']} -> tracker {tracker['id']}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tracker/trackers/{tracker['id']}", headers=self.headers)
    
    # ── Validation Tests ──
    
    def test_template_requires_columns(self):
        """Template creation should fail without columns"""
        template_data = {
            "name": "TEST_Empty_Template",
            "columns": []
        }
        
        resp = requests.post(f"{BASE_URL}/api/tracker/templates",
                            headers=self.headers, json=template_data)
        assert resp.status_code == 400
        print("✓ Template creation requires at least one column")
    
    def test_tracker_requires_valid_mandate(self):
        """Tracker creation should fail with invalid mandate_id"""
        # First create a template
        template_data = {
            "name": "TEST_Temp_Template",
            "columns": [{"key": "full_name", "label": "Full Name", "category": "Basic Info", "field_type": "text", "required": True, "order": 0}]
        }
        template_resp = requests.post(f"{BASE_URL}/api/tracker/templates",
                                     headers=self.headers, json=template_data)
        template_id = template_resp.json()["id"]
        
        tracker_data = {
            "name": "TEST_Invalid_Mandate_Tracker",
            "mandate_id": "invalid-mandate-id",
            "template_id": template_id
        }
        
        resp = requests.post(f"{BASE_URL}/api/tracker/trackers",
                            headers=self.headers, json=tracker_data)
        assert resp.status_code == 404
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tracker/templates/{template_id}", headers=self.headers)
        print("✓ Tracker creation validates mandate_id")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
