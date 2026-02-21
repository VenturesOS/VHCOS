import requests
import sys
import json
from datetime import datetime

class VHCTalentOSAPITester:
    def __init__(self, base_url="https://security-verify.preview.emergentagent.com"):
        self.base_url = base_url
        self.admin_token = None
        self.candidate_token = None
        self.employer_token = None
        self.recruiter_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def run_test(self, name, method, endpoint, expected_status, data=None, token=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json() if response.content else {}
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"   Error: {error_detail}")
                except:
                    print(f"   Response: {response.text}")
                self.failed_tests.append({
                    "test": name,
                    "endpoint": endpoint,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "error": response.text[:200]
                })
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.failed_tests.append({
                "test": name,
                "endpoint": endpoint,
                "error": str(e)
            })
            return False, {}

    def test_admin_login(self):
        """Test admin login and get token"""
        print("\n" + "="*50)
        print("TESTING ADMIN LOGIN")
        print("="*50)
        
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            data={"email": "admin@vhc.in", "password": "vhc@123"}
        )
        if success and 'access_token' in response:
            self.admin_token = response['access_token']
            print(f"✅ Admin token obtained: {self.admin_token[:20]}...")
            return True
        return False

    def test_admin_stats(self):
        """Test admin dashboard stats"""
        if not self.admin_token:
            print("❌ Skipping admin stats - no admin token")
            return False
            
        success, response = self.run_test(
            "Admin Stats",
            "GET",
            "stats/admin",
            200,
            token=self.admin_token
        )
        
        if success:
            required_fields = ['total_users', 'total_jobs', 'total_applications', 'total_companies']
            for field in required_fields:
                if field not in response:
                    print(f"❌ Missing field in stats: {field}")
                    return False
            print(f"✅ Stats data: {response}")
        return success

    def test_user_management(self):
        """Test user management endpoints"""
        if not self.admin_token:
            print("❌ Skipping user management - no admin token")
            return False
            
        print("\n" + "="*50)
        print("TESTING USER MANAGEMENT")
        print("="*50)
        
        # Get all users
        success, users = self.run_test(
            "Get All Users",
            "GET",
            "users",
            200,
            token=self.admin_token
        )
        
        if success and users:
            print(f"✅ Found {len(users)} users")
            # Test get specific user
            if len(users) > 0:
                user_id = users[0]['id']
                self.run_test(
                    "Get Specific User",
                    "GET",
                    f"users/{user_id}",
                    200,
                    token=self.admin_token
                )
        
        return success

    def test_candidate_registration(self):
        """Test candidate registration"""
        print("\n" + "="*50)
        print("TESTING CANDIDATE REGISTRATION")
        print("="*50)
        
        timestamp = datetime.now().strftime("%H%M%S")
        candidate_data = {
            "email": f"candidate_{timestamp}@test.com",
            "name": f"Test Candidate {timestamp}",
            "password": "TestPass123!",
            "role": "candidate"
        }
        
        success, response = self.run_test(
            "Candidate Registration",
            "POST",
            "auth/register",
            200,
            data=candidate_data
        )
        
        if success and 'access_token' in response:
            self.candidate_token = response['access_token']
            print(f"✅ Candidate registered and token obtained")
            return True
        return False

    def test_employer_registration(self):
        """Test employer registration"""
        print("\n" + "="*50)
        print("TESTING EMPLOYER REGISTRATION")
        print("="*50)
        
        timestamp = datetime.now().strftime("%H%M%S")
        employer_data = {
            "email": f"employer_{timestamp}@test.com",
            "name": f"Test Employer {timestamp}",
            "password": "TestPass123!",
            "role": "employer"
        }
        
        success, response = self.run_test(
            "Employer Registration",
            "POST",
            "auth/register",
            200,
            data=employer_data
        )
        
        if success and 'access_token' in response:
            self.employer_token = response['access_token']
            print(f"✅ Employer registered and token obtained")
            return True
        return False

    def test_recruiter_registration(self):
        """Test recruiter registration"""
        print("\n" + "="*50)
        print("TESTING RECRUITER REGISTRATION")
        print("="*50)
        
        timestamp = datetime.now().strftime("%H%M%S")
        recruiter_data = {
            "email": f"recruiter_{timestamp}@test.com",
            "name": f"Test Recruiter {timestamp}",
            "password": "TestPass123!",
            "role": "recruiter"
        }
        
        success, response = self.run_test(
            "Recruiter Registration",
            "POST",
            "auth/register",
            200,
            data=recruiter_data
        )
        
        if success and 'access_token' in response:
            self.recruiter_token = response['access_token']
            print(f"✅ Recruiter registered and token obtained")
            return True
        return False

    def test_job_management(self):
        """Test job creation and browsing"""
        print("\n" + "="*50)
        print("TESTING JOB MANAGEMENT")
        print("="*50)
        
        # Test job browsing (public endpoint)
        self.run_test(
            "Browse Jobs (Public)",
            "GET",
            "jobs/browse",
            200
        )
        
        # Test job creation with employer token
        if self.employer_token:
            job_data = {
                "title": "Test Software Engineer",
                "description": "Test job description for software engineer position",
                "requirements": "Python, FastAPI, React",
                "location": "Remote",
                "job_type": "full-time",
                "salary_min": 80000,
                "salary_max": 120000,
                "department": "Engineering"
            }
            
            success, job_response = self.run_test(
                "Create Job (Employer)",
                "POST",
                "jobs",
                200,
                data=job_data,
                token=self.employer_token
            )
            
            if success:
                print(f"✅ Job created with ID: {job_response.get('id')}")
                
                # Test getting jobs as employer
                self.run_test(
                    "Get Jobs (Employer)",
                    "GET",
                    "jobs",
                    200,
                    token=self.employer_token
                )
        
        # Test getting jobs as candidate
        if self.candidate_token:
            self.run_test(
                "Get Jobs (Candidate)",
                "GET",
                "jobs",
                200,
                token=self.candidate_token
            )

    def test_company_management(self):
        """Test company creation and listing"""
        print("\n" + "="*50)
        print("TESTING COMPANY MANAGEMENT")
        print("="*50)
        
        # Test getting companies
        if self.admin_token:
            self.run_test(
                "Get Companies (Admin)",
                "GET",
                "companies",
                200,
                token=self.admin_token
            )
        
        # Test creating company as employer
        if self.employer_token:
            company_data = {
                "name": "Test Company Inc",
                "description": "A test company for recruitment",
                "industry": "Technology",
                "website": "https://testcompany.com",
                "location": "San Francisco, CA"
            }
            
            self.run_test(
                "Create Company (Employer)",
                "POST",
                "companies",
                200,
                data=company_data,
                token=self.employer_token
            )

    def test_application_flow(self):
        """Test job application flow"""
        print("\n" + "="*50)
        print("TESTING APPLICATION FLOW")
        print("="*50)
        
        if not self.candidate_token:
            print("❌ Skipping application flow - no candidate token")
            return False
        
        # First get available jobs
        success, jobs = self.run_test(
            "Get Available Jobs for Application",
            "GET",
            "jobs/browse",
            200
        )
        
        if success and jobs and len(jobs) > 0:
            job_id = jobs[0]['id']
            print(f"✅ Found job to apply to: {job_id}")
            
            # Apply to the job
            application_data = {
                "job_id": job_id,
                "cover_letter": "I am very interested in this position and believe I would be a great fit."
            }
            
            success, app_response = self.run_test(
                "Create Application",
                "POST",
                "applications",
                200,
                data=application_data,
                token=self.candidate_token
            )
            
            if success:
                print(f"✅ Application created with ID: {app_response.get('id')}")
                
                # Get candidate's applications
                self.run_test(
                    "Get My Applications",
                    "GET",
                    "applications",
                    200,
                    token=self.candidate_token
                )
        else:
            print("❌ No jobs available to apply to")

    def test_auth_me_endpoints(self):
        """Test /auth/me endpoint for all roles"""
        print("\n" + "="*50)
        print("TESTING AUTH/ME ENDPOINTS")
        print("="*50)
        
        tokens = [
            ("Admin", self.admin_token),
            ("Candidate", self.candidate_token),
            ("Employer", self.employer_token),
            ("Recruiter", self.recruiter_token)
        ]
        
        for role, token in tokens:
            if token:
                self.run_test(
                    f"Get Me ({role})",
                    "GET",
                    "auth/me",
                    200,
                    token=token
                )

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print(f"📊 Tests run: {self.tests_run}")
        print(f"✅ Tests passed: {self.tests_passed}")
        print(f"❌ Tests failed: {self.tests_run - self.tests_passed}")
        print(f"📈 Success rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failed_tests:
            print("\n❌ FAILED TESTS:")
            for i, test in enumerate(self.failed_tests, 1):
                print(f"{i}. {test['test']}")
                print(f"   Endpoint: {test.get('endpoint', 'N/A')}")
                if 'expected' in test:
                    print(f"   Expected: {test['expected']}, Got: {test['actual']}")
                print(f"   Error: {test.get('error', 'Unknown error')}")
                print()
        
        return self.tests_passed == self.tests_run

def main():
    print("🚀 Starting VHC Talent OS API Testing...")
    print(f"🌐 Backend URL: https://security-verify.preview.emergentagent.com")
    
    tester = VHCTalentOSAPITester()
    
    # Run all tests in sequence
    try:
        # 1. Test admin login first
        if not tester.test_admin_login():
            print("❌ Admin login failed - stopping critical tests")
            return 1
        
        # 2. Test admin functionality
        tester.test_admin_stats()
        tester.test_user_management()
        
        # 3. Test user registrations
        tester.test_candidate_registration()
        tester.test_employer_registration()
        tester.test_recruiter_registration()
        
        # 4. Test job management
        tester.test_job_management()
        
        # 5. Test company management
        tester.test_company_management()
        
        # 6. Test application flow
        tester.test_application_flow()
        
        # 7. Test auth/me endpoints
        tester.test_auth_me_endpoints()
        
    except KeyboardInterrupt:
        print("\n⚠️ Testing interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Unexpected error during testing: {str(e)}")
        return 1
    
    # Print final summary
    success = tester.print_summary()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())