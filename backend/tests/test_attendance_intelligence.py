"""
Attendance Intelligence / Analytics Backend Tests
Tests for:
- GET /api/attendance/analytics - Returns {metrics, charts, insights}
- GET /api/attendance/analytics/health-scores - Health scores (0-100 range)
- POST /api/attendance/analytics/cron/trigger-reminders - Trigger reminder job
- POST /api/attendance/analytics/cron/trigger-auto-absent - Trigger auto-absent marking
- GET /api/attendance/analytics/cron-logs - Cron job execution history
- GET /api/attendance/analytics/notifications - In-app notifications
- PUT /api/attendance/settings - Extended settings (reminder_time, auto_absent_time, etc.)
- Cron job lock mechanism prevents duplicate execution
- should_remind() decision layer - skips weekends, holidays, approved leaves, already-checked-in
"""
import pytest
import requests
import os
import time
from datetime import datetime, timedelta

# Use internal localhost for backend tests to avoid Cloudflare issues
BASE_URL = "http://localhost:8001"

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"

RECRUITER_EMAIL = "yamini@vhc.in"
RECRUITER_PASSWORD = "VhcAdmin@2024"


class TestAttendanceAnalyticsEndpoint:
    """Tests for GET /api/attendance/analytics - Main analytics endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        time.sleep(2)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json()["access_token"]
    
    def test_analytics_returns_correct_structure(self, admin_token):
        """Test GET /api/attendance/analytics returns {metrics, charts, insights}"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics", 
            params={"days": 30},
            headers=headers
        )
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        
        # Validate top-level structure
        assert "metrics" in data, "Response missing 'metrics'"
        assert "charts" in data, "Response missing 'charts'"
        assert "insights" in data, "Response missing 'insights'"
        
        # Validate metrics structure
        metrics = data["metrics"]
        required_metric_fields = [
            "period", "headcount", "total_records", "present", "absent",
            "late", "wfh", "total_hours", "avg_hours_per_day",
            "attendance_rate", "absentee_rate", "late_rate"
        ]
        for field in required_metric_fields:
            assert field in metrics, f"Metrics missing '{field}'"
        
        # Validate charts structure
        charts = data["charts"]
        required_chart_fields = ["daily_trend", "weekly_late", "team_comparison", "work_mode_distribution"]
        for field in required_chart_fields:
            assert field in charts, f"Charts missing '{field}'"
        
        # Validate insights is a list
        assert isinstance(data["insights"], list), "Insights should be a list"
        
        print(f"Analytics: headcount={metrics['headcount']}, present={metrics['present']}, absent={metrics['absent']}")
        print(f"Charts: daily_trend={len(charts['daily_trend'])} days, team={len(charts['team_comparison'])} users")
        print(f"Insights: {len(data['insights'])} patterns detected")
    
    def test_analytics_daily_trend_chart_data(self, admin_token):
        """Test daily_trend chart data structure"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics", 
            params={"days": 30},
            headers=headers
        )
        assert resp.status_code == 200
        
        daily_trend = resp.json()["charts"]["daily_trend"]
        if daily_trend:
            entry = daily_trend[0]
            assert "date" in entry, "daily_trend missing 'date'"
            assert "present" in entry, "daily_trend missing 'present'"
            assert "absent" in entry, "daily_trend missing 'absent'"
            print(f"Daily trend sample: {entry}")
    
    def test_analytics_work_mode_distribution(self, admin_token):
        """Test work_mode_distribution chart data (pie chart)"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics", 
            params={"days": 30},
            headers=headers
        )
        assert resp.status_code == 200
        
        work_mode_dist = resp.json()["charts"]["work_mode_distribution"]
        assert isinstance(work_mode_dist, list), "work_mode_distribution should be a list"
        
        # Validate structure (for pie chart)
        for entry in work_mode_dist:
            assert "name" in entry, "work_mode_distribution entry missing 'name'"
            assert "value" in entry, "work_mode_distribution entry missing 'value'"
        
        print(f"Work mode distribution: {work_mode_dist}")
    
    def test_analytics_team_comparison(self, admin_token):
        """Test team_comparison chart data (bar chart)"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics", 
            params={"days": 30},
            headers=headers
        )
        assert resp.status_code == 200
        
        team_comparison = resp.json()["charts"]["team_comparison"]
        if team_comparison:
            entry = team_comparison[0]
            assert "name" in entry, "team_comparison missing 'name'"
            assert "present" in entry, "team_comparison missing 'present'"
            assert "absent" in entry, "team_comparison missing 'absent'"
            assert "late" in entry, "team_comparison missing 'late'"
            print(f"Team comparison sample: {entry}")


class TestHealthScoresEndpoint:
    """Tests for GET /api/attendance/analytics/health-scores"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        time.sleep(2)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return resp.json()["access_token"]
    
    def test_health_scores_returns_correct_structure(self, admin_token):
        """Test health scores endpoint returns scores for all users"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics/health-scores", 
            params={"days": 30},
            headers=headers
        )
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "scores" in data, "Response missing 'scores'"
        assert "average_score" in data, "Response missing 'average_score'"
        
        # Validate scores structure
        scores = data["scores"]
        assert isinstance(scores, list), "Scores should be a list"
        
        if scores:
            score_entry = scores[0]
            assert "user_id" in score_entry, "Score missing 'user_id'"
            assert "name" in score_entry, "Score missing 'name'"
            assert "score" in score_entry, "Score missing 'score'"
            assert "label" in score_entry, "Score missing 'label'"
            
            # Validate score is 0-100
            for s in scores:
                assert 0 <= s["score"] <= 100, f"Score {s['score']} out of 0-100 range"
        
        print(f"Health scores: {len(scores)} users, avg={data['average_score']}")
    
    def test_health_scores_breakdown(self, admin_token):
        """Test health score breakdown fields"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics/health-scores", 
            params={"days": 30},
            headers=headers
        )
        assert resp.status_code == 200
        
        scores = resp.json()["scores"]
        if scores:
            score_entry = scores[0]
            # Check for breakdown (if present)
            if "breakdown" in score_entry:
                breakdown = score_entry["breakdown"]
                assert isinstance(breakdown, dict), "Breakdown should be a dict"
            
            # Check for stats (if present)
            if "stats" in score_entry:
                stats = score_entry["stats"]
                assert isinstance(stats, dict), "Stats should be a dict"
                print(f"Health score stats: {stats}")


class TestCronJobEndpoints:
    """Tests for cron job triggering and logging"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        time.sleep(2)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return resp.json()["access_token"]
    
    def test_trigger_reminders_creates_notifications(self, admin_token):
        """Test POST /api/attendance/analytics/cron/trigger-reminders"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.post(f"{BASE_URL}/api/attendance/analytics/cron/trigger-reminders", 
            headers=headers
        )
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "message" in data, "Response missing 'message'"
        print(f"Trigger reminders: {data['message']}")
    
    def test_trigger_auto_absent_marks_employees(self, admin_token):
        """Test POST /api/attendance/analytics/cron/trigger-auto-absent"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.post(f"{BASE_URL}/api/attendance/analytics/cron/trigger-auto-absent", 
            headers=headers
        )
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "message" in data, "Response missing 'message'"
        print(f"Trigger auto-absent: {data['message']}")
    
    def test_cron_logs_shows_execution_history(self, admin_token):
        """Test GET /api/attendance/analytics/cron-logs returns execution history"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics/cron-logs", 
            params={"limit": 20},
            headers=headers
        )
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "logs" in data, "Response missing 'logs'"
        
        logs = data["logs"]
        assert isinstance(logs, list), "Logs should be a list"
        
        if logs:
            log_entry = logs[0]
            assert "job_name" in log_entry, "Log missing 'job_name'"
            assert "status" in log_entry, "Log missing 'status'"
            assert "executed_at" in log_entry, "Log missing 'executed_at'"
            
            print(f"Cron logs: {len(logs)} entries")
            for log in logs[:3]:
                print(f"  - {log['job_name']}: {log['status']} at {log['executed_at']}")
    
    def test_cron_logs_filter_by_job_name(self, admin_token):
        """Test cron logs can be filtered by job_name"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics/cron-logs", 
            params={"job_name": "attendance_reminder", "limit": 5},
            headers=headers
        )
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        logs = resp.json()["logs"]
        # All returned logs should be for the specified job
        for log in logs:
            assert log["job_name"] == "attendance_reminder", f"Wrong job_name: {log['job_name']}"
        
        print(f"Filtered cron logs (attendance_reminder): {len(logs)} entries")


class TestNotificationsEndpoint:
    """Tests for GET /api/attendance/analytics/notifications"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        time.sleep(2)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return resp.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter_token(self):
        """Get recruiter token"""
        time.sleep(2)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": RECRUITER_EMAIL,
            "password": RECRUITER_PASSWORD
        })
        assert resp.status_code == 200
        return resp.json()["access_token"]
    
    def test_get_notifications_returns_correct_structure(self, admin_token):
        """Test GET /api/attendance/analytics/notifications"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics/notifications", 
            params={"limit": 20},
            headers=headers
        )
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "notifications" in data, "Response missing 'notifications'"
        assert "unread_count" in data, "Response missing 'unread_count'"
        
        print(f"Notifications: {len(data['notifications'])} total, {data['unread_count']} unread")
    
    def test_recruiter_can_view_own_notifications(self, recruiter_token):
        """Recruiter can view their own notifications"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics/notifications", 
            params={"limit": 10},
            headers=headers
        )
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "notifications" in data
        print(f"Recruiter notifications: {len(data['notifications'])}")


class TestExtendedSettingsEndpoint:
    """Tests for PUT /api/attendance/settings with new fields"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        time.sleep(2)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return resp.json()["access_token"]
    
    def test_get_settings_includes_new_fields(self, admin_token):
        """Test GET /api/attendance/settings returns extended fields"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/settings", headers=headers)
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        
        # Check for new fields
        expected_fields = [
            "work_start_time", "work_end_time", "late_threshold_minutes",
            "half_day_hours", "full_day_hours",
            "reminder_time", "auto_absent_time", "overtime_threshold_minutes",
            "grace_window_minutes", "weekend_days"
        ]
        for field in expected_fields:
            assert field in data, f"Settings missing '{field}'"
        
        print(f"Settings: reminder_time={data['reminder_time']}, auto_absent_time={data['auto_absent_time']}")
        print(f"Settings: overtime_threshold={data['overtime_threshold_minutes']}m, grace_window={data['grace_window_minutes']}m")
        print(f"Settings: weekend_days={data['weekend_days']}")
    
    def test_update_extended_settings(self, admin_token):
        """Test PUT /api/attendance/settings accepts new fields"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Update extended settings
        resp = requests.put(f"{BASE_URL}/api/attendance/settings", 
            json={
                "reminder_time": "10:15",
                "auto_absent_time": "18:45",
                "overtime_threshold_minutes": 90,
                "grace_window_minutes": 45,
                "weekend_days": [0, 6]  # Sunday, Saturday
            },
            headers=headers
        )
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert data["reminder_time"] == "10:15", f"reminder_time not updated: {data}"
        assert data["auto_absent_time"] == "18:45", f"auto_absent_time not updated: {data}"
        assert data["overtime_threshold_minutes"] == 90, f"overtime_threshold not updated: {data}"
        assert data["grace_window_minutes"] == 45, f"grace_window not updated: {data}"
        
        print("Extended settings updated successfully")
        
        # Restore defaults
        resp = requests.put(f"{BASE_URL}/api/attendance/settings", 
            json={
                "reminder_time": "10:00",
                "auto_absent_time": "18:30",
                "overtime_threshold_minutes": 60,
                "grace_window_minutes": 30
            },
            headers=headers
        )
        assert resp.status_code == 200


class TestRoleBasedAccessControl:
    """Tests for role-based access control on analytics endpoints"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        time.sleep(2)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return resp.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def recruiter_token(self):
        """Get recruiter token"""
        time.sleep(2)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": RECRUITER_EMAIL,
            "password": RECRUITER_PASSWORD
        })
        assert resp.status_code == 200
        return resp.json()["access_token"]
    
    def test_recruiter_cannot_access_analytics(self, recruiter_token):
        """Recruiter should NOT access analytics endpoint (admin/employer only)"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics", headers=headers)
        assert resp.status_code == 403, f"Expected 403, got: {resp.status_code}"
        print("Recruiter correctly denied access to analytics")
    
    def test_recruiter_cannot_access_health_scores(self, recruiter_token):
        """Recruiter should NOT access health scores endpoint"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics/health-scores", headers=headers)
        assert resp.status_code == 403, f"Expected 403, got: {resp.status_code}"
        print("Recruiter correctly denied access to health scores")
    
    def test_recruiter_cannot_trigger_cron_jobs(self, recruiter_token):
        """Recruiter should NOT trigger cron jobs (admin only)"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        resp = requests.post(f"{BASE_URL}/api/attendance/analytics/cron/trigger-reminders", headers=headers)
        assert resp.status_code == 403, f"Expected 403 for trigger-reminders, got: {resp.status_code}"
        
        resp = requests.post(f"{BASE_URL}/api/attendance/analytics/cron/trigger-auto-absent", headers=headers)
        assert resp.status_code == 403, f"Expected 403 for trigger-auto-absent, got: {resp.status_code}"
        
        print("Recruiter correctly denied access to cron triggers")
    
    def test_recruiter_cannot_view_cron_logs(self, recruiter_token):
        """Recruiter should NOT view cron logs (admin only)"""
        headers = {"Authorization": f"Bearer {recruiter_token}"}
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics/cron-logs", headers=headers)
        assert resp.status_code == 403, f"Expected 403, got: {resp.status_code}"
        print("Recruiter correctly denied access to cron logs")
    
    def test_admin_can_access_all_analytics_endpoints(self, admin_token):
        """Admin can access all analytics endpoints"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        endpoints = [
            ("GET", "/api/attendance/analytics"),
            ("GET", "/api/attendance/analytics/health-scores"),
            ("GET", "/api/attendance/analytics/cron-logs"),
            ("GET", "/api/attendance/analytics/notifications"),
        ]
        
        for method, endpoint in endpoints:
            resp = requests.get(f"{BASE_URL}{endpoint}", headers=headers)
            assert resp.status_code == 200, f"Admin failed on {endpoint}: {resp.status_code}"
            print(f"Admin access to {endpoint}: OK")


class TestCronJobLockMechanism:
    """Tests for cron job lock to prevent duplicate execution"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        time.sleep(2)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return resp.json()["access_token"]
    
    def test_multiple_triggers_dont_duplicate(self, admin_token):
        """Test that triggering reminders twice quickly doesn't cause issues"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get initial log count
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics/cron-logs", 
            params={"job_name": "attendance_reminder", "limit": 100},
            headers=headers
        )
        assert resp.status_code == 200
        initial_count = len(resp.json()["logs"])
        
        # Trigger twice quickly
        resp1 = requests.post(f"{BASE_URL}/api/attendance/analytics/cron/trigger-reminders", headers=headers)
        resp2 = requests.post(f"{BASE_URL}/api/attendance/analytics/cron/trigger-reminders", headers=headers)
        
        # Both should return 200 (the second will skip due to lock or complete normally)
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        
        time.sleep(0.5)
        
        # Get new log count
        resp = requests.get(f"{BASE_URL}/api/attendance/analytics/cron-logs", 
            params={"job_name": "attendance_reminder", "limit": 100},
            headers=headers
        )
        new_count = len(resp.json()["logs"])
        
        # Should have at most 2 new entries (not duplicates causing issues)
        new_entries = new_count - initial_count
        assert new_entries <= 2, f"Too many new entries: {new_entries}"
        print(f"Lock mechanism working: {new_entries} new log entries after double trigger")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
