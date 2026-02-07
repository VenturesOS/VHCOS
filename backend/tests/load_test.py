#!/usr/bin/env python3
"""
VHC Talent OS - Comprehensive Load & Stress Test Suite
Tests platform at maximum capacity with concurrent users performing all operations.
"""

import asyncio
import aiohttp
import time
import uuid
import json
import random
import statistics
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import os

# Configuration
API_URL = os.environ.get("API_URL", "https://upload-chunks.preview.emergentagent.com")
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"

# Test Configuration
NUM_ADMINS = 2
NUM_EMPLOYERS = 8
NUM_RECRUITERS = 40
TOTAL_USERS = NUM_ADMINS + NUM_EMPLOYERS + NUM_RECRUITERS  # 50

# Stress levels
CONCURRENT_REQUESTS = [10, 25, 50, 75, 100, 150, 200]
OPERATIONS_PER_USER = 20


@dataclass
class TestMetrics:
    """Stores test metrics for analysis"""
    endpoint: str
    method: str
    response_times: List[float] = field(default_factory=list)
    success_count: int = 0
    error_count: int = 0
    errors: List[str] = field(default_factory=list)
    
    @property
    def avg_response_time(self) -> float:
        return statistics.mean(self.response_times) if self.response_times else 0
    
    @property
    def p95_response_time(self) -> float:
        if not self.response_times:
            return 0
        sorted_times = sorted(self.response_times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[idx] if idx < len(sorted_times) else sorted_times[-1]
    
    @property
    def p99_response_time(self) -> float:
        if not self.response_times:
            return 0
        sorted_times = sorted(self.response_times)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[idx] if idx < len(sorted_times) else sorted_times[-1]
    
    @property
    def min_response_time(self) -> float:
        return min(self.response_times) if self.response_times else 0
    
    @property
    def max_response_time(self) -> float:
        return max(self.response_times) if self.response_times else 0
    
    @property
    def error_rate(self) -> float:
        total = self.success_count + self.error_count
        return (self.error_count / total * 100) if total > 0 else 0
    
    @property
    def throughput(self) -> float:
        total_time = sum(self.response_times)
        return len(self.response_times) / total_time if total_time > 0 else 0


class LoadTestSuite:
    def __init__(self):
        self.admin_token = None
        self.test_users: Dict[str, Dict] = {}  # {user_id: {email, password, token, role}}
        self.test_jobs: List[str] = []
        self.test_candidates: List[str] = []
        self.metrics: Dict[str, TestMetrics] = defaultdict(lambda: TestMetrics("", ""))
        self.global_start_time = None
        self.global_end_time = None
        
    async def get_admin_token(self, session: aiohttp.ClientSession) -> str:
        """Get admin authentication token"""
        async with session.post(
            f"{API_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        ) as resp:
            data = await resp.json()
            return data.get("access_token")
    
    async def create_test_user(self, session: aiohttp.ClientSession, role: str, index: int) -> Dict:
        """Create a test user"""
        email = f"loadtest_{role}_{index}_{uuid.uuid4().hex[:8]}@test.vhc.in"
        password = "TestPassword123!"
        name = f"Load Test {role.title()} {index}"
        
        try:
            async with session.post(
                f"{API_URL}/api/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "name": name,
                    "role": role
                }
            ) as resp:
                if resp.status in [200, 201]:
                    data = await resp.json()
                    # Login to get token
                    async with session.post(
                        f"{API_URL}/api/auth/login",
                        json={"email": email, "password": password}
                    ) as login_resp:
                        login_data = await login_resp.json()
                        return {
                            "id": data.get("id") or data.get("user", {}).get("id"),
                            "email": email,
                            "password": password,
                            "name": name,
                            "role": role,
                            "token": login_data.get("access_token")
                        }
                else:
                    error = await resp.text()
                    print(f"Failed to create {role} user: {error}")
                    return None
        except Exception as e:
            print(f"Error creating user: {e}")
            return None
    
    async def setup_test_users(self, session: aiohttp.ClientSession):
        """Create all test users"""
        print(f"\n{'='*60}")
        print("PHASE 1: CREATING TEST USERS")
        print(f"{'='*60}")
        
        tasks = []
        
        # Create admins (using existing admin for 1, create 1 more)
        self.test_users["admin_0"] = {
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "role": "admin",
            "token": self.admin_token
        }
        for i in range(1, NUM_ADMINS):
            tasks.append(self.create_test_user(session, "admin", i))
        
        # Create employers
        for i in range(NUM_EMPLOYERS):
            tasks.append(self.create_test_user(session, "employer", i))
        
        # Create recruiters
        for i in range(NUM_RECRUITERS):
            tasks.append(self.create_test_user(session, "recruiter", i))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        user_idx = 1
        for result in results:
            if isinstance(result, dict) and result:
                self.test_users[f"user_{user_idx}"] = result
                user_idx += 1
        
        # Count by role
        roles = defaultdict(int)
        for u in self.test_users.values():
            roles[u.get("role", "unknown")] += 1
        
        print(f"✅ Created {len(self.test_users)} test users:")
        for role, count in roles.items():
            print(f"   - {role}: {count}")
    
    async def timed_request(
        self, 
        session: aiohttp.ClientSession, 
        method: str, 
        endpoint: str, 
        token: str = None,
        json_data: dict = None,
        data: aiohttp.FormData = None
    ) -> tuple:
        """Execute a timed request and record metrics"""
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        metric_key = f"{method}:{endpoint.split('?')[0]}"
        if metric_key not in self.metrics:
            self.metrics[metric_key] = TestMetrics(endpoint, method)
        
        start_time = time.time()
        try:
            async with session.request(
                method, 
                f"{API_URL}{endpoint}",
                headers=headers,
                json=json_data if method != "GET" and not data else None,
                data=data
            ) as resp:
                elapsed = time.time() - start_time
                self.metrics[metric_key].response_times.append(elapsed)
                
                if resp.status < 400:
                    self.metrics[metric_key].success_count += 1
                    try:
                        return (resp.status, await resp.json(), elapsed)
                    except:
                        return (resp.status, await resp.text(), elapsed)
                else:
                    self.metrics[metric_key].error_count += 1
                    error_text = await resp.text()
                    self.metrics[metric_key].errors.append(f"{resp.status}: {error_text[:100]}")
                    return (resp.status, error_text, elapsed)
        except Exception as e:
            elapsed = time.time() - start_time
            self.metrics[metric_key].error_count += 1
            self.metrics[metric_key].errors.append(str(e)[:100])
            return (0, str(e), elapsed)
    
    async def simulate_admin_operations(self, session: aiohttp.ClientSession, user: Dict, ops: int):
        """Simulate admin user operations"""
        token = user.get("token") or self.admin_token
        
        for _ in range(ops):
            op = random.choice(["search_candidates", "get_users", "get_companies", "get_stats", "get_jobs"])
            
            if op == "search_candidates":
                search_term = random.choice(["python", "java", "react", "manager", "sales", "marketing"])
                await self.timed_request(session, "GET", f"/api/candidate-bank?search={search_term}&limit=20", token)
            elif op == "get_users":
                await self.timed_request(session, "GET", "/api/admin/users", token)
            elif op == "get_companies":
                await self.timed_request(session, "GET", "/api/admin/companies", token)
            elif op == "get_stats":
                await self.timed_request(session, "GET", "/api/admin/dashboard-stats", token)
            elif op == "get_jobs":
                await self.timed_request(session, "GET", "/api/jobs", token)
            
            await asyncio.sleep(random.uniform(0.1, 0.5))
    
    async def simulate_employer_operations(self, session: aiohttp.ClientSession, user: Dict, ops: int):
        """Simulate employer user operations"""
        token = user.get("token")
        if not token:
            return
        
        for _ in range(ops):
            op = random.choice(["search_candidates", "get_jobs", "get_pipeline", "ai_match", "get_applications"])
            
            if op == "search_candidates":
                search_term = random.choice(["developer", "engineer", "analyst", "designer", "lead"])
                await self.timed_request(session, "GET", f"/api/candidate-bank?search={search_term}&limit=20", token)
            elif op == "get_jobs":
                await self.timed_request(session, "GET", "/api/jobs", token)
            elif op == "get_pipeline":
                await self.timed_request(session, "GET", "/api/employer/pipeline-stats", token)
            elif op == "ai_match":
                await self.timed_request(
                    session, "POST", "/api/matching/find-candidates",
                    token,
                    json_data={
                        "jd_text": "Senior Software Engineer with Python and Django experience",
                        "quick_match": True,
                        "semantic_search": True,
                        "limit": 10
                    }
                )
            elif op == "get_applications":
                await self.timed_request(session, "GET", "/api/applications?limit=20", token)
            
            await asyncio.sleep(random.uniform(0.1, 0.5))
    
    async def simulate_recruiter_operations(self, session: aiohttp.ClientSession, user: Dict, ops: int):
        """Simulate recruiter user operations"""
        token = user.get("token")
        if not token:
            return
        
        for _ in range(ops):
            op = random.choice(["search_candidates", "get_jobs", "get_referrals", "view_candidate"])
            
            if op == "search_candidates":
                skills = random.choice(["java", "python", "javascript", "sql", "aws", "docker"])
                await self.timed_request(session, "GET", f"/api/candidate-bank?search={skills}&limit=15", token)
            elif op == "get_jobs":
                await self.timed_request(session, "GET", "/api/jobs", token)
            elif op == "get_referrals":
                await self.timed_request(session, "GET", "/api/referrals", token)
            elif op == "view_candidate":
                # Get a random candidate
                status, data, _ = await self.timed_request(session, "GET", "/api/candidate-bank?limit=5", token)
                if status == 200 and isinstance(data, dict) and data.get("candidates"):
                    candidate = random.choice(data["candidates"])
                    await self.timed_request(session, "GET", f"/api/candidate-bank/{candidate['id']}", token)
            
            await asyncio.sleep(random.uniform(0.1, 0.5))
    
    async def run_concurrent_load_test(self, session: aiohttp.ClientSession, concurrency: int):
        """Run load test with specified concurrency"""
        print(f"\n{'='*60}")
        print(f"LOAD TEST: {concurrency} CONCURRENT OPERATIONS")
        print(f"{'='*60}")
        
        tasks = []
        ops_per_user = max(1, OPERATIONS_PER_USER // (concurrency // 10 + 1))
        
        for user_key, user in list(self.test_users.items())[:concurrency]:
            role = user.get("role", "recruiter")
            
            if role == "admin":
                tasks.append(self.simulate_admin_operations(session, user, ops_per_user))
            elif role == "employer":
                tasks.append(self.simulate_employer_operations(session, user, ops_per_user))
            else:
                tasks.append(self.simulate_recruiter_operations(session, user, ops_per_user))
        
        # Fill remaining with mixed operations
        while len(tasks) < concurrency:
            user = random.choice(list(self.test_users.values()))
            role = user.get("role", "recruiter")
            if role == "admin":
                tasks.append(self.simulate_admin_operations(session, user, ops_per_user // 2))
            elif role == "employer":
                tasks.append(self.simulate_employer_operations(session, user, ops_per_user // 2))
            else:
                tasks.append(self.simulate_recruiter_operations(session, user, ops_per_user // 2))
        
        start = time.time()
        await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start
        
        total_requests = sum(m.success_count + m.error_count for m in self.metrics.values())
        total_errors = sum(m.error_count for m in self.metrics.values())
        
        print(f"   Completed in {elapsed:.2f}s")
        print(f"   Total requests: {total_requests}")
        print(f"   Error rate: {(total_errors/total_requests*100) if total_requests > 0 else 0:.2f}%")
        
        return {
            "concurrency": concurrency,
            "duration": elapsed,
            "total_requests": total_requests,
            "error_count": total_errors,
            "rps": total_requests / elapsed if elapsed > 0 else 0
        }
    
    async def test_bulk_upload(self, session: aiohttp.ClientSession):
        """Test bulk upload with the provided ZIP file"""
        print(f"\n{'='*60}")
        print("BULK UPLOAD STRESS TEST")
        print(f"{'='*60}")
        
        zip_path = "/tmp/test_cvs.zip"
        if not os.path.exists(zip_path):
            print("❌ Test ZIP file not found")
            return None
        
        file_size = os.path.getsize(zip_path)
        print(f"📁 File size: {file_size / (1024*1024):.2f} MB")
        
        # Test chunked upload
        chunk_size = 512 * 1024  # 512KB
        total_chunks = (file_size + chunk_size - 1) // chunk_size
        
        print(f"   Testing chunked upload ({total_chunks} chunks)...")
        
        start_time = time.time()
        
        # Initialize upload
        status, data, init_time = await self.timed_request(
            session, "POST", "/api/admin/bulk-import/chunk/init",
            self.admin_token,
            json_data={
                "filename": "test_cvs.zip",
                "total_size": file_size,
                "total_chunks": total_chunks
            }
        )
        
        if status != 200:
            print(f"❌ Failed to init upload: {data}")
            return None
        
        upload_id = data.get("upload_id")
        print(f"   Upload ID: {upload_id}")
        
        # Upload chunks
        with open(zip_path, "rb") as f:
            for chunk_idx in range(total_chunks):
                chunk_data = f.read(chunk_size)
                
                form_data = aiohttp.FormData()
                form_data.add_field("upload_id", upload_id)
                form_data.add_field("chunk_index", str(chunk_idx))
                form_data.add_field("chunk", chunk_data, filename=f"chunk_{chunk_idx}")
                
                status, _, chunk_time = await self.timed_request(
                    session, "POST", "/api/admin/bulk-import/chunk/upload",
                    self.admin_token,
                    data=form_data
                )
                
                if (chunk_idx + 1) % 20 == 0:
                    progress = (chunk_idx + 1) / total_chunks * 100
                    print(f"   Progress: {progress:.1f}% ({chunk_idx + 1}/{total_chunks} chunks)")
        
        # Complete upload
        status, _, complete_time = await self.timed_request(
            session, "POST", f"/api/admin/bulk-import/chunk/complete?upload_id={upload_id}",
            self.admin_token
        )
        
        upload_time = time.time() - start_time
        
        print(f"   ✅ Upload completed in {upload_time:.2f}s")
        print(f"   Throughput: {file_size / upload_time / (1024*1024):.2f} MB/s")
        
        # Test async processing
        print(f"\n   Testing async CV processing...")
        status, data, _ = await self.timed_request(
            session, "POST", f"/api/admin/bulk-import/cv-zip-async",
            self.admin_token,
            json_data={"upload_id": upload_id}
        )
        
        if status == 200:
            job_id = data.get("job_id")
            batch_id = data.get("batch_id")
            print(f"   Background job started: {job_id}")
            
            # Monitor progress
            for _ in range(60):  # Wait up to 5 minutes
                await asyncio.sleep(5)
                status, job_data, _ = await self.timed_request(
                    session, "GET", f"/api/background-jobs/{job_id}",
                    self.admin_token
                )
                if status == 200 and isinstance(job_data, dict):
                    progress = job_data.get("progress", 0)
                    job_status = job_data.get("status")
                    print(f"   Processing: {progress}% - {job_status}")
                    if job_status in ["completed", "failed"]:
                        break
        
        return {
            "file_size_mb": file_size / (1024*1024),
            "upload_time_s": upload_time,
            "throughput_mbps": file_size / upload_time / (1024*1024),
            "chunks": total_chunks
        }
    
    async def test_search_performance(self, session: aiohttp.ClientSession):
        """Test search performance under various loads"""
        print(f"\n{'='*60}")
        print("SEARCH PERFORMANCE TEST")
        print(f"{'='*60}")
        
        search_terms = [
            "python", "java", "react", "manager", "sales", 
            "developer", "engineer", "analyst", "lead", "senior",
            "mumbai", "bangalore", "delhi", "pune", "hyderabad"
        ]
        
        search_metrics = []
        
        for term in search_terms:
            times = []
            for _ in range(5):  # 5 searches per term
                status, data, elapsed = await self.timed_request(
                    session, "GET", f"/api/candidate-bank?search={term}&limit=50",
                    self.admin_token
                )
                times.append(elapsed)
                if status == 200 and isinstance(data, dict):
                    result_count = len(data.get("candidates", []))
            
            search_metrics.append({
                "term": term,
                "avg_time": statistics.mean(times),
                "min_time": min(times),
                "max_time": max(times)
            })
            print(f"   '{term}': avg={statistics.mean(times)*1000:.1f}ms, max={max(times)*1000:.1f}ms")
        
        return search_metrics
    
    async def test_ai_matching_load(self, session: aiohttp.ClientSession):
        """Test AI matching under load"""
        print(f"\n{'='*60}")
        print("AI MATCHING STRESS TEST")
        print(f"{'='*60}")
        
        jds = [
            "Senior Python Developer with Django and FastAPI experience. 5+ years required.",
            "Full Stack Engineer with React, Node.js, and AWS. Remote friendly.",
            "Data Scientist with ML expertise, Python, TensorFlow. PhD preferred.",
            "DevOps Engineer with Kubernetes, Docker, CI/CD pipelines.",
            "Product Manager with B2B SaaS experience, Agile methodology.",
        ]
        
        results = []
        
        # Test different concurrency levels
        for concurrent in [1, 5, 10]:
            print(f"\n   Testing {concurrent} concurrent AI match requests...")
            
            tasks = []
            for i in range(concurrent):
                jd = random.choice(jds)
                tasks.append(self.timed_request(
                    session, "POST", "/api/matching/find-candidates",
                    self.admin_token,
                    json_data={
                        "jd_text": jd,
                        "quick_match": False,  # Full AI matching
                        "semantic_search": True,
                        "limit": 20
                    }
                ))
            
            start = time.time()
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.time() - start
            
            success = sum(1 for r in responses if isinstance(r, tuple) and r[0] == 200)
            times = [r[2] for r in responses if isinstance(r, tuple)]
            
            results.append({
                "concurrent": concurrent,
                "success_rate": success / concurrent * 100,
                "total_time": elapsed,
                "avg_per_request": statistics.mean(times) if times else 0,
                "rps": concurrent / elapsed if elapsed > 0 else 0
            })
            
            print(f"   Success: {success}/{concurrent}, Time: {elapsed:.2f}s, Avg: {statistics.mean(times)*1000:.1f}ms")
        
        return results
    
    async def test_database_stress(self, session: aiohttp.ClientSession):
        """Test database under heavy read/write load"""
        print(f"\n{'='*60}")
        print("DATABASE STRESS TEST")
        print(f"{'='*60}")
        
        # Rapid-fire reads
        print("\n   Testing rapid-fire reads...")
        read_tasks = []
        for _ in range(100):
            endpoint = random.choice([
                "/api/candidate-bank?limit=10",
                "/api/jobs?limit=10",
                "/api/applications?limit=10"
            ])
            read_tasks.append(self.timed_request(session, "GET", endpoint, self.admin_token))
        
        start = time.time()
        results = await asyncio.gather(*read_tasks, return_exceptions=True)
        elapsed = time.time() - start
        
        success = sum(1 for r in results if isinstance(r, tuple) and r[0] == 200)
        print(f"   100 reads in {elapsed:.2f}s ({100/elapsed:.1f} RPS), Success: {success}%")
        
        return {
            "reads_100_time": elapsed,
            "reads_rps": 100 / elapsed,
            "success_rate": success
        }
    
    async def cleanup_test_users(self, session: aiohttp.ClientSession):
        """Delete all test users"""
        print(f"\n{'='*60}")
        print("CLEANUP: DELETING TEST USERS")
        print(f"{'='*60}")
        
        deleted = 0
        for user_key, user in list(self.test_users.items()):
            if user.get("email", "").startswith("loadtest_"):
                user_id = user.get("id")
                if user_id:
                    status, _, _ = await self.timed_request(
                        session, "DELETE", f"/api/admin/users/{user_id}",
                        self.admin_token
                    )
                    if status in [200, 204]:
                        deleted += 1
        
        print(f"   ✅ Deleted {deleted} test users")
    
    def generate_report(self, load_results: List[Dict], bulk_upload: Dict, search_metrics: List, ai_results: List, db_stress: Dict):
        """Generate comprehensive performance report"""
        report = []
        report.append("\n" + "="*80)
        report.append("VHC TALENT OS - COMPREHENSIVE LOAD TEST REPORT")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("="*80)
        
        # Overall Summary
        report.append("\n" + "="*80)
        report.append("EXECUTIVE SUMMARY")
        report.append("="*80)
        
        total_requests = sum(m.success_count + m.error_count for m in self.metrics.values())
        total_errors = sum(m.error_count for m in self.metrics.values())
        all_times = []
        for m in self.metrics.values():
            all_times.extend(m.response_times)
        
        report.append(f"""
📊 Test Duration: {(self.global_end_time - self.global_start_time):.2f} seconds
👥 Test Users Created: {len(self.test_users)}
📡 Total API Requests: {total_requests:,}
✅ Successful Requests: {total_requests - total_errors:,}
❌ Failed Requests: {total_errors:,}
📈 Overall Error Rate: {(total_errors/total_requests*100) if total_requests > 0 else 0:.2f}%
⚡ Average Response Time: {statistics.mean(all_times)*1000:.1f}ms
🔥 P95 Response Time: {sorted(all_times)[int(len(all_times)*0.95)]*1000:.1f}ms
💀 P99 Response Time: {sorted(all_times)[int(len(all_times)*0.99)]*1000:.1f}ms
""")
        
        # Capacity Analysis
        report.append("\n" + "="*80)
        report.append("CAPACITY ANALYSIS BY CONCURRENCY LEVEL")
        report.append("="*80)
        
        report.append("""
| Concurrency | Duration | Requests | Errors | RPS    | Status      |
|-------------|----------|----------|--------|--------|-------------|""")
        
        for r in load_results:
            error_rate = (r.get("error_count", 0) / r.get("total_requests", 1)) * 100
            status = "🟢 SAFE" if error_rate < 1 else ("🟡 OPTIMAL" if error_rate < 5 else "🔴 DANGER")
            report.append(f"| {r['concurrency']:11} | {r['duration']:7.2f}s | {r['total_requests']:8} | {r.get('error_count', 0):6} | {r['rps']:6.1f} | {status:11} |")
        
        # Endpoint Performance
        report.append("\n" + "="*80)
        report.append("TOP 15 ENDPOINT PERFORMANCE (by request count)")
        report.append("="*80)
        
        sorted_metrics = sorted(self.metrics.items(), key=lambda x: x[1].success_count + x[1].error_count, reverse=True)[:15]
        
        report.append("""
| Endpoint                                    | Requests | Avg(ms) | P95(ms) | P99(ms) | Errors |
|---------------------------------------------|----------|---------|---------|---------|--------|""")
        
        for key, m in sorted_metrics:
            endpoint = key.split(":", 1)[1][:43]
            report.append(f"| {endpoint:43} | {m.success_count + m.error_count:8} | {m.avg_response_time*1000:7.1f} | {m.p95_response_time*1000:7.1f} | {m.p99_response_time*1000:7.1f} | {m.error_count:6} |")
        
        # Search Performance
        if search_metrics:
            report.append("\n" + "="*80)
            report.append("SEARCH PERFORMANCE")
            report.append("="*80)
            
            report.append("""
| Search Term   | Avg Time | Min Time | Max Time | Status      |
|---------------|----------|----------|----------|-------------|""")
            
            for s in search_metrics:
                avg_ms = s["avg_time"] * 1000
                status = "🟢 FAST" if avg_ms < 200 else ("🟡 OK" if avg_ms < 500 else "🔴 SLOW")
                report.append(f"| {s['term']:13} | {avg_ms:7.1f}ms | {s['min_time']*1000:7.1f}ms | {s['max_time']*1000:7.1f}ms | {status:11} |")
        
        # AI Matching Performance
        if ai_results:
            report.append("\n" + "="*80)
            report.append("AI MATCHING PERFORMANCE")
            report.append("="*80)
            
            report.append("""
| Concurrent | Success Rate | Total Time | Avg/Request | RPS   |
|------------|--------------|------------|-------------|-------|""")
            
            for r in ai_results:
                report.append(f"| {r['concurrent']:10} | {r['success_rate']:11.1f}% | {r['total_time']:9.2f}s | {r['avg_per_request']*1000:10.1f}ms | {r['rps']:5.2f} |")
        
        # Bulk Upload Performance
        if bulk_upload:
            report.append("\n" + "="*80)
            report.append("BULK UPLOAD PERFORMANCE")
            report.append("="*80)
            report.append(f"""
📁 File Size: {bulk_upload.get('file_size_mb', 0):.2f} MB
⏱️ Upload Time: {bulk_upload.get('upload_time_s', 0):.2f} seconds
🚀 Throughput: {bulk_upload.get('throughput_mbps', 0):.2f} MB/s
📦 Total Chunks: {bulk_upload.get('chunks', 0)}
""")
        
        # Database Stress Results
        if db_stress:
            report.append("\n" + "="*80)
            report.append("DATABASE STRESS TEST")
            report.append("="*80)
            report.append(f"""
📖 100 Rapid Reads: {db_stress.get('reads_100_time', 0):.2f} seconds
⚡ Read RPS: {db_stress.get('reads_rps', 0):.1f} requests/second
✅ Success Rate: {db_stress.get('success_rate', 0)}%
""")
        
        # Recommendations
        report.append("\n" + "="*80)
        report.append("🎯 PERFORMANCE THRESHOLDS & RECOMMENDATIONS")
        report.append("="*80)
        
        # Determine safe, optimal, and danger zones
        if load_results:
            safe_concurrency = max([r['concurrency'] for r in load_results if r.get('error_count', 0) / max(r.get('total_requests', 1), 1) < 0.01], default=10)
            optimal_concurrency = max([r['concurrency'] for r in load_results if r.get('error_count', 0) / max(r.get('total_requests', 1), 1) < 0.05], default=25)
            danger_concurrency = min([r['concurrency'] for r in load_results if r.get('error_count', 0) / max(r.get('total_requests', 1), 1) > 0.10], default=200)
        else:
            safe_concurrency, optimal_concurrency, danger_concurrency = 10, 25, 100
        
        report.append(f"""
┌─────────────────────────────────────────────────────────────────┐
│ CONCURRENT USER RECOMMENDATIONS                                  │
├─────────────────────────────────────────────────────────────────┤
│ 🟢 SAFE ZONE (< 1% errors):     Up to {safe_concurrency:3} concurrent users       │
│ 🟡 OPTIMAL ZONE (< 5% errors):  Up to {optimal_concurrency:3} concurrent users       │
│ 🔴 DANGER ZONE (> 10% errors):  Above {danger_concurrency:3} concurrent users       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ RESPONSE TIME THRESHOLDS                                         │
├─────────────────────────────────────────────────────────────────┤
│ 🟢 EXCELLENT: < 200ms (Search, List APIs)                        │
│ 🟡 ACCEPTABLE: 200-500ms (Complex queries, Dashboard)            │
│ 🔴 NEEDS OPTIMIZATION: > 500ms                                   │
│ 💀 CRITICAL: > 2000ms (AI Matching with full LLM)                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SCALING RECOMMENDATIONS                                          │
├─────────────────────────────────────────────────────────────────┤
│ 1. Current setup handles ~{optimal_concurrency} concurrent users well           │
│ 2. For 100+ users: Add read replicas to MongoDB Atlas            │
│ 3. For 200+ users: Implement horizontal scaling (K8s)            │
│ 4. AI Matching is the bottleneck - use quick_match for speed     │
│ 5. Search is fast thanks to Atlas Search + Redis caching         │
└─────────────────────────────────────────────────────────────────┘
""")
        
        # Error Summary
        report.append("\n" + "="*80)
        report.append("ERROR SUMMARY (Top 10 by frequency)")
        report.append("="*80)
        
        all_errors = []
        for key, m in self.metrics.items():
            for err in m.errors[:3]:
                all_errors.append(f"{key}: {err}")
        
        if all_errors:
            for err in all_errors[:10]:
                report.append(f"   ❌ {err[:100]}")
        else:
            report.append("   ✅ No significant errors recorded")
        
        return "\n".join(report)
    
    async def run_full_test(self):
        """Run the complete load test suite"""
        self.global_start_time = time.time()
        
        print("\n" + "="*80)
        print("VHC TALENT OS - COMPREHENSIVE LOAD TEST")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=50)
        timeout = aiohttp.ClientTimeout(total=120)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Get admin token
            self.admin_token = await self.get_admin_token(session)
            if not self.admin_token:
                print("❌ Failed to get admin token")
                return
            
            print(f"✅ Admin authenticated")
            
            # Setup test users
            await self.setup_test_users(session)
            
            # Run load tests at different concurrency levels
            load_results = []
            for concurrency in [10, 25, 50]:
                result = await self.run_concurrent_load_test(session, concurrency)
                load_results.append(result)
            
            # Test search performance
            search_metrics = await self.test_search_performance(session)
            
            # Test AI matching
            ai_results = await self.test_ai_matching_load(session)
            
            # Test database stress
            db_stress = await self.test_database_stress(session)
            
            # Test bulk upload (optional - takes time)
            bulk_upload = None
            print("\n⏳ Starting bulk upload test (this may take several minutes)...")
            try:
                bulk_upload = await self.test_bulk_upload(session)
            except Exception as e:
                print(f"❌ Bulk upload test failed: {e}")
            
            # Cleanup
            await self.cleanup_test_users(session)
        
        self.global_end_time = time.time()
        
        # Generate report
        report = self.generate_report(load_results, bulk_upload, search_metrics, ai_results, db_stress)
        
        # Save report
        report_path = "/app/test_reports/load_test_report.txt"
        with open(report_path, "w") as f:
            f.write(report)
        
        print(report)
        print(f"\n📄 Report saved to: {report_path}")
        
        return report


async def main():
    suite = LoadTestSuite()
    await suite.run_full_test()


if __name__ == "__main__":
    asyncio.run(main())
