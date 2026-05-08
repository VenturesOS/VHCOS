# VHC EC2 Diagnostic Commands

Run these commands on your EC2 server to investigate the May 4-5 downtime incidents.

## Quick Health Check (Run First)
```bash
# Check if site is responding
curl -s https://ventureshrd.com/api/health | python3 -m json.tool

# New incident analysis endpoint (shows connection pool, capture stats)
curl -s https://ventureshrd.com/api/health/incident-analysis | python3 -m json.tool
```

## Step 1: Server Resource Check
```bash
echo "=== SERVER LOAD ===" && uptime
echo ""
echo "=== MEMORY ===" && free -h
echo ""
echo "=== DISK ===" && df -h /
echo ""
echo "=== GUNICORN WORKERS ===" && ps aux | grep gunicorn | grep -v grep | wc -l
```

## Step 2: Check Gunicorn Error Logs
```bash
# Last 100 errors
sudo tail -100 /var/log/gunicorn/error.log | grep -i "error\|timeout\|connection\|memory\|worker"

# Specific MongoDB connection issues
sudo grep -i "serverselectiontimeout\|connection.*timeout\|pymongo.*error\|ServerSelectionTimeoutError" /var/log/gunicorn/error.log | tail -30
```

## Step 3: Check Capture Activity on May 4th
```bash
# Count captures on May 4th
sudo grep "2026-05-04" /var/log/gunicorn/access.log | grep -c "/api/extension/capture"

# Count captures on May 5th
sudo grep "2026-05-05" /var/log/gunicorn/access.log | grep -c "/api/extension/capture"

# Check for 502/503/504 errors on May 4th
sudo grep "2026-05-04" /var/log/nginx/access.log | grep -E " (502|503|504) " | wc -l
```

## Step 4: Check Service Restarts
```bash
# When was Gunicorn last restarted?
sudo journalctl -u gunicorn --since "2026-05-01" | grep -i "start\|stop\|restart\|kill" | tail -20

# System reboots
last reboot | head -5
```

## Step 5: Check MongoDB Connection from EC2
```bash
# Test MongoDB connectivity (replace with your actual connection string)
python3 -c "
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import certifi
import os

async def test():
    try:
        # Load from your .env or config
        mongo_url = os.environ.get('MONGO_URL', '')
        if not mongo_url:
            print('MONGO_URL not set in environment')
            return
        client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000, tlsCAFile=certifi.where())
        await client.admin.command('ping')
        print('✅ MongoDB connection successful')
        info = await client.admin.command('serverStatus')
        print(f'Connections: current={info[\"connections\"][\"current\"]}, available={info[\"connections\"][\"available\"]}')
    except Exception as e:
        print(f'❌ MongoDB error: {e}')

asyncio.run(test())
"
```

## Step 6: Deploy Latest Changes
After investigation, deploy the updated code with MongoDB pool improvements:

```bash
cd /home/ubuntu/vhc-platform
git pull origin main
sudo systemctl restart gunicorn
cd frontend && yarn build && sudo cp -r build/* /var/www/html/
```

## Changes Made in This Update

1. **Increased MongoDB Connection Pool**:
   - maxPoolSize: 20 → 50
   - minPoolSize: 2 → 5
   - Timeouts increased for Atlas Flex tier

2. **New Diagnostic Endpoint**: `/api/health/incident-analysis`
   - Shows real-time system metrics (CPU, memory)
   - MongoDB connection pool stats
   - Recent capture activity (24h)
   - Error patterns

3. **Extension v5.4.1**:
   - Fixed background-tab capture scraping wrong contacts
   - Available at `/api/download/naukri-extension`

## Likely Root Causes of May 4th Incidents

Based on the pattern of multiple 5-27 minute "Connection Timeout" incidents:

1. **MongoDB Atlas Flex Throttling**: The Flex tier has shared/limited resources. Heavy capture load can exhaust connection limits.

2. **Extension Queue Buildup**: When server is down, extensions queue captures locally. When server comes back, all queued captures hit simultaneously = spike.

3. **AWS Bill Due May 1**: If there was any payment processing delay, AWS might have throttled or briefly suspended the instance.

4. **Gunicorn Worker Exhaustion**: Default workers might have been overwhelmed by concurrent AI extraction + DB writes.

## Recommendations

1. **Monitor the new endpoint**: Check `/api/health/incident-analysis` periodically
2. **Consider upgrading MongoDB**: Flex → M10 dedicated ($57/month) for consistent performance
3. **Add UptimeRobot for the health endpoint**: `/api/health` (not just the homepage)
