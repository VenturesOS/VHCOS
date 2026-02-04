"""
Test Suite for VHC Talent OS P1 - Email Notifications and Job Alert Subscriptions
Tests all alert preferences, notification history, and job notification trigger endpoints
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://fast-match-db.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
CANDIDATE_EMAIL = "testcandidate@vhc.in"
CANDIDATE_PASSWORD = "Test@123"


class TestSetup:
    """Setup and authentication tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def candidate_token(self):
        """Get candidate authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CANDIDATE_EMAIL,
            "password": CANDIDATE_PASSWORD
        })
        assert response.status_code == 200, f"Candidate login failed: {response.text}"
        return response.json()["access_token"]
    
    def test_admin_login(self):
        """Test admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "admin"
        print("✅ Admin login successful")
    
    def test_candidate_login(self):
        """Test candidate login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CANDIDATE_EMAIL,
            "password": CANDIDATE_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "candidate"
        print("✅ Candidate login successful")


class TestAlertPreferences:
    """Test job alert preferences CRUD operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get candidate token for each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CANDIDATE_EMAIL,
            "password": CANDIDATE_PASSWORD
        })
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_alert_preferences_creates_default(self):
        """GET /api/alerts/preferences - Should create default preferences if not exists"""
        response = requests.get(f"{BASE_URL}/api/alerts/preferences", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "id" in data
        assert "candidate_id" in data
        assert "candidate_email" in data
        assert "is_active" in data
        assert "email_enabled" in data
        assert "skills" in data
        assert "frequency" in data
        assert "whatsapp_opt_in" in data
        assert "notification_channels" in data
        
        # Verify default values
        assert data["email_enabled"] == True
        assert data["whatsapp_opt_in"] == False
        assert "email" in data["notification_channels"]
        print(f"✅ GET /api/alerts/preferences - Default preferences created/retrieved")
        print(f"   is_active: {data['is_active']}, email_enabled: {data['email_enabled']}")
    
    def test_create_alert_preferences(self):
        """POST /api/alerts/preferences - Create/enable job alert preferences"""
        payload = {
            "skills": ["Python", "FastAPI", "React"],
            "location_preference": "Remote",
            "experience_min": 2,
            "experience_max": 8,
            "job_types": ["full-time", "remote"],
            "frequency": "instant",
            "email_enabled": True
        }
        
        response = requests.post(f"{BASE_URL}/api/alerts/preferences", 
                                 json=payload, headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["is_active"] == True  # Should be activated
        assert data["skills"] == ["Python", "FastAPI", "React"]
        assert data["location_preference"] == "Remote"
        assert data["experience_min"] == 2
        assert data["experience_max"] == 8
        assert "full-time" in data["job_types"]
        assert data["frequency"] == "instant"
        print("✅ POST /api/alerts/preferences - Preferences created and activated")
    
    def test_update_alert_preferences(self):
        """PUT /api/alerts/preferences - Update existing preferences"""
        payload = {
            "skills": ["Python", "Django", "PostgreSQL"],
            "location_preference": "Bangalore",
            "frequency": "daily"
        }
        
        response = requests.put(f"{BASE_URL}/api/alerts/preferences", 
                                json=payload, headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["skills"] == ["Python", "Django", "PostgreSQL"]
        assert data["location_preference"] == "Bangalore"
        assert data["frequency"] == "daily"
        print("✅ PUT /api/alerts/preferences - Preferences updated successfully")
    
    def test_pause_alerts(self):
        """POST /api/alerts/pause - Pause job alerts"""
        response = requests.post(f"{BASE_URL}/api/alerts/pause", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "message" in data
        assert "paused" in data["message"].lower()
        
        # Verify alerts are paused
        prefs_response = requests.get(f"{BASE_URL}/api/alerts/preferences", headers=self.headers)
        assert prefs_response.json()["is_active"] == False
        print("✅ POST /api/alerts/pause - Alerts paused successfully")
    
    def test_resume_alerts(self):
        """POST /api/alerts/resume - Resume job alerts"""
        response = requests.post(f"{BASE_URL}/api/alerts/resume", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "message" in data
        assert "resumed" in data["message"].lower()
        
        # Verify alerts are resumed
        prefs_response = requests.get(f"{BASE_URL}/api/alerts/preferences", headers=self.headers)
        assert prefs_response.json()["is_active"] == True
        print("✅ POST /api/alerts/resume - Alerts resumed successfully")
    
    def test_unsubscribe_from_alerts(self):
        """DELETE /api/alerts/preferences - Unsubscribe from alerts"""
        response = requests.delete(f"{BASE_URL}/api/alerts/preferences", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "message" in data
        assert "unsubscribed" in data["message"].lower()
        
        # Verify alerts are deactivated
        prefs_response = requests.get(f"{BASE_URL}/api/alerts/preferences", headers=self.headers)
        assert prefs_response.json()["is_active"] == False
        print("✅ DELETE /api/alerts/preferences - Unsubscribed successfully")


class TestWhatsAppOptInOut:
    """Test WhatsApp opt-in/opt-out functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get candidate token for each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CANDIDATE_EMAIL,
            "password": CANDIDATE_PASSWORD
        })
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_whatsapp_opt_in_fails_when_not_configured(self):
        """POST /api/alerts/whatsapp/opt-in - Should fail when Twilio not configured"""
        payload = {
            "whatsapp_number": "+919876543210",
            "opt_in": True
        }
        
        response = requests.post(f"{BASE_URL}/api/alerts/whatsapp/opt-in", 
                                 json=payload, headers=self.headers)
        
        # Should return 400 because Twilio is not configured
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data
        assert "not configured" in data["detail"].lower()
        print("✅ POST /api/alerts/whatsapp/opt-in - Correctly fails when Twilio not configured")
    
    def test_whatsapp_opt_out(self):
        """POST /api/alerts/whatsapp/opt-out - Should work even if not opted in"""
        response = requests.post(f"{BASE_URL}/api/alerts/whatsapp/opt-out", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "message" in data
        assert "opted out" in data["message"].lower() or "whatsapp" in data["message"].lower()
        print("✅ POST /api/alerts/whatsapp/opt-out - Opt-out successful")


class TestNotificationHistory:
    """Test notification history endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get candidate token for each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CANDIDATE_EMAIL,
            "password": CANDIDATE_PASSWORD
        })
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_notification_history(self):
        """GET /api/notifications/history - Get candidate's notification history"""
        response = requests.get(f"{BASE_URL}/api/notifications/history?limit=10", 
                                headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        
        # If there are notifications, verify structure
        if len(data) > 0:
            notif = data[0]
            assert "id" in notif
            assert "type" in notif
            assert "channel" in notif
            assert "status" in notif
            assert "created_at" in notif
            print(f"✅ GET /api/notifications/history - Found {len(data)} notifications")
        else:
            print("✅ GET /api/notifications/history - Empty history (expected for new user)")


class TestAdminNotificationStats:
    """Test admin notification statistics endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_notification_stats(self):
        """GET /api/admin/notifications/stats - Get notification statistics"""
        response = requests.get(f"{BASE_URL}/api/admin/notifications/stats", 
                                headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "total_sent" in data
        assert "total_failed" in data
        assert "total_skipped" in data
        assert "email_sent" in data
        assert "whatsapp_sent" in data
        assert "active_subscribers" in data
        assert "whatsapp_opted_in" in data
        
        # Verify values are integers
        assert isinstance(data["total_sent"], int)
        assert isinstance(data["active_subscribers"], int)
        
        print(f"✅ GET /api/admin/notifications/stats - Stats retrieved")
        print(f"   total_sent: {data['total_sent']}, total_skipped: {data['total_skipped']}")
        print(f"   active_subscribers: {data['active_subscribers']}")
    
    def test_notification_stats_requires_admin(self):
        """GET /api/admin/notifications/stats - Should require admin role"""
        # Get candidate token
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CANDIDATE_EMAIL,
            "password": CANDIDATE_PASSWORD
        })
        candidate_token = response.json()["access_token"]
        candidate_headers = {"Authorization": f"Bearer {candidate_token}"}
        
        response = requests.get(f"{BASE_URL}/api/admin/notifications/stats", 
                                headers=candidate_headers)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✅ Admin stats endpoint correctly requires admin role")


class TestJobNotificationTriggers:
    """Test job creation with notifications and manual notification triggers"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_create_job_with_notifications(self):
        """POST /api/jobs/with-notifications - Create job and trigger notifications"""
        job_payload = {
            "title": f"TEST_Senior Python Developer {uuid.uuid4().hex[:6]}",
            "description": "We are looking for a Senior Python Developer with FastAPI experience.",
            "requirements": "5+ years Python, FastAPI, PostgreSQL, Docker",
            "location": "Remote",
            "salary_range": "150000-200000",
            "job_type": "full-time",
            "experience_required": "5-8 years"
        }
        
        response = requests.post(f"{BASE_URL}/api/jobs/with-notifications", 
                                 json=job_payload, headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "id" in data
        assert data["title"] == job_payload["title"]
        assert data["status"] == "active"
        
        # Store job_id for cleanup
        self.created_job_id = data["id"]
        print(f"✅ POST /api/jobs/with-notifications - Job created: {data['id']}")
        print("   Notification task triggered in background")
        return data["id"]
    
    def test_manually_trigger_notifications(self):
        """POST /api/jobs/{job_id}/notify-candidates - Manually trigger notifications"""
        # First get an existing job
        response = requests.get(f"{BASE_URL}/api/jobs", headers=self.headers)
        assert response.status_code == 200
        
        jobs = response.json()
        if len(jobs) == 0:
            pytest.skip("No jobs available to test notification trigger")
        
        job_id = jobs[0]["id"]
        
        response = requests.post(f"{BASE_URL}/api/jobs/{job_id}/notify-candidates", 
                                 headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "message" in data
        assert "job_id" in data
        assert data["job_id"] == job_id
        print(f"✅ POST /api/jobs/{job_id}/notify-candidates - Notification task started")
    
    def test_notify_nonexistent_job(self):
        """POST /api/jobs/{job_id}/notify-candidates - Should fail for non-existent job"""
        fake_job_id = str(uuid.uuid4())
        
        response = requests.post(f"{BASE_URL}/api/jobs/{fake_job_id}/notify-candidates", 
                                 headers=self.headers)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✅ Notify non-existent job correctly returns 404")


class TestAuthorizationChecks:
    """Test that endpoints require proper authentication"""
    
    def test_alerts_preferences_requires_auth(self):
        """Alert preferences endpoints require authentication"""
        response = requests.get(f"{BASE_URL}/api/alerts/preferences")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ GET /api/alerts/preferences requires authentication")
    
    def test_notification_history_requires_auth(self):
        """Notification history requires authentication"""
        response = requests.get(f"{BASE_URL}/api/notifications/history")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ GET /api/notifications/history requires authentication")
    
    def test_admin_stats_requires_auth(self):
        """Admin stats requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/notifications/stats")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ GET /api/admin/notifications/stats requires authentication")


class TestCleanup:
    """Cleanup test data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_cleanup_test_jobs(self):
        """Clean up TEST_ prefixed jobs"""
        response = requests.get(f"{BASE_URL}/api/jobs", headers=self.headers)
        if response.status_code == 200:
            jobs = response.json()
            test_jobs = [j for j in jobs if j.get("title", "").startswith("TEST_")]
            for job in test_jobs:
                requests.delete(f"{BASE_URL}/api/jobs/{job['id']}", headers=self.headers)
            print(f"✅ Cleaned up {len(test_jobs)} test jobs")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
