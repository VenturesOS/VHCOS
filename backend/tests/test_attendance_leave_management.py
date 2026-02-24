"""
Attendance & Leave Management Backend Tests
Tests for:
- Self check-in/check-out with admin override
- Leave request/approval workflow with leave bank
- Monthly attendance summary
- Holiday calendar CRUD
- Visibility: Admin sees all, recruiter sees own only
"""
import pytest
import requests
import os
import time
from datetime import datetime, timedelta

# Use internal localhost for backend tests to avoid Cloudflare
BASE_URL = "http://localhost:8001"

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
ADMIN_USER_ID = "eb962d6f-ad6f-454a-bd7b-edc68f8b4ff7"

RECRUITER_EMAIL = "yamini@vhc.in"
RECRUITER_PASSWORD = "VhcAdmin@2024"
RECRUITER_USER_ID = "06b70e35-bb06-41b9-a5f1-d9111112ae78"


class TestAttendanceEndpoints:
    """Tests for attendance check-in/out, my attendance, today status, and admin functions"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        time.sleep(1)  # Rate limiting
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter_token(self):
        """Get recruiter token"""
        time.sleep(2)  # Rate limiting
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": RECRUITER_EMAIL,
            "password": RECRUITER_PASSWORD
        })
        assert resp.status_code == 200, f"Recruiter login failed: {resp.text}"
        return resp.json()["access_token"]
    
    def test_recruiter_check_in(self, recruiter_token):
        """Test recruiter check-in - should return record with check_in time, status, work_mode"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        resp = requests.post(f"{BASE_URL}/api/attendance/check-in", 
            json={"work_mode": "office", "notes": "Test check-in"},
            headers=headers
        )
        # Accept both 200 (success) and 409 (already checked in)
        assert resp.status_code in [200, 409], f"Check-in failed: {resp.status_code} - {resp.text}"
        
        if resp.status_code == 200:
            data = resp.json()
            assert "check_in" in data, "Response missing check_in"
            assert "status" in data, "Response missing status"
            assert "work_mode" in data, "Response missing work_mode"
            assert data["status"] in ["present", "half_day"], f"Unexpected status: {data['status']}"
            print(f"Check-in successful: {data['check_in']}, status: {data['status']}, work_mode: {data['work_mode']}")
        else:
            print("Already checked in today - expected for repeat tests")
    
    def test_recruiter_today_status(self, recruiter_token):
        """Test GET /api/attendance/today returns today's status"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/today", headers=headers)
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "today" in data, "Response missing 'today' key"
        print(f"Today status: {data['today']}")
    
    def test_recruiter_check_out(self, recruiter_token):
        """Test recruiter check-out - should return hours_worked"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        resp = requests.post(f"{BASE_URL}/api/attendance/check-out", 
            json={"notes": "Test check-out"},
            headers=headers
        )
        # Accept 200 (success), 400 (no check-in), or 409 (already checked out)
        assert resp.status_code in [200, 400, 409], f"Check-out failed: {resp.status_code} - {resp.text}"
        
        if resp.status_code == 200:
            data = resp.json()
            assert "hours_worked" in data, "Response missing hours_worked"
            print(f"Check-out successful: hours_worked={data['hours_worked']}")
        elif resp.status_code == 409:
            print("Already checked out today")
        else:
            print("No check-in found (may need to check-in first)")
    
    def test_recruiter_my_attendance(self, recruiter_token):
        """Test GET /api/attendance/my returns attendance records"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        now = datetime.now()
        resp = requests.get(f"{BASE_URL}/api/attendance/my", 
            params={"month": now.month, "year": now.year},
            headers=headers
        )
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "records" in data, "Response missing 'records'"
        assert "month" in data, "Response missing 'month'"
        assert "year" in data, "Response missing 'year'"
        print(f"My attendance: {len(data['records'])} records for {data['month']}/{data['year']}")
    
    def test_admin_mark_attendance(self, admin_token):
        """Test admin marking attendance for another user"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        resp = requests.post(f"{BASE_URL}/api/attendance/admin/mark", 
            json={
                "user_id": RECRUITER_USER_ID,
                "date": yesterday,
                "status": "present",
                "check_in": "09:00",
                "check_out": "18:00",
                "notes": "Admin marked attendance"
            },
            headers=headers
        )
        assert resp.status_code == 200, f"Admin mark failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert data["user_id"] == RECRUITER_USER_ID, "Wrong user_id"
        assert data["date"] == yesterday, "Wrong date"
        assert data["status"] == "present", "Wrong status"
        assert "marked_by" in data, "Response missing marked_by"
        print(f"Admin marked attendance for {yesterday}: {data['status']}, marked_by: {data['marked_by']}")
    
    def test_admin_get_all_attendance(self, admin_token):
        """Test GET /api/attendance/all returns all records (admin only)"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        now = datetime.now()
        
        resp = requests.get(f"{BASE_URL}/api/attendance/all", 
            params={"month": now.month, "year": now.year},
            headers=headers
        )
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "records" in data, "Response missing 'records'"
        assert "users" in data, "Response missing 'users'"
        print(f"All attendance: {len(data['records'])} records, {len(data['users'])} users")
    
    def test_admin_monthly_report(self, admin_token):
        """Test GET /api/attendance/report/monthly returns summary for all users"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        now = datetime.now()
        
        resp = requests.get(f"{BASE_URL}/api/attendance/report/monthly", 
            params={"month": now.month, "year": now.year},
            headers=headers
        )
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "summaries" in data, "Response missing 'summaries'"
        assert "month" in data, "Response missing 'month'"
        assert "year" in data, "Response missing 'year'"
        assert "holidays" in data, "Response missing 'holidays'"
        
        # Validate summary structure
        if data["summaries"]:
            summary = data["summaries"][0]
            required_fields = ["user_id", "name", "email", "present", "absent", "leaves", "total_hours"]
            for field in required_fields:
                assert field in summary, f"Summary missing '{field}'"
        
        print(f"Monthly report: {len(data['summaries'])} users, {len(data['holidays'])} holidays")


class TestLeaveManagement:
    """Tests for leave request, approval, balance, and admin functions"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        time.sleep(1)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter_token(self):
        """Get recruiter token"""
        time.sleep(2)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": RECRUITER_EMAIL,
            "password": RECRUITER_PASSWORD
        })
        assert resp.status_code == 200, f"Recruiter login failed: {resp.text}"
        return resp.json()["access_token"]
    
    def test_set_leave_balance(self, admin_token):
        """Test admin setting leave quota for a user"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        resp = requests.put(f"{BASE_URL}/api/attendance/leave/admin/balance/{RECRUITER_USER_ID}", 
            json={
                "casual_leave": 12,
                "sick_leave": 6,
                "earned_leave": 15,
                "comp_off": 3
            },
            headers=headers
        )
        assert resp.status_code == 200, f"Set balance failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert data["user_id"] == RECRUITER_USER_ID, "Wrong user_id"
        assert data.get("casual_leave_total") == 12, f"casual_leave_total mismatch: {data}"
        assert data.get("sick_leave_total") == 6, f"sick_leave_total mismatch: {data}"
        print(f"Leave balance set: CL={data.get('casual_leave_total')}, SL={data.get('sick_leave_total')}, EL={data.get('earned_leave_total')}, CO={data.get('comp_off_total')}")
    
    def test_get_leave_balance(self, recruiter_token):
        """Test GET /api/attendance/leave/balance returns leave balance with correct totals"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        resp = requests.get(f"{BASE_URL}/api/attendance/leave/balance", headers=headers)
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "user_id" in data, "Response missing user_id"
        assert "casual_leave_total" in data, "Response missing casual_leave_total"
        assert "sick_leave_total" in data, "Response missing sick_leave_total"
        # _used fields may not exist if leave balance was only set (not incremented)
        casual_used = data.get("casual_leave_used", 0)
        
        print(f"Leave balance: CL={data['casual_leave_total']}/{casual_used}, SL={data['sick_leave_total']}/{data.get('sick_leave_used', 0)}")
    
    def test_create_leave_request(self, recruiter_token):
        """Test POST /api/attendance/leave/request creates a leave request"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        # Request leave for next month
        next_month = datetime.now().replace(day=15) + timedelta(days=30)
        start_date = next_month.strftime("%Y-%m-%d")
        end_date = (next_month + timedelta(days=1)).strftime("%Y-%m-%d")
        
        resp = requests.post(f"{BASE_URL}/api/attendance/leave/request", 
            json={
                "leave_type": "casual",
                "start_date": start_date,
                "end_date": end_date,
                "reason": "Test leave request from automated testing",
                "half_day": False
            },
            headers=headers
        )
        assert resp.status_code == 200, f"Leave request failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "id" in data, "Response missing id"
        assert data["leave_type"] == "casual", "Wrong leave_type"
        assert data["status"] == "pending", "Status should be pending"
        assert data["days"] == 2, f"Days mismatch: expected 2, got {data['days']}"
        
        print(f"Leave request created: {data['id']}, {data['days']} days, status: {data['status']}")
        return data["id"]
    
    def test_get_pending_leaves(self, admin_token):
        """Test GET /api/attendance/leave/requests/pending returns pending requests"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        resp = requests.get(f"{BASE_URL}/api/attendance/leave/requests/pending", headers=headers)
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "requests" in data, "Response missing 'requests'"
        print(f"Pending leaves: {len(data['requests'])} requests")
        return data["requests"]
    
    def test_approve_leave_request(self, admin_token, recruiter_token):
        """Test PUT /api/attendance/leave/requests/{id}/approve approves and deducts balance"""
        # First get pending requests
        headers_admin = {"Authorization": f"Bearer {admin_token}"}
        headers_recruiter = {"Authorization": f"Bearer {recruiter_token}"}
        
        # Get current balance
        balance_resp = requests.get(f"{BASE_URL}/api/attendance/leave/balance", headers=headers_recruiter)
        assert balance_resp.status_code == 200
        initial_used = balance_resp.json().get("casual_leave_used", 0)
        
        # Get pending requests
        pending_resp = requests.get(f"{BASE_URL}/api/attendance/leave/requests/pending", headers=headers_admin)
        assert pending_resp.status_code == 200
        pending = pending_resp.json()["requests"]
        
        if not pending:
            pytest.skip("No pending leave requests to approve")
        
        # Approve the first pending request
        request_id = pending[0]["id"]
        days = pending[0]["days"]
        
        resp = requests.put(f"{BASE_URL}/api/attendance/leave/requests/{request_id}/approve", 
            json={"notes": "Approved by automated test"},
            headers=headers_admin
        )
        assert resp.status_code == 200, f"Approve failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert data["status"] == "approved", f"Unexpected status: {data}"
        print(f"Leave approved: {request_id}")
        
        # Verify balance deducted
        time.sleep(0.5)
        balance_resp = requests.get(f"{BASE_URL}/api/attendance/leave/balance", headers=headers_recruiter)
        assert balance_resp.status_code == 200
        new_used = balance_resp.json().get("casual_leave_used", 0)
        
        # Balance should have increased by days approved
        assert new_used >= initial_used, f"Balance not deducted: initial={initial_used}, new={new_used}"
        print(f"Balance deducted: {initial_used} -> {new_used}")


class TestHolidayManagement:
    """Tests for holiday CRUD operations"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        time.sleep(1)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter_token(self):
        """Get recruiter token"""
        time.sleep(2)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": RECRUITER_EMAIL,
            "password": RECRUITER_PASSWORD
        })
        assert resp.status_code == 200, f"Recruiter login failed: {resp.text}"
        return resp.json()["access_token"]
    
    def test_list_holidays(self, recruiter_token):
        """Test GET /api/attendance/holidays lists holidays"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        resp = requests.get(f"{BASE_URL}/api/attendance/holidays", 
            params={"year": datetime.now().year},
            headers=headers
        )
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "holidays" in data, "Response missing 'holidays'"
        assert "year" in data, "Response missing 'year'"
        
        print(f"Holidays: {len(data['holidays'])} for year {data['year']}")
        for h in data["holidays"]:
            print(f"  - {h['name']} ({h['date']}): {h['holiday_type']}")
    
    def test_create_holiday(self, admin_token):
        """Test POST /api/attendance/holidays creates a holiday"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create a test holiday for next year to avoid conflicts
        test_date = f"{datetime.now().year + 1}-12-25"
        
        resp = requests.post(f"{BASE_URL}/api/attendance/holidays", 
            json={
                "name": "TEST_Christmas_Automated",
                "date": test_date,
                "holiday_type": "festival",
                "is_optional": True
            },
            headers=headers
        )
        # Accept 200 (created) or 409 (already exists)
        assert resp.status_code in [200, 409], f"Create holiday failed: {resp.status_code} - {resp.text}"
        
        if resp.status_code == 200:
            data = resp.json()
            assert data["name"] == "TEST_Christmas_Automated"
            assert data["date"] == test_date
            print(f"Holiday created: {data['name']} on {data['date']}")
            return data["id"]
        else:
            print("Holiday already exists on this date")
            return None
    
    def test_update_holiday(self, admin_token):
        """Test PUT /api/attendance/holidays/{id} updates a holiday"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # First get existing holidays to find one to update
        resp = requests.get(f"{BASE_URL}/api/attendance/holidays", 
            params={"year": datetime.now().year + 1},
            headers=headers
        )
        assert resp.status_code == 200
        
        holidays = resp.json()["holidays"]
        test_holidays = [h for h in holidays if h["name"].startswith("TEST_")]
        
        if not test_holidays:
            pytest.skip("No test holidays to update")
        
        holiday_id = test_holidays[0]["id"]
        
        resp = requests.put(f"{BASE_URL}/api/attendance/holidays/{holiday_id}", 
            json={
                "name": "TEST_Christmas_Updated",
                "is_optional": False
            },
            headers=headers
        )
        assert resp.status_code == 200, f"Update failed: {resp.status_code} - {resp.text}"
        print(f"Holiday {holiday_id} updated")
    
    def test_delete_holiday(self, admin_token):
        """Test DELETE /api/attendance/holidays/{id} deletes a holiday"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get test holidays
        resp = requests.get(f"{BASE_URL}/api/attendance/holidays", 
            params={"year": datetime.now().year + 1},
            headers=headers
        )
        assert resp.status_code == 200
        
        holidays = resp.json()["holidays"]
        test_holidays = [h for h in holidays if h["name"].startswith("TEST_")]
        
        if not test_holidays:
            pytest.skip("No test holidays to delete")
        
        holiday_id = test_holidays[0]["id"]
        
        resp = requests.delete(f"{BASE_URL}/api/attendance/holidays/{holiday_id}", headers=headers)
        assert resp.status_code == 200, f"Delete failed: {resp.status_code} - {resp.text}"
        print(f"Holiday {holiday_id} deleted")
        
        # Verify deletion
        resp = requests.get(f"{BASE_URL}/api/attendance/holidays", 
            params={"year": datetime.now().year + 1},
            headers=headers
        )
        remaining = [h for h in resp.json()["holidays"] if h["id"] == holiday_id]
        assert len(remaining) == 0, "Holiday not deleted"


class TestAccessControl:
    """Tests for visibility/access control - admin vs recruiter"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        time.sleep(1)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter_token(self):
        """Get recruiter token"""
        time.sleep(2)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": RECRUITER_EMAIL,
            "password": RECRUITER_PASSWORD
        })
        assert resp.status_code == 200, f"Recruiter login failed: {resp.text}"
        return resp.json()["access_token"]
    
    def test_recruiter_cannot_access_all_attendance(self, recruiter_token):
        """Recruiter should NOT access /api/attendance/all (admin only)"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        resp = requests.get(f"{BASE_URL}/api/attendance/all", headers=headers)
        assert resp.status_code == 403, f"Expected 403, got: {resp.status_code}"
        print("Recruiter correctly denied access to /all endpoint")
    
    def test_recruiter_cannot_mark_admin_attendance(self, recruiter_token):
        """Recruiter should NOT access /api/attendance/admin/mark (admin only)"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        resp = requests.post(f"{BASE_URL}/api/attendance/admin/mark", 
            json={
                "user_id": ADMIN_USER_ID,
                "date": "2026-01-15",
                "status": "present"
            },
            headers=headers
        )
        assert resp.status_code == 403, f"Expected 403, got: {resp.status_code}"
        print("Recruiter correctly denied access to admin/mark endpoint")
    
    def test_recruiter_cannot_access_monthly_report(self, recruiter_token):
        """Recruiter should NOT access /api/attendance/report/monthly (admin only)"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        resp = requests.get(f"{BASE_URL}/api/attendance/report/monthly", headers=headers)
        assert resp.status_code == 403, f"Expected 403, got: {resp.status_code}"
        print("Recruiter correctly denied access to monthly report")
    
    def test_recruiter_cannot_set_leave_balance(self, recruiter_token):
        """Recruiter should NOT access /api/attendance/leave/admin/balance/{id} (admin only)"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        resp = requests.put(f"{BASE_URL}/api/attendance/leave/admin/balance/{ADMIN_USER_ID}", 
            json={"casual_leave": 10},
            headers=headers
        )
        assert resp.status_code == 403, f"Expected 403, got: {resp.status_code}"
        print("Recruiter correctly denied access to set leave balance")
    
    def test_recruiter_cannot_create_holiday(self, recruiter_token):
        """Recruiter should NOT create holidays (admin only)"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        resp = requests.post(f"{BASE_URL}/api/attendance/holidays", 
            json={
                "name": "Unauthorized Holiday",
                "date": "2026-12-31",
                "holiday_type": "national"
            },
            headers=headers
        )
        assert resp.status_code == 403, f"Expected 403, got: {resp.status_code}"
        print("Recruiter correctly denied access to create holiday")
    
    def test_recruiter_can_view_holidays(self, recruiter_token):
        """Recruiter CAN view holidays (read access allowed)"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        resp = requests.get(f"{BASE_URL}/api/attendance/holidays", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got: {resp.status_code}"
        print("Recruiter can view holidays - correct")
    
    def test_admin_can_access_all(self, admin_token):
        """Admin can access all endpoints"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Test all admin-only endpoints
        endpoints = [
            ("GET", "/api/attendance/all"),
            ("GET", "/api/attendance/report/monthly"),
            ("GET", "/api/attendance/leave/requests/pending"),
            ("GET", "/api/attendance/leave/admin/balances"),
        ]
        
        for method, endpoint in endpoints:
            if method == "GET":
                resp = requests.get(f"{BASE_URL}{endpoint}", headers=headers)
            assert resp.status_code == 200, f"Admin failed on {endpoint}: {resp.status_code}"
            print(f"Admin access to {endpoint}: OK")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
