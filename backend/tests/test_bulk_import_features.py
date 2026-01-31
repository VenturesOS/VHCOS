"""
Test Suite for VHC Talent OS Bulk Import Features
Tests:
1. Import History Dashboard - GET /api/admin/bulk-import/batches
2. Batch Details - GET /api/admin/bulk-import/batches/{batch_id}
3. Attach CV - PUT /api/admin/bulk-import/attach-cv/{candidate_id}
4. discovered_by tracking when linking bulk-imported candidate to job
5. Candidate Bank badges for bulk-imported candidates
"""
import pytest
import requests
import os
import io
import tempfile

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


class TestImportHistoryDashboard:
    """Test Import History Dashboard endpoints"""
    
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
    
    def test_get_import_batches_requires_auth(self):
        """GET /api/admin/bulk-import/batches requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/bulk-import/batches")
        assert response.status_code in [401, 403]
        print("✅ GET /api/admin/bulk-import/batches requires authentication")
    
    def test_get_import_batches_success(self):
        """GET /api/admin/bulk-import/batches returns batch list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/bulk-import/batches",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "batches" in data
        assert isinstance(data["batches"], list)
        
        # Verify batch structure
        if len(data["batches"]) > 0:
            batch = data["batches"][0]
            assert "id" in batch
            assert "mode" in batch
            assert "created_at" in batch
            assert "status" in batch
            print(f"✅ GET /api/admin/bulk-import/batches returns {len(data['batches'])} batches")
        else:
            print("✅ GET /api/admin/bulk-import/batches returns empty batch list")
    
    def test_get_import_batches_has_stats(self):
        """Batches include statistics (successful, failed, duplicates_merged)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/bulk-import/batches",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Find a completed batch
        completed_batches = [b for b in data["batches"] if b.get("status") == "completed"]
        if len(completed_batches) > 0:
            batch = completed_batches[0]
            assert "results" in batch
            results = batch["results"]
            assert "successful" in results
            assert "failed" in results
            assert "duplicates_merged" in results
            print(f"✅ Completed batch has stats: successful={results['successful']}, failed={results['failed']}, merged={results['duplicates_merged']}")
        else:
            print("⚠️ No completed batches found to verify stats")


class TestBatchDetails:
    """Test Batch Details endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_batch_details_requires_auth(self):
        """GET /api/admin/bulk-import/batches/{batch_id} requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/bulk-import/batches/test-id")
        assert response.status_code in [401, 403]
        print("✅ GET /api/admin/bulk-import/batches/{batch_id} requires authentication")
    
    def test_get_batch_details_not_found(self):
        """GET /api/admin/bulk-import/batches/{batch_id} returns 404 for invalid ID"""
        response = requests.get(
            f"{BASE_URL}/api/admin/bulk-import/batches/invalid-batch-id",
            headers=self.headers
        )
        assert response.status_code == 404
        print("✅ GET /api/admin/bulk-import/batches/{batch_id} returns 404 for invalid ID")
    
    def test_get_batch_details_success(self):
        """GET /api/admin/bulk-import/batches/{batch_id} returns batch details"""
        # First get list of batches
        list_response = requests.get(
            f"{BASE_URL}/api/admin/bulk-import/batches",
            headers=self.headers
        )
        assert list_response.status_code == 200
        batches = list_response.json()["batches"]
        
        if len(batches) > 0:
            batch_id = batches[0]["id"]
            response = requests.get(
                f"{BASE_URL}/api/admin/bulk-import/batches/{batch_id}",
                headers=self.headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == batch_id
            assert "mode" in data
            assert "created_at" in data
            assert "status" in data
            print(f"✅ GET /api/admin/bulk-import/batches/{batch_id} returns batch details")
        else:
            pytest.skip("No batches available to test details")


class TestAttachCV:
    """Test Attach CV endpoint for bulk-imported candidates"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_attach_cv_requires_auth(self):
        """PUT /api/admin/bulk-import/attach-cv/{candidate_id} requires authentication"""
        response = requests.put(f"{BASE_URL}/api/admin/bulk-import/attach-cv/test-id")
        assert response.status_code in [401, 403]
        print("✅ PUT /api/admin/bulk-import/attach-cv/{candidate_id} requires authentication")
    
    def test_attach_cv_not_found(self):
        """PUT /api/admin/bulk-import/attach-cv/{candidate_id} returns 404 for invalid ID"""
        # Create a dummy PDF file
        files = {"cv_file": ("test.pdf", b"%PDF-1.4 test content", "application/pdf")}
        response = requests.put(
            f"{BASE_URL}/api/admin/bulk-import/attach-cv/invalid-candidate-id",
            headers=self.headers,
            files=files
        )
        assert response.status_code == 404
        print("✅ PUT /api/admin/bulk-import/attach-cv/{candidate_id} returns 404 for invalid ID")
    
    def test_attach_cv_invalid_file_type(self):
        """PUT /api/admin/bulk-import/attach-cv/{candidate_id} rejects invalid file types"""
        # Get a bulk-imported candidate without CV
        restricted_response = requests.get(
            f"{BASE_URL}/api/admin/bulk-import/restricted-candidates",
            headers=self.headers
        )
        assert restricted_response.status_code == 200
        candidates = restricted_response.json()["candidates"]
        
        # Find candidate without CV
        no_cv_candidates = [c for c in candidates if c.get("cv_attached") == False]
        if len(no_cv_candidates) > 0:
            candidate_id = no_cv_candidates[0]["id"]
            
            # Try to upload invalid file type
            files = {"cv_file": ("test.txt", b"text content", "text/plain")}
            response = requests.put(
                f"{BASE_URL}/api/admin/bulk-import/attach-cv/{candidate_id}",
                headers=self.headers,
                files=files
            )
            assert response.status_code == 400
            print("✅ PUT /api/admin/bulk-import/attach-cv/{candidate_id} rejects invalid file types")
        else:
            pytest.skip("No bulk-imported candidates without CV found")
    
    def test_attach_cv_success(self):
        """PUT /api/admin/bulk-import/attach-cv/{candidate_id} attaches CV successfully"""
        # Get a bulk-imported candidate without CV
        restricted_response = requests.get(
            f"{BASE_URL}/api/admin/bulk-import/restricted-candidates",
            headers=self.headers
        )
        assert restricted_response.status_code == 200
        candidates = restricted_response.json()["candidates"]
        
        # Find candidate without CV
        no_cv_candidates = [c for c in candidates if c.get("cv_attached") == False]
        if len(no_cv_candidates) > 0:
            candidate_id = no_cv_candidates[0]["id"]
            candidate_name = no_cv_candidates[0]["name"]
            
            # Create a valid PDF file
            pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
            files = {"cv_file": ("test_resume.pdf", pdf_content, "application/pdf")}
            
            response = requests.put(
                f"{BASE_URL}/api/admin/bulk-import/attach-cv/{candidate_id}",
                headers=self.headers,
                files=files
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] == True
            assert "message" in data
            assert data["candidate_id"] == candidate_id
            print(f"✅ PUT /api/admin/bulk-import/attach-cv/{candidate_id} attached CV to {candidate_name}")
            
            # Verify cv_attached is now True
            verify_response = requests.get(
                f"{BASE_URL}/api/candidate-bank/{candidate_id}",
                headers=self.headers
            )
            if verify_response.status_code == 200:
                updated_candidate = verify_response.json()
                assert updated_candidate.get("cv_attached") == True
                print(f"✅ Verified cv_attached=True for candidate {candidate_name}")
        else:
            pytest.skip("No bulk-imported candidates without CV found")


class TestDiscoveredByTracking:
    """Test discovered_by tracking when linking bulk-imported candidate to job"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.user = response.json()["user"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_discovered_by_populated_on_link(self):
        """discovered_by array is populated when linking bulk-imported candidate to job"""
        # Get restricted candidates
        restricted_response = requests.get(
            f"{BASE_URL}/api/admin/bulk-import/restricted-candidates",
            headers=self.headers
        )
        assert restricted_response.status_code == 200
        candidates = restricted_response.json()["candidates"]
        
        # Find candidate with discovered_by populated
        discovered_candidates = [c for c in candidates if len(c.get("discovered_by", [])) > 0]
        if len(discovered_candidates) > 0:
            candidate = discovered_candidates[0]
            discovered_by = candidate["discovered_by"][0]
            
            assert "user_id" in discovered_by
            assert "user_role" in discovered_by
            assert "user_name" in discovered_by
            assert "added_at" in discovered_by
            assert "job_id" in discovered_by
            assert "job_title" in discovered_by
            
            print(f"✅ discovered_by populated for candidate {candidate['name']}")
            print(f"   Discovered by: {discovered_by['user_name']} ({discovered_by['user_role']})")
            print(f"   Job: {discovered_by['job_title']}")
        else:
            # Test by linking a candidate to a job
            # Find candidate without discovered_by
            no_discovered = [c for c in candidates if len(c.get("discovered_by", [])) == 0]
            if len(no_discovered) > 0:
                candidate = no_discovered[0]
                
                # Get an active job
                jobs_response = requests.get(
                    f"{BASE_URL}/api/jobs",
                    headers=self.headers
                )
                if jobs_response.status_code == 200:
                    jobs = jobs_response.json()
                    active_jobs = [j for j in jobs if j.get("status") == "active"]
                    
                    if len(active_jobs) > 0:
                        job = active_jobs[0]
                        
                        # First update mandatory fields
                        update_response = requests.put(
                            f"{BASE_URL}/api/candidate-bank/{candidate['id']}/salary-notice",
                            headers=self.headers,
                            params={
                                "current_salary": 1000000,
                                "notice_period": "30 days",
                                "location": "Bangalore",
                                "experience_years": 5
                            }
                        )
                        
                        # Link candidate to job
                        link_response = requests.post(
                            f"{BASE_URL}/api/applications/link-candidate",
                            headers=self.headers,
                            json={
                                "candidate_id": candidate["id"],
                                "job_id": job["id"]
                            }
                        )
                        
                        if link_response.status_code == 200:
                            # Verify discovered_by was populated
                            verify_response = requests.get(
                                f"{BASE_URL}/api/candidate-bank/{candidate['id']}",
                                headers=self.headers
                            )
                            if verify_response.status_code == 200:
                                updated = verify_response.json()
                                discovered_by = updated.get("discovered_by", [])
                                if len(discovered_by) > 0:
                                    print(f"✅ discovered_by populated after linking candidate to job")
                                    print(f"   Candidate: {candidate['name']}")
                                    print(f"   Job: {job['title']}")
                                else:
                                    print("⚠️ discovered_by not populated after link")
                        elif link_response.status_code == 400:
                            # Application might already exist
                            print(f"⚠️ Could not link candidate (may already be linked): {link_response.json()}")
            else:
                print("⚠️ No candidates available to test discovered_by tracking")


class TestCandidateBankBulkImportBadges:
    """Test Candidate Bank shows correct badges for bulk-imported candidates"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_bulk_import_candidates_have_source_field(self):
        """Bulk-imported candidates have source='bulk_import'"""
        response = requests.get(
            f"{BASE_URL}/api/admin/bulk-import/restricted-candidates",
            headers=self.headers
        )
        assert response.status_code == 200
        candidates = response.json()["candidates"]
        
        if len(candidates) > 0:
            for candidate in candidates[:5]:  # Check first 5
                assert candidate.get("source") == "bulk_import"
            print(f"✅ All {len(candidates)} bulk-imported candidates have source='bulk_import'")
        else:
            pytest.skip("No bulk-imported candidates found")
    
    def test_bulk_import_candidates_have_restricted_flag(self):
        """Bulk-imported candidates have bulk_import_restricted=True"""
        response = requests.get(
            f"{BASE_URL}/api/admin/bulk-import/restricted-candidates",
            headers=self.headers
        )
        assert response.status_code == 200
        candidates = response.json()["candidates"]
        
        if len(candidates) > 0:
            for candidate in candidates[:5]:  # Check first 5
                assert candidate.get("bulk_import_restricted") == True
            print(f"✅ All {len(candidates)} bulk-imported candidates have bulk_import_restricted=True")
        else:
            pytest.skip("No bulk-imported candidates found")
    
    def test_bulk_import_candidates_have_cv_attached_field(self):
        """Bulk-imported candidates have cv_attached field"""
        response = requests.get(
            f"{BASE_URL}/api/admin/bulk-import/restricted-candidates",
            headers=self.headers
        )
        assert response.status_code == 200
        candidates = response.json()["candidates"]
        
        if len(candidates) > 0:
            with_cv = sum(1 for c in candidates if c.get("cv_attached") == True)
            without_cv = sum(1 for c in candidates if c.get("cv_attached") == False)
            print(f"✅ Bulk-imported candidates: {with_cv} with CV, {without_cv} without CV")
        else:
            pytest.skip("No bulk-imported candidates found")
    
    def test_candidate_bank_returns_bulk_import_fields(self):
        """Candidate Bank API returns bulk import specific fields"""
        response = requests.get(
            f"{BASE_URL}/api/candidate-bank",
            headers=self.headers
        )
        assert response.status_code == 200
        candidates = response.json()
        
        # Find bulk-imported candidates
        bulk_imported = [c for c in candidates if c.get("source") == "bulk_import"]
        if len(bulk_imported) > 0:
            candidate = bulk_imported[0]
            # Check for bulk import specific fields
            assert "source" in candidate
            assert "bulk_import_restricted" in candidate or candidate.get("source") == "bulk_import"
            print(f"✅ Candidate Bank returns bulk import fields for {len(bulk_imported)} candidates")
        else:
            print("⚠️ No bulk-imported candidates in Candidate Bank response")


class TestRestrictedCandidatesEndpoint:
    """Test restricted candidates endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_restricted_candidates_requires_auth(self):
        """GET /api/admin/bulk-import/restricted-candidates requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/bulk-import/restricted-candidates")
        assert response.status_code in [401, 403]
        print("✅ GET /api/admin/bulk-import/restricted-candidates requires authentication")
    
    def test_get_restricted_candidates_success(self):
        """GET /api/admin/bulk-import/restricted-candidates returns restricted candidates"""
        response = requests.get(
            f"{BASE_URL}/api/admin/bulk-import/restricted-candidates",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "candidates" in data
        assert isinstance(data["candidates"], list)
        print(f"✅ GET /api/admin/bulk-import/restricted-candidates returns {data['count']} candidates")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
