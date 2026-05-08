# AWS Deployment Commands - Quick Reference

## 🚀 Deploy to Production (AWS)

### Step 1: SSH into AWS Server
```bash
ssh ubuntu@your-aws-ip
# OR use your configured SSH alias
ssh vhc-aws
```

### Step 2: Navigate to Project Directory
```bash
cd ~/vhc-talent-os
# OR wherever your project is located
```

### Step 3: Pull Latest Changes
```bash
git pull origin main
```

### Step 4: (RECOMMENDED) Clear Legacy LLM Cache
This prevents old Claude cache from interfering with new Groq extractions.

```bash
cd backend

# Dry-run first (safe, no changes)
python3 -m utils.clear_llm_cache --dry-run

# If satisfied with dry-run output, run actual cleanup
python3 -m utils.clear_llm_cache
# Type 'DELETE' when prompted to confirm
```

**Expected Output:**
```
============================================================
LLM Cache Cleanup Utility
============================================================
Database: vhc_talent_os
Collection: llm_enrichment_cache
Current cache entries: 1247
Mode: LIVE (cache will be cleared)
============================================================

⚠️  WARNING: This will permanently delete all 1247 cache entries!
Type 'DELETE' to confirm: DELETE

🔄 Deleting cache entries...
✅ Successfully deleted 1247 cache entries
✅ Cache cleared successfully. All entries removed.
```

### Step 5: Restart Gunicorn (Backend)
```bash
cd ~/vhc-talent-os
sudo systemctl restart gunicorn
sudo systemctl status gunicorn
```

**Expected Status:**
```
● gunicorn.service - Gunicorn instance to serve VHC Talent OS
   Loaded: loaded (/etc/systemd/system/gunicorn.service; enabled)
   Active: active (running) since Thu 2024-12-XX XX:XX:XX UTC
```

### Step 6: Verify Deployment

#### Check Backend Logs (Real-time)
```bash
sudo tail -f /var/log/gunicorn/error.log
```

Look for:
- ✅ `INFO:     Started server process`
- ✅ `[CRITICAL INIT] MongoDB OK`
- ✅ NO error messages

#### Check Groq Configuration
```bash
grep "USE_GROQ_ENRICHMENT" ~/vhc-talent-os/backend/.env
grep "GROQ_API_KEY" ~/vhc-talent-os/backend/.env | head -1
```

Should output:
```
USE_GROQ_ENRICHMENT="true"
GROQ_API_KEY="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"
```

---

## 🧪 Testing After Deployment

### Test 1: Capture with Admin Account
1. Open Chrome Extension
2. Login as `admin@vhc.in` / `VhcAdmin@2024`
3. Navigate to any Naukri profile
4. Click "Capture Profile" in extension
5. Check AWS backend logs:
```bash
sudo tail -f /var/log/gunicorn/error.log | grep -E "GROQ|Groq|BG-Targeted"
```

**Expected Log Output:**
```
INFO: [BG-Targeted] Using GROQ (Llama 3.3 70B) for extraction...
INFO: [Groq] Extracted: phone=found, work_exp=3 entries
INFO: [BG-Targeted] ✅ Enrichment complete | Token usage: ~3000 = 65% savings
```

### Test 2: Capture with Non-Admin Account
1. Logout from extension
2. Login as `maneet@vhc.in` / `12345678`
3. Capture the **same** Naukri profile
4. Check logs again (should see identical Groq usage)

### Test 3: Compare Results
1. Login to VHC Talent OS web app
2. Navigate to **Candidates** section
3. Search for the captured profile
4. Verify:
   - Work experience is extracted correctly (no education data in work_experience)
   - Phone number is captured (if visible on Naukri)
   - Skills, CTC, location are populated
   - **NO difference** between admin and non-admin captures

---

## 🔧 Troubleshooting

### Backend Won't Start
```bash
# Check logs for errors
sudo tail -n 100 /var/log/gunicorn/error.log

# Check service status
sudo systemctl status gunicorn

# Restart service
sudo systemctl restart gunicorn
```

### Still Seeing Claude in Logs (Not Groq)
```bash
# Verify Groq flag
grep "USE_GROQ_ENRICHMENT" ~/vhc-talent-os/backend/.env

# If it shows "false" or is missing, fix it:
cd ~/vhc-talent-os/backend
echo 'USE_GROQ_ENRICHMENT="true"' >> .env
sudo systemctl restart gunicorn
```

### Cache Cleanup Fails
```bash
# Check Python can access MongoDB
cd ~/vhc-talent-os/backend
python3 -c "from config import mongodb_uri, db_name; print(f'Connected: {db_name}')"

# Try manual cache clear (MongoDB shell)
mongo "your-mongodb-uri"
use vhc_talent_os
db.llm_enrichment_cache.deleteMany({})
```

### Extension Shows "Server Error"
```bash
# Check if backend is actually running
curl http://localhost:8001/health
# Should return: {"status": "healthy"}

# Check Cloudflare relay is working
curl https://your-app-url.com/api/health
```

---

## 📊 Monitoring Groq Cost Savings

### Check Daily Token Usage
```bash
# Login to Groq Console
# Navigate to: https://console.groq.com/usage
# Check token consumption trends
```

**Expected Reduction:**
- **Before**: ~11M tokens/day (Claude)
- **After**: ~3M tokens/day (Groq targeted enrichment)
- **Savings**: 73% token reduction

**Cost Comparison:**
- **Claude**: $5,250/month
- **Groq**: $720/month
- **Total Savings**: $4,530/month (86%)

---

## 📝 Rollback (If Needed)

If deployment causes issues, rollback to previous stable version:

```bash
cd ~/vhc-talent-os

# Find the last stable commit
git log --oneline -10

# Rollback to a specific commit (example)
git reset --hard <commit-hash>

# Restart backend
sudo systemctl restart gunicorn

# Verify status
sudo systemctl status gunicorn
```

**Note**: Contact dev team before rollback to debug the actual issue.

---

## ✅ Deployment Checklist

- [ ] SSH into AWS server
- [ ] Pull latest changes (`git pull origin main`)
- [ ] Clear LLM cache (`python3 -m utils.clear_llm_cache`)
- [ ] Restart Gunicorn (`sudo systemctl restart gunicorn`)
- [ ] Verify Groq flag is `true` in `.env`
- [ ] Check backend logs for errors
- [ ] Test capture with admin account
- [ ] Test capture with non-admin account
- [ ] Compare results (should be identical)
- [ ] Monitor Groq token usage in console

---

**Deployment Date**: ___________  
**Deployed By**: ___________  
**Status**: ⬜ Success | ⬜ Issues Found | ⬜ Rolled Back

---

**End of AWS Deployment Guide**
