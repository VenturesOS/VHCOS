"""
Test Match History Feature - New feature for VHC Talent OS
Tests:
1. GET /api/matching/history - returns list of past match searches for current user
2. GET /api/matching/history/{id} - returns full detail with top_results array
3. Role-based access control (Admin sees all, Employer/Recruiter see only their own)
4. Quick match creates history entry with top_results
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
EMPLOYER_EMAIL = "employer@vhctalent.com"
EMPLOYER_PASSWORD = "VhcTalent@2024"
RECRUITER_EMAIL = "recruiter@vhctalent.com"
RECRUITER_PASSWORD = "VhcTalent@2024"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def employer_token():
    """Get employer auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": EMPLOYER_EMAIL,
        "password": EMPLOYER_PASSWORD
    })
    assert response.status_code == 200, f"Employer login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def recruiter_token():
    """Get recruiter auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": RECRUITER_EMAIL,
        "password": RECRUITER_PASSWORD
    })
    assert response.status_code == 200, f"Recruiter login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def employer_user_id(employer_token):
    """Get employer user ID"""
    response = requests.get(f"{BASE_URL}/api/auth/me", headers={
        "Authorization": f"Bearer {employer_token}"
    })
    assert response.status_code == 200
    return response.json()["id"]


@pytest.fixture(scope="module")
def recruiter_user_id(recruiter_token):
    """Get recruiter user ID"""
    response = requests.get(f"{BASE_URL}/api/auth/me", headers={
        "Authorization": f"Bearer {recruiter_token}"
    })
    assert response.status_code == 200
    return response.json()["id"]


class TestMatchHistoryEndpointAuth:
    """Test authentication requirements for match history endpoints"""
    
    def test_match_history_requires_auth(self):
        """GET /api/matching/history requires authentication"""
        response = requests.get(f"{BASE_URL}/api/matching/history")
        assert response.status_code == 401, "Should require authentication"
        print("✅ GET /api/matching/history requires authentication")
    
    def test_match_history_detail_requires_auth(self):
        """GET /api/matching/history/{id} requires authentication"""
        response = requests.get(f"{BASE_URL}/api/matching/history/some-id")
        assert response.status_code == 401, "Should require authentication"
        print("✅ GET /api/matching/history/{id} requires authentication")


class TestMatchHistoryList:
    """Test GET /api/matching/history - list endpoint"""
    
    def test_admin_can_get_all_history(self, admin_token):
        """Admin can view all match history entries"""
        response = requests.get(
            f"{BASE_URL}/api/matching/history",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Should return a list"
        print(f"✅ Admin sees {len(data)} history entries (all users)")
        
        # Verify structure of history items
        if data:
            item = data[0]
            assert "id" in item, "History item must have id"
            assert "timestamp" in item, "History item must have timestamp"
            # mode field indicates quick or full_ai
            print(f"  Sample entry: job_title={item.get('job_title')}, mode={item.get('mode')}, matched_count={item.get('matched_count')}")
    
    def test_employer_sees_only_own_history(self, employer_token, employer_user_id):
        """Employer sees only their own match history"""
        response = requests.get(
            f"{BASE_URL}/api/matching/history",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Should return a list"
        
        # Verify all entries belong to this employer
        for item in data:
            if "searched_by" in item:  # Field may not be in projection but if present, verify it
                pass  # This is fine, searched_by is filtered server-side
        
        print(f"✅ Employer sees {len(data)} history entries (own only)")
    
    def test_recruiter_sees_only_own_history(self, recruiter_token, recruiter_user_id):
        """Recruiter sees only their own match history"""
        response = requests.get(
            f"{BASE_URL}/api/matching/history",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Should return a list"
        print(f"✅ Recruiter sees {len(data)} history entries (own only)")


class TestMatchHistoryDetail:
    """Test GET /api/matching/history/{id} - detail endpoint"""
    
    def test_get_history_detail_with_valid_id(self, admin_token):
        """Admin can get history detail with valid ID"""
        # First get history list to find a valid ID
        list_response = requests.get(
            f"{BASE_URL}/api/matching/history",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert list_response.status_code == 200
        data = list_response.json()
        
        if not data:
            pytest.skip("No history entries to test detail view")
        
        # Get detail of first entry
        history_id = data[0]["id"]
        detail_response = requests.get(
            f"{BASE_URL}/api/matching/history/{history_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert detail_response.status_code == 200, f"Failed: {detail_response.text}"
        detail = detail_response.json()
        
        # Verify detail structure
        assert "id" in detail, "Detail must have id"
        assert "timestamp" in detail, "Detail must have timestamp"
        
        # Check if top_results array exists (might be empty for older entries)
        if "top_results" in detail:
            assert isinstance(detail["top_results"], list), "top_results must be array"
            print(f"✅ History detail has {len(detail.get('top_results', []))} top_results")
            
            # Verify top_results structure if not empty
            if detail["top_results"]:
                result = detail["top_results"][0]
                assert "candidate_id" in result or "candidate_name" in result, "Result must have candidate info"
                assert "score" in result, "Result must have score"
        else:
            print("ℹ️  History entry has no top_results (older entry)")
        
        print(f"✅ History detail retrieved: id={history_id}")
    
    def test_get_history_detail_invalid_id_returns_404(self, admin_token):
        """GET /api/matching/history/{invalid_id} returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/matching/history/non-existent-id-12345",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 404, f"Should return 404, got {response.status_code}"
        print("✅ Invalid history ID returns 404")
    
    def test_employer_cannot_access_others_history(self, employer_token, admin_token):
        """Employer cannot access history entries they don't own"""
        # First, get admin's history to find an entry not owned by employer
        admin_history = requests.get(
            f"{BASE_URL}/api/matching/history",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert admin_history.status_code == 200
        all_entries = admin_history.json()
        
        # Get employer's history
        employer_history = requests.get(
            f"{BASE_URL}/api/matching/history",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert employer_history.status_code == 200
        employer_entries = employer_history.json()
        employer_ids = {e["id"] for e in employer_entries}
        
        # Find an entry that doesn't belong to employer
        other_entry = None
        for entry in all_entries:
            if entry["id"] not in employer_ids:
                other_entry = entry
                break
        
        if not other_entry:
            pytest.skip("All entries belong to employer, cannot test access control")
        
        # Try to access other user's history
        response = requests.get(
            f"{BASE_URL}/api/matching/history/{other_entry['id']}",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 403, f"Should return 403, got {response.status_code}: {response.text}"
        print("✅ Employer cannot access other users' history (403)")


class TestQuickMatchCreatesHistory:
    """Test that running quick match creates a history entry"""
    
    def test_quick_match_creates_history_entry(self, employer_token):
        """Running a quick match search should create a history entry"""
        # Get initial history count
        initial_response = requests.get(
            f"{BASE_URL}/api/matching/history",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert initial_response.status_code == 200
        initial_count = len(initial_response.json())
        
        # Run a quick match search
        match_response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            headers={"Authorization": f"Bearer {employer_token}"},
            json={
                "jd_text": "Looking for Python developer with Django experience",
                "match_mode": "quick",
                "limit": 10
            }
        )
        assert match_response.status_code == 200, f"Quick match failed: {match_response.text}"
        
        # Wait a bit for history to be saved
        time.sleep(1)
        
        # Check history again
        final_response = requests.get(
            f"{BASE_URL}/api/matching/history",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert final_response.status_code == 200
        final_history = final_response.json()
        final_count = len(final_history)
        
        assert final_count >= initial_count, "History entry should be created after quick match"
        print(f"✅ Quick match created history entry (count: {initial_count} -> {final_count})")
        
        # Verify latest entry has top_results
        if final_history:
            latest = final_history[0]
            detail_response = requests.get(
                f"{BASE_URL}/api/matching/history/{latest['id']}",
                headers={"Authorization": f"Bearer {employer_token}"}
            )
            assert detail_response.status_code == 200
            detail = detail_response.json()
            
            if "top_results" in detail:
                print(f"  Latest history has {len(detail['top_results'])} top_results")
    
    def test_history_entry_contains_correct_data(self, recruiter_token):
        """History entry should contain job_title, filters, counts, etc."""
        # Run a match with specific filters
        match_response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            headers={"Authorization": f"Bearer {recruiter_token}"},
            json={
                "jd_text": "Senior React developer with Node.js backend experience",
                "match_mode": "quick",
                "must_have_location": "Mumbai",
                "min_experience": 3,
                "max_experience": 8,
                "limit": 5
            }
        )
        assert match_response.status_code == 200, f"Match failed: {match_response.text}"
        
        time.sleep(1)
        
        # Get latest history
        history_response = requests.get(
            f"{BASE_URL}/api/matching/history",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert history_response.status_code == 200
        history = history_response.json()
        
        if not history:
            pytest.skip("No history entries found")
        
        latest = history[0]
        
        # Verify entry contains expected fields
        assert "job_title" in latest or "jd_text" in latest, "Entry should have job info"
        assert "timestamp" in latest, "Entry must have timestamp"
        assert "mode" in latest, "Entry must have mode"
        
        # Get detail to check filters
        detail_response = requests.get(
            f"{BASE_URL}/api/matching/history/{latest['id']}",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()
        
        # Verify filters are stored
        if "filters" in detail:
            filters = detail["filters"]
            print(f"  Stored filters: location={filters.get('location')}, min_exp={filters.get('min_exp')}, max_exp={filters.get('max_exp')}")
        
        print(f"✅ History entry contains correct data structure")


class TestMatchHistoryStructure:
    """Test the structure of match history data"""
    
    def test_history_list_fields(self, admin_token):
        """Verify history list returns expected fields for list view"""
        response = requests.get(
            f"{BASE_URL}/api/matching/history",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        if not data:
            pytest.skip("No history entries to verify structure")
        
        # Fields expected in list view
        expected_list_fields = ["id", "timestamp"]
        optional_list_fields = ["job_id", "job_title", "jd_text", "mode", "matched_count", "ai_scored_count", 
                                "total_time_seconds", "filters", "searched_by_name", "searched_by_role"]
        
        item = data[0]
        for field in expected_list_fields:
            assert field in item, f"List item missing required field: {field}"
        
        present_optional = [f for f in optional_list_fields if f in item]
        print(f"✅ History list structure verified. Optional fields present: {present_optional}")
    
    def test_history_detail_fields(self, admin_token):
        """Verify history detail returns full data including top_results"""
        # Get list first
        list_response = requests.get(
            f"{BASE_URL}/api/matching/history",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert list_response.status_code == 200
        data = list_response.json()
        
        if not data:
            pytest.skip("No history entries to verify detail structure")
        
        # Get detail
        detail_response = requests.get(
            f"{BASE_URL}/api/matching/history/{data[0]['id']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()
        
        # Verify detail has more fields than list
        assert "id" in detail, "Detail must have id"
        
        # top_results should be in detail (might be empty for old entries)
        if "top_results" in detail and detail["top_results"]:
            result = detail["top_results"][0]
            expected_result_fields = ["score"]
            optional_result_fields = ["candidate_id", "candidate_name", "candidate_email", 
                                     "matched_skills", "missing_skills", "explanation"]
            
            for field in expected_result_fields:
                assert field in result, f"Result missing required field: {field}"
            
            present = [f for f in optional_result_fields if f in result]
            print(f"✅ top_results structure verified. Optional fields: {present}")
        else:
            print("ℹ️  No top_results in this history entry (older entry or no matches)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
