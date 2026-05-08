# ✅ Experience Extraction Bug - FIXED

**Date**: December 2025  
**Issue**: `experience_years` was capturing as `1` or `2` instead of decimal `2.05` (for 2 years 5 months)  
**Root Cause**: Multiple `int()` conversions destroying the decimal value

---

## 🐛 **Root Cause Analysis**

The LLM prompts were correctly instructed to extract experience as decimals (2y 5m = 2.05), but the values were being converted to integers at **7 different places** in the backend code:

### **Files Modified:**

1. **`/app/backend/services/extension_service.py`** (Lines 652, 817)
   ```python
   # BEFORE:
   "experience_years": int(profile.total_experience_years)  # ❌ Killed 2.05 → 2
   
   # AFTER:
   "experience_years": float(profile.total_experience_years)  # ✅ Preserves 2.05
   ```

2. **`/app/backend/services/naukri_regex_parser.py`** (Line 102)
   ```python
   # BEFORE:
   exp_m = re.search(r'Save\s*(\d+)\s*y\s*[\u20B9]', text)
   if exp_m:
       header['experience_years'] = int(exp_m.group(1))  # ❌ Only captured years
   
   # AFTER:
   exp_m = re.search(r'Save\s*(\d+)\s*y\s*(\d+)?\s*m?[\u20B9]', text)
   if exp_m:
       years = int(exp_m.group(1))
       months = int(exp_m.group(2)) if exp_m.group(2) else 0
       header['experience_years'] = round(years + (months / 100), 2)  # ✅ 2y 5m = 2.05
   ```

3. **`/app/backend/routes/extension.py`** (Lines 1002, 2475)
   ```python
   # BEFORE:
   updates["experience_years"] = int(_exp)  # ❌ Destroyed decimal
   
   # AFTER:
   updates["experience_years"] = round(_exp, 2)  # ✅ Preserves 2.05
   ```

4. **`/app/backend/routes/candidates.py`** (Lines 297, 318, 864)
5. **`/app/backend/routes/cv_upload.py`** (Line 441)

---

## ✅ **The Correct Formula**

### **Years + (Months / 100)**

| Input | Calculation | Output |
|-------|-------------|--------|
| "2y 5m" | 2 + (5/100) | **2.05** |
| "3y 10m" | 3 + (10/100) | **3.10** |
| "12y 11m" | 12 + (11/100) | **12.11** |
| "5 years" | 5 + (0/100) | **5.0** |

### **Month Conversion Table:**
- 1 month = 0.01
- 2 months = 0.02
- 5 months = 0.05
- 10 months = 0.10
- 11 months = 0.11

---

## 🧪 **Test Results**

```bash
$ python3 /app/test_experience_fix.py

✅ Test 1: Float Conversion - PASSED
✅ Test 2: Regex Parser Simulation - PASSED  
✅ Test 3: Full Profile Extraction - PASSED

Extracted: 2.05 (float) ✅
```

---

## 🚀 **Deployment**

**Status**: ✅ **DEPLOYED** (Backend restarted successfully)

```bash
sudo supervisorctl restart backend
# backend: RUNNING
```

---

## 📋 **Next Steps for User**

1. **Capture a NEW candidate** from Naukri with experience like "2y 5m"
2. **Check MongoDB** to verify:
   ```javascript
   db.candidate_bank.find({}, {name: 1, experience_years: 1}).sort({created_at: -1}).limit(3)
   ```
3. **Expected Result**:
   ```json
   { "name": "New Candidate", "experience_years": 2.05 }  ✅
   ```

---

## 📄 **Saved Reports for You**

When you ask for "prompt analysis" or "token report", I'll provide:

1. **`/app/ACTUAL_PROMPT_COMMANDS.md`** — Complete breakdown of all 9 LLM prompts with exact token counts
2. **`/app/TOKEN_ANALYSIS_REPORT.md`** — Executive summary with optimization strategies
3. **`/app/extract_actual_prompts.py`** — Reusable script to re-analyze prompts

---

**Status**: ✅ **BUG FIXED** — Experience decimals now preserved correctly (2y 5m = 2.05)
