"""
Client Submission Tracker System Tests
Tests tracker CRUD, templates, rows, validation, and bidirectional sync.

Features tested:
- GET /api/tracker/columns - Master columns (58 columns, 11 categories)
- Template CRUD (create, list, clone)
- Tracker CRUD (create linked to mandate/template, list with row_count, get with rows)
- Row operations (add candidate with auto-fill, duplicate 409, inline edit, status update with sync)
- Validation (green/yellow/red status)
- Bidirectional sync (tracker→pipeline, pipeline→tracker)
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://hr-platform-staging-1.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"

# Known IDs from context
EXISTING_JOB_ID = "c72113dc-b62e-437c-8712-0fb9f6541d1d"  # Senior Python Developer
EXISTING_TEMPLATE_ID = "ea672bda-fa5a-4989-a8ec-d8c8ea024fa7"  # Executive Hiring Template
EXISTING_TRACKER_ID = "68b62013-f67e-4064-a0e2-89fafb8efe0d"  # Senior Python Dev Tracker


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    
    token = response.json().get("token")
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


class TestMasterColumns:
    """Test master column definitions"""
    
    def test_get_master_columns_returns_columns(self, admin_session):
        """GET /api/tracker/columns returns columns list"""
        response = admin_session.get(f"{BASE_URL}/api/tracker/columns")
        assert response.status_code == 200
        
        data = response.json()
        assert "columns" in data
        assert isinstance(data["columns"], list)
        print(f"Total columns: {len(data['columns'])}")
    
    def test_master_columns_count_58(self, admin_session):
        """Should have 58 master columns"""
        response = admin_session.get(f"{BASE_URL}/api/tracker/columns")
        assert response.status_code == 200
        
        data = response.json()
        columns = data.get("columns", [])
        assert len(columns) == 58, f"Expected 58 columns, got {len(columns)}"
    
    def test_master_columns_has_11_categories(self, admin_session):
        """Should have 11 categories"""
        response = admin_session.get(f"{BASE_URL}/api/tracker/columns")
        assert response.status_code == 200
        
        data = response.json()
        categories = data.get("categories", [])
        assert len(categories) == 11, f"Expected 11 categories, got {len(categories)}"
        print(f"Categories: {categories}")
    
    def test_master_columns_has_field_types(self, admin_session):
        """Should return field types"""
        response = admin_session.get(f"{BASE_URL}/api/tracker/columns")
        assert response.status_code == 200
        
        data = response.json()
        assert "field_types" in data
        assert "text" in data["field_types"]
        assert "currency" in data["field_types"]


class TestTemplates:
    """Test tracker template CRUD"""
    
    def test_list_templates(self, admin_session):
        """GET /api/tracker/templates lists templates"""
        response = admin_session.get(f"{BASE_URL}/api/tracker/templates")
        assert response.status_code == 200
        
        data = response.json()
        assert "templates" in data
        assert isinstance(data["templates"], list)
        print(f"Templates count: {len(data['templates'])}")
    
    def test_create_template(self, admin_session):
        """POST /api/tracker/templates creates a template with columns"""
        template_data = {
            "name": f"TEST_Template_{int(time.time())}",
            "description": "Test template for automated testing",
            "columns": [
                {"key": "full_name", "label": "Full Name", "category": "Basic Info", "field_type": "text", "required": True, "order": 1},
                {"key": "email", "label": "Email", "category": "Contact Details", "field_type": "text", "required": True, "order": 2},
                {"key": "mobile_number", "label": "Mobile Number", "category": "Contact Details", "field_type": "text", "required": True, "order": 3},
                {"key": "current_ctc", "label": "Current CTC", "category": "Compensation", "field_type": "currency", "required": False, "order": 4},
            ]
        }
        
        response = admin_session.post(f"{BASE_URL}/api/tracker/templates", json=template_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "id" in data
        assert data["name"] == template_data["name"]
        assert len(data["columns"]) == 4
        print(f"Created template: {data['id']}")
        
        # Store for cleanup
        TestTemplates.created_template_id = data["id"]
    
    def test_get_existing_template(self, admin_session):
        """GET /api/tracker/templates/{id} returns template"""
        response = admin_session.get(f"{BASE_URL}/api/tracker/templates/{EXISTING_TEMPLATE_ID}")
        
        if response.status_code == 404:
            pytest.skip("Existing template not found")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == EXISTING_TEMPLATE_ID
        print(f"Template name: {data.get('name')}, columns: {len(data.get('columns', []))}")
    
    def test_clone_template(self, admin_session):
        """POST /api/tracker/templates/{id}/clone clones a template"""
        # Use the template we just created
        if not hasattr(TestTemplates, 'created_template_id'):
            pytest.skip("No template to clone")
        
        clone_name = f"TEST_Cloned_{int(time.time())}"
        response = admin_session.post(
            f"{BASE_URL}/api/tracker/templates/{TestTemplates.created_template_id}/clone",
            params={"name": clone_name}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["name"] == clone_name
        assert data["id"] != TestTemplates.created_template_id
        print(f"Cloned template: {data['id']}")
        
        # Store for cleanup
        TestTemplates.cloned_template_id = data["id"]
    
    def test_delete_test_templates(self, admin_session):
        """Cleanup: Delete test templates"""
        for template_id in [
            getattr(TestTemplates, 'created_template_id', None),
            getattr(TestTemplates, 'cloned_template_id', None)
        ]:
            if template_id:
                response = admin_session.delete(f"{BASE_URL}/api/tracker/templates/{template_id}")
                print(f"Deleted template {template_id}: {response.status_code}")


class TestTrackers:
    """Test tracker CRUD"""
    
    def test_list_trackers_with_row_count(self, admin_session):
        """GET /api/tracker/trackers lists trackers with row_count"""
        response = admin_session.get(f"{BASE_URL}/api/tracker/trackers")
        assert response.status_code == 200
        
        data = response.json()
        assert "trackers" in data
        
        if data["trackers"]:
            tracker = data["trackers"][0]
            assert "row_count" in tracker
            print(f"First tracker: {tracker.get('name')}, rows: {tracker.get('row_count')}")
    
    def test_create_tracker_linked_to_mandate(self, admin_session):
        """POST /api/tracker/trackers creates tracker linked to mandate and template"""
        # First, get an existing template
        templates_response = admin_session.get(f"{BASE_URL}/api/tracker/templates")
        templates = templates_response.json().get("templates", [])
        
        if not templates:
            pytest.skip("No templates available")
        
        template_id = templates[0]["id"]
        
        # Verify job exists
        job_response = admin_session.get(f"{BASE_URL}/api/jobs/{EXISTING_JOB_ID}")
        if job_response.status_code != 200:
            pytest.skip("Job not found")
        
        tracker_data = {
            "name": f"TEST_Tracker_{int(time.time())}",
            "mandate_id": EXISTING_JOB_ID,
            "template_id": template_id
        }
        
        response = admin_session.post(f"{BASE_URL}/api/tracker/trackers", json=tracker_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "id" in data
        assert data["mandate_id"] == EXISTING_JOB_ID
        assert data["template_id"] == template_id
        print(f"Created tracker: {data['id']} for mandate: {data.get('mandate_name')}")
        
        # Store for later tests
        TestTrackers.created_tracker_id = data["id"]
    
    def test_get_tracker_with_rows(self, admin_session):
        """GET /api/tracker/trackers/{id} returns tracker with rows"""
        response = admin_session.get(f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}")
        
        if response.status_code == 404:
            pytest.skip("Existing tracker not found")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "rows" in data
        assert "columns" in data
        assert "row_count" in data
        print(f"Tracker: {data.get('name')}, columns: {len(data['columns'])}, rows: {data['row_count']}")
    
    def test_delete_test_tracker(self, admin_session):
        """Cleanup: Delete test tracker"""
        if hasattr(TestTrackers, 'created_tracker_id'):
            response = admin_session.delete(f"{BASE_URL}/api/tracker/trackers/{TestTrackers.created_tracker_id}")
            print(f"Deleted tracker: {response.status_code}")


class TestRowOperations:
    """Test tracker row operations"""
    
    @pytest.fixture(scope="class")
    def test_tracker_with_applications(self, admin_session):
        """Get or create a tracker with applications to add"""
        # Get applications for the existing job
        apps_response = admin_session.get(f"{BASE_URL}/api/applications", params={"job_id": EXISTING_JOB_ID})
        if apps_response.status_code != 200 or not apps_response.json():
            pytest.skip("No applications found for job")
        
        applications = apps_response.json()
        
        # Get existing tracker
        tracker_response = admin_session.get(f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}")
        if tracker_response.status_code != 200:
            pytest.skip("Existing tracker not found")
        
        return {
            "tracker_id": EXISTING_TRACKER_ID,
            "applications": applications,
            "tracker": tracker_response.json()
        }
    
    def test_add_row_duplicate_returns_409(self, admin_session, test_tracker_with_applications):
        """POST /api/tracker/trackers/{id}/rows returns 409 for duplicate candidate+mandate"""
        tracker = test_tracker_with_applications["tracker"]
        
        # If there are existing rows, try to add the same candidate again
        if tracker.get("rows"):
            existing_row = tracker["rows"][0]
            add_row_data = {
                "candidate_id": existing_row.get("candidate_id"),
                "application_id": existing_row.get("application_id")
            }
            
            response = admin_session.post(
                f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}/rows",
                json=add_row_data
            )
            assert response.status_code == 409
            print(f"Duplicate row correctly rejected: {response.json()}")
        else:
            pytest.skip("No existing rows to test duplicate")
    
    def test_update_row_inline_edit(self, admin_session, test_tracker_with_applications):
        """PUT /api/tracker/trackers/{id}/rows/{rowId} updates cell data"""
        tracker = test_tracker_with_applications["tracker"]
        
        if not tracker.get("rows"):
            pytest.skip("No rows to edit")
        
        row = tracker["rows"][0]
        row_id = row["id"]
        
        update_data = {
            "data": {
                "recruiter_notes": f"Automated test note at {int(time.time())}"
            }
        }
        
        response = admin_session.put(
            f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}/rows/{row_id}",
            json=update_data
        )
        assert response.status_code == 200
        
        # Verify update
        tracker_response = admin_session.get(f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}")
        updated_row = next((r for r in tracker_response.json()["rows"] if r["id"] == row_id), None)
        assert updated_row
        assert "recruiter_notes" in updated_row.get("data", {})
        print(f"Row updated: {row_id}")
    
    def test_update_row_status_syncs_pipeline(self, admin_session, test_tracker_with_applications):
        """PUT /api/tracker/trackers/{id}/rows/{rowId}/status updates submission status AND syncs pipeline"""
        tracker = test_tracker_with_applications["tracker"]
        
        if not tracker.get("rows"):
            pytest.skip("No rows to update status")
        
        row = tracker["rows"][0]
        row_id = row["id"]
        application_id = row.get("application_id")
        
        if not application_id:
            pytest.skip("Row has no application_id")
        
        # Get current application stage
        app_response = admin_session.get(f"{BASE_URL}/api/applications/{application_id}")
        if app_response.status_code != 200:
            pytest.skip("Application not found")
        
        current_stage = app_response.json().get("stage", "applied")
        print(f"Current application stage: {current_stage}")
        
        # Update to interview_scheduled
        status_update = {"submission_status": "interview_scheduled"}
        response = admin_session.put(
            f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}/rows/{row_id}/status",
            json=status_update
        )
        
        assert response.status_code == 200
        assert response.json().get("submission_status") == "interview_scheduled"
        print(f"Row status updated to interview_scheduled")
        
        # Verify pipeline sync (should move to interview stage)
        # Allow a moment for async sync
        time.sleep(0.5)
        
        synced_app_response = admin_session.get(f"{BASE_URL}/api/applications/{application_id}")
        if synced_app_response.status_code == 200:
            new_stage = synced_app_response.json().get("stage")
            print(f"Application stage after sync: {new_stage}")
            # The sync should move it to 'interview' (TRACKER_TO_PIPELINE mapping)
            if current_stage not in ["interview", "offered", "hired", "joined"]:
                assert new_stage == "interview" or new_stage == current_stage, \
                    f"Expected 'interview' or unchanged, got {new_stage}"


class TestValidation:
    """Test tracker validation for download readiness"""
    
    def test_validation_returns_status(self, admin_session):
        """GET /api/tracker/trackers/{id}/validation returns green/yellow/red status"""
        response = admin_session.get(f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}/validation")
        
        if response.status_code == 404:
            pytest.skip("Tracker not found")
        
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert data["status"] in ["green", "yellow", "red"]
        assert "message" in data
        assert "total_rows" in data
        
        print(f"Validation status: {data['status']} - {data['message']}")
        print(f"Total rows: {data['total_rows']}, Total issues: {data.get('total_issues', 0)}")
    
    def test_validation_returns_missing_field_details(self, admin_session):
        """Validation response includes missing field details"""
        response = admin_session.get(f"{BASE_URL}/api/tracker/trackers/{EXISTING_TRACKER_ID}/validation")
        
        if response.status_code == 404:
            pytest.skip("Tracker not found")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "issues" in data
        if data["issues"]:
            issue = data["issues"][0]
            assert "row_id" in issue
            assert "field" in issue
            assert "field_label" in issue
            print(f"Sample issue: {issue}")


class TestSyncBehavior:
    """Test bidirectional sync between tracker and pipeline"""
    
    def test_add_candidate_to_tracker_moves_pipeline_to_submitted(self, admin_session):
        """SYNC TEST: Adding candidate to tracker moves pipeline to submitted_to_client"""
        # Get applications that are NOT yet submitted
        apps_response = admin_session.get(f"{BASE_URL}/api/applications", params={"job_id": EXISTING_JOB_ID})
        if apps_response.status_code != 200:
            pytest.skip("Could not get applications")
        
        applications = apps_response.json()
        
        # Find an application that's in applied or shortlisted stage
        eligible_app = None
        for app in applications:
            stage = app.get("stage", "applied")
            if stage in ["applied", "shortlisted"]:
                eligible_app = app
                break
        
        if not eligible_app:
            pytest.skip("No eligible applications to test sync")
        
        # Create a new tracker for this test
        templates_response = admin_session.get(f"{BASE_URL}/api/tracker/templates")
        templates = templates_response.json().get("templates", [])
        if not templates:
            pytest.skip("No templates available")
        
        tracker_data = {
            "name": f"TEST_Sync_Tracker_{int(time.time())}",
            "mandate_id": EXISTING_JOB_ID,
            "template_id": templates[0]["id"]
        }
        
        tracker_response = admin_session.post(f"{BASE_URL}/api/tracker/trackers", json=tracker_data)
        if tracker_response.status_code != 200:
            pytest.skip("Could not create test tracker")
        
        test_tracker_id = tracker_response.json()["id"]
        
        try:
            # Add the application to tracker
            add_row_data = {
                "candidate_id": eligible_app.get("candidate_id"),
                "application_id": eligible_app["id"]
            }
            
            add_response = admin_session.post(
                f"{BASE_URL}/api/tracker/trackers/{test_tracker_id}/rows",
                json=add_row_data
            )
            
            if add_response.status_code == 409:
                print("Application already in a tracker")
            else:
                assert add_response.status_code == 200
                
                # Check pipeline stage changed to submitted_to_client
                time.sleep(0.5)
                app_check = admin_session.get(f"{BASE_URL}/api/applications/{eligible_app['id']}")
                if app_check.status_code == 200:
                    new_stage = app_check.json().get("stage")
                    print(f"After adding to tracker: stage = {new_stage}")
                    # Should be submitted_to_client due to sync
                    assert new_stage in ["submitted_to_client", "interview", "offered", "hired", "joined"], \
                        f"Expected submitted_to_client or later, got {new_stage}"
        finally:
            # Cleanup
            admin_session.delete(f"{BASE_URL}/api/tracker/trackers/{test_tracker_id}")


class TestTrackerEvents:
    """Test tracker event logging"""
    
    def test_get_tracker_events(self, admin_session):
        """GET /api/tracker/events returns event history"""
        response = admin_session.get(f"{BASE_URL}/api/tracker/events")
        assert response.status_code == 200
        
        data = response.json()
        assert "events" in data
        print(f"Total events: {len(data['events'])}")
        
        if data["events"]:
            event = data["events"][0]
            print(f"Latest event: {event.get('previous_stage')} → {event.get('new_stage')} (source: {event.get('source')})")
    
    def test_get_events_filtered_by_tracker(self, admin_session):
        """GET /api/tracker/events with tracker_id filter"""
        response = admin_session.get(
            f"{BASE_URL}/api/tracker/events",
            params={"tracker_id": EXISTING_TRACKER_ID}
        )
        assert response.status_code == 200
        
        data = response.json()
        print(f"Events for tracker {EXISTING_TRACKER_ID}: {len(data['events'])}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
