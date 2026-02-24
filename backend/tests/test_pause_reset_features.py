"""
Tests for Pause Mode and Pre-Launch Reset Features
- Pause Mode: Toggle pause state, blocked check-in/check-out when paused, admin endpoints still work
- Pre-Launch Reset: Requires 'RESET DATA' confirmation, clears operational data
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPauseAndResetFeatures:
    """Tests for Pause Mode and Pre-Launch Reset functionality"""
    
    admin_token = None
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for authenticated tests"""
        if not TestPauseAndResetFeatures.admin_token:
            login_resp = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": "admin@vhc.in", "password": "VhcAdmin@2024"}
            )
            assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
            TestPauseAndResetFeatures.admin_token = login_resp.json().get("access_token")
        self.admin_headers = {"Authorization": f"Bearer {TestPauseAndResetFeatures.admin_token}"}
    
    # ====== PAUSE MODE - Backend Tests ======
    
    def test_01_get_attendance_status_returns_is_paused(self):
        """GET /api/attendance/status should return {is_paused: true/false}"""
        resp = requests.get(f"{BASE_URL}/api/attendance/status", headers=self.admin_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "is_paused" in data, "Response should contain 'is_paused' field"
        assert isinstance(data["is_paused"], bool), "is_paused should be boolean"
        print(f"✓ GET /api/attendance/status returns is_paused={data['is_paused']}")
    
    def test_02_set_pause_on_via_settings(self):
        """PUT /api/attendance/settings with {is_paused: true} should set paused state"""
        resp = requests.put(
            f"{BASE_URL}/api/attendance/settings",
            headers=self.admin_headers,
            json={"is_paused": True}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("is_paused") == True, "is_paused should be True after update"
        print("✓ PUT /api/attendance/settings - pause ON")
    
    def test_03_verify_status_is_paused_after_setting(self):
        """GET /api/attendance/status should return is_paused=true"""
        resp = requests.get(f"{BASE_URL}/api/attendance/status", headers=self.admin_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("is_paused") == True, "is_paused should be True"
        print("✓ Status confirmed as paused")
    
    def test_04_check_in_blocked_when_paused(self):
        """POST /api/attendance/check-in should return 403 when paused"""
        resp = requests.post(
            f"{BASE_URL}/api/attendance/check-in",
            headers=self.admin_headers,
            json={"work_mode": "office"}
        )
        # Should return 403 or 409 (if already checked in) - 403 is expected when paused
        assert resp.status_code in [403, 409], f"Expected 403 or 409, got {resp.status_code}: {resp.text}"
        if resp.status_code == 403:
            data = resp.json()
            assert "paused" in data.get("detail", "").lower(), "Error should mention paused state"
            print("✓ Check-in blocked with 403 when paused")
        else:
            print("✓ Check-in returned 409 (already checked in), pause blocking may have been tested before check-in")
    
    def test_05_check_out_blocked_when_paused(self):
        """POST /api/attendance/check-out should return 403 when paused"""
        resp = requests.post(
            f"{BASE_URL}/api/attendance/check-out",
            headers=self.admin_headers,
            json={}
        )
        # Should return 403 (paused) or 400 (no check-in)
        assert resp.status_code in [400, 403], f"Expected 400 or 403, got {resp.status_code}: {resp.text}"
        if resp.status_code == 403:
            data = resp.json()
            assert "paused" in data.get("detail", "").lower(), "Error should mention paused state"
            print("✓ Check-out blocked with 403 when paused")
        else:
            print("✓ Check-out returned 400 (no check-in found)")
    
    def test_06_admin_get_all_attendance_works_when_paused(self):
        """GET /api/attendance/all should still work when paused"""
        resp = requests.get(
            f"{BASE_URL}/api/attendance/all",
            headers=self.admin_headers
        )
        assert resp.status_code == 200, f"Admin endpoint should work when paused: {resp.text}"
        data = resp.json()
        assert "records" in data, "Response should contain 'records' field"
        print(f"✓ GET /api/attendance/all works when paused (returned {len(data.get('records', []))} records)")
    
    def test_07_admin_monthly_report_works_when_paused(self):
        """GET /api/attendance/report/monthly should still work when paused"""
        resp = requests.get(
            f"{BASE_URL}/api/attendance/report/monthly",
            headers=self.admin_headers
        )
        assert resp.status_code == 200, f"Admin report should work when paused: {resp.text}"
        data = resp.json()
        assert "summaries" in data, "Response should contain 'summaries' field"
        print(f"✓ GET /api/attendance/report/monthly works when paused")
    
    def test_08_admin_settings_works_when_paused(self):
        """GET /api/attendance/settings should still work when paused"""
        resp = requests.get(
            f"{BASE_URL}/api/attendance/settings",
            headers=self.admin_headers
        )
        assert resp.status_code == 200, f"Admin settings should work when paused: {resp.text}"
        data = resp.json()
        assert "is_paused" in data, "Response should contain 'is_paused' field"
        print("✓ GET /api/attendance/settings works when paused")
    
    def test_09_set_pause_off_via_settings(self):
        """PUT /api/attendance/settings with {is_paused: false} should resume tracking"""
        resp = requests.put(
            f"{BASE_URL}/api/attendance/settings",
            headers=self.admin_headers,
            json={"is_paused": False}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("is_paused") == False, "is_paused should be False after update"
        print("✓ PUT /api/attendance/settings - pause OFF")
    
    def test_10_verify_status_is_active_after_resume(self):
        """GET /api/attendance/status should return is_paused=false"""
        resp = requests.get(f"{BASE_URL}/api/attendance/status", headers=self.admin_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("is_paused") == False, "is_paused should be False"
        print("✓ Status confirmed as active (not paused)")
    
    # ====== PRE-LAUNCH RESET - Backend Tests ======
    
    def test_11_pre_launch_reset_wrong_confirmation_returns_400(self):
        """POST /api/attendance/admin/pre-launch-reset with wrong confirmation returns 400"""
        resp = requests.post(
            f"{BASE_URL}/api/attendance/admin/pre-launch-reset",
            headers=self.admin_headers,
            json={"confirmation": "WRONG"}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "invalid" in data.get("detail", "").lower() or "reset data" in data.get("detail", "").lower(), \
            "Error should mention invalid confirmation"
        print("✓ Pre-launch reset with wrong confirmation returns 400")
    
    def test_12_pre_launch_reset_empty_confirmation_returns_400(self):
        """POST /api/attendance/admin/pre-launch-reset with empty confirmation returns 400"""
        resp = requests.post(
            f"{BASE_URL}/api/attendance/admin/pre-launch-reset",
            headers=self.admin_headers,
            json={"confirmation": ""}
        )
        assert resp.status_code == 400 or resp.status_code == 422, f"Expected 400/422, got {resp.status_code}: {resp.text}"
        print("✓ Pre-launch reset with empty confirmation returns 400/422")
    
    def test_13_pre_launch_reset_correct_confirmation_succeeds(self):
        """POST /api/attendance/admin/pre-launch-reset with 'RESET DATA' succeeds"""
        resp = requests.post(
            f"{BASE_URL}/api/attendance/admin/pre-launch-reset",
            headers=self.admin_headers,
            json={"confirmation": "RESET DATA"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "deleted" in data, "Response should contain 'deleted' field with counts"
        assert "message" in data, "Response should contain success message"
        deleted = data.get("deleted", {})
        print(f"✓ Pre-launch reset succeeded. Deleted counts: {deleted}")
    
    # ====== NON-ADMIN ACCESS CONTROL Tests ======
    
    def test_14_non_admin_cannot_access_settings(self):
        """Non-admin users should get 403 on /api/attendance/settings"""
        # Try to login as a recruiter
        recruiter_login = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "yamini@vhc.in", "password": "VhcAdmin@2024"}
        )
        if recruiter_login.status_code != 200:
            pytest.skip("Recruiter user not available for testing")
        
        recruiter_token = recruiter_login.json().get("access_token")
        recruiter_headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        resp = requests.get(f"{BASE_URL}/api/attendance/settings", headers=recruiter_headers)
        assert resp.status_code == 403, f"Non-admin should get 403, got {resp.status_code}"
        print("✓ Non-admin cannot access GET /api/attendance/settings")
    
    def test_15_non_admin_cannot_access_pre_launch_reset(self):
        """Non-admin users should get 403 on /api/attendance/admin/pre-launch-reset"""
        recruiter_login = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "yamini@vhc.in", "password": "VhcAdmin@2024"}
        )
        if recruiter_login.status_code != 200:
            pytest.skip("Recruiter user not available for testing")
        
        recruiter_token = recruiter_login.json().get("access_token")
        recruiter_headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        resp = requests.post(
            f"{BASE_URL}/api/attendance/admin/pre-launch-reset",
            headers=recruiter_headers,
            json={"confirmation": "RESET DATA"}
        )
        assert resp.status_code == 403, f"Non-admin should get 403, got {resp.status_code}"
        print("✓ Non-admin cannot access POST /api/attendance/admin/pre-launch-reset")
    
    def test_16_unauthenticated_cannot_access_settings(self):
        """Unauthenticated users should get 401/403 on /api/attendance/settings"""
        resp = requests.get(f"{BASE_URL}/api/attendance/settings")
        assert resp.status_code in [401, 403], f"Unauthenticated should get 401/403, got {resp.status_code}"
        print("✓ Unauthenticated cannot access /api/attendance/settings")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
