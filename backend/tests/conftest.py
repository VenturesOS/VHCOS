"""Shared test configuration - loads credentials from environment."""
import os

# Test credentials - loaded from environment or test_credentials.md
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@vhc.in")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "VhcAdmin@2024")
RECRUITER_EMAIL = os.environ.get("TEST_RECRUITER_EMAIL", "yamini@vhc.in")
RECRUITER_PASSWORD = os.environ.get("TEST_RECRUITER_PASSWORD", "Ventures@321")

API_BASE = os.environ.get("TEST_API_BASE", "http://localhost:8001/api")
