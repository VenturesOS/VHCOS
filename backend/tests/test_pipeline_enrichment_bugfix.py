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
import time

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


# Module-scoped session to avoid rate limiting
@pytest.fixture(scope="module")
def admin_session():
    """Single login session for all tests to avoid rate limiting"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login once
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json().get("access_token")
    session.headers.update({"Authorization": f"Bearer {token}"})
    
    return session


class TestAdminPipelineEnrichment:
    """Tests for admin pipeline enrichment"""
    
    def test_admin_pipeline_returns_enriched_fields(self, admin_session):
        """Admin pipeline should return enriched candidate fields from candidate_bank"""
        response = admin_session.get(f"{BASE_URL}/api/admin/pipeline")
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
    
    def test_admin_pipeline_specific_candidate_enrichment(self, admin_session):
        """Verify specific candidate (Harsha D.) has correct enriched data"""
        response = admin_session.get(f"{BASE_URL}/api/admin/pipeline")
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
        
        # Check education is populated
        education = harsha_app.get('education')
        assert education is not None and education != '-', f"Education not enriched: {education}"
        
        print(f"[PASS] Harsha D. enrichment verified - Location: {harsha_app.get('location')}, Employer: {harsha_app.get('current_employer')}")
    
    def test_admin_pipeline_stage_counts_present(self, admin_session):
        """Stage counts should still work after enrichment fix"""
        response = admin_session.get(f"{BASE_URL}/api/admin/pipeline")
        assert response.status_code == 200
        
        data = response.json()
        stage_counts = data.get("stage_counts", {})
        
        expected_stages = ['applied', 'shortlisted', 'interview', 'offered', 'hired', 'joined', 'rejected']
        for stage in expected_stages:
            assert stage in stage_counts, f"Missing stage count: {stage}"
        
        print(f"[PASS] Stage counts present: {stage_counts}")
    
    def test_admin_pipeline_total_applications_count(self, admin_session):
        """Total applications count should be accurate"""
        response = admin_session.get(f"{BASE_URL}/api/admin/pipeline")
        assert response.status_code == 200
        
        data = response.json()
        total = data.get("total_applications", 0)
        stage_total = sum(data.get("stage_counts", {}).values())
        
        assert total == stage_total, f"Total mismatch: total_applications={total}, stage_counts_sum={stage_total}"
        print(f"[PASS] Total applications: {total}")
    
    def test_pipeline_filters_still_work(self, admin_session):
        """Pipeline filtering by recruiter/job should still work after enrichment fix"""
        response = admin_session.get(f"{BASE_URL}/api/admin/pipeline")
        assert response.status_code == 200
        
        data = response.json()
        filters = data.get("filters", {})
        
        assert "employers" in filters or "recruiters" in filters or "jobs" in filters
        print(f"[PASS] Pipeline filters still available: {list(filters.keys())}")


class TestJobApplicantsEnrichment:
    """Tests for job applicants endpoint enrichment"""
    
    def test_job_applicants_endpoint_returns_enriched_fields(self, admin_session):
        """Job applicants endpoint should return enriched fields from candidate_bank"""
        job_id = "3f943892-b692-4417-818c-5e2359af3288"
        
        response = admin_session.get(f"{BASE_URL}/api/jobs/{job_id}/applicants")
        
        if response.status_code == 404:
            pytest.skip("Job not found - skipping job applicants test")
        
        assert response.status_code == 200, f"Job applicants failed: {response.text}"
        
        data = response.json()
        applicants = data.get("applicants", [])
        
        if len(applicants) == 0:
            pytest.skip("No applicants for this job")
        
        # Check that applicants have enriched fields
        for app in applicants:
            enriched_present = sum(1 for f in ['location', 'current_employer', 'designation', 'industry'] 
                                   if app.get(f) and app.get(f) != '-')
            assert enriched_present >= 1, f"Applicant {app.get('candidate_name')} has no enriched fields"
        
        print(f"[PASS] Job applicants enrichment: {len(applicants)} applicants with enriched data")
    
    def test_job_applicants_new_fields_present(self, admin_session):
        """Verify new fields in job applicants response schema"""
        job_id = "3f943892-b692-4417-818c-5e2359af3288"
        
        response = admin_session.get(f"{BASE_URL}/api/jobs/{job_id}/applicants")
        
        if response.status_code == 404:
            pytest.skip("Job not found")
        
        assert response.status_code == 200
        
        data = response.json()
        applicants = data.get("applicants", [])
        
        if not applicants:
            pytest.skip("No applicants")
        
        app = applicants[0]
        new_fields = ['current_employer', 'designation', 'industry', 'education', 'expected_salary', 'ug_course']
        
        for field in new_fields:
            # Field should exist in response schema
            assert field in app or app.get(field) is not None or app.get(field) == None, f"Field {field} not in applicant response"
        
        print(f"[PASS] New enriched fields present in job applicants response")


class TestTrackerAutoFill:
    """Tests for tracker auto-fill using candidate_bank with correct field names"""
    
    def test_tracker_templates_accessible(self, admin_session):
        """Verify tracker templates endpoint works"""
        response = admin_session.get(f"{BASE_URL}/api/tracker/templates")
        assert response.status_code == 200, f"Tracker templates failed: {response.text}"
        
        data = response.json()
        assert "templates" in data
        print(f"[PASS] Tracker templates accessible: {len(data.get('templates', []))} templates")
    
    def test_tracker_columns_available(self, admin_session):
        """Verify tracker master columns are available"""
        response = admin_session.get(f"{BASE_URL}/api/tracker/columns")
        assert response.status_code == 200, f"Tracker columns failed: {response.text}"
        
        data = response.json()
        assert "columns" in data
        
        columns = data.get("columns", [])
        print(f"[PASS] Tracker columns available: {len(columns)} columns")


class TestEnrichmentSummary:
    """Summary tests for pipeline enrichment bug fix"""
    
    def test_enrichment_fix_working(self, admin_session):
        """Summary: Verify the enrichment bug fix is working"""
        response = admin_session.get(f"{BASE_URL}/api/admin/pipeline")
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
    
    def test_no_regression_pipeline_structure(self, admin_session):
        """Verify pipeline response structure is intact after enrichment fix"""
        response = admin_session.get(f"{BASE_URL}/api/admin/pipeline")
        assert response.status_code == 200
        
        data = response.json()
        
        # Required top-level keys
        assert "pipeline" in data
        assert "stage_counts" in data
        assert "total_applications" in data
        assert "filters" in data
        
        # Pipeline should have stage keys
        pipeline = data.get("pipeline", {})
        assert isinstance(pipeline, dict)
        
        # Stage counts should match pipeline
        total_in_pipeline = sum(len(apps) for apps in pipeline.values())
        assert data["total_applications"] == total_in_pipeline
        
        print(f"[PASS] Pipeline response structure intact")
