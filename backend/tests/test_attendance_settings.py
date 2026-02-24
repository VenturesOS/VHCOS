"""
Attendance Settings API Tests
Tests for GET/PUT /api/attendance/settings endpoints
- Admin-only access control
- All settings fields returned/updated correctly
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def admin_token():
    """Get admin token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@vhc.in",
        "password": "VhcAdmin@2024"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Admin login failed")

@pytest.fixture(scope="module")
def recruiter_token():
    """Get recruiter token (non-admin)"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "yamini@vhc.in",
        "password": "VhcAdmin@2024"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Recruiter login failed")

class TestAttendanceSettingsGetEndpoint:
    """Test GET /api/attendance/settings"""

    def test_get_settings_admin_success(self, admin_token):
        """Admin should be able to GET attendance settings"""
        response = requests.get(
            f"{BASE_URL}/api/attendance/settings",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify all expected fields are present
        expected_fields = [
            "work_start_time", "work_end_time", "late_threshold_minutes",
            "half_day_hours", "full_day_hours", "reminder_time", "auto_absent_time",
            "overtime_threshold_minutes", "grace_window_minutes", "weekend_days"
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify field types
        assert isinstance(data.get("weekend_days"), list), "weekend_days should be a list"
        assert isinstance(data.get("grace_window_minutes"), int), "grace_window_minutes should be int"
        assert isinstance(data.get("overtime_threshold_minutes"), int), "overtime_threshold_minutes should be int"
        print(f"Settings retrieved: {data}")

    def test_get_settings_recruiter_denied(self, recruiter_token):
        """Recruiter (non-admin) should get 403 on settings endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/attendance/settings",
            headers={"Authorization": f"Bearer {recruiter_token}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("Recruiter correctly denied access to settings")

    def test_get_settings_unauthenticated(self):
        """Unauthenticated request should get 401"""
        response = requests.get(f"{BASE_URL}/api/attendance/settings")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

class TestAttendanceSettingsPutEndpoint:
    """Test PUT /api/attendance/settings"""

    def test_update_settings_admin_success(self, admin_token):
        """Admin should be able to UPDATE attendance settings"""
        # First get current settings
        get_response = requests.get(
            f"{BASE_URL}/api/attendance/settings",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        original_settings = get_response.json()
        
        # Update with new values
        update_data = {
            "work_start_time": "09:30",
            "work_end_time": "18:30",
            "reminder_time": "10:15",
            "auto_absent_time": "19:00",
            "grace_window_minutes": 45,
            "overtime_threshold_minutes": 90,
            "late_threshold_minutes": 20,
            "weekend_days": [0, 6]  # Sunday and Saturday
        }
        
        response = requests.put(
            f"{BASE_URL}/api/attendance/settings",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=update_data
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        updated_data = response.json()
        
        # Verify updates were applied
        assert updated_data.get("work_start_time") == "09:30"
        assert updated_data.get("work_end_time") == "18:30"
        assert updated_data.get("reminder_time") == "10:15"
        assert updated_data.get("auto_absent_time") == "19:00"
        assert updated_data.get("grace_window_minutes") == 45
        assert updated_data.get("overtime_threshold_minutes") == 90
        assert updated_data.get("late_threshold_minutes") == 20
        assert updated_data.get("weekend_days") == [0, 6]
        
        print(f"Settings updated successfully: {updated_data}")

    def test_update_settings_partial_update(self, admin_token):
        """Admin should be able to update only specific fields"""
        # Update only grace_window_minutes
        update_data = {"grace_window_minutes": 60}
        
        response = requests.put(
            f"{BASE_URL}/api/attendance/settings",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=update_data
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("grace_window_minutes") == 60
        print("Partial update successful")

    def test_update_settings_weekend_days(self, admin_token):
        """Test updating weekend_days array"""
        # Set only Sunday as weekend
        update_data = {"weekend_days": [0]}
        
        response = requests.put(
            f"{BASE_URL}/api/attendance/settings",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=update_data
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("weekend_days") == [0]
        
        # Restore to Sun + Sat
        requests.put(
            f"{BASE_URL}/api/attendance/settings",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"weekend_days": [0, 6]}
        )
        print("Weekend days update successful")

    def test_update_settings_recruiter_denied(self, recruiter_token):
        """Recruiter (non-admin) should get 403 on PUT settings"""
        response = requests.put(
            f"{BASE_URL}/api/attendance/settings",
            headers={"Authorization": f"Bearer {recruiter_token}"},
            json={"grace_window_minutes": 30}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("Recruiter correctly denied from updating settings")

    def test_update_settings_unauthenticated(self):
        """Unauthenticated request should get 401"""
        response = requests.put(
            f"{BASE_URL}/api/attendance/settings",
            json={"grace_window_minutes": 30}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

class TestAttendanceSettingsDataIntegrity:
    """Test data integrity and persistence"""

    def test_settings_persist_after_update(self, admin_token):
        """Verify settings persist correctly after update"""
        # Update settings
        unique_value = 77
        update_data = {"grace_window_minutes": unique_value}
        
        requests.put(
            f"{BASE_URL}/api/attendance/settings",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=update_data
        )
        
        # GET again to verify persistence
        get_response = requests.get(
            f"{BASE_URL}/api/attendance/settings",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert get_response.status_code == 200
        data = get_response.json()
        assert data.get("grace_window_minutes") == unique_value
        print("Settings persistence verified")

    def test_all_fields_returned_in_response(self, admin_token):
        """Verify all fields are returned in settings response"""
        response = requests.get(
            f"{BASE_URL}/api/attendance/settings",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        data = response.json()
        
        required_fields = [
            "work_start_time", "work_end_time", "late_threshold_minutes",
            "half_day_hours", "full_day_hours", "reminder_time", "auto_absent_time",
            "overtime_threshold_minutes", "grace_window_minutes", "weekend_days"
        ]
        
        missing = [f for f in required_fields if f not in data]
        assert len(missing) == 0, f"Missing fields: {missing}"
        print(f"All {len(required_fields)} required fields present in response")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
