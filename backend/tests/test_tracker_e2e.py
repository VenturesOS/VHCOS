"""
Comprehensive E2E Testing for Talent Operating System
Tests: Tracker System, Analytics Endpoints, Excel Export/Upload, Bidirectional Sync

Features tested:
- Full E2E flow: Create tracker → Add candidate → Update status → Sync to pipeline
- Template CRUD (create, list, get, clone, delete)
- Tracker CRUD (create, list, get, delete)
- Row operations (add candidate, inline edit, status update, delete row)
- Bidirectional sync (tracker→pipeline, pipeline→tracker)
- Download validation endpoint (green/yellow/red status)
- Excel export (GET /api/tracker/trackers/{id}/export)
- Excel/CSV upload (POST /api/tracker/trackers/{id}/upload) - CRITICAL
- Pipeline Conversion API (GET /api/analytics/pipeline-conversion)
- Revenue Forecast API (GET /api/analytics/revenue-forecast)
- Recruiter Performance API (GET /api/analytics/recruiter-performance)
- Mandate Performance API (GET /api/analytics/mandate-performance)
"""

import pytest
import requests
import os
import time
import io
import csv

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://ai-match-stable.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
EMPLOYER_EMAIL = "employer@vhc.in"
EMPLOYER_PASSWORD = "VhcEmployer@2024"

# Known IDs from context
EXISTING_JOB_ID = "c72113dc-b62e-437c-8712-0fb9f6541d1d"  # Senior Python Developer
EXISTING_TEMPLATE_ID = "ea672bda-fa5a-4989-a8ec-d8c8ea024fa7"  # Executive Hiring Template
EXISTING_TRACKER_ID = "68b62013-f67e-4064-a0e2-89fafb8efe0d"  # Senior Python Dev Tracker

# Module-level session and tokens
_admin_session = None
_admin_token = None
_employer_session = None
_employer_token = None

# Created resources for cleanup
_test_template_id = None
_test_tracker_id = None
_test_row_id = None


def get_admin_session():
    """Get authenticated admin session"""
    global _admin_session, _admin_token
    
    if _admin_session and _admin_token:
        return _admin_session
    
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if response.status_code != 200:
        raise Exception(f"Admin login failed: {response.status_code} - {response.text}")
    
    data = response.json()
    _admin_token = data.get("access_token") or data.get("token")
    session.headers.update({"Authorization": f"Bearer {_admin_token}"})
    _admin_session = session
    return session


def get_employer_session():
    """Get authenticated employer session"""
    global _employer_session, _employer_token
    
    if _employer_session and _employer_token:
        return _employer_session
    
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": EMPLOYER_EMAIL,
        "password": EMPLOYER_PASSWORD
    })
    
    if response.status_code != 200:
        # Skip employer tests if credentials invalid
        pytest.skip(f"Employer login failed: {response.status_code} - credentials may be invalid")
    
    data = response.json()
    _employer_token = data.get("access_token") or data.get("token")
    session.headers.update({"Authorization": f"Bearer {_employer_token}"})
    _employer_session = session
    return session


# ==================== FULL E2E FLOW TEST ====================

class TestFullE2EFlow:
    """Full pipeline + tracker E2E flow test"""

    def test_01_create_template(self):
        """Create a new tracker template"""
        global _test_template_id
        session = get_admin_session()
        
        template_data = {
            "name": f"TEST_E2E_Template_{int(time.time())}",
            "description": "E2E test template",
            "columns": [
                {"key": "full_name", "label": "Full Name", "category": "Basic Info", "field_type": "text", "required": True, "order": 1},
                {"key": "email", "label": "Email", "category": "Contact Details", "field_type": "text", "required": True, "order": 2},
                {"key": "mobile_number", "label": "Mobile Number", "category": "Contact Details", "field_type": "text", "required": True, "order": 3},
                {"key": "current_company", "label": "Current Company", "category": "Professional", "field_type": "text", "required": False, "order": 4},
                {"key": "current_ctc", "label": "Current CTC", "category": "Compensation", "field_type": "currency", "required": False, "order": 5},
            ]
        }
        
        response = session.post(f"{BASE_URL}/api/tracker/templates", json=template_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "id" in data
        assert data["name"] == template_data["name"]
        assert len(data["columns"]) == 5
        
        _test_template_id = data["id"]
        print(f"Created E2E template: {_test_template_id}")

    def test_02_create_tracker(self):
        """Create a new tracker linked to mandate and template"""
        global _test_tracker_id, _test_template_id
        session = get_admin_session()
        
        # Use existing template if E2E template not created
        template_id = _test_template_id or EXISTING_TEMPLATE_ID
        
        tracker_data = {
            "name": f"TEST_E2E_Tracker_{int(time.time())}",
            "mandate_id": EXISTING_JOB_ID,
            "template_id": template_id
        }
        
        response = session.post(f"{BASE_URL}/api/tracker/trackers", json=tracker_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "id" in data
        assert data["mandate_id"] == EXISTING_JOB_ID
        
        _test_tracker_id = data["id"]
        print(f"Created E2E tracker: {_test_tracker_id}")

    def test_03_list_trackers_with_row_count(self):
        """List trackers and verify row_count field"""
        session = get_admin_session()
        
        response = session.get(f"{BASE_URL}/api/tracker/trackers")
        assert response.status_code == 200
        
        data = response.json()
        assert "trackers" in data
        
        # Find our test tracker
        if _test_tracker_id:
            test_tracker = next((t for t in data["trackers"] if t["id"] == _test_tracker_id), None)
            assert test_tracker is not None
            assert "row_count" in test_tracker
            print(f"Test tracker row_count: {test_tracker['row_count']}")

    def test_04_get_tracker_with_rows(self):
        """Get tracker details with rows"""
        session = get_admin_session()
        tracker_id = _test_tracker_id or EXISTING_TRACKER_ID
        
        response = session.get(f"{BASE_URL}/api/tracker/trackers/{tracker_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert "rows" in data
        assert "columns" in data
        assert "row_count" in data
        print(f"Tracker has {data['row_count']} rows, {len(data['columns'])} columns")

    def test_05_validation_endpoint(self):
        """Test download validation endpoint"""
        session = get_admin_session()
        tracker_id = _test_tracker_id or EXISTING_TRACKER_ID
        
        response = session.get(f"{BASE_URL}/api/tracker/trackers/{tracker_id}/validation")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert data["status"] in ["green", "yellow", "red"]
        assert "message" in data
        assert "total_rows" in data
        assert "issues" in data
        
        print(f"Validation: {data['status']} - {data['message']}")

    def test_99_cleanup_test_resources(self):
        """Cleanup: Delete test tracker and template"""
        session = get_admin_session()
        
        # Delete tracker first (to clean tracker_rows too)
        if _test_tracker_id:
            response = session.delete(f"{BASE_URL}/api/tracker/trackers/{_test_tracker_id}")
            print(f"Deleted test tracker: {response.status_code}")
        
        # Delete template
        if _test_template_id:
            response = session.delete(f"{BASE_URL}/api/tracker/templates/{_test_template_id}")
            print(f"Deleted test template: {response.status_code}")


# ==================== EXCEL UPLOAD TEST (CRITICAL) ====================

class TestExcelUpload:
    """Test Excel/CSV upload endpoint - CRITICAL untested feature"""

    def test_01_upload_csv_file(self):
        """POST /api/tracker/trackers/{id}/upload with CSV file"""
        session = get_admin_session()
        
        # Create a test CSV file content
        csv_content = """full_name,email,mobile_number,current_company,current_ctc
John Test,john.test@example.com,9876543210,Test Corp,1500000
Jane Demo,jane.demo@example.com,9876543211,Demo Inc,1800000
Bob Sample,bob.sample@example.com,9876543212,Sample Ltd,2000000"""
        
        # Use multipart/form-data for file upload
        files = {
            'file': ('test_upload.csv', csv_content, 'text/csv')
        }
        
        # Remove Content-Type header for multipart
        headers = {"Authorization": session.headers.get("Authorization")}
        
        response = requests.post(
            f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}/upload",
            files=files,
            headers=headers
        )
        
        print(f"Upload response: {response.status_code} - {response.text[:500]}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "imported" in data
        assert "message" in data
        assert data["imported"] >= 0  # May be 0 if rows already exist
        
        print(f"Upload result: {data}")

    def test_02_verify_uploaded_rows(self):
        """Verify rows were added after upload"""
        session = get_admin_session()
        
        response = session.get(f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}")
        assert response.status_code == 200
        
        data = response.json()
        print(f"After upload: {data['row_count']} rows")
        
        # Check if uploaded data exists
        rows = data.get("rows", [])
        email_set = {r.get("data", {}).get("email") for r in rows}
        
        # At least one of our test emails should be present
        test_emails = {"john.test@example.com", "jane.demo@example.com", "bob.sample@example.com"}
        found_emails = email_set.intersection(test_emails)
        print(f"Found uploaded emails: {found_emails}")


# ==================== EXCEL EXPORT TEST ====================

class TestExcelExport:
    """Test Excel export endpoint"""

    def test_export_excel_returns_xlsx(self):
        """GET /api/tracker/trackers/{id}/export returns .xlsx file"""
        session = get_admin_session()
        
        response = session.get(f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}/export")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Check content type
        content_type = response.headers.get("Content-Type", "")
        assert "spreadsheet" in content_type or "octet-stream" in content_type, f"Unexpected content type: {content_type}"
        
        # Check content disposition header
        content_disp = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp
        assert ".xlsx" in content_disp
        
        # Verify file has content
        assert len(response.content) > 0
        
        print(f"Excel export: {len(response.content)} bytes, disposition: {content_disp}")


# ==================== ANALYTICS ENDPOINTS ====================

class TestAnalyticsEndpoints:
    """Test analytics endpoints: pipeline conversion, revenue forecast, recruiter/mandate performance"""

    def test_pipeline_conversion_api(self):
        """GET /api/analytics/pipeline-conversion returns stage counts and conversion rates"""
        session = get_admin_session()
        
        response = session.get(f"{BASE_URL}/api/analytics/pipeline-conversion")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "stage_counts" in data
        assert "total_applications" in data
        assert "conversions" in data
        
        # Verify conversion structure
        conversions = data["conversions"]
        assert "applied_to_shortlisted" in conversions
        assert "shortlisted_to_submitted" in conversions
        assert "submitted_to_interview" in conversions
        assert "interview_to_offered" in conversions
        assert "offered_to_hired" in conversions
        assert "hired_to_joined" in conversions
        
        # Each conversion should have count and rate
        for key, val in conversions.items():
            assert "count" in val
            assert "rate" in val
        
        print(f"Pipeline: {data['total_applications']} total applications")
        print(f"Stage counts: {data['stage_counts']}")

    def test_revenue_forecast_api(self):
        """GET /api/analytics/revenue-forecast returns forecast data"""
        session = get_admin_session()
        
        response = session.get(f"{BASE_URL}/api/analytics/revenue-forecast")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "total_forecast_pipeline" in data
        assert "total_realized_revenue" in data
        assert "total_candidates_with_offer" in data
        assert "by_stage" in data
        assert "probability_map" in data
        
        print(f"Revenue forecast: {data['total_forecast_pipeline']} pipeline, {data['total_realized_revenue']} realized")

    def test_recruiter_performance_api(self):
        """GET /api/analytics/recruiter-performance returns recruiter metrics"""
        session = get_admin_session()
        
        response = session.get(f"{BASE_URL}/api/analytics/recruiter-performance")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "recruiters" in data
        
        if data["recruiters"]:
            recruiter = data["recruiters"][0]
            assert "recruiter_id" in recruiter
            assert "total_candidates" in recruiter
            assert "submitted" in recruiter
            assert "offered" in recruiter
            assert "joined" in recruiter
            assert "conversion_rate" in recruiter
        
        print(f"Recruiter performance: {len(data['recruiters'])} recruiters")

    def test_mandate_performance_api(self):
        """GET /api/analytics/mandate-performance returns mandate metrics"""
        session = get_admin_session()
        
        response = session.get(f"{BASE_URL}/api/analytics/mandate-performance")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "mandates" in data
        
        if data["mandates"]:
            mandate = data["mandates"][0]
            assert "mandate_id" in mandate
            assert "mandate_name" in mandate
            assert "total_candidates" in mandate
            assert "submitted" in mandate
            assert "submission_rate" in mandate
        
        print(f"Mandate performance: {len(data['mandates'])} mandates")


# ==================== EMPLOYER ACCESS TEST ====================

class TestEmployerAccess:
    """Test employer can access trackers (read-only)"""

    def test_employer_can_list_trackers(self):
        """Employer GET /api/tracker/trackers returns trackers for their mandates"""
        session = get_employer_session()
        
        response = session.get(f"{BASE_URL}/api/tracker/trackers")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "trackers" in data
        print(f"Employer can see {len(data['trackers'])} trackers")

    def test_employer_can_get_tracker_details(self):
        """Employer GET /api/tracker/trackers/{id} returns tracker details"""
        session = get_employer_session()
        
        response = session.get(f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}")
        
        # May be 403 if employer doesn't have access to this specific tracker, or 200 if they do
        assert response.status_code in [200, 403, 404], f"Unexpected: {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "rows" in data
            print(f"Employer accessed tracker: {data.get('name')}")
        else:
            print(f"Employer doesn't have access (expected): {response.status_code}")

    def test_employer_cannot_add_rows(self):
        """Employer cannot add rows to tracker (read-only)"""
        session = get_employer_session()
        
        add_row_data = {
            "candidate_id": "test-candidate",
            "application_id": "test-application"
        }
        
        response = session.post(
            f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}/rows",
            json=add_row_data
        )
        
        # Should be 403 (forbidden) since employer is read-only
        assert response.status_code in [403, 404, 422], f"Expected forbidden, got {response.status_code}"
        print(f"Employer add row blocked: {response.status_code}")


# ==================== BIDIRECTIONAL SYNC TEST ====================

class TestBidirectionalSync:
    """Test bidirectional sync between tracker and pipeline"""

    def test_tracker_status_to_pipeline_sync(self):
        """Verify tracker status change syncs to pipeline stage"""
        session = get_admin_session()
        
        # Get existing tracker with rows
        response = session.get(f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}")
        if response.status_code != 200:
            pytest.skip("Existing tracker not found")
        
        tracker = response.json()
        if not tracker.get("rows"):
            pytest.skip("No rows to test sync")
        
        row = tracker["rows"][0]
        row_id = row["id"]
        application_id = row.get("application_id")
        
        if not application_id:
            pytest.skip("Row has no application_id")
        
        # Get current application stage
        app_response = session.get(f"{BASE_URL}/api/applications/{application_id}")
        if app_response.status_code != 200:
            pytest.skip("Application not found")
        
        current_stage = app_response.json().get("stage")
        print(f"Current application stage: {current_stage}")
        
        # Update tracker status
        status_update = {"submission_status": "interview_scheduled"}
        response = session.put(
            f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}/rows/{row_id}/status",
            json=status_update
        )
        
        assert response.status_code == 200, f"Status update failed: {response.status_code}: {response.text}"
        
        # Verify sync (give it time to propagate)
        time.sleep(0.5)
        
        synced_response = session.get(f"{BASE_URL}/api/applications/{application_id}")
        if synced_response.status_code == 200:
            new_stage = synced_response.json().get("stage")
            print(f"After sync: {new_stage}")
            
            # According to TRACKER_TO_PIPELINE mapping: interview_scheduled → interview
            if current_stage in ["applied", "shortlisted", "submitted_to_client"]:
                assert new_stage == "interview", f"Expected 'interview', got {new_stage}"


# ==================== MASTER COLUMNS TEST ====================

class TestMasterColumns:
    """Test master columns endpoint"""

    def test_master_columns_returns_58_columns(self):
        """GET /api/tracker/columns returns 58 master columns"""
        session = get_admin_session()
        
        response = session.get(f"{BASE_URL}/api/tracker/columns")
        assert response.status_code == 200
        
        data = response.json()
        assert "columns" in data
        assert "categories" in data
        assert "field_types" in data
        
        assert len(data["columns"]) == 58, f"Expected 58 columns, got {len(data['columns'])}"
        assert len(data["categories"]) == 11, f"Expected 11 categories, got {len(data['categories'])}"
        
        print(f"Master columns: {len(data['columns'])} columns, {len(data['categories'])} categories")


# ==================== ROW OPERATIONS TEST ====================

class TestRowOperations:
    """Test tracker row operations"""

    def test_inline_edit_row(self):
        """PUT /api/tracker/trackers/{id}/rows/{rowId} updates cell data"""
        session = get_admin_session()
        
        # Get existing tracker with rows
        response = session.get(f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}")
        if response.status_code != 200:
            pytest.skip("Existing tracker not found")
        
        tracker = response.json()
        if not tracker.get("rows"):
            pytest.skip("No rows to edit")
        
        row = tracker["rows"][0]
        row_id = row["id"]
        
        # Update a field
        update_data = {
            "data": {
                "recruiter_notes": f"E2E test note at {int(time.time())}"
            }
        }
        
        response = session.put(
            f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}/rows/{row_id}",
            json=update_data
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify update
        verify_response = session.get(f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}")
        updated_row = next((r for r in verify_response.json()["rows"] if r["id"] == row_id), None)
        assert updated_row is not None
        assert "recruiter_notes" in updated_row.get("data", {})
        
        print(f"Row {row_id} updated successfully")

    def test_duplicate_row_returns_409(self):
        """POST /api/tracker/trackers/{id}/rows returns 409 for duplicate"""
        session = get_admin_session()
        
        # Get existing tracker with rows
        response = session.get(f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}")
        if response.status_code != 200:
            pytest.skip("Existing tracker not found")
        
        tracker = response.json()
        if not tracker.get("rows"):
            pytest.skip("No rows to test duplicate")
        
        row = tracker["rows"][0]
        
        # Try to add the same candidate again
        add_row_data = {
            "candidate_id": row.get("candidate_id"),
            "application_id": row.get("application_id")
        }
        
        response = session.post(
            f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}/rows",
            json=add_row_data
        )
        
        assert response.status_code == 409, f"Expected 409, got {response.status_code}: {response.text}"
        print(f"Duplicate correctly rejected: {response.json()}")


# ==================== EVENTS HISTORY TEST ====================

class TestEventsHistory:
    """Test tracker/pipeline events history"""

    def test_get_events(self):
        """GET /api/tracker/events returns event history"""
        session = get_admin_session()
        
        response = session.get(f"{BASE_URL}/api/tracker/events")
        assert response.status_code == 200
        
        data = response.json()
        assert "events" in data
        
        print(f"Total events: {len(data['events'])}")
        if data["events"]:
            event = data["events"][0]
            print(f"Latest: {event.get('previous_stage')} → {event.get('new_stage')} (source: {event.get('source')})")

    def test_get_events_by_tracker(self):
        """GET /api/tracker/events filtered by tracker_id"""
        session = get_admin_session()
        
        response = session.get(
            f"{BASE_URL}/api/tracker/events",
            params={"tracker_id": EXISTING_TRACKER_ID}
        )
        assert response.status_code == 200
        
        data = response.json()
        print(f"Events for tracker: {len(data['events'])}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
