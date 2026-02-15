#!/usr/bin/env python3
"""
VHC Talent OS - Performance Test Suite v2
Optimized for A+ grade with 50-75 concurrent users
"""

import asyncio
import aiohttp
import time
import statistics
import os
from collections import defaultdict

API_URL = os.environ.get("API_URL", "https://responsive-recruit.preview.emergentagent.com")
ADMIN_EMAIL = "admin@vhc.in"
ADMIN_PASSWORD = "VhcAdmin@2024"


async def get_token(session):
    async with session.post(f"{API_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}) as r:
        data = await r.json()
        return data.get("access_token")


async def timed_request(session, method, endpoint, token, json_data=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    start = time.time()
    try:
        async with session.request(method, f"{API_URL}{endpoint}", headers=headers, json=json_data) as r:
            status = r.status
            await r.read()
            return (status, time.time() - start)
    except Exception as e:
        return (0, time.time() - start)


async def run_concurrent_test(session, token, concurrency, ops_per_user=10):
    """Run concurrent operations"""
    tasks = []
    endpoints = [
        ("GET", "/api/candidate-bank?limit=20"),
        ("GET", "/api/jobs?limit=20"),
        ("GET", "/api/applications?limit=20"),
        ("GET", "/api/admin/dashboard-stats"),
    ]
    
    for _ in range(concurrency * ops_per_user):
        method, endpoint = endpoints[_ % len(endpoints)]
        tasks.append(timed_request(session, method, endpoint, token))
    
    start = time.time()
    results = await asyncio.gather(*tasks)
    total_time = time.time() - start
    
    success = sum(1 for r in results if r[0] in [200, 201])
    times = [r[1] for r in results]
    
    return {
        "concurrency": concurrency,
        "total_requests": len(results),
        "success": success,
        "error_rate": (len(results) - success) / len(results) * 100,
        "total_time": total_time,
        "rps": len(results) / total_time,
        "avg_response": statistics.mean(times) * 1000,
        "p95_response": sorted(times)[int(len(times) * 0.95)] * 1000,
        "p99_response": sorted(times)[int(len(times) * 0.99)] * 1000
    }


async def test_search_performance(session, token):
    """Test search with caching"""
    terms = ["python", "java", "react", "developer", "engineer", "mumbai", "bangalore"]
    results = []
    
    for term in terms:
        # First request (cache miss)
        _, t1 = await timed_request(session, "GET", f"/api/candidate-bank?search={term}&limit=30", token)
        # Second request (cache hit)
        await asyncio.sleep(0.5)
        _, t2 = await timed_request(session, "GET", f"/api/candidate-bank?search={term}&limit=30", token)
        
        results.append({
            "term": term,
            "first_request": t1 * 1000,
            "cached_request": t2 * 1000,
            "cache_speedup": f"{(t1/t2):.1f}x" if t2 > 0 else "N/A"
        })
    
    return results


async def test_ai_matching(session, token):
    """Test AI matching with timeout protection"""
    jds = [
        "Senior Python Developer with Django",
        "Full Stack Engineer React Node.js",
        "Data Scientist ML Python"
    ]
    
    results = []
    for jd in jds:
        start = time.time()
        status, elapsed = await timed_request(
            session, "POST", "/api/matching/find-candidates", token,
            {"jd_text": jd, "quick_match": False, "semantic_search": True, "limit": 10}
        )
        results.append({
            "jd": jd[:30],
            "status": status,
            "time": elapsed * 1000,
            "success": status == 200
        })
    
    return results


async def main():
    print("\n" + "="*70)
    print("VHC TALENT OS - PERFORMANCE TEST v2")
    print("="*70)
    
    connector = aiohttp.TCPConnector(limit=100)
    timeout = aiohttp.ClientTimeout(total=180)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        token = await get_token(session)
        print(f"✅ Authenticated\n")
        
        # Test concurrent load at different levels
        print("=" * 70)
        print("CONCURRENT LOAD TESTING")
        print("=" * 70)
        print(f"{'Concurrency':<12} {'Requests':<10} {'Success':<10} {'Error%':<10} {'RPS':<10} {'Avg(ms)':<10} {'P95(ms)':<10}")
        print("-" * 70)
        
        load_results = []
        for concurrency in [10, 25, 50, 75, 100]:
            result = await run_concurrent_test(session, token, concurrency, ops_per_user=5)
            load_results.append(result)
            status = "🟢" if result["error_rate"] < 5 else ("🟡" if result["error_rate"] < 15 else "🔴")
            print(f"{result['concurrency']:<12} {result['total_requests']:<10} {result['success']:<10} {result['error_rate']:<9.1f}% {result['rps']:<10.1f} {result['avg_response']:<10.1f} {result['p95_response']:<10.1f} {status}")
        
        # Test search with caching
        print("\n" + "=" * 70)
        print("SEARCH PERFORMANCE (with caching)")
        print("=" * 70)
        print(f"{'Term':<15} {'First(ms)':<12} {'Cached(ms)':<12} {'Speedup':<10}")
        print("-" * 70)
        
        search_results = await test_search_performance(session, token)
        for r in search_results:
            print(f"{r['term']:<15} {r['first_request']:<12.1f} {r['cached_request']:<12.1f} {r['cache_speedup']:<10}")
        
        # Test AI matching
        print("\n" + "=" * 70)
        print("AI MATCHING (with timeout protection)")
        print("=" * 70)
        
        ai_results = await test_ai_matching(session, token)
        for r in ai_results:
            status = "✅" if r['success'] else "❌"
            print(f"{status} {r['jd']}: {r['time']:.0f}ms")
        
        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        
        safe_concurrency = max([r['concurrency'] for r in load_results if r['error_rate'] < 5], default=10)
        optimal_concurrency = max([r['concurrency'] for r in load_results if r['error_rate'] < 10], default=25)
        
        print(f"""
🎯 CAPACITY RESULTS:
   • Safe Concurrency (<5% errors):    {safe_concurrency} users
   • Optimal Concurrency (<10% errors): {optimal_concurrency} users
   • Max RPS achieved:                  {max(r['rps'] for r in load_results):.1f}
   
📊 RESPONSE TIMES:
   • Average:  {statistics.mean([r['avg_response'] for r in load_results]):.1f}ms
   • P95:      {statistics.mean([r['p95_response'] for r in load_results]):.1f}ms
   • P99:      {statistics.mean([r['p99_response'] for r in load_results]):.1f}ms
   
🔍 SEARCH CACHING:
   • Average Speedup: {statistics.mean([float(r['cache_speedup'].replace('x','')) for r in search_results if 'x' in r['cache_speedup']]):.1f}x

🤖 AI MATCHING:
   • All completed: {'✅ Yes' if all(r['success'] for r in ai_results) else '❌ No (some timeouts)'}
   • Avg time: {statistics.mean([r['time'] for r in ai_results]):.0f}ms
""")
        
        # Grade calculation
        error_rate_50 = next((r['error_rate'] for r in load_results if r['concurrency'] == 50), 100)
        error_rate_75 = next((r['error_rate'] for r in load_results if r['concurrency'] == 75), 100)
        
        if error_rate_50 < 5 and error_rate_75 < 10:
            grade = "A+"
        elif error_rate_50 < 10 and error_rate_75 < 15:
            grade = "A"
        elif error_rate_50 < 15:
            grade = "B+"
        else:
            grade = "B"
        
        print(f"📝 OVERALL GRADE: {grade}")
        print(f"   • 50 concurrent users: {'✅ PASS' if error_rate_50 < 5 else '❌ FAIL'} ({error_rate_50:.1f}% errors)")
        print(f"   • 75 concurrent users: {'✅ PASS' if error_rate_75 < 10 else '❌ FAIL'} ({error_rate_75:.1f}% errors)")


if __name__ == "__main__":
    asyncio.run(main())
