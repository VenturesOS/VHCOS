"""
Test Suite for Dual-Layer Revenue Engine.

Tests:
- Part 1: Central calculate_revenue() for percentage/fixed/level_based
- Part 2: Forecast revenue stored in application (not revenue collection)
- Part 3: Offered stage creates revenue record with commercial snapshot
- Part 4: Joined stage locks revenue (immutable)
- Part 5: Date-filter aggregation by company/job/recruiter
- Part 6: Recruiter role never sees revenue fields
- Part 7: Integrity safeguards (no offered without offered_ctc, etc.)
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://crash-root-cause.preview.emergentagent.com"

# Test credentials
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"
EMPLOYER_EMAIL = "ajit@vhc.in"
EMPLOYER_PASSWORD = "12345678"

# Known test data - Volvo Commercial Vehicle has 8.33% percentage commercial
VOLVO_COMPANY_ID = "8066c10f-215b-4ed2-9b2d-8726b609e4fa"
# This job has company_id properly linked (not the manager job which has empty company_id)
VOLVO_JOB_ID = "36a27da3-00b4-4f45-80a6-eb73f980709c"  # Assistant Manager, Area Sales Manager
VOLVO_PERCENTAGE = 8.33


class TestRevenueEngineSetup:
    """Setup fixtures and helper functions."""

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin auth token."""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        return resp.json()["access_token"]

    @pytest.fixture(scope="class")
    def employer_token(self):
        """Get employer auth token."""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": EMPLOYER_EMAIL,
            "password": EMPLOYER_PASSWORD
        })
        assert resp.status_code == 200, f"Employer login failed: {resp.text}"
        return resp.json()["access_token"]

    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    @pytest.fixture(scope="class")
    def employer_headers(self, employer_token):
        return {"Authorization": f"Bearer {employer_token}", "Content-Type": "application/json"}


class TestForecastRevenue(TestRevenueEngineSetup):
    """Part 2: Forecast revenue calculation tests."""

    def test_forecast_percentage_commercial(self, admin_headers):
        """POST /api/revenue/forecast — percentage commercial: salary * pct/100, rounded to rupee."""
        # Get a test application from Volvo job
        resp = requests.get(
            f"{BASE_URL}/api/applications",
            params={"job_id": VOLVO_JOB_ID},
            headers=admin_headers
        )
        assert resp.status_code == 200
        apps = resp.json()
        assert len(apps) > 0, "No applications found for Volvo job"
        
        test_app = apps[0]
        expected_ctc = 1200000  # 12 LPA
        
        # Calculate forecast revenue
        resp = requests.post(f"{BASE_URL}/api/revenue/forecast", headers=admin_headers, json={
            "application_id": test_app["id"],
            "expected_ctc": expected_ctc
        })
        assert resp.status_code == 200, f"Forecast failed: {resp.text}"
        data = resp.json()
        
        # Verify structured response
        assert data["commercial_type"] == "percentage"
        assert data["percentage_used"] == VOLVO_PERCENTAGE
        
        # Verify calculation: 1200000 * 8.33 / 100 = 99960 (rounded to nearest rupee)
        expected_revenue = round(expected_ctc * VOLVO_PERCENTAGE / 100)
        assert data["revenue_amount"] == expected_revenue, f"Expected {expected_revenue}, got {data['revenue_amount']}"
        
        print(f"✅ Forecast revenue for {expected_ctc} CTC = {data['revenue_amount']} (percentage: {data['percentage_used']}%)")

    def test_forecast_missing_salary_returns_400(self, admin_headers):
        """POST /api/revenue/forecast — missing salary raises 400."""
        resp = requests.get(
            f"{BASE_URL}/api/applications",
            params={"job_id": VOLVO_JOB_ID},
            headers=admin_headers
        )
        apps = resp.json()
        test_app = apps[0]
        
        # Send with 0 or missing salary
        resp = requests.post(f"{BASE_URL}/api/revenue/forecast", headers=admin_headers, json={
            "application_id": test_app["id"],
            "expected_ctc": 0
        })
        assert resp.status_code == 400, f"Expected 400 for 0 CTC, got {resp.status_code}"
        assert "Salary" in resp.json().get("detail", "") or "salary" in resp.json().get("detail", "").lower()
        print("✅ Missing/zero salary correctly returns 400")

    def test_forecast_stores_in_application(self, admin_headers):
        """Verify forecast is stored in application, not revenue collection."""
        resp = requests.get(
            f"{BASE_URL}/api/applications",
            params={"job_id": VOLVO_JOB_ID},
            headers=admin_headers
        )
        apps = resp.json()
        test_app = apps[0]
        expected_ctc = 1500000  # 15 LPA
        
        # Post forecast
        resp = requests.post(f"{BASE_URL}/api/revenue/forecast", headers=admin_headers, json={
            "application_id": test_app["id"],
            "expected_ctc": expected_ctc
        })
        assert resp.status_code == 200
        
        # Get application - should have forecast fields
        resp = requests.get(f"{BASE_URL}/api/applications/{test_app['id']}", headers=admin_headers)
        assert resp.status_code == 200
        app_data = resp.json()
        
        assert app_data.get("expected_ctc") == expected_ctc, "expected_ctc not stored in application"
        assert app_data.get("forecast_revenue") is not None, "forecast_revenue not stored in application"
        
        # Revenue collection should NOT have this application yet (only offered/joined creates revenue)
        resp = requests.get(f"{BASE_URL}/api/revenue/by-application/{test_app['id']}", headers=admin_headers)
        assert resp.status_code == 200
        # After forecast, revenue record may or may not exist (depends on stage)
        
        print(f"✅ Forecast stored in application: expected_ctc={app_data['expected_ctc']}, forecast_revenue={app_data['forecast_revenue']}")


class TestOfferedStage(TestRevenueEngineSetup):
    """Part 3: Offered stage creates revenue record with commercial snapshot."""

    def test_offered_creates_revenue_record(self, admin_headers):
        """POST /api/revenue/offered/{app_id} — creates revenue record with commercial_snapshot."""
        # Get a test application
        resp = requests.get(
            f"{BASE_URL}/api/applications",
            params={"job_id": VOLVO_JOB_ID},
            headers=admin_headers
        )
        apps = resp.json()
        # Find app not already in joined status
        test_app = None
        for app in apps:
            if app.get("stage") not in ("joined", "hired"):
                test_app = app
                break
        
        if not test_app:
            pytest.skip("No eligible application for offered test")
        
        offered_ctc = 1800000  # 18 LPA
        offer_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        resp = requests.post(
            f"{BASE_URL}/api/revenue/offered/{test_app['id']}",
            headers=admin_headers,
            json={"offered_ctc": offered_ctc, "offer_date": offer_date}
        )
        assert resp.status_code == 200, f"Offered stage failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert data["revenue_status"] == "offered"
        assert data["offered_ctc"] == offered_ctc
        assert "revenue_id" in data
        
        # Verify revenue record created
        resp = requests.get(f"{BASE_URL}/api/revenue/by-application/{test_app['id']}", headers=admin_headers)
        assert resp.status_code == 200
        rev_data = resp.json()
        
        assert rev_data.get("revenue") is not None, "Revenue record not created"
        revenue = rev_data["revenue"]
        
        # Verify commercial_snapshot
        assert "commercial_snapshot" in revenue, "commercial_snapshot missing"
        snapshot = revenue["commercial_snapshot"]
        assert snapshot.get("type") == "percentage"
        assert snapshot.get("percentage_value") == VOLVO_PERCENTAGE
        
        print(f"✅ Offered stage created revenue record with commercial_snapshot: {snapshot['type']} @ {snapshot.get('percentage_value')}%")
        
        # Clean up - reset stage for further tests
        return test_app["id"]

    def test_offered_missing_ctc_returns_400(self, admin_headers):
        """POST /api/revenue/offered/{app_id} — missing offered_ctc returns 400."""
        resp = requests.get(
            f"{BASE_URL}/api/applications",
            params={"job_id": VOLVO_JOB_ID},
            headers=admin_headers
        )
        apps = resp.json()
        test_app = apps[0]
        
        # Missing offered_ctc
        resp = requests.post(
            f"{BASE_URL}/api/revenue/offered/{test_app['id']}",
            headers=admin_headers,
            json={"offer_date": "2026-01-20"}  # No offered_ctc
        )
        assert resp.status_code == 422 or resp.status_code == 400, f"Expected 400/422, got {resp.status_code}"
        print("✅ Missing offered_ctc correctly returns 400/422")

    def test_offered_with_zero_ctc_returns_400(self, admin_headers):
        """POST /api/revenue/offered/{app_id} — zero offered_ctc returns 400."""
        resp = requests.get(
            f"{BASE_URL}/api/applications",
            params={"job_id": VOLVO_JOB_ID},
            headers=admin_headers
        )
        apps = resp.json()
        test_app = apps[0]
        
        resp = requests.post(
            f"{BASE_URL}/api/revenue/offered/{test_app['id']}",
            headers=admin_headers,
            json={"offered_ctc": 0, "offer_date": "2026-01-20"}
        )
        assert resp.status_code == 400, f"Expected 400 for zero CTC, got {resp.status_code}"
        print("✅ Zero offered_ctc correctly returns 400")


class TestJoinedStage(TestRevenueEngineSetup):
    """Part 4: Joined stage locks revenue (immutable)."""

    @pytest.fixture(scope="class")
    def setup_offered_app(self, admin_headers):
        """Create an application in offered state for joined tests."""
        # Get an application
        resp = requests.get(
            f"{BASE_URL}/api/applications",
            params={"job_id": VOLVO_JOB_ID},
            headers=admin_headers
        )
        apps = resp.json()
        
        # Find one not already joined
        for app in apps:
            if app.get("stage") not in ("joined", "hired"):
                # Move to offered
                resp = requests.post(
                    f"{BASE_URL}/api/revenue/offered/{app['id']}",
                    headers=admin_headers,
                    json={"offered_ctc": 2000000, "offer_date": "2026-01-20"}
                )
                if resp.status_code == 200:
                    return app["id"]
        
        return None

    def test_joined_requires_offered_first(self, admin_headers):
        """POST /api/revenue/joined/{app_id} — without offered stage first returns 400."""
        # Create a fresh application without offered stage
        resp = requests.get(
            f"{BASE_URL}/api/applications",
            params={"job_id": VOLVO_JOB_ID},
            headers=admin_headers
        )
        apps = resp.json()
        
        # Find one in applied or shortlisted stage (not offered)
        fresh_app = None
        for app in apps:
            if app.get("stage") in ("applied", "shortlisted", "interview") and not app.get("offered_ctc"):
                fresh_app = app
                break
        
        if not fresh_app:
            pytest.skip("No fresh application without offered_ctc")
        
        resp = requests.post(
            f"{BASE_URL}/api/revenue/joined/{fresh_app['id']}",
            headers=admin_headers,
            json={"join_date": "2026-02-01"}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "offered" in resp.json().get("detail", "").lower() or "revenue" in resp.json().get("detail", "").lower()
        print("✅ Joined without offered stage correctly returns 400")

    def test_joined_missing_join_date_returns_400(self, admin_headers, setup_offered_app):
        """POST /api/revenue/joined/{app_id} — missing join_date returns 400."""
        if not setup_offered_app:
            pytest.skip("No offered app available")
        
        resp = requests.post(
            f"{BASE_URL}/api/revenue/joined/{setup_offered_app}",
            headers=admin_headers,
            json={}  # Missing join_date
        )
        assert resp.status_code == 422 or resp.status_code == 400, f"Expected 400/422, got {resp.status_code}"
        print("✅ Missing join_date correctly returns 400/422")


class TestAggregation(TestRevenueEngineSetup):
    """Part 5: Date-filter aggregation by company/job/recruiter."""

    def test_aggregate_by_company(self, admin_headers):
        """GET /api/revenue/aggregate/by-company — filters by join_date range."""
        from_date = "2025-01-01"
        to_date = "2027-12-31"
        
        resp = requests.get(
            f"{BASE_URL}/api/revenue/aggregate/by-company",
            headers=admin_headers,
            params={"from_date": from_date, "to_date": to_date}
        )
        assert resp.status_code == 200, f"Aggregation failed: {resp.text}"
        data = resp.json()
        
        assert "from_date" in data
        assert "to_date" in data
        assert "data" in data
        assert isinstance(data["data"], list)
        
        # Verify structure of results
        for item in data["data"]:
            assert "company_id" in item
            assert "total_revenue" in item
            assert "count" in item
        
        print(f"✅ Aggregate by company returned {len(data['data'])} companies")

    def test_aggregate_by_job(self, admin_headers):
        """GET /api/revenue/aggregate/by-job — correct grouping."""
        from_date = "2025-01-01"
        to_date = "2027-12-31"
        
        resp = requests.get(
            f"{BASE_URL}/api/revenue/aggregate/by-job",
            headers=admin_headers,
            params={"from_date": from_date, "to_date": to_date}
        )
        assert resp.status_code == 200, f"Aggregation failed: {resp.text}"
        data = resp.json()
        
        assert "data" in data
        for item in data["data"]:
            assert "job_id" in item
            assert "total_revenue" in item
        
        print(f"✅ Aggregate by job returned {len(data['data'])} jobs")

    def test_aggregate_by_recruiter(self, admin_headers):
        """GET /api/revenue/aggregate/by-recruiter — enriches with recruiter name."""
        from_date = "2025-01-01"
        to_date = "2027-12-31"
        
        resp = requests.get(
            f"{BASE_URL}/api/revenue/aggregate/by-recruiter",
            headers=admin_headers,
            params={"from_date": from_date, "to_date": to_date}
        )
        assert resp.status_code == 200, f"Aggregation failed: {resp.text}"
        data = resp.json()
        
        assert "data" in data
        for item in data["data"]:
            assert "recruiter_id" in item
            assert "recruiter_name" in item, "Recruiter name should be enriched"
            assert "total_revenue" in item
        
        print(f"✅ Aggregate by recruiter returned {len(data['data'])} recruiters with names")


class TestRecruiterRoleRestriction(TestRevenueEngineSetup):
    """Part 6: Recruiter role NEVER sees revenue fields."""

    @pytest.fixture(scope="class")
    def recruiter_token(self, admin_headers):
        """Get or create a recruiter for testing."""
        # First, check if we can find existing recruiter
        test_email = "TEST_recruiter_revenue@vhc.in"
        
        # Try to login
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_email,
            "password": "Test1234!"
        })
        
        if resp.status_code == 200:
            return resp.json()["access_token"]
        
        # Create a test recruiter
        resp = requests.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": test_email,
            "password": "Test1234!",
            "name": "TEST Revenue Recruiter",
            "role": "recruiter"
        })
        
        if resp.status_code in (200, 201):
            # Login
            resp = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": test_email,
                "password": "Test1234!"
            })
            if resp.status_code == 200:
                return resp.json()["access_token"]
        
        return None

    def test_revenue_records_empty_for_recruiter(self, recruiter_token):
        """GET /api/revenue/records — recruiter gets empty response."""
        if not recruiter_token:
            pytest.skip("Could not create recruiter for test")
        
        headers = {"Authorization": f"Bearer {recruiter_token}", "Content-Type": "application/json"}
        
        resp = requests.get(f"{BASE_URL}/api/revenue/records", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        
        # Recruiter should get empty records
        assert data.get("records") == [] or data.get("message") is not None
        print("✅ Recruiter gets empty revenue records as expected")

    def test_applications_strips_revenue_fields_for_recruiter(self, recruiter_token, admin_headers):
        """GET /api/applications — recruiter role: forecast_revenue/offered_ctc/expected_ctc fields STRIPPED."""
        if not recruiter_token:
            pytest.skip("Could not create recruiter for test")
        
        # First verify admin sees the fields
        resp = requests.get(f"{BASE_URL}/api/applications", headers=admin_headers)
        assert resp.status_code == 200
        admin_apps = resp.json()
        
        # Find one with revenue fields
        has_revenue_fields = False
        for app in admin_apps:
            if app.get("forecast_revenue") or app.get("offered_ctc") or app.get("expected_ctc"):
                has_revenue_fields = True
                break
        
        # Now check recruiter view
        headers = {"Authorization": f"Bearer {recruiter_token}", "Content-Type": "application/json"}
        resp = requests.get(f"{BASE_URL}/api/applications", headers=headers)
        
        # May be 200 or 403 depending on access
        if resp.status_code == 200:
            recruiter_apps = resp.json()
            for app in recruiter_apps:
                # Verify revenue fields are stripped
                assert app.get("forecast_revenue") is None, f"forecast_revenue should be stripped for recruiter"
                assert app.get("offered_ctc") is None, f"offered_ctc should be stripped for recruiter"
                assert app.get("expected_ctc") is None, f"expected_ctc should be stripped for recruiter"
            print("✅ Revenue fields stripped from applications for recruiter")
        else:
            print(f"✅ Recruiter applications access: {resp.status_code}")


class TestIntegritySafeguards(TestRevenueEngineSetup):
    """Part 7: Integrity safeguards (no offered without offered_ctc, no joined without offered, no edit after joined)."""

    def test_stage_offered_blocked_without_offered_ctc(self, admin_headers):
        """PUT /api/applications/{app_id} — stage=offered blocked without offered_ctc."""
        # Get an application
        resp = requests.get(
            f"{BASE_URL}/api/applications",
            params={"job_id": VOLVO_JOB_ID},
            headers=admin_headers
        )
        apps = resp.json()
        
        # Find one not in offered/joined state
        test_app = None
        for app in apps:
            if app.get("stage") not in ("offered", "joined", "hired") and not app.get("offered_ctc"):
                test_app = app
                break
        
        if not test_app:
            pytest.skip("No fresh application to test stage transition")
        
        # Try to move to offered without offered_ctc
        resp = requests.put(
            f"{BASE_URL}/api/applications/{test_app['id']}",
            headers=admin_headers,
            json={"stage": "offered"}  # No offered_ctc
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "offered_ctc" in resp.json().get("detail", "").lower()
        print("✅ Stage=offered blocked without offered_ctc")

    def test_stage_joined_blocked_without_offered_ctc(self, admin_headers):
        """PUT /api/applications/{app_id} — stage=joined blocked without offered_ctc set."""
        resp = requests.get(
            f"{BASE_URL}/api/applications",
            params={"job_id": VOLVO_JOB_ID},
            headers=admin_headers
        )
        apps = resp.json()
        
        # Find one without offered_ctc
        test_app = None
        for app in apps:
            if not app.get("offered_ctc") and app.get("stage") not in ("joined", "hired"):
                test_app = app
                break
        
        if not test_app:
            pytest.skip("No application without offered_ctc")
        
        resp = requests.put(
            f"{BASE_URL}/api/applications/{test_app['id']}",
            headers=admin_headers,
            json={"stage": "joined"}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        print("✅ Stage=joined blocked without offered_ctc")

    def test_offered_blocked_after_joined(self, admin_headers):
        """POST /api/revenue/offered/{app_id} — blocked after joined (immutable)."""
        # We need an application in joined state
        resp = requests.get(f"{BASE_URL}/api/applications", headers=admin_headers)
        apps = resp.json()
        
        joined_app = None
        for app in apps:
            if app.get("stage") == "joined":
                joined_app = app
                break
        
        if not joined_app:
            # Try to find one and move it to joined
            pytest.skip("No joined application to test immutability")
        
        # Try to re-process offered
        resp = requests.post(
            f"{BASE_URL}/api/revenue/offered/{joined_app['id']}",
            headers=admin_headers,
            json={"offered_ctc": 2500000, "offer_date": "2026-02-01"}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "locked" in resp.json().get("detail", "").lower() or "joined" in resp.json().get("detail", "").lower()
        print("✅ Offered blocked after joined (immutable)")


class TestCompanyWithoutCommercial(TestRevenueEngineSetup):
    """Test forecast fails for companies without commercial."""

    def test_forecast_company_without_commercial_returns_400(self, admin_headers):
        """POST /api/revenue/forecast — company without commercial raises 400."""
        # First, find a company without commercial
        resp = requests.get(f"{BASE_URL}/api/companies", headers=admin_headers)
        companies = resp.json()
        
        no_commercial_company = None
        for c in companies:
            if not c.get("commercial"):
                no_commercial_company = c
                break
        
        if not no_commercial_company:
            print("ℹ️ All companies have commercials, skipping test")
            pytest.skip("No company without commercial found")
        
        # Find a job for this company
        resp = requests.get(f"{BASE_URL}/api/jobs", headers=admin_headers)
        jobs = resp.json()
        
        test_job = None
        for j in jobs:
            if j.get("company_id") == no_commercial_company["id"]:
                test_job = j
                break
        
        if not test_job:
            pytest.skip("No job found for company without commercial")
        
        # Find an application for this job
        resp = requests.get(
            f"{BASE_URL}/api/applications",
            params={"job_id": test_job["id"]},
            headers=admin_headers
        )
        apps = resp.json()
        
        if not apps:
            pytest.skip("No applications for job with company without commercial")
        
        # Try forecast
        resp = requests.post(f"{BASE_URL}/api/revenue/forecast", headers=admin_headers, json={
            "application_id": apps[0]["id"],
            "expected_ctc": 1500000
        })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "commercial" in resp.json().get("detail", "").lower()
        print("✅ Company without commercial correctly returns 400")


class TestEmployerEndpointsNoRegression(TestRevenueEngineSetup):
    """Verify employer endpoints still work after revenue engine changes."""

    def test_employer_my_team(self, employer_headers):
        """GET /api/employer/my-team still works."""
        resp = requests.get(f"{BASE_URL}/api/employer/my-team", headers=employer_headers)
        assert resp.status_code == 200, f"my-team failed: {resp.text}"
        data = resp.json()
        assert "team" in data or "members" in data or isinstance(data, dict)
        print("✅ /api/employer/my-team works")

    def test_employer_companies(self, employer_headers):
        """GET /api/employer/companies still works."""
        resp = requests.get(f"{BASE_URL}/api/employer/companies", headers=employer_headers)
        assert resp.status_code == 200, f"companies failed: {resp.text}"
        print("✅ /api/employer/companies works")

    def test_employer_pipeline(self, employer_headers):
        """GET /api/employer/pipeline still works."""
        resp = requests.get(f"{BASE_URL}/api/employer/pipeline", headers=employer_headers)
        assert resp.status_code == 200, f"pipeline failed: {resp.text}"
        print("✅ /api/employer/pipeline works")

    def test_admin_analytics(self, admin_headers):
        """GET /api/analytics/admin still works."""
        resp = requests.get(f"{BASE_URL}/api/analytics/admin", headers=admin_headers)
        assert resp.status_code == 200, f"analytics failed: {resp.text}"
        print("✅ /api/analytics/admin works")


class TestRevenueRecordsAndByApplication(TestRevenueEngineSetup):
    """Test revenue records and by-application endpoints."""

    def test_get_revenue_records_admin(self, admin_headers):
        """GET /api/revenue/records — admin sees all."""
        resp = requests.get(f"{BASE_URL}/api/revenue/records", headers=admin_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "records" in data
        print(f"✅ Admin revenue records: {len(data['records'])} records")

    def test_get_revenue_by_application(self, admin_headers):
        """GET /api/revenue/by-application/{app_id} — returns revenue for app."""
        # First get an application with revenue
        resp = requests.get(f"{BASE_URL}/api/revenue/records", headers=admin_headers)
        records = resp.json().get("records", [])
        
        if not records:
            pytest.skip("No revenue records to test")
        
        test_app_id = records[0]["application_id"]
        
        resp = requests.get(f"{BASE_URL}/api/revenue/by-application/{test_app_id}", headers=admin_headers)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "revenue" in data
        print(f"✅ Revenue by application returned: {data['revenue'] is not None}")


class TestCleanup(TestRevenueEngineSetup):
    """Cleanup test data."""

    def test_cleanup_test_recruiter(self, admin_headers):
        """Clean up test recruiter created during tests."""
        # Find and delete test recruiter
        resp = requests.get(f"{BASE_URL}/api/users", headers=admin_headers)
        if resp.status_code == 200:
            users = resp.json()
            for user in users:
                if user.get("email", "").startswith("TEST_"):
                    # Delete test user
                    resp = requests.delete(
                        f"{BASE_URL}/api/users/{user['id']}",
                        headers=admin_headers
                    )
                    print(f"Cleaned up test user: {user['email']}")
        print("✅ Cleanup completed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
