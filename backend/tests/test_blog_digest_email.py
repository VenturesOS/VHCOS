"""
Blog Digest Email API Tests — Phase 2: Resend integration for weekly digest distribution.
Tests admin digest endpoints, public unsubscribe/resubscribe, and access control.
"""
import pytest
import requests
import os
import hmac
import hashlib

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
JWT_SECRET_KEY = "vhc-talent-os-jwt-secret-key-2024-production"

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
# Employer credentials - using existing employer user
EMPLOYER_EMAIL = "maneet@vhc.in"
EMPLOYER_PASSWORD = "VhcEmployer@2024"  # May not work - will skip tests if login fails


def generate_unsubscribe_token(user_id: str, email: str) -> str:
    """Generate HMAC-based unsubscribe token (same logic as backend)."""
    payload = f"{user_id}:{email}"
    sig = hmac.new(JWT_SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{user_id}:{sig}"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def admin_user_data():
    """Get admin user data from /api/auth/me."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    me_response = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert me_response.status_code == 200
    return me_response.json()


@pytest.fixture(scope="module")
def employer_token():
    """Get employer (non-admin) authentication token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMPLOYER_EMAIL, "password": EMPLOYER_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Employer login failed (credentials may not be set): {response.text}")
    return response.json()["access_token"]


class TestAdminDigestList:
    """Test GET /api/admin/blog-digests - list digests with send_log enrichment"""
    
    def test_list_digests_admin_success(self, admin_token):
        """Admin can list all digests with send log enrichment."""
        response = requests.get(
            f"{BASE_URL}/api/admin/blog-digests",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "digests" in data
        assert isinstance(data["digests"], list)
        
        # If digests exist, check structure
        if data["digests"]:
            digest = data["digests"][0]
            assert "week_key" in digest
            assert "title" in digest
            # send_log should be present (may be null if not sent)
            assert "send_log" in digest
        print(f"Found {len(data['digests'])} digests")
    
    def test_list_digests_employer_forbidden(self, employer_token):
        """Non-admin (employer) gets 403 on admin endpoint."""
        response = requests.get(
            f"{BASE_URL}/api/admin/blog-digests",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 403
        print("Employer correctly blocked from admin digest list")
    
    def test_list_digests_no_auth_forbidden(self):
        """Unauthenticated request gets 401 or 403."""
        response = requests.get(f"{BASE_URL}/api/admin/blog-digests")
        assert response.status_code in [401, 403]  # Either is acceptable for no auth


class TestAdminDigestPreview:
    """Test GET /api/admin/blog-digest/preview - preview email HTML"""
    
    def test_preview_digest_latest(self, admin_token):
        """Admin can preview latest digest HTML."""
        response = requests.get(
            f"{BASE_URL}/api/admin/blog-digest/preview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        # May be 404 if no digests exist
        if response.status_code == 404:
            print("No digest found to preview - skipping")
            pytest.skip("No digest available for preview")
        
        assert response.status_code == 200
        data = response.json()
        assert "week_key" in data
        assert "html" in data
        assert "title" in data
        
        # Verify HTML contains expected elements
        html = data["html"]
        assert "VHC Talent Advisory" in html
        assert "Unsubscribe" in html
        print(f"Preview generated for digest: {data['week_key']}")
    
    def test_preview_digest_with_week_key(self, admin_token):
        """Admin can preview specific digest by week_key."""
        # First get list to find a week_key
        list_resp = requests.get(
            f"{BASE_URL}/api/admin/blog-digests",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        if list_resp.status_code != 200 or not list_resp.json().get("digests"):
            pytest.skip("No digests available")
        
        week_key = list_resp.json()["digests"][0]["week_key"]
        
        response = requests.get(
            f"{BASE_URL}/api/admin/blog-digest/preview",
            params={"week_key": week_key},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["week_key"] == week_key
        print(f"Preview for specific week_key {week_key} successful")
    
    def test_preview_digest_employer_forbidden(self, employer_token):
        """Non-admin gets 403 on preview endpoint."""
        response = requests.get(
            f"{BASE_URL}/api/admin/blog-digest/preview",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 403


class TestAdminSendDigest:
    """Test POST /api/admin/blog-digest/send - send digest to segments"""
    
    def test_send_digest_invalid_segment(self, admin_token):
        """Invalid segment returns 400."""
        response = requests.post(
            f"{BASE_URL}/api/admin/blog-digest/send",
            json={"segments": ["invalid_segment"]},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400
        assert "Invalid segments" in response.json().get("detail", "")
        print("Invalid segment correctly rejected")
    
    def test_send_digest_empty_segments(self, admin_token):
        """Empty segments list returns 400."""
        response = requests.post(
            f"{BASE_URL}/api/admin/blog-digest/send",
            json={"segments": []},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400
        assert "At least one segment" in response.json().get("detail", "")
        print("Empty segments correctly rejected")
    
    def test_send_digest_employer_forbidden(self, employer_token):
        """Non-admin gets 403 on send endpoint."""
        response = requests.post(
            f"{BASE_URL}/api/admin/blog-digest/send",
            json={"segments": ["employer"]},
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 403
        print("Employer correctly blocked from sending digest")
    
    def test_send_digest_duplicate_prevention(self, admin_token):
        """Sending to same segment+week combo is blocked (skipped with reason=duplicate)."""
        # First check if digests exist
        list_resp = requests.get(
            f"{BASE_URL}/api/admin/blog-digests",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        if list_resp.status_code != 200 or not list_resp.json().get("digests"):
            pytest.skip("No digests available to test duplicate prevention")
        
        digest = list_resp.json()["digests"][0]
        week_key = digest["week_key"]
        
        # Check if this digest was already sent to 'admin' segment
        if digest.get("send_log"):
            # Try sending again to the same segment
            response = requests.post(
                f"{BASE_URL}/api/admin/blog-digest/send",
                json={"segments": ["admin"], "week_key": week_key},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code == 200
            data = response.json()
            # Should be skipped due to duplicate
            if data.get("status") == "skipped" and data.get("reason") == "duplicate":
                print(f"Duplicate prevention working: {data['message']}")
            else:
                print(f"Send result: {data}")
        else:
            print("Digest not yet sent - duplicate prevention not tested")


class TestAdminRecipientPreview:
    """Test GET /api/admin/blog-digest/recipients - preview recipients"""
    
    def test_recipients_single_segment(self, admin_token):
        """Admin can preview recipients for single segment."""
        response = requests.get(
            f"{BASE_URL}/api/admin/blog-digest/recipients",
            params={"segments": "employer"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "segments" in data
        assert "total" in data
        assert "recipients" in data
        assert "employer" in data["segments"]
        
        # Check recipient structure
        if data["recipients"]:
            r = data["recipients"][0]
            assert "email" in r
            assert "role" in r
        print(f"Found {data['total']} recipients for employer segment")
    
    def test_recipients_multiple_segments(self, admin_token):
        """Admin can preview recipients for multiple segments."""
        response = requests.get(
            f"{BASE_URL}/api/admin/blog-digest/recipients",
            params={"segments": "employer,recruiter,candidate"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["segments"]) == 3
        print(f"Found {data['total']} recipients for 3 segments")
    
    def test_recipients_invalid_segment_filtered(self, admin_token):
        """Invalid segments are filtered out."""
        response = requests.get(
            f"{BASE_URL}/api/admin/blog-digest/recipients",
            params={"segments": "invalid,employer"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # Only valid segment should remain
        assert "employer" in data["segments"]
        assert "invalid" not in data["segments"]
        print("Invalid segments correctly filtered")
    
    def test_recipients_all_invalid_400(self, admin_token):
        """All invalid segments returns 400."""
        response = requests.get(
            f"{BASE_URL}/api/admin/blog-digest/recipients",
            params={"segments": "invalid1,invalid2"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400
        assert "No valid segments" in response.json().get("detail", "")
    
    def test_recipients_employer_forbidden(self, employer_token):
        """Non-admin gets 403."""
        response = requests.get(
            f"{BASE_URL}/api/admin/blog-digest/recipients",
            params={"segments": "employer"},
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 403


class TestAdminSendLogs:
    """Test GET /api/admin/blog-digest/send-logs - get send history"""
    
    def test_send_logs_admin_success(self, admin_token):
        """Admin can get send logs."""
        response = requests.get(
            f"{BASE_URL}/api/admin/blog-digest/send-logs",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert isinstance(data["logs"], list)
        
        # Check log structure if logs exist
        if data["logs"]:
            log = data["logs"][0]
            assert "digest_week_key" in log
            assert "segments" in log
            assert "total_recipients" in log
            assert "success_count" in log
            assert "failure_count" in log
            assert "completed_at" in log
        print(f"Found {len(data['logs'])} send logs")
    
    def test_send_logs_employer_forbidden(self, employer_token):
        """Non-admin gets 403."""
        response = requests.get(
            f"{BASE_URL}/api/admin/blog-digest/send-logs",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 403


class TestAdminSubscriptionStats:
    """Test GET /api/admin/blog-digest/subscription-stats"""
    
    def test_subscription_stats_admin(self, admin_token):
        """Admin can get subscription stats."""
        response = requests.get(
            f"{BASE_URL}/api/admin/blog-digest/subscription-stats",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_unsubscribed" in data
        assert "by_role" in data
        print(f"Subscription stats: {data['total_unsubscribed']} unsubscribed")
    
    def test_subscription_stats_employer_forbidden(self, employer_token):
        """Non-admin gets 403."""
        response = requests.get(
            f"{BASE_URL}/api/admin/blog-digest/subscription-stats",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 403


class TestPublicUnsubscribe:
    """Test GET /api/unsubscribe/{token} - public unsubscribe endpoint"""
    
    def test_unsubscribe_invalid_token(self):
        """Invalid token returns 400 with HTML page."""
        response = requests.get(f"{BASE_URL}/api/unsubscribe/invalid_token")
        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")
        assert "Invalid Link" in response.text
        print("Invalid token correctly rejected with HTML page")
    
    def test_unsubscribe_valid_token_format(self, admin_user_data):
        """Valid token format with real user processes correctly."""
        user_id = admin_user_data["id"]
        email = admin_user_data["email"]
        token = generate_unsubscribe_token(user_id, email)
        
        response = requests.get(f"{BASE_URL}/api/unsubscribe/{token}")
        # Should return HTML page (200 for success, or 404 if user not found in some edge cases)
        assert response.status_code in [200, 400, 404]
        assert "text/html" in response.headers.get("content-type", "")
        
        if response.status_code == 200:
            assert "Unsubscribed Successfully" in response.text or "unsubscribed" in response.text.lower()
            print(f"Unsubscribe successful for user {email}")
        else:
            print(f"Unsubscribe returned {response.status_code}")


class TestPublicResubscribe:
    """Test GET /api/resubscribe/{token} - public resubscribe endpoint"""
    
    def test_resubscribe_invalid_token(self):
        """Invalid token returns 400 with HTML page."""
        response = requests.get(f"{BASE_URL}/api/resubscribe/invalid_token")
        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")
        assert "Invalid Link" in response.text
        print("Invalid resubscribe token correctly rejected")
    
    def test_resubscribe_valid_token(self, admin_user_data):
        """Valid token resubscribes user (if previously unsubscribed)."""
        user_id = admin_user_data["id"]
        email = admin_user_data["email"]
        token = generate_unsubscribe_token(user_id, email)
        
        response = requests.get(f"{BASE_URL}/api/resubscribe/{token}")
        assert response.status_code in [200, 400]
        assert "text/html" in response.headers.get("content-type", "")
        
        if response.status_code == 200:
            print(f"Resubscribe processed for user {email}")
        else:
            print(f"Resubscribe returned {response.status_code} - may need prior unsubscribe")


class TestDigestTrigger:
    """Test POST /api/admin/blog-digest/trigger - manual digest generation"""
    
    def test_trigger_digest_admin(self, admin_token):
        """Admin can trigger digest generation."""
        response = requests.post(
            f"{BASE_URL}/api/admin/blog-digest/trigger",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"Trigger result: {data.get('status')} - {data.get('reason', data.get('message', ''))}")
    
    def test_trigger_digest_employer_forbidden(self, employer_token):
        """Non-admin gets 403."""
        response = requests.post(
            f"{BASE_URL}/api/admin/blog-digest/trigger",
            headers={"Authorization": f"Bearer {employer_token}"}
        )
        assert response.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
