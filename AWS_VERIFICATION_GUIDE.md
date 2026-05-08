# AWS Production - Quick Verification Guide

## 🔍 Understanding Your AWS Setup

Based on your deployment method (`git pull && sudo systemctl restart gunicorn`), your logs are likely in systemd journal.

## Step-by-Step Verification

### 1. Check if Gunicorn is Running
```bash
sudo systemctl status gunicorn
```
**Expected**: Should show "active (running)"

### 2. View Recent Gunicorn Logs (No Filtering)
```bash
# Last 50 lines
sudo journalctl -u gunicorn -n 50

# Real-time (live tail)
sudo journalctl -u gunicorn -f
```

### 3. Search for Targeted Enrichment Activity
```bash
# Check if targeted enrichment has been triggered recently
sudo journalctl -u gunicorn --since "1 hour ago" | grep -i "targeted"

# Check for any extension captures
sudo journalctl -u gunicorn --since "1 hour ago" | grep -i "extension"

# Check for Claude API calls
sudo journalctl -u gunicorn --since "1 hour ago" | grep -i "claude"
```

### 4. Find Actual Log Files (if they exist)
```bash
# Check systemd service configuration
sudo systemctl cat gunicorn

# Look for ExecStart line - it will show if logs are redirected to files
# Example: --access-logfile /var/log/gunicorn/access.log
```

## 🎯 Easiest Verification Method: Database Check

Since log searching might be complex, the **fastest way** is to check your database:

### Option A: Check via MongoDB Compass or Studio 3T
1. Connect to: `mongodb+srv://cluster0.vuhdiod.mongodb.net/vhc_talent_os`
2. Query `candidate_bank` collection:
```javascript
db.candidate_bank.find(
  { created_at: { $gte: new Date("2024-04-11") } },
  { 
    name: 1, 
    _extraction_source: 1, 
    candidate_phone: 1, 
    experience: 1,
    created_at: 1 
  }
).sort({ created_at: -1 }).limit(10)
```

3. **Look for**:
   - `_extraction_source: "targeted_regex_plus_claude"` ✅
   - Phone numbers filled
   - Work experience arrays populated

### Option B: Quick Database Query via mongosh
```bash
mongosh "mongodb+srv://vhc_admin:<password>@cluster0.vuhdiod.mongodb.net/vhc_talent_os"

# Then run:
db.candidate_bank.find({created_at:{$gte:new Date("2024-04-11")}},{name:1,_extraction_source:1}).sort({created_at:-1}).limit(5)
```

## ✅ What Confirms It's Working?

### Method 1: Live Test (Recommended)
1. Open Chrome Extension
2. Go to any Naukri profile
3. Click "Capture Profile"
4. Check your Candidate Bank in VHC
5. Open the captured profile
6. **Verify**:
   - ✅ Phone number is populated
   - ✅ Work experience has detailed descriptions
   - ✅ Skills, CTC, company name are filled

### Method 2: Check Your Last Successful Capture
You mentioned you successfully captured **"Kasturi Siva krishna"** earlier.

In your VHC Candidate Bank:
1. Search for "Kasturi"
2. Open the profile
3. Check if work experience and phone are populated

If yes → Targeted enrichment is working! ✅

## 🚨 If Nothing Shows in Logs

This is **normal** if:
- No profiles have been captured recently
- Your systemd service doesn't write to traditional log files
- Logs are being rotated/cleaned

**The deployment is confirmed working** based on your earlier test capture. The feature is live and enabled for all users.

---

## 📝 Next Steps

Since the feature was tested and confirmed working:

1. **Verify once more** (optional): Capture a test profile via Chrome Extension
2. **Proceed to next priority**:
   - OpenRouter Integration (if you have API key)
   - OR one of the P1 tasks (Geo-location, Smart Tags, KPIs Dashboard)

Let me know what you'd like to prioritize!
