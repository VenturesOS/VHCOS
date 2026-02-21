# Cloudflare Zero Trust Access — Setup Guide

## Overview
This guide explains how to configure Cloudflare Zero Trust Access to protect admin routes in the VHC Talent OS application.

## What is Protected
- `/admin/*` — All admin dashboard pages (frontend)
- `/api/admin/*` — All admin API endpoints (backend)

## Prerequisites
1. A Cloudflare account with Zero Trust plan
2. A domain configured in Cloudflare (e.g., `ventureshrd.com`)
3. Admin access to the Cloudflare Zero Trust dashboard

## Step-by-Step Configuration

### 1. Create a Zero Trust Application
1. Go to **Cloudflare Dashboard** → **Zero Trust** → **Access** → **Applications**
2. Click **Add an Application** → Select **Self-hosted**
3. Configure:
   - **Application name:** `VHC Admin Dashboard`
   - **Session Duration:** `24 hours` (recommended)
   - **Application domain:** `ventureshrd.com`
   - **Path:** `/admin` (this protects all `/admin/*` routes)
4. Click **Next**

### 2. Add Access Policies
1. **Policy name:** `Admin Team Access`
2. **Action:** Allow
3. **Include rules** (choose one or more):
   - **Emails:** Add admin email addresses (e.g., `admin@vhc.in`)
   - **Email domain:** `vhc.in` (allows all company emails)
   - **Identity Provider Group:** Select your IdP group
4. Optionally add **Require** rules:
   - **Country:** Restrict to specific countries
   - **MFA:** Require multi-factor authentication

### 3. Create an API Application (for `/api/admin/*`)
1. **Add another Application** → **Self-hosted**
2. Configure:
   - **Application name:** `VHC Admin API`
   - **Application domain:** `ventureshrd.com`
   - **Path:** `/api/admin`
3. Apply the same access policies as above

### 4. Get the Application AUD Tag
1. In the application settings, find the **Application Audience (AUD) Tag**
2. Copy this value — you'll need it for the backend configuration

### 5. Configure Backend Environment Variables
Add these to your `backend/.env`:

```env
CF_ACCESS_TEAM_DOMAIN=your-team-name
CF_ACCESS_AUD=your-application-aud-tag
```

- `CF_ACCESS_TEAM_DOMAIN`: Your Zero Trust team name (found in Zero Trust dashboard URL)
- `CF_ACCESS_AUD`: The AUD tag from step 4

### 6. Verify Configuration
Once configured, the backend middleware will:
1. Check for the `Cf-Access-Jwt-Assertion` header on admin routes
2. Verify the JWT against Cloudflare's public certificates
3. Block access if the token is missing or invalid
4. Log all blocked attempts as security events

## How It Works
1. User navigates to `/admin/*`
2. Cloudflare Access intercepts the request
3. User authenticates via Cloudflare's login page
4. Cloudflare issues a JWT in the `Cf-Access-Jwt-Assertion` header
5. Backend middleware validates this JWT
6. If valid, the request proceeds to the application's own JWT auth

## Security Events
All Zero Trust-related events are logged to the `security_events` collection:
- `zero_trust_missing_token` — Request without CF Access header (severity: HIGH)
- `zero_trust_invalid_token` — Invalid CF Access JWT (severity: CRITICAL)

These events appear in the System Health dashboard under the Security Events panel.

## Troubleshooting
- **403 "Access denied"**: Check that `CF_ACCESS_TEAM_DOMAIN` and `CF_ACCESS_AUD` are correct
- **Certificate fetch fails**: Ensure the backend can reach `cloudflareaccess.com`
- **Token validation fails**: Verify the AUD tag matches the application
- **Users can't access**: Check the Access Policy includes the correct emails/groups

## Disabling Zero Trust
To disable, simply leave the env variables empty:
```env
CF_ACCESS_TEAM_DOMAIN=
CF_ACCESS_AUD=
```
The middleware will pass through all requests when not configured.
