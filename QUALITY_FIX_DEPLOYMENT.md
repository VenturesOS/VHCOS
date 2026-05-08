# Quality Validation Fix - Deployment Guide

## 🎯 Problem Fixed

**Issue**: Profiles were being saved with education data as work experience (e.g., "GPA: 67%" as job title, "Gita university" as company name).

**Root Cause**: The quality scoring system only checked if fields *existed*, not if they made *sense*. Regex parser would extract garbage, get a high quality score, and the system would skip Claude enrichment entirely.

**Result**: Profiles saved with bad data and `enrichment_status: pending` forever.

---

## ✅ Solution Implemented

### 1. **Work Experience Validation**
New function: `_validate_work_experience()`

**Rejects work experience if:**
- Company name contains: university, college, school, institute, academy, IIT, NIT, IIM
- Designation contains: GPA:, CGPA:, %, grade:, marks:, score:
- Designation is just a number or < 3 characters
- Company or designation is empty/too short

### 2. **Enhanced Quality Scoring**
Updated function: `_score_extraction_quality()`

**Now validates BEFORE scoring:**
- Work experience entries
- Current employer (no education keywords)
- Current designation (no grade patterns)

**Returns 0.0 quality score** (forces Claude enrichment) if validation fails.

---

## 📊 Test Results

```
WORK EXPERIENCE VALIDATION TESTS
✅ PASS - BAD: Education as work exp (GPA as designation)
✅ PASS - BAD: IIT as company  
✅ PASS - GOOD: Real company
✅ PASS - GOOD: Multiple experiences

QUALITY SCORING TESTS
✅ SESHU KUMAR quality score: 0.0% (forces Claude enrichment)
✅ Good profile quality score: 100.0% (can skip Claude)

✅ VALIDATION FIX IS WORKING!
```

---

## 🚀 Deployment to AWS Production

### Step 1: Pull Latest Code

```bash
cd /home/ubuntu/vhc-platform
git pull origin main
```

### Step 2: Restart Backend

```bash
sudo systemctl restart gunicorn
```

### Step 3: Verify

```bash
# Check service status
sudo systemctl status gunicorn

# Monitor logs for validation warnings
sudo journalctl -u gunicorn -f | grep "Quality Check"
```

---

## 🔍 What to Look For

### In Logs (Good Sign)
```
[Quality Check] FAILED: Company 'gita university' looks like education, not employer
[Quality Score] Work experience validation FAILED — forcing Claude enrichment
```

This means the system detected bad data and will trigger Claude to fix it.

### In Candidate Profiles

**Before Fix:**
- Work experience: "GPA: 67%" at "Gita university"
- enrichment_status: `pending` or `dom_regex_complete`
- Phone: missing

**After Fix:**
- Work experience: Proper job titles and companies
- enrichment_status: `enriched`
- Phone: filled
- Multiple work experiences with descriptions

---

## 📈 Expected Impact

### Cost Impact
- Slightly higher Claude usage (good profiles still skip Claude at 50%+ quality)
- Bad profiles now get enriched instead of staying broken
- Overall: Minimal cost increase, huge quality improvement

### Quality Impact
- **Eliminates** education-as-work-experience bug
- **Prevents** profiles from being saved with garbage data
- **Ensures** problematic captures get Claude enrichment

---

## 🧪 Testing After Deployment

### Test 1: Capture a New Profile
1. Use Chrome Extension to capture any Naukri profile
2. Check the profile in Candidate Bank after 30 seconds
3. Verify work experience has real companies and job titles (not universities or GPAs)

### Test 2: Monitor Quality Validation
```bash
# Watch for validation warnings in real-time
sudo journalctl -u gunicorn -f | grep -E "(Quality Check|Quality Score)"
```

You should see validation running and catching bad data.

---

## 🐛 If Issues Occur

### Issue: Service Won't Start
```bash
# Check error logs
sudo journalctl -u gunicorn -n 50

# Verify Python syntax
cd /home/ubuntu/vhc-platform/backend
python3 -m py_compile routes/extension.py
```

### Issue: All Captures Using Claude (High Cost)
Check logs for quality scores:
```bash
sudo journalctl -u gunicorn -n 100 | grep "Quality Score"
```

If quality scores are all 0%, the validation might be too strict. Contact for adjustment.

---

## 📝 Next Steps

1. **Deploy to AWS production** using steps above
2. **Monitor first 10-20 captures** to verify fix is working
3. **Report any profiles** that still have bad work experience
4. **Optionally**: Run bulk re-enrichment on existing bad profiles (separate task)

---

## ✅ Success Criteria

- ✅ No more profiles with "GPA:", "%" in designation
- ✅ No more profiles with "university", "college" as company name
- ✅ Work experience contains actual job titles and companies
- ✅ Phone numbers populated (from Claude targeted enrichment)
- ✅ enrichment_status: `enriched` instead of `pending`

---

**This is a systematic fix that prevents the issue from happening again for ALL future captures.**
