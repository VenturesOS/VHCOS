# Chrome Extension Fix - Education Capture

## Issue
Extension v5.2.0 has an 8000 character limit that cuts off before the education section.

## Files to Update

### 1. Find the Extension Source Code
Location: Wherever you maintain the extension source (likely `vhc-naukri-extension/`)

### 2. Locate the Capture Logic
Look for these files:
- `background.js` - Main extension logic
- `content.js` - Page scraping logic
- `naukri-scraper.js` or similar

### 3. Find the Character Limit

Search for these patterns in the code:
```javascript
// Look for:
.substring(0, 8000)
.slice(0, 8000)
text.length > 8000
maxLength: 8000
MAX_TEXT_LENGTH = 8000
```

### 4. Apply the Fix

**Option A: Increase Character Limit (Quick Fix)**
```javascript
// BEFORE:
const rawText = fullText.substring(0, 8000);

// AFTER:
const rawText = fullText.substring(0, 20000);  // Increased to 20k
```

**Option B: Specific Education Capture (Better Fix)**

Add this function to capture education separately:

```javascript
function extractEducation() {
    const educationData = [];
    
    // Naukri education section selectors (adjust based on actual DOM)
    const educationSection = document.querySelector('.education-section') 
        || document.querySelector('#education')
        || document.querySelector('[data-section="education"]');
    
    if (educationSection) {
        const entries = educationSection.querySelectorAll('.education-entry, .degree-item');
        
        entries.forEach(entry => {
            const degree = entry.querySelector('.degree')?.textContent?.trim();
            const institution = entry.querySelector('.institution, .college')?.textContent?.trim();
            const year = entry.querySelector('.year, .passing-year')?.textContent?.trim();
            
            if (degree || institution) {
                educationData.push({
                    degree: degree || '',
                    institution: institution || '',
                    year: year || ''
                });
            }
        });
    }
    
    return educationData;
}

// Include in payload:
const payload = {
    raw_text: fullText.substring(0, 20000),  // Increased limit
    education: extractEducation(),  // Separate education field
    // ... other fields
};
```

**Option C: Priority Capture (Best Fix)**

Capture education FIRST before work experience fills the buffer:

```javascript
function capturePriorityFields() {
    const sections = {
        name: '',
        email: '',
        phone: '',
        education: '',  // Capture this early
        experience: '',
        skills: '',
        summary: ''
    };
    
    // 1. Capture structured fields first
    sections.education = document.querySelector('.education-section')?.innerText || '';
    sections.name = document.querySelector('.name, .candidate-name')?.innerText || '';
    sections.email = document.querySelector('.email')?.innerText || '';
    
    // 2. Then capture long-form content
    sections.experience = document.querySelector('.experience-section')?.innerText || '';
    
    // 3. Concatenate in priority order
    const rawText = [
        sections.name,
        sections.email,
        sections.phone,
        sections.education,  // Education comes BEFORE experience
        sections.summary,
        sections.skills,
        sections.experience
    ].filter(Boolean).join('\n\n');
    
    return rawText.substring(0, 20000);
}
```

## 5. Update Extension Version

In `manifest.json`:
```json
{
  "version": "5.2.1",  // Increment version
  "description": "Fixed education capture - increased text limit to 20k chars"
}
```

## 6. Test the Fix

1. **Load the updated extension:**
   - Go to `chrome://extensions/`
   - Click "Load unpacked"
   - Select your extension folder
   - OR click "Reload" if already loaded

2. **Test capture:**
   - Go to Deepak's Naukri profile
   - Click extension to capture
   - Check backend logs:
     ```bash
     tail -f /var/log/gunicorn/*.log | grep "Full-Groq"
     ```

3. **Verify education extraction:**
   - After capture completes (~5-10 seconds)
   - Check VHC profile - Education tab should show data

## 7. Deploy Updated Extension

1. **Build extension:** `npm run build` or `yarn build` (if applicable)
2. **Package:** Zip the extension folder
3. **Distribute:** Share with your team or upload to Chrome Web Store

## Quick Verification Commands

After deploying the updated extension and capturing a profile:

```bash
# Check raw text length
mongo vhc_talent_os --eval 'db.candidate_bank.findOne({name: "Test Candidate"}, {raw_text_for_enrichment: 1}).raw_text_for_enrichment.length'

# Check if education keywords are captured
mongo vhc_talent_os --eval 'db.candidate_bank.findOne({name: "Test Candidate"}, {raw_text_for_enrichment: 1}).raw_text_for_enrichment' | grep -i "education\|degree\|b.tech"
```

## Troubleshooting

**Education still not captured?**
1. Check browser console for errors (`F12` → Console tab)
2. Verify selectors match Naukri's current DOM structure
3. Test on a profile with visible education section
4. Check if education section requires scrolling/expanding

**Need Help?**
Share:
- Extension source code (GitHub repo or zip)
- Browser console errors
- Screenshot of Naukri profile HTML (F12 → Elements tab)

---

**After fixing, ALL future captures will automatically include education!** ✅
