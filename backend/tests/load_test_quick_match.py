"""
Load Test for VHC Talent OS - Quick Match Performance
Validates: 50-75 concurrent users, <5% error rate, no timeouts.
"""
import asyncio
import aiohttp
import time
import json
import statistics
import sys

API_URL = None
TOKEN = None

async def login(session):
    """Get auth token."""
    async with session.post(f"{API_URL}/api/auth/login", json={
        "email": "admin@vhc.in", "password": "VhcAdmin@2024"
    }) as resp:
        data = await resp.json()
        return data.get("access_token")

async def quick_match_request(session, token, req_id):
    """Simulate a Quick Match request."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "jd_text": "Looking for a Python developer with 3-5 years experience in Django, FastAPI, SQL, MongoDB, Redis. Good communication skills required.",
        "match_mode": "quick",
        "limit": 20,
    }
    start = time.time()
    try:
        async with session.post(f"{API_URL}/api/matching/find-candidates",
                                json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            elapsed = time.time() - start
            status = resp.status
            body = await resp.text()
            if status == 200:
                results = json.loads(body)
                return {"id": req_id, "status": status, "time": elapsed, "count": len(results), "error": None}
            else:
                return {"id": req_id, "status": status, "time": elapsed, "count": 0, "error": body[:200]}
    except asyncio.TimeoutError:
        return {"id": req_id, "status": 0, "time": time.time() - start, "count": 0, "error": "TIMEOUT"}
    except Exception as e:
        return {"id": req_id, "status": 0, "time": time.time() - start, "count": 0, "error": str(e)[:200]}

async def run_load_test(concurrent_users, total_requests):
    """Run the load test with specified concurrency."""
    global API_URL, TOKEN

    # Read API URL from env file
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                API_URL = line.strip().split("=", 1)[1]
                break

    print(f"\n{'='*60}")
    print(f"  VHC Talent OS Load Test - Quick Match Endpoint")
    print(f"  Target: {concurrent_users} concurrent users, {total_requests} total requests")
    print(f"  API: {API_URL}/api/matching/find-candidates")
    print(f"{'='*60}\n")

    async with aiohttp.ClientSession() as session:
        TOKEN = await login(session)
        if not TOKEN:
            print("ERROR: Failed to get auth token")
            return

        print(f"Authenticated. Starting load test...\n")

        # Use a semaphore to limit concurrency
        sem = asyncio.Semaphore(concurrent_users)
        results = []

        async def bounded_request(req_id):
            async with sem:
                return await quick_match_request(session, TOKEN, req_id)

        start_time = time.time()
        tasks = [bounded_request(i) for i in range(total_requests)]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time

    # Analyze results
    successes = [r for r in results if r["status"] == 200]
    failures = [r for r in results if r["status"] != 200]
    timeouts = [r for r in results if r["error"] == "TIMEOUT"]
    rate_limited = [r for r in results if r["status"] == 429]

    response_times = [r["time"] for r in successes]

    error_rate = len(failures) / len(results) * 100 if results else 100
    pass_mark = error_rate < 5

    print(f"\n{'='*60}")
    print(f"  LOAD TEST RESULTS")
    print(f"{'='*60}")
    print(f"  Total Requests:      {len(results)}")
    print(f"  Concurrent Users:    {concurrent_users}")
    print(f"  Total Duration:      {total_time:.2f}s")
    print(f"  Throughput:          {len(results)/total_time:.1f} req/s")
    print(f"  ")
    print(f"  Successes:           {len(successes)} ({len(successes)/len(results)*100:.1f}%)")
    print(f"  Failures:            {len(failures)} ({error_rate:.1f}%)")
    print(f"    - Timeouts:        {len(timeouts)}")
    print(f"    - Rate Limited:    {len(rate_limited)}")
    print(f"    - Other Errors:    {len(failures) - len(timeouts) - len(rate_limited)}")
    print(f"  ")
    if response_times:
        print(f"  Response Times (successful):")
        print(f"    Min:               {min(response_times):.2f}s")
        print(f"    Max:               {max(response_times):.2f}s")
        print(f"    Mean:              {statistics.mean(response_times):.2f}s")
        print(f"    Median:            {statistics.median(response_times):.2f}s")
        print(f"    P95:               {sorted(response_times)[int(len(response_times)*0.95)]:.2f}s")
        print(f"    P99:               {sorted(response_times)[int(len(response_times)*0.99)]:.2f}s")
    print(f"  ")
    print(f"  ERROR RATE: {error_rate:.1f}%  {'PASS' if pass_mark else 'FAIL'} (target: <5%)")
    print(f"  GRADE: {'A+' if error_rate == 0 and (not response_times or statistics.median(response_times) < 5) else 'A' if pass_mark else 'F'}")
    print(f"{'='*60}\n")

    # Print failures for debugging
    if failures[:5]:
        print("Sample failures:")
        for f in failures[:5]:
            print(f"  req#{f['id']}: status={f['status']}, time={f['time']:.2f}s, error={f['error'][:100]}")

    # Write report
    report = {
        "test_type": "load_test",
        "endpoint": "/api/matching/find-candidates",
        "mode": "quick_match",
        "concurrent_users": concurrent_users,
        "total_requests": len(results),
        "total_duration_s": round(total_time, 2),
        "throughput_rps": round(len(results)/total_time, 1),
        "successes": len(successes),
        "failures": len(failures),
        "timeouts": len(timeouts),
        "rate_limited": len(rate_limited),
        "error_rate_pct": round(error_rate, 2),
        "pass": pass_mark,
        "response_times": {
            "min": round(min(response_times), 3) if response_times else None,
            "max": round(max(response_times), 3) if response_times else None,
            "mean": round(statistics.mean(response_times), 3) if response_times else None,
            "median": round(statistics.median(response_times), 3) if response_times else None,
            "p95": round(sorted(response_times)[int(len(response_times)*0.95)], 3) if response_times else None,
        },
    }
    with open("/app/test_reports/load_test_quick_match.json", "w") as f:
        json.dump(report, f, indent=2)
    print("Report saved to /app/test_reports/load_test_quick_match.json")

    return pass_mark


if __name__ == "__main__":
    users = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    requests = int(sys.argv[2]) if len(sys.argv) > 2 else 75
    result = asyncio.run(run_load_test(users, requests))
    sys.exit(0 if result else 1)
