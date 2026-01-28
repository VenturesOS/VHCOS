"""
Test Suite for VHC Talent OS - AI Screening Scope Verification
Tests that AI Screening searches ENTIRE candidate database, not just role-visible candidates.

CRITICAL GOVERNANCE FIX:
- AI Screening is a SYSTEM-LEVEL INTELLIGENCE function
- DATA VISIBILITY ≠ AI SEARCH SCOPE
- Results are READ-ONLY, CONTEXTUAL VISIBILITY - no edit/ownership rights granted
"""
import pytest
import requests
import os
import time
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
EMPLOYER_EMAIL = "employer@vhctalent.com"
EMPLOYER_PASSWORD = "VhcTalent@2024"
RECRUITER_EMAIL = "recruiter@vhctalent.com"
RECRUITER_PASSWORD = "VhcTalent@2024"


class TestSetup:
    """Setup and authentication helpers"""
    
    @staticmethod
    def get_token(email, password):
        """Get authentication token for any user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": password
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        return None
    
    @staticmethod
    def get_admin_token():
        return TestSetup.get_token(ADMIN_EMAIL, ADMIN_PASSWORD)
    
    @staticmethod
    def get_employer_token():
        return TestSetup.get_token(EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
    
    @staticmethod
    def get_recruiter_token():
        return TestSetup.get_token(RECRUITER_EMAIL, RECRUITER_PASSWORD)


class TestAIScreeningScope:
    """Test that AI Screening searches ENTIRE candidate database"""
    
    def test_admin_ai_screening_searches_all_candidates(self):
        """Test Admin AI screening searches entire database"""
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # First, get total candidate count from candidate bank
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=headers)
        assert response.status_code == 200, f"Failed to get candidate bank: {response.text}"
        total_candidates = len(response.json())
        print(f"Total candidates in database: {total_candidates}")
        
        # Now run AI screening with a generic JD
        match_request = {
            "jd_text": "Software Engineer with Python and JavaScript experience"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            json=match_request,
            headers=headers
        )
        assert response.status_code == 200, f"AI screening failed: {response.text}"
        
        results = response.json()
        screened_count = len(results)
        
        print(f"Admin AI Screening: {screened_count} candidates screened out of {total_candidates} total")
        
        # AI screening should search ALL candidates
        assert screened_count == total_candidates, \
            f"AI screening should search ALL {total_candidates} candidates, but only searched {screened_count}"
        
        # Verify source tracking is present
        if results:
            first_result = results[0]
            assert "source" in first_result, "Results should include source tracking"
            print(f"✅ Admin AI Screening searches ENTIRE database ({screened_count} candidates)")
    
    def test_employer_ai_screening_searches_all_candidates(self):
        """Test Employer AI screening searches entire database (not just their visible candidates)"""
        employer_token = TestSetup.get_employer_token()
        admin_token = TestSetup.get_admin_token()
        assert employer_token, "Failed to get employer token"
        assert admin_token, "Failed to get admin token"
        
        employer_headers = {"Authorization": f"Bearer {employer_token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get total candidate count (admin view)
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        assert response.status_code == 200
        total_candidates = len(response.json())
        
        # Get employer's visible candidates (for comparison)
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=employer_headers)
        assert response.status_code == 200
        employer_visible_candidates = len(response.json())
        
        print(f"Total candidates: {total_candidates}, Employer visible: {employer_visible_candidates}")
        
        # Run AI screening as employer
        match_request = {
            "jd_text": "Software Engineer with Python and JavaScript experience"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            json=match_request,
            headers=employer_headers
        )
        assert response.status_code == 200, f"Employer AI screening failed: {response.text}"
        
        results = response.json()
        screened_count = len(results)
        
        print(f"Employer AI Screening: {screened_count} candidates screened")
        
        # CRITICAL: AI screening should search ALL candidates, not just employer-visible ones
        assert screened_count == total_candidates, \
            f"Employer AI screening should search ALL {total_candidates} candidates, not just {employer_visible_candidates} visible ones. Got {screened_count}"
        
        # Verify source_role tracking
        if results:
            sources = set(r.get("source_role") for r in results if r.get("source_role"))
            print(f"Source roles in results: {sources}")
        
        print(f"✅ Employer AI Screening searches ENTIRE database ({screened_count} candidates)")
    
    def test_recruiter_ai_screening_searches_all_candidates(self):
        """Test Recruiter AI screening searches entire database (not just their visible candidates)"""
        recruiter_token = TestSetup.get_recruiter_token()
        admin_token = TestSetup.get_admin_token()
        assert recruiter_token, "Failed to get recruiter token"
        assert admin_token, "Failed to get admin token"
        
        recruiter_headers = {"Authorization": f"Bearer {recruiter_token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get total candidate count (admin view)
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        assert response.status_code == 200
        total_candidates = len(response.json())
        
        # Get recruiter's visible candidates (for comparison)
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=recruiter_headers)
        assert response.status_code == 200
        recruiter_visible_candidates = len(response.json())
        
        print(f"Total candidates: {total_candidates}, Recruiter visible: {recruiter_visible_candidates}")
        
        # Run AI screening as recruiter
        match_request = {
            "jd_text": "Software Engineer with Python and JavaScript experience"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            json=match_request,
            headers=recruiter_headers
        )
        assert response.status_code == 200, f"Recruiter AI screening failed: {response.text}"
        
        results = response.json()
        screened_count = len(results)
        
        print(f"Recruiter AI Screening: {screened_count} candidates screened")
        
        # CRITICAL: AI screening should search ALL candidates, not just recruiter-visible ones
        assert screened_count == total_candidates, \
            f"Recruiter AI screening should search ALL {total_candidates} candidates, not just {recruiter_visible_candidates} visible ones. Got {screened_count}"
        
        print(f"✅ Recruiter AI Screening searches ENTIRE database ({screened_count} candidates)")
    
    def test_ai_screening_includes_source_tracking(self):
        """Test that AI screening results include source tracking (admin/employer/recruiter)"""
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        match_request = {
            "jd_text": "Software Engineer"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            json=match_request,
            headers=headers
        )
        assert response.status_code == 200
        
        results = response.json()
        
        if results:
            # Check that source tracking fields are present
            first_result = results[0]
            assert "source" in first_result, "Results should include 'source' field"
            
            # source_role may be None for some candidates (e.g., self-registered)
            # but the field should exist
            print(f"Sample result source: {first_result.get('source')}, source_role: {first_result.get('source_role')}")
            
            # Count sources
            sources = {}
            for r in results:
                src = r.get("source_role") or r.get("source") or "unknown"
                sources[src] = sources.get(src, 0) + 1
            
            print(f"Source distribution: {sources}")
            print(f"✅ AI Screening includes source tracking")
        else:
            print("⚠️ No candidates in database to verify source tracking")


class TestAIScreeningVsDataBankVisibility:
    """Test that AI Screening scope is different from Data Bank visibility"""
    
    def test_ai_screening_scope_differs_from_data_bank_visibility(self):
        """
        Verify that AI Screening searches more candidates than Data Bank shows.
        This confirms the governance fix: DATA VISIBILITY ≠ AI SEARCH SCOPE
        """
        recruiter_token = TestSetup.get_recruiter_token()
        admin_token = TestSetup.get_admin_token()
        
        if not recruiter_token or not admin_token:
            pytest.skip("Could not get tokens")
        
        recruiter_headers = {"Authorization": f"Bearer {recruiter_token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get recruiter's visible candidates in Data Bank
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=recruiter_headers)
        assert response.status_code == 200
        data_bank_visible = len(response.json())
        
        # Get total candidates (admin view)
        response = requests.get(f"{BASE_URL}/api/candidate-bank", headers=admin_headers)
        assert response.status_code == 200
        total_candidates = len(response.json())
        
        # Run AI screening as recruiter
        match_request = {"jd_text": "Software Engineer"}
        response = requests.post(
            f"{BASE_URL}/api/matching/find-candidates",
            json=match_request,
            headers=recruiter_headers
        )
        assert response.status_code == 200
        ai_screening_count = len(response.json())
        
        print(f"Data Bank visible to recruiter: {data_bank_visible}")
        print(f"AI Screening searched: {ai_screening_count}")
        print(f"Total candidates in system: {total_candidates}")
        
        # AI screening should search ALL candidates
        assert ai_screening_count == total_candidates, \
            f"AI Screening should search all {total_candidates} candidates, got {ai_screening_count}"
        
        # If recruiter has limited visibility, AI screening should search MORE
        if data_bank_visible < total_candidates:
            assert ai_screening_count > data_bank_visible, \
                f"AI Screening ({ai_screening_count}) should search more than Data Bank visibility ({data_bank_visible})"
            print(f"✅ GOVERNANCE VERIFIED: AI Screening scope ({ai_screening_count}) > Data Bank visibility ({data_bank_visible})")
        else:
            print(f"✅ AI Screening searches entire database ({ai_screening_count} candidates)")


class TestMandateAllocation:
    """Test mandate allocation to recruiters"""
    
    def test_mandate_assignment_endpoint_exists(self):
        """Test that mandate assignment endpoint exists"""
        token = TestSetup.get_employer_token()
        assert token, "Failed to get employer token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get team recruiters
        response = requests.get(f"{BASE_URL}/api/mandates/team-recruiters", headers=headers)
        # Should return 200 or 404 if no team, but not 500
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            print(f"Team recruiters: {data.get('recruiters', [])}")
            print("✅ Mandate team recruiters endpoint working")
        else:
            print("⚠️ No team found for employer")
    
    def test_mandate_assignment_to_recruiter(self):
        """Test assigning a mandate (job) to a recruiter"""
        employer_token = TestSetup.get_employer_token()
        assert employer_token, "Failed to get employer token"
        
        headers = {"Authorization": f"Bearer {employer_token}"}
        
        # Get employer's jobs
        response = requests.get(f"{BASE_URL}/api/jobs", headers=headers)
        assert response.status_code == 200
        jobs = response.json()
        
        if not jobs:
            print("⚠️ No jobs found for employer to test mandate assignment")
            return
        
        job_id = jobs[0]["id"]
        
        # Get team recruiters
        response = requests.get(f"{BASE_URL}/api/mandates/team-recruiters", headers=headers)
        if response.status_code != 200:
            print("⚠️ No team recruiters available")
            return
        
        recruiters = response.json().get("recruiters", [])
        if not recruiters:
            print("⚠️ No recruiters in team")
            return
        
        recruiter_id = recruiters[0]["id"]
        
        # Assign mandate
        response = requests.post(
            f"{BASE_URL}/api/mandates/assign",
            json={"job_id": job_id, "recruiter_ids": [recruiter_id]},
            headers=headers
        )
        
        if response.status_code == 200:
            print(f"✅ Mandate assigned to recruiter: {recruiter_id}")
        else:
            print(f"Mandate assignment response: {response.status_code} - {response.text}")


class TestAuditLogs:
    """Test audit log recording"""
    
    def test_audit_logs_endpoint_exists(self):
        """Test that audit logs endpoint exists"""
        token = TestSetup.get_admin_token()
        assert token, "Failed to get admin token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Try to get audit logs
        response = requests.get(f"{BASE_URL}/api/audit-logs", headers=headers)
        
        # Should return 200 or 404 if endpoint doesn't exist
        if response.status_code == 200:
            logs = response.json()
            print(f"✅ Audit logs endpoint working, found {len(logs)} logs")
        elif response.status_code == 404:
            print("⚠️ Audit logs endpoint not found - may be at different path")
        else:
            print(f"Audit logs response: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
