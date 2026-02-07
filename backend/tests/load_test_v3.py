"""
Load Test v3 - Safe staggered load test for VHC Talent OS
Ramps up gradually to avoid connection storms.
"""
import asyncio
import aiohttp
import time
import json
import statistics
import sys

async def run_load_test(max_concurrent, total_requests):
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                api = line.strip().split("=", 1)[1]
                break

    print(f"\n{'='*60}")
    print(f"  Load Test v3 - Staggered (max {max_concurrent} concurrent, {total_requests} total)")
    print(f"{'='*60}\n")

    connector = aiohttp.TCPConnector(limit=max_concurrent, limit_per_host=max_concurrent)
    async with aiohttp.ClientSession(connector=connector) as session:
        r = await session.post(f"{api}/api/auth/login", json={"email": "admin@vhc.in", "password": "VhcAdmin@2024"})
        data = await r.json()
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "jd_text": "Python developer with Django FastAPI SQL MongoDB experience",
            "match_mode": "quick", "limit": 10, "semantic_search": False,
        }

        results = []
        sem = asyncio.Semaphore(max_concurrent)

        async def request_with_ramp(req_id):
            # Stagger: add small delay based on request ID
            await asyncio.sleep(req_id * 0.05)  # 50ms stagger between requests
            async with sem:
                start = time.time()
                try:
                    async with session.post(
                        f"{api}/api/matching/find-candidates",
                        json=payload, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=25)
                    ) as resp:
                        elapsed = time.time() - start
                        body = await resp.text()
                        return {"id": req_id, "status": resp.status, "time": elapsed,
                                "error": body[:150] if resp.status != 200 else None}
                except asyncio.TimeoutError:
                    return {"id": req_id, "status": 0, "time": time.time() - start, "error": "TIMEOUT"}
                except Exception as e:
                    return {"id": req_id, "status": 0, "time": time.time() - start, "error": str(e)[:150]}

        t0 = time.time()
        tasks = [request_with_ramp(i) for i in range(total_requests)]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - t0

    successes = [r for r in results if r["status"] == 200]
    failures = [r for r in results if r["status"] != 200]
    timeouts = [r for r in results if r.get("error") == "TIMEOUT"]
    rate_limited = [r for r in results if r["status"] == 429]
    server_busy = [r for r in results if r["status"] == 503]
    response_times = [r["time"] for r in successes]
    error_rate = len(failures) / len(results) * 100

    print(f"  Total: {len(results)} | Success: {len(successes)} | Fail: {len(failures)}")
    print(f"  Timeouts: {len(timeouts)} | Rate Limited: {len(rate_limited)} | Server Busy: {len(server_busy)}")
    print(f"  Error Rate: {error_rate:.1f}% | Duration: {total_time:.1f}s")
    if response_times:
        print(f"  Resp Time: min={min(response_times):.2f}s avg={statistics.mean(response_times):.2f}s max={max(response_times):.2f}s")
        print(f"  P50={statistics.median(response_times):.2f}s P95={sorted(response_times)[int(len(response_times)*0.95)]:.2f}s")

    grade = "A+" if error_rate == 0 else "A" if error_rate < 5 else "B" if error_rate < 15 else "F"
    print(f"  GRADE: {grade} (target: <5% error rate)")
    print(f"{'='*60}\n")

    if failures[:3]:
        print("Sample errors:")
        for f in failures[:3]:
            print(f"  #{f['id']}: status={f['status']}, time={f['time']:.2f}s, err={f.get('error','')[:80]}")

    report = {
        "concurrent": max_concurrent, "total": total_requests,
        "successes": len(successes), "failures": len(failures),
        "error_rate": round(error_rate, 2), "grade": grade,
        "timeouts": len(timeouts), "rate_limited": len(rate_limited),
        "server_busy": len(server_busy),
        "response_times": {
            "min": round(min(response_times), 3) if response_times else None,
            "mean": round(statistics.mean(response_times), 3) if response_times else None,
            "max": round(max(response_times), 3) if response_times else None,
            "p50": round(statistics.median(response_times), 3) if response_times else None,
        } if response_times else {},
    }
    with open("/app/test_reports/load_test_v3.json", "w") as f:
        json.dump(report, f, indent=2)
    return error_rate < 5

if __name__ == "__main__":
    c = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 75
    ok = asyncio.run(run_load_test(c, n))
    sys.exit(0 if ok else 1)
