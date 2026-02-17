#!/usr/bin/env python3
"""Post-deployment verification script for ventureshrd.com production"""
import requests
import json
import sys

PROD_URL = "https://ventureshrd.com"
results = []

def check(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((name, status, detail))
    print(f"  [{status}] {name}: {detail}")

def main():
    print("=" * 60)
    print("POST-DEPLOY PRODUCTION VERIFICATION")
    print("=" * 60)

    # Login
    print("\n1. Authentication Tests")
    creds = [
        ("admin@vhc.in", "VhcAdmin@2024", "admin"),
        ("ajit@vhc.in", "12345678", "employer"),
        ("jatin@vhc.in", "12345678", "recruiter"),
        ("maneet@vhc.in", "12345678", "employer"),
        ("siddharth@vhc.in", "12345678", "admin"),
    ]
    admin_token = None
    for email, pwd, expected_role in creds:
        r = requests.post(f"{PROD_URL}/api/auth/login",
                         json={"email": email, "password": pwd}, timeout=10)
        if r.status_code == 200 and "access_token" in r.json():
            d = r.json()
            role = d["user"]["role"]
            check(f"Login {email}", role == expected_role, f"role={role}")
            if email == "admin@vhc.in":
                admin_token = d["access_token"]
        else:
            check(f"Login {email}", False, f"HTTP {r.status_code}")

    if not admin_token:
        print("\nFATAL: Admin login failed. Cannot continue.")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {admin_token}"}

    # Data counts
    print("\n2. Data Count Verification (Atlas Fingerprint)")
    r = requests.get(f"{PROD_URL}/api/users", headers=headers, timeout=10)
    users = r.json()
    check("Users count", len(users) == 14, f"got {len(users)}, expect 14")

    r = requests.get(f"{PROD_URL}/api/companies", headers=headers, timeout=10)
    companies = r.json()
    test_cos = [c for c in companies if "TEST" in c.get("name", "")]
    check("Companies count", len(companies) == 7, f"got {len(companies)}, expect 7")
    check("No TEST companies", len(test_cos) == 0, f"found {len(test_cos)} TEST")

    r = requests.get(f"{PROD_URL}/api/candidate-bank?page=1&page_size=1", headers=headers, timeout=10)
    total_cands = r.json().get("total", 0)
    check("Candidates count", total_cands == 1719, f"got {total_cands}, expect 1719")

    # Teams
    print("\n3. Functional Validation")
    r = requests.get(f"{PROD_URL}/api/teams", headers=headers, timeout=10)
    check("Teams page loads", r.status_code == 200, f"HTTP {r.status_code}")
    if r.status_code == 200:
        teams = r.json()
        check("Teams count", len(teams) == 4, f"got {len(teams)}, expect 4")

    # Assign employer
    r = requests.put(
        f"{PROD_URL}/api/companies/f56968c2-8967-460d-8904-fdc4bc0eb1b4/assign-employer",
        params={"employer_id": "cf36890a-b8fa-47e2-abf3-d4600f04c831"},
        headers=headers, timeout=10)
    check("Assign employer", r.status_code == 200, f"HTTP {r.status_code}")

    # System health
    r = requests.get(f"{PROD_URL}/api/system-errors/stats", headers=headers, timeout=10)
    check("System health stats", r.status_code == 200, f"HTTP {r.status_code}")

    # SEO
    r = requests.get(f"{PROD_URL}/api/sitemap.xml", timeout=10)
    check("Sitemap", r.status_code == 200, f"HTTP {r.status_code}")

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"RESULTS: {passed} PASS, {failed} FAIL")
    print("=" * 60)
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
