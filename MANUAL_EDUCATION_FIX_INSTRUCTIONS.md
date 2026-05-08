# Manual Education Fix - Instructions

## Problem
Education field showing "Not Available" even after code deployment.

## Quick Fix (Run on AWS Server)

### Step 1: Pull Latest Code
```bash
cd ~/vhc-platform
git pull origin main
```

### Step 2: Copy Fix Script
```bash
# Copy the fix script from the repo to your server
cp fix_education_manual.py ~/
chmod +x ~/fix_education_manual.py
```

### Step 3: Run Diagnostic Script
```bash
cd ~/vhc-platform
python3 fix_education_manual.py
```

## What the Script Does

1. ✅ Connects to your MongoDB database
2. ✅ Finds Deepak Diptiman Nayak's profile
3. ✅ Checks current education status
4. ✅ Runs Groq extraction on the stored raw text
5. ✅ Shows what Groq extracted (for debugging)
6. ✅ Saves education to database if extracted
7. ✅ Verifies the update worked

## Expected Output

If successful, you'll see:
```
✅ Groq extraction successful!
✅ Education extracted: 1 entries
✅ Database updated with education
✅ VERIFIED: Education now has 1 entries
```

## If Script Shows "No education extracted"

This means the raw text doesn't contain education information. Solutions:

### Option A: Re-capture from Naukri Extension
1. Delete the old Deepak profile in VHC
2. Go to his Naukri profile: https://www.naukri.com/...
3. Capture again using Chrome extension
4. Wait 5-10 seconds for background enrichment
5. Refresh and check Education tab

### Option B: Manually Add Education
If the Naukri profile doesn't have education, you can add it manually in VHC:
1. Open Deepak's profile
2. Click "Edit" button
3. Go to Education tab
4. Add: B.Tech / B.E., Orissa Engineering College, BPUT, Odisha, 2004

## Troubleshooting

### "Profile not found"
- The profile might have a different name
- Try searching in VHC candidate bank

### "No raw_text_for_enrichment found"
- The profile was captured before we added raw text storage
- Solution: Re-capture from Naukri extension

### "Groq extraction failed"
- Check Groq API key in backend/.env
- Run: `grep GROQ_API_KEY ~/vhc-platform/backend/.env`

### Database update fails
- Check MongoDB connection string
- Ensure you have write permissions

## After Running Script

1. **Restart Gunicorn** (optional, but recommended):
   ```bash
   sudo systemctl restart gunicorn
   ```

2. **Check in VHC UI**:
   - Open Deepak's profile
   - Click "Education" tab
   - Should now show "B.Tech / B.E." from "Orissa Engineering College"

3. **If still not showing**:
   - Clear browser cache (Ctrl+Shift+R)
   - Or try in incognito mode

## Next Steps

After this manual fix works, all future captures will automatically extract education correctly because we've fixed:
1. ✅ Groq prompt (uses `year_of_passing` instead of `year`)
2. ✅ Backend save logic (saves education from Groq)
3. ✅ CTC conversion (lakhs → rupees)
4. ✅ Notice period extraction (text + days)
5. ✅ Summary generation (2-3 sentences)

---

**Need Help?** Share the full output of the diagnostic script.
