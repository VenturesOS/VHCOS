# VHC Talent OS - Naukri Auto Capture Extension

## Overview
This Chrome extension automatically captures candidate profiles from Naukri.com and saves them to your VHC Talent OS candidate bank.

## Features
- ✅ **Auto-capture**: Profiles are captured automatically when you view them on Naukri
- ✅ **Smart Update**: Only updates if Naukri profile is newer than existing data
- ✅ **Duplicate Detection**: Checks by Naukri ID, Email, and Phone
- ✅ **Offline Queue**: Profiles are queued when offline and synced when back online
- ✅ **Complete Data**: Captures all available profile data including work history, education, skills, certifications
- ✅ **Non-intrusive**: Small toast notifications that don't interrupt your workflow

## Data Captured
- Personal: Name, Email, Phone, Photo, DOB, Gender, Marital Status
- Professional: Headline, Summary, Current Company/Designation
- Compensation: Current Salary, Expected Salary, Notice Period
- Experience: Complete work history with descriptions
- Education: All educational qualifications
- Skills: Key skills and detailed skill proficiency
- Additional: Certifications, Projects, Languages
- Preferences: Location, Industry, Functional Area

## Installation (Developer Mode)

### Step 1: Download Extension
Download and extract the `vhc-naukri-extension.zip` file

### Step 2: Open Chrome Extensions
1. Open Chrome browser
2. Go to `chrome://extensions/`
3. Enable **"Developer mode"** (toggle in top right)

### Step 3: Load Extension
1. Click **"Load unpacked"**
2. Select the extracted `browser-extension` folder
3. Extension will appear in your toolbar

### Step 4: Login to VHC
1. Click the VHC extension icon in toolbar
2. Enter your VHC Portal URL (e.g., `https://your-vhc-portal.com`)
3. Enter your VHC email and password
4. Click **"Login to VHC"**

## Usage

### Automatic Capture (Default)
1. Simply browse Naukri candidate profiles as usual
2. When you open a profile page, the extension waits 3 seconds
3. Scrolls the page to load all content
4. Captures and saves the profile automatically
5. Shows a toast notification confirming the action:
   - ✅ "Added to VHC" - New profile created
   - 🔄 "Profile updated" - Existing profile updated with newer data
   - ℹ️ "Already up-to-date" - No changes needed

### Settings
Click the extension icon to access settings:
- **Auto-capture profiles**: Enable/disable automatic capture
- **Show notifications**: Enable/disable toast notifications

### Statistics
The popup shows your capture statistics:
- Captured Today
- Captured This Week
- Total Captured
- Total Updated

## Supported Naukri Pages
- Candidate profile pages
- Resume view pages (ResDex)
- CV preview pages

## Troubleshooting

### Extension not capturing?
1. Check if auto-capture is enabled in settings
2. Verify you're logged in to VHC
3. Ensure the page is a Naukri profile page

### "Session expired" error?
Your VHC login token has expired. Click the extension and login again.

### Profiles not syncing?
1. Check your internet connection
2. Queued profiles will sync automatically when online
3. Check the queue count in extension popup

## Privacy & Security
- Data is sent only to YOUR VHC Talent OS instance
- No data is sent to any third party
- Uses secure HTTPS connections
- Login credentials are stored locally in Chrome

## Technical Requirements
- Chrome/Edge browser (Manifest V3 compatible)
- VHC Talent OS account (Employer/Recruiter role)
- Active internet connection (profiles queue when offline)

## Version History
- **v1.0.0** - Initial release
  - Auto-capture from Naukri profiles
  - Smart duplicate detection
  - Offline queue support
  - Statistics tracking

---

**Powered by VHC Talent OS**
