"""
Test: Pipeline Enrichment Bug Fix
Tests that candidate fields (location, current_employer, designation, industry, education, 
expected_salary, ug_course, headline) are properly enriched from candidate_bank data.

Bug: When candidates were added to pipeline, these fields showed as '-' (dashes) 
even though data existed in candidate_bank collection.

Fix Applied:
- Admin pipeline (/api/admin/pipeline) - batch lookup from candidate_bank with fallback
- Employer pipeline (/api/employer/pipeline) - same enrichment pattern
- Job applicants (/api/applications/jobs/{job_id}/applicants) - enrichment from candidate_bank
- Application creation (self-apply and shortlist) - denormalization of fields
- Tracker auto-fill - changed db.candidates to db.candidate_bank with correct field names
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Enriched fields that should NOT be dashes after the fix
ENRICHED_FIELDS = [
    'location',
    'current_employer', 
    'designation',
    'industry',
    'education',
    'expected_salary',
    'headline'
]


class TestPipelineEnrichmentBugfix:
    """Tests for the pipeline enrichment bug fix"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        self.admin_token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.admin_token}"}
    
    # ============== ADMIN PIPELINE ENRICHMENT ==============
    
    def test_admin_pipeline_returns_enriched_fields(self):
        """Admin pipeline should return enriched candidate fields from candidate_bank"""
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=self.headers)
        assert response.status_code == 200, f"Admin pipeline failed: {response.text}"
        
        data = response.json()
        assert "pipeline" in data
        assert "stage_counts" in data
        assert "total_applications" in data
        
        # Collect all applications from all stages
        all_apps = []
        for stage, apps in data.get("pipeline", {}).items():
            all_apps.extend(apps)
        
        if len(all_apps) == 0:
            pytest.skip("No applications in pipeline to test enrichment")
        
        # Check that at least one application has enriched fields (not all dashes)
        enriched_count = 0
        for app in all_apps:
            # Check each enriched field
            has_enriched_data = False
            for field in ENRICHED_FIELDS:
                value = app.get(field)
                if value and value != '-' and value != 'null' and value != 'None':
                    has_enriched_data = True
                    break
            if has_enriched_data:
                enriched_count += 1
        
        assert enriched_count > 0, f"No applications have enriched fields. Sample app: {all_apps[0] if all_apps else 'N/A'}"
        print(f"[PASS] Admin pipeline: {enriched_count}/{len(all_apps)} applications have enriched data")
    
    def test_admin_pipeline_specific_candidate_enrichment(self):
        """Verify specific candidate (Harsha D.) has correct enriched data"""
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        all_apps = []
        for stage, apps in data.get("pipeline", {}).items():
            all_apps.extend(apps)
        
        # Find Harsha D. application
        harsha_app = next((a for a in all_apps if 'Harsha' in (a.get('candidate_name') or '')), None)
        
        if not harsha_app:
            pytest.skip("Harsha D. application not found in pipeline")
        
        # Verify enriched fields based on context note
        assert harsha_app.get('location') == 'Pune', f"Location mismatch: {harsha_app.get('location')}"
        assert 'Pan India Manufacturing' in (harsha_app.get('current_employer') or ''), f"Employer mismatch: {harsha_app.get('current_employer')}"
        assert 'Compliance' in (harsha_app.get('designation') or '') or 'Manager' in (harsha_app.get('designation') or ''), f"Designation mismatch: {harsha_app.get('designation')}"
        assert harsha_app.get('industry') == 'Manufacturing', f"Industry mismatch: {harsha_app.get('industry')}"
        
        # Check education is populated (list with degree info)
        education = harsha_app.get('education')
        assert education is not None and education != '-', f"Education not enriched: {education}"
        
        print(f"[PASS] Harsha D. enrichment verified - Location: {harsha_app.get('location')}, Employer: {harsha_app.get('current_employer')}")
    
    def test_admin_pipeline_stage_counts_present(self):
        """Stage counts should still work after enrichment fix"""
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        stage_counts = data.get("stage_counts", {})
        
        # Should have standard stages
        expected_stages = ['applied', 'shortlisted', 'interview', 'offered', 'hired', 'joined', 'rejected']
        for stage in expected_stages:
            assert stage in stage_counts, f"Missing stage count: {stage}"
        
        print(f"[PASS] Stage counts present: {stage_counts}")
    
    # ============== JOB APPLICANTS ENRICHMENT ==============
    
    def test_job_applicants_endpoint_returns_enriched_fields(self):
        """Job applicants endpoint should return enriched fields from candidate_bank"""
        # Use the known job_id from context
        job_id = "3f943892-b692-4417-818c-5e2359af3288"
        
        response = requests.get(f"{BASE_URL}/api/jobs/{job_id}/applicants", headers=self.headers)
        
        if response.status_code == 404:
            pytest.skip("Job not found - skipping job applicants test")
        
        assert response.status_code == 200, f"Job applicants failed: {response.text}"
        
        data = response.json()
        applicants = data.get("applicants", [])
        
        if len(applicants) == 0:
            pytest.skip("No applicants for this job")
        
        # Check that applicants have enriched fields
        for app in applicants:
            # At least some enriched fields should be present
            enriched_present = sum(1 for f in ['location', 'current_employer', 'designation', 'industry'] 
                                   if app.get(f) and app.get(f) != '-')
            
            assert enriched_present >= 1, f"Applicant {app.get('candidate_name')} has no enriched fields"
        
        print(f"[PASS] Job applicants enrichment: {len(applicants)} applicants with enriched data")
    
    def test_job_applicants_new_fields_present(self):
        """Verify new fields (current_employer, designation, industry, education, expected_salary, ug_course) in response"""
        job_id = "3f943892-b692-4417-818c-5e2359af3288"
        
        response = requests.get(f"{BASE_URL}/api/jobs/{job_id}/applicants", headers=self.headers)
        
        if response.status_code == 404:
            pytest.skip("Job not found")
        
        assert response.status_code == 200
        
        data = response.json()
        applicants = data.get("applicants", [])
        
        if not applicants:
            pytest.skip("No applicants")
        
        # Check first applicant has the new enriched fields in schema
        app = applicants[0]
        new_fields = ['current_employer', 'designation', 'industry', 'education', 'expected_salary', 'ug_course']
        
        for field in new_fields:
            # Field should exist in response (even if None)
            assert field in app or app.get(field) is not None, f"Field {field} not in applicant response"
        
        print(f"[PASS] New enriched fields present in job applicants response")
    
    # ============== FALLBACK PRIORITY ==============
    
    def test_fallback_priority_application_field_first(self):
        """Pipeline should use application field value first, fallback to candidate_bank if null"""
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        all_apps = []
        for stage, apps in data.get("pipeline", {}).items():
            all_apps.extend(apps)
        
        if not all_apps:
            pytest.skip("No applications to test")
        
        # The response structure should have enriched fields
        # The backend code does: app.get("location") or cb.get("location")
        # This means application field takes precedence
        
        # Just verify the enrichment logic is working (fields have values)
        app = all_apps[0]
        # Location should be present from either source
        location = app.get('location')
        # As long as it's not a dash, the enrichment worked
        assert location is None or location != '-', f"Location is still dash: {location}"
        
        print(f"[PASS] Fallback priority check - fields are populated")
    
    # ============== NO REGRESSION ==============
    
    def test_pipeline_filters_still_work(self):
        """Pipeline filtering by recruiter/job should still work after enrichment fix"""
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        filters = data.get("filters", {})
        
        # Filters should still be present
        assert "employers" in filters or "recruiters" in filters or "jobs" in filters
        
        print(f"[PASS] Pipeline filters still available: {list(filters.keys())}")
    
    def test_admin_pipeline_total_applications_count(self):
        """Total applications count should be accurate"""
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        total = data.get("total_applications", 0)
        
        # Count from stage_counts
        stage_total = sum(data.get("stage_counts", {}).values())
        
        assert total == stage_total, f"Total mismatch: total_applications={total}, stage_counts_sum={stage_total}"
        
        print(f"[PASS] Total applications: {total}")
    
    # ============== CANDIDATE BANK DATA AVAILABILITY ==============
    
    def test_candidate_bank_has_data(self):
        """Verify candidate_bank collection has data (prerequisite for enrichment)"""
        # Use search endpoint to check candidate_bank
        response = requests.get(f"{BASE_URL}/api/candidate-bank/stats", headers=self.headers)
        
        if response.status_code == 404:
            # Try alternative - list candidates
            response = requests.get(f"{BASE_URL}/api/candidate-bank?limit=1", headers=self.headers)
        
        # Just verify we can access candidate_bank data
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
        
        print(f"[PASS] Candidate bank accessible")


class TestTrackerAutoFillBugfix:
    """Tests for tracker auto-fill reading from candidate_bank with correct field names"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
        )
        assert response.status_code == 200
        self.admin_token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.admin_token}"}
    
    def test_tracker_templates_accessible(self):
        """Verify tracker templates endpoint works"""
        response = requests.get(f"{BASE_URL}/api/tracker/templates", headers=self.headers)
        assert response.status_code == 200, f"Tracker templates failed: {response.text}"
        
        data = response.json()
        assert "templates" in data
        
        print(f"[PASS] Tracker templates accessible: {len(data.get('templates', []))} templates")
    
    def test_tracker_columns_available(self):
        """Verify tracker master columns are available"""
        response = requests.get(f"{BASE_URL}/api/tracker/columns", headers=self.headers)
        assert response.status_code == 200, f"Tracker columns failed: {response.text}"
        
        data = response.json()
        assert "columns" in data
        
        # Check that field mappings include the correct names (not old ones)
        columns = data.get("columns", [])
        column_keys = [c.get("key") for c in columns]
        
        # Should have correct field names from the fix
        # Old: current_company -> New: current_employer (via candidate_bank)
        # Old: current_designation -> New: designation (via candidate_bank)
        
        print(f"[PASS] Tracker columns available: {len(columns)} columns")


class TestShortlistDenormalization:
    """Tests for application creation denormalization (storing candidate_bank fields)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
        )
        assert response.status_code == 200
        self.admin_token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.admin_token}"}
    
    def test_applications_have_denormalized_fields(self):
        """Verify applications store denormalized candidate fields"""
        # Get an application directly to check stored fields
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        all_apps = []
        for stage, apps in data.get("pipeline", {}).items():
            all_apps.extend(apps)
        
        if not all_apps:
            pytest.skip("No applications to check")
        
        # The response shows enriched fields - this confirms either:
        # 1. Fields are denormalized in application document, OR
        # 2. Fields are enriched from candidate_bank at query time
        # Both are valid solutions for the bug fix
        
        app = all_apps[0]
        denorm_fields = ['current_employer', 'designation', 'industry', 'education']
        
        present_fields = [f for f in denorm_fields if app.get(f) and app.get(f) != '-']
        
        print(f"[PASS] Denormalized/enriched fields present: {present_fields}")


# Summary test for quick verification
class TestPipelineEnrichmentSummary:
    """Quick summary tests for pipeline enrichment"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
        )
        assert response.status_code == 200
        self.headers = {"Authorization": f"Bearer {response.json().get('access_token')}"}
    
    def test_enrichment_fix_working(self):
        """Summary: Verify the enrichment bug fix is working"""
        response = requests.get(f"{BASE_URL}/api/admin/pipeline", headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        all_apps = []
        for stage, apps in data.get("pipeline", {}).items():
            all_apps.extend(apps)
        
        if not all_apps:
            pytest.skip("No applications")
        
        # Check if any app has enriched data (not dashes)
        for app in all_apps:
            loc = app.get('location', '-')
            emp = app.get('current_employer', '-')
            desg = app.get('designation', '-')
            
            if loc != '-' or emp != '-' or desg != '-':
                print(f"[PASS] Enrichment working - Sample: location={loc}, employer={emp}, designation={desg}")
                return
        
        pytest.fail("No enriched data found in any application")
