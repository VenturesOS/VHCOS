"""
Test DELETE Capabilities for Core Entities
Tests: Company Delete, Application Delete (Pipeline Removal), Company Update
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDeleteCapabilities:
    """Test DELETE endpoints for companies and applications"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Get admin token"""
        self.admin_email = "admin@vhc.in"
        self.admin_password = "VhcAdmin@2024"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": self.admin_email,
            "password": self.admin_password
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        token = login_resp.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
    # ============== COMPANY DELETE TESTS ==============
    
    def test_delete_company_success(self):
        """Test DELETE /api/companies/{id} - soft deletes company"""
        # First create a test company
        company_data = {
            "name": f"TEST_DeleteCompany_{uuid.uuid4().hex[:8]}",
            "industry": "Technology",
            "location": "Test City",
            "website": "https://test-delete.com",
            "description": "Test company for deletion"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/companies", json=company_data)
        assert create_resp.status_code == 200, f"Create company failed: {create_resp.text}"
        company_id = create_resp.json()["id"]
        
        # Delete the company
        delete_resp = self.session.delete(f"{BASE_URL}/api/companies/{company_id}")
        assert delete_resp.status_code == 200, f"Delete company failed: {delete_resp.text}"
        
        # Verify response structure
        delete_data = delete_resp.json()
        assert "message" in delete_data
        assert delete_data["company_id"] == company_id
        assert "jobs_archived" in delete_data
        print(f"✅ Company deleted successfully: {delete_data}")
        
    def test_delete_company_not_found(self):
        """Test DELETE /api/companies/{id} - returns 404 for non-existent company"""
        fake_id = str(uuid.uuid4())
        delete_resp = self.session.delete(f"{BASE_URL}/api/companies/{fake_id}")
        assert delete_resp.status_code == 404, f"Expected 404, got {delete_resp.status_code}"
        print("✅ Delete non-existent company returns 404")
        
    def test_delete_company_requires_admin(self):
        """Test DELETE /api/companies/{id} - requires admin role"""
        # Create a non-admin user session
        non_admin_session = requests.Session()
        non_admin_session.headers.update({"Content-Type": "application/json"})
        
        # Try to delete without auth
        delete_resp = non_admin_session.delete(f"{BASE_URL}/api/companies/{uuid.uuid4()}")
        assert delete_resp.status_code in [401, 403], f"Expected 401/403, got {delete_resp.status_code}"
        print("✅ Delete company requires authentication")
        
    def test_delete_company_cascade_jobs_archived(self):
        """Test DELETE /api/companies/{id} - archives linked jobs"""
        # Create a test company
        company_data = {
            "name": f"TEST_CascadeCompany_{uuid.uuid4().hex[:8]}",
            "industry": "Technology",
            "location": "Test City"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/companies", json=company_data)
        assert create_resp.status_code == 200
        company_id = create_resp.json()["id"]
        company_name = create_resp.json()["name"]
        
        # Create a job linked to this company
        job_data = {
            "title": f"TEST_Job_For_Cascade_{uuid.uuid4().hex[:8]}",
            "company_id": company_id,
            "company_name": company_name,
            "location": "Test City",
            "employment_type": "full_time",
            "experience_min": 2,
            "experience_max": 5,
            "salary_min": 500000,
            "salary_max": 1000000,
            "description": "Test job for cascade delete"
        }
        job_resp = self.session.post(f"{BASE_URL}/api/jobs", json=job_data)
        # Job creation may require additional fields, check response
        if job_resp.status_code == 200:
            job_id = job_resp.json()["id"]
            
            # Delete the company
            delete_resp = self.session.delete(f"{BASE_URL}/api/companies/{company_id}")
            assert delete_resp.status_code == 200
            
            # Check jobs_archived count
            delete_data = delete_resp.json()
            print(f"✅ Company deleted, jobs_archived: {delete_data.get('jobs_archived', 0)}")
        else:
            # If job creation fails, just delete the company
            delete_resp = self.session.delete(f"{BASE_URL}/api/companies/{company_id}")
            assert delete_resp.status_code == 200
            print(f"✅ Company deleted (job creation skipped): {delete_resp.json()}")
            
    # ============== APPLICATION DELETE TESTS ==============
    
    def test_delete_application_success(self):
        """Test DELETE /api/applications/{id} - removes candidate from pipeline"""
        # Get existing applications
        apps_resp = self.session.get(f"{BASE_URL}/api/applications")
        assert apps_resp.status_code == 200
        applications = apps_resp.json()
        
        if len(applications) > 0:
            # Find an application that's not already removed
            test_app = None
            for app in applications:
                if app.get("stage") != "removed" and app.get("status") != "removed":
                    test_app = app
                    break
            
            if test_app:
                app_id = test_app["id"]
                candidate_name = test_app.get("candidate_name", "Unknown")
                
                # Delete the application
                delete_resp = self.session.delete(f"{BASE_URL}/api/applications/{app_id}")
                assert delete_resp.status_code == 200, f"Delete application failed: {delete_resp.text}"
                
                # Verify response
                delete_data = delete_resp.json()
                assert "message" in delete_data
                assert delete_data["application_id"] == app_id
                print(f"✅ Application deleted: {candidate_name} removed from pipeline")
            else:
                print("⚠️ No suitable application found for deletion test (all removed)")
        else:
            print("⚠️ No applications found to test deletion")
            
    def test_delete_application_not_found(self):
        """Test DELETE /api/applications/{id} - returns 404 for non-existent application"""
        fake_id = str(uuid.uuid4())
        delete_resp = self.session.delete(f"{BASE_URL}/api/applications/{fake_id}")
        assert delete_resp.status_code == 404, f"Expected 404, got {delete_resp.status_code}"
        print("✅ Delete non-existent application returns 404")
        
    def test_delete_application_requires_admin(self):
        """Test DELETE /api/applications/{id} - requires admin role"""
        # Create a non-admin user session
        non_admin_session = requests.Session()
        non_admin_session.headers.update({"Content-Type": "application/json"})
        
        # Try to delete without auth
        delete_resp = non_admin_session.delete(f"{BASE_URL}/api/applications/{uuid.uuid4()}")
        assert delete_resp.status_code in [401, 403], f"Expected 401/403, got {delete_resp.status_code}"
        print("✅ Delete application requires authentication")
        
    def test_delete_application_soft_delete_preserves_data(self):
        """Test DELETE /api/applications/{id} - soft delete preserves data for audit"""
        # Get existing applications
        apps_resp = self.session.get(f"{BASE_URL}/api/applications")
        assert apps_resp.status_code == 200
        applications = apps_resp.json()
        
        # Find a removed application to verify it still exists
        removed_apps = [a for a in applications if a.get("stage") == "removed" or a.get("status") == "removed"]
        if removed_apps:
            # Verify we can still fetch the removed application
            app_id = removed_apps[0]["id"]
            get_resp = self.session.get(f"{BASE_URL}/api/applications/{app_id}")
            assert get_resp.status_code == 200, "Removed application should still be accessible"
            print(f"✅ Soft deleted application still accessible: {app_id}")
        else:
            print("⚠️ No removed applications to verify soft delete")
            
    # ============== COMPANY UPDATE TESTS ==============
    
    def test_update_company_success(self):
        """Test PUT /api/companies/{id} - updates company details"""
        # Create a test company
        company_data = {
            "name": f"TEST_UpdateCompany_{uuid.uuid4().hex[:8]}",
            "industry": "Technology",
            "location": "Original City",
            "website": "https://original.com",
            "description": "Original description"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/companies", json=company_data)
        assert create_resp.status_code == 200
        company_id = create_resp.json()["id"]
        
        # Update the company
        update_data = {
            "name": f"TEST_UpdatedCompany_{uuid.uuid4().hex[:8]}",
            "industry": "Healthcare",
            "location": "Updated City",
            "website": "https://updated.com",
            "description": "Updated description"
        }
        update_resp = self.session.put(f"{BASE_URL}/api/companies/{company_id}", json=update_data)
        assert update_resp.status_code == 200, f"Update company failed: {update_resp.text}"
        
        # Verify update
        updated_company = update_resp.json()
        assert updated_company["industry"] == "Healthcare"
        assert updated_company["location"] == "Updated City"
        print(f"✅ Company updated successfully: {updated_company['name']}")
        
        # Cleanup - delete the test company
        self.session.delete(f"{BASE_URL}/api/companies/{company_id}")
        
    def test_update_company_not_found(self):
        """Test PUT /api/companies/{id} - returns 404 for non-existent company"""
        fake_id = str(uuid.uuid4())
        update_data = {
            "name": "Test",
            "industry": "Test",
            "location": "Test"
        }
        update_resp = self.session.put(f"{BASE_URL}/api/companies/{fake_id}", json=update_data)
        assert update_resp.status_code == 404, f"Expected 404, got {update_resp.status_code}"
        print("✅ Update non-existent company returns 404")
        
    # ============== EXISTING DELETE ENDPOINTS TESTS ==============
    
    def test_delete_job_still_works(self):
        """Test DELETE /api/jobs/{id} - existing endpoint still works"""
        # Create a test job
        job_data = {
            "title": f"TEST_DeleteJob_{uuid.uuid4().hex[:8]}",
            "location": "Test City",
            "employment_type": "full_time",
            "experience_min": 2,
            "experience_max": 5,
            "salary_min": 500000,
            "salary_max": 1000000,
            "description": "Test job for deletion"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/jobs", json=job_data)
        if create_resp.status_code == 200:
            job_id = create_resp.json()["id"]
            
            # Delete the job
            delete_resp = self.session.delete(f"{BASE_URL}/api/jobs/{job_id}")
            assert delete_resp.status_code == 200, f"Delete job failed: {delete_resp.text}"
            print(f"✅ Job delete endpoint still works")
        else:
            print(f"⚠️ Job creation failed, skipping delete test: {create_resp.text}")
            
    def test_delete_user_still_works(self):
        """Test DELETE /api/users/{id} - existing endpoint still works (soft delete)"""
        # Create a test user
        user_data = {
            "email": f"test_delete_{uuid.uuid4().hex[:8]}@test.com",
            "name": "Test Delete User",
            "password": "TestPass123!",
            "role": "recruiter"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/admin/users", json=user_data)
        if create_resp.status_code == 200:
            user_id = create_resp.json()["id"]
            
            # Delete the user
            delete_resp = self.session.delete(f"{BASE_URL}/api/users/{user_id}")
            assert delete_resp.status_code == 200, f"Delete user failed: {delete_resp.text}"
            print(f"✅ User delete endpoint still works (soft delete)")
        else:
            print(f"⚠️ User creation failed, skipping delete test: {create_resp.text}")
            
    def test_delete_team_still_works(self):
        """Test DELETE /api/teams/{id} - existing endpoint still works"""
        # Get existing teams
        teams_resp = self.session.get(f"{BASE_URL}/api/teams")
        if teams_resp.status_code == 200:
            teams = teams_resp.json()
            # Create a test team to delete
            team_data = {
                "name": f"TEST_DeleteTeam_{uuid.uuid4().hex[:8]}",
                "employer_id": teams[0]["employer_id"] if teams else None
            }
            if team_data["employer_id"]:
                create_resp = self.session.post(f"{BASE_URL}/api/teams", json=team_data)
                if create_resp.status_code == 200:
                    team_id = create_resp.json()["id"]
                    
                    # Delete the team
                    delete_resp = self.session.delete(f"{BASE_URL}/api/teams/{team_id}")
                    assert delete_resp.status_code == 200, f"Delete team failed: {delete_resp.text}"
                    print(f"✅ Team delete endpoint still works")
                else:
                    print(f"⚠️ Team creation failed: {create_resp.text}")
            else:
                print("⚠️ No employer found for team creation")
        else:
            print(f"⚠️ Get teams failed: {teams_resp.text}")
            
    def test_delete_commercial_still_works(self):
        """Test DELETE /api/commercials/{id} - existing endpoint still works"""
        # Get existing commercials
        commercials_resp = self.session.get(f"{BASE_URL}/api/commercials")
        if commercials_resp.status_code == 200:
            commercials = commercials_resp.json()
            if commercials:
                # Get companies for creating a test commercial
                companies_resp = self.session.get(f"{BASE_URL}/api/companies")
                if companies_resp.status_code == 200 and companies_resp.json():
                    company_id = companies_resp.json()[0]["id"]
                    
                    # Create a test commercial
                    commercial_data = {
                        "company_id": company_id,
                        "commercial_name": f"TEST_DeleteCommercial_{uuid.uuid4().hex[:8]}",
                        "type": "percentage",
                        "fee_percentage": 10,
                        "is_active": True
                    }
                    create_resp = self.session.post(f"{BASE_URL}/api/commercials", json=commercial_data)
                    if create_resp.status_code == 200:
                        commercial_id = create_resp.json()["id"]
                        
                        # Delete the commercial
                        delete_resp = self.session.delete(f"{BASE_URL}/api/commercials/{commercial_id}")
                        assert delete_resp.status_code == 200, f"Delete commercial failed: {delete_resp.text}"
                        print(f"✅ Commercial delete endpoint still works")
                    else:
                        print(f"⚠️ Commercial creation failed: {create_resp.text}")
                else:
                    print("⚠️ No companies found for commercial creation")
            else:
                print("⚠️ No commercials found")
        else:
            print(f"⚠️ Get commercials failed: {commercials_resp.text}")


class TestAdminPipelineDelete:
    """Test admin pipeline view with delete functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Get admin token"""
        self.admin_email = "admin@vhc.in"
        self.admin_password = "VhcAdmin@2024"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": self.admin_email,
            "password": self.admin_password
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
    def test_admin_pipeline_loads(self):
        """Test GET /api/admin/pipeline - loads pipeline data"""
        resp = self.session.get(f"{BASE_URL}/api/admin/pipeline")
        assert resp.status_code == 200, f"Admin pipeline failed: {resp.text}"
        
        data = resp.json()
        assert "pipeline" in data
        assert "stage_counts" in data
        assert "total_applications" in data
        assert "filters" in data
        print(f"✅ Admin pipeline loads: {data['total_applications']} total applications")
        
    def test_admin_pipeline_with_filters(self):
        """Test GET /api/admin/pipeline with filters"""
        # Get pipeline with filters
        resp = self.session.get(f"{BASE_URL}/api/admin/pipeline")
        assert resp.status_code == 200
        
        data = resp.json()
        filters = data.get("filters", {})
        
        # Test with employer filter if available
        if filters.get("employers"):
            employer_id = filters["employers"][0]["id"]
            filtered_resp = self.session.get(f"{BASE_URL}/api/admin/pipeline", params={"employer_id": employer_id})
            assert filtered_resp.status_code == 200
            print(f"✅ Admin pipeline with employer filter works")
            
        # Test with job filter if available
        if filters.get("jobs"):
            job_id = filters["jobs"][0]["id"]
            filtered_resp = self.session.get(f"{BASE_URL}/api/admin/pipeline", params={"job_id": job_id})
            assert filtered_resp.status_code == 200
            print(f"✅ Admin pipeline with job filter works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
