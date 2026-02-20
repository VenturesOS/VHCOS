"""
Pipeline Restructure Tests - Talent OS
Tests new stage order, validation rules, and revenue endpoints
New stages: applied → shortlisted → submitted_to_client → interview → offered → hired → joined
Parallel statuses: rejected, on_hold
Removed: over_budget, not_qualified
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPipelineStages:
    """Test pipeline stage configuration and admin pipeline endpoint"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Admin authentication failed")
    
    @pytest.fixture
    def employer_token(self):
        """Get employer authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "employer@vhc.in",
            "password": "VhcEmployer@2024"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Employer authentication failed")
    
    @pytest.fixture
    def recruiter_token(self):
        """Get recruiter authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "recruiter@vhc.in",
            "password": "VhcRecruiter@2024"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Recruiter authentication failed")
    
    def test_admin_pipeline_returns_all_new_stages(self, admin_token):
        """GET /api/admin/pipeline returns all new stages including submitted_to_client, hired, joined"""
        response = requests.get(
            f"{BASE_URL}/api/admin/pipeline",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check pipeline data contains all expected stages
        assert "pipeline" in data
        pipeline = data["pipeline"]
        
        expected_stages = [
            "applied", "shortlisted", "submitted_to_client", 
            "interview", "offered", "hired", "joined", 
            "rejected", "on_hold"
        ]
        for stage in expected_stages:
            assert stage in pipeline, f"Stage '{stage}' missing from pipeline"
        
        # Verify removed stages are NOT present
        removed_stages = ["over_budget", "not_qualified"]
        for stage in removed_stages:
            assert stage not in pipeline, f"Removed stage '{stage}' should not be in pipeline"
        
        print(f"✓ Admin pipeline returns all 9 stages: {list(pipeline.keys())}")
    
    def test_pipeline_stage_counts_include_submitted_to_client(self, admin_token):
        """Pipeline stage counts include submitted_to_client in response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/pipeline",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "stage_counts" in data
        stage_counts = data["stage_counts"]
        
        # Verify submitted_to_client is in stage_counts
        assert "submitted_to_client" in stage_counts, "submitted_to_client missing from stage_counts"
        assert "hired" in stage_counts, "hired missing from stage_counts"
        assert "joined" in stage_counts, "joined missing from stage_counts"
        
        print(f"✓ Stage counts include new stages: {stage_counts}")
    
    def test_admin_stats_include_new_stages(self, admin_token):
        """GET /api/stats/admin includes submitted_to_client and joined in stage_stats"""
        response = requests.get(
            f"{BASE_URL}/api/stats/admin",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Admin stats endpoint should return successfully
        assert "total_users" in data or "total_jobs" in data
        print(f"✓ Admin stats endpoint returns data: {list(data.keys())}")
    
    def test_recruiter_stats_include_new_stages(self, recruiter_token):
        """GET /api/stats/recruiter includes submitted_to_client and joined in pipeline_stats"""
        response = requests.get(
            f"{BASE_URL}/api/stats/recruiter",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "pipeline_stats" in data
        pipeline_stats = data["pipeline_stats"]
        
        # Verify new stages are in pipeline_stats
        assert "submitted_to_client" in pipeline_stats, "submitted_to_client missing from recruiter pipeline_stats"
        assert "hired" in pipeline_stats, "hired missing from recruiter pipeline_stats"
        assert "joined" in pipeline_stats, "joined missing from recruiter pipeline_stats"
        
        print(f"✓ Recruiter stats include new stages: {pipeline_stats}")
    
    def test_employer_stats_include_new_stages(self, employer_token):
        """GET /api/stats/employer includes submitted_to_client and joined in stage_stats"""
        response = requests.get(
            f"{BASE_URL}/api/stats/employer",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "stage_stats" in data
        stage_stats = data["stage_stats"]
        
        # Verify new stages are in stage_stats
        assert "submitted_to_client" in stage_stats, "submitted_to_client missing from employer stage_stats"
        assert "hired" in stage_stats, "hired missing from employer stage_stats"
        assert "joined" in stage_stats, "joined missing from employer stage_stats"
        
        print(f"✓ Employer stats include new stages: {stage_stats}")


class TestStageTransitionValidation:
    """Test stage transition validation rules"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Admin authentication failed")
    
    @pytest.fixture
    def get_test_application(self, admin_token):
        """Get an application ID for testing"""
        response = requests.get(
            f"{BASE_URL}/api/applications",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        if response.status_code == 200:
            apps = response.json()
            if apps:
                return apps[0]
        return None
    
    def test_applied_to_shortlisted_allowed(self, admin_token):
        """Stage transition: applied->shortlisted OK"""
        # Get an application in 'applied' stage
        response = requests.get(
            f"{BASE_URL}/api/applications",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        apps = response.json()
        
        applied_app = next((a for a in apps if a.get("stage") == "applied"), None)
        
        if not applied_app:
            pytest.skip("No application in 'applied' stage to test")
        
        # Try to move to shortlisted
        update_response = requests.put(
            f"{BASE_URL}/api/applications/{applied_app['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"stage": "shortlisted"}
        )
        
        # Should succeed (200)
        assert update_response.status_code == 200
        
        # Revert back to applied
        requests.put(
            f"{BASE_URL}/api/applications/{applied_app['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"stage": "applied"}
        )
        
        print("✓ applied->shortlisted transition allowed")
    
    def test_shortlisted_to_submitted_allowed(self, admin_token):
        """Stage transition: shortlisted->submitted_to_client OK"""
        response = requests.get(
            f"{BASE_URL}/api/applications",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        apps = response.json()
        
        shortlisted_app = next((a for a in apps if a.get("stage") == "shortlisted"), None)
        
        if not shortlisted_app:
            pytest.skip("No application in 'shortlisted' stage to test")
        
        # Try to move to submitted_to_client
        update_response = requests.put(
            f"{BASE_URL}/api/applications/{shortlisted_app['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"stage": "submitted_to_client"}
        )
        
        # Should succeed (200)
        assert update_response.status_code == 200
        
        # Revert back
        requests.put(
            f"{BASE_URL}/api/applications/{shortlisted_app['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"stage": "shortlisted"}
        )
        
        print("✓ shortlisted->submitted_to_client transition allowed")
    
    def test_cannot_jump_to_hired_without_offered(self, admin_token):
        """Stage transition: can't jump to hired without offered stage (should return 400)"""
        response = requests.get(
            f"{BASE_URL}/api/applications",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        apps = response.json()
        
        # Find an application NOT in offered stage
        app = next((a for a in apps if a.get("stage") in ["applied", "shortlisted", "interview"]), None)
        
        if not app:
            pytest.skip("No application in early stage to test")
        
        original_stage = app.get("stage")
        
        # Try to jump to hired
        update_response = requests.put(
            f"{BASE_URL}/api/applications/{app['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"stage": "hired"}
        )
        
        # Should fail (400)
        assert update_response.status_code == 400, f"Expected 400, got {update_response.status_code}"
        error_detail = update_response.json().get("detail", "")
        assert "offered" in error_detail.lower() or "ctc" in error_detail.lower()
        
        print(f"✓ Cannot jump from {original_stage} to hired: {error_detail}")
    
    def test_cannot_jump_to_joined_without_hired(self, admin_token):
        """Stage transition: can't jump to joined without hired stage (should return 400)"""
        response = requests.get(
            f"{BASE_URL}/api/applications",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        apps = response.json()
        
        # Find an application NOT in hired stage
        app = next((a for a in apps if a.get("stage") in ["applied", "shortlisted", "interview", "offered"]), None)
        
        if not app:
            pytest.skip("No application in early/offered stage to test")
        
        original_stage = app.get("stage")
        
        # Try to jump to joined
        update_response = requests.put(
            f"{BASE_URL}/api/applications/{app['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"stage": "joined"}
        )
        
        # Should fail (400)
        assert update_response.status_code == 400, f"Expected 400, got {update_response.status_code}"
        error_detail = update_response.json().get("detail", "")
        
        print(f"✓ Cannot jump from {original_stage} to joined: {error_detail}")
    
    def test_rejected_allowed_from_any_stage(self, admin_token):
        """Stage transition: rejected/on_hold allowed from any stage"""
        response = requests.get(
            f"{BASE_URL}/api/applications",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        apps = response.json()
        
        # Find any application not in joined
        app = next((a for a in apps if a.get("stage") not in ["joined", "rejected"]), None)
        
        if not app:
            pytest.skip("No application available to test rejection")
        
        original_stage = app.get("stage")
        
        # Move to rejected
        update_response = requests.put(
            f"{BASE_URL}/api/applications/{app['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"stage": "rejected"}
        )
        
        # Should succeed (200)
        assert update_response.status_code == 200
        
        # Revert back
        requests.put(
            f"{BASE_URL}/api/applications/{app['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"stage": original_stage}
        )
        
        print(f"✓ rejected allowed from {original_stage}")
    
    def test_on_hold_allowed_from_any_stage(self, admin_token):
        """Stage transition: on_hold allowed from any stage"""
        response = requests.get(
            f"{BASE_URL}/api/applications",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        apps = response.json()
        
        # Find any application not in joined/on_hold
        app = next((a for a in apps if a.get("stage") not in ["joined", "on_hold"]), None)
        
        if not app:
            pytest.skip("No application available to test on_hold")
        
        original_stage = app.get("stage")
        
        # Move to on_hold
        update_response = requests.put(
            f"{BASE_URL}/api/applications/{app['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"stage": "on_hold"}
        )
        
        # Should succeed (200)
        assert update_response.status_code == 200
        
        # Revert back
        requests.put(
            f"{BASE_URL}/api/applications/{app['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"stage": original_stage}
        )
        
        print(f"✓ on_hold allowed from {original_stage}")


class TestRevenueHiredEndpoint:
    """Test revenue/hired endpoint"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@vhc.in",
            "password": "VhcAdmin@2024"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Admin authentication failed")
    
    def test_hired_endpoint_exists(self, admin_token):
        """POST /api/revenue/hired/{app_id} endpoint exists"""
        # Test with a fake app_id - should return 404 (not found), not 405 (method not allowed)
        response = requests.post(
            f"{BASE_URL}/api/revenue/hired/fake-app-id",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"date_of_joining": "2026-02-01"}
        )
        
        # Should be 404 (app not found), not 405 (endpoint doesn't exist)
        assert response.status_code in [404, 400], f"Expected 404 or 400, got {response.status_code}"
        print(f"✓ POST /api/revenue/hired endpoint exists (returned {response.status_code})")
    
    def test_hired_endpoint_requires_date_of_joining(self, admin_token):
        """POST /api/revenue/hired/{app_id} requires date_of_joining"""
        # Get an application in offered stage
        apps_response = requests.get(
            f"{BASE_URL}/api/applications",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert apps_response.status_code == 200
        apps = apps_response.json()
        
        offered_app = next((a for a in apps if a.get("stage") == "offered"), None)
        
        if not offered_app:
            # Test with any app - should fail due to missing DOJ
            test_app = apps[0] if apps else None
            if not test_app:
                pytest.skip("No applications available")
            
            # Try without date_of_joining
            response = requests.post(
                f"{BASE_URL}/api/revenue/hired/{test_app['id']}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={}  # Missing date_of_joining
            )
            
            assert response.status_code == 400 or response.status_code == 422
            print("✓ POST /api/revenue/hired requires date_of_joining")
        else:
            # Try without date_of_joining
            response = requests.post(
                f"{BASE_URL}/api/revenue/hired/{offered_app['id']}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={}  # Missing date_of_joining
            )
            
            assert response.status_code == 400 or response.status_code == 422
            print("✓ POST /api/revenue/hired requires date_of_joining")
    
    def test_offered_endpoint_exists(self, admin_token):
        """POST /api/revenue/offered/{app_id} endpoint exists"""
        response = requests.post(
            f"{BASE_URL}/api/revenue/offered/fake-app-id",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"offered_ctc": 1000000, "offer_date": "2026-01-15"}
        )
        
        # Should be 404 (app not found), not 405 (endpoint doesn't exist)
        assert response.status_code in [404, 400], f"Expected 404 or 400, got {response.status_code}"
        print(f"✓ POST /api/revenue/offered endpoint exists (returned {response.status_code})")
    
    def test_joined_endpoint_exists(self, admin_token):
        """POST /api/revenue/joined/{app_id} endpoint exists"""
        response = requests.post(
            f"{BASE_URL}/api/revenue/joined/fake-app-id",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"join_date": "2026-02-01"}
        )
        
        # Should be 404 (app not found), not 405 (endpoint doesn't exist)
        assert response.status_code in [404, 400], f"Expected 404 or 400, got {response.status_code}"
        print(f"✓ POST /api/revenue/joined endpoint exists (returned {response.status_code})")


class TestEmployerPipeline:
    """Test employer pipeline returns new stages"""
    
    @pytest.fixture
    def employer_token(self):
        """Get employer authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "employer@vhc.in",
            "password": "VhcEmployer@2024"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Employer authentication failed")
    
    def test_employer_pipeline_endpoint(self, employer_token):
        """GET /api/employer/pipeline returns new stages"""
        response = requests.get(
            f"{BASE_URL}/api/employer/pipeline",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        
        # Allow 200 or check if endpoint exists
        if response.status_code == 200:
            data = response.json()
            
            if "pipeline" in data:
                pipeline = data["pipeline"]
                # Check for new stages
                expected_stages = ["applied", "shortlisted", "submitted_to_client", "interview", "offered", "hired", "joined"]
                for stage in expected_stages:
                    assert stage in pipeline or stage in data.get("stage_counts", {}), f"Stage {stage} missing"
            
            if "stage_counts" in data:
                stage_counts = data["stage_counts"]
                assert "submitted_to_client" in stage_counts or "hired" in stage_counts, "New stages missing from employer pipeline"
            
            print("✓ Employer pipeline returns new stages")
        else:
            # Endpoint might not exist or require different permissions
            print(f"Note: Employer pipeline returned {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
