# Test Credentials

## Admin
- Email: `admin@vhc.in`
- Password: `VhcAdmin@2024`

## Recruiter test accounts (May 2026)
- `hr6@vhc.in` / `12345678` — **Diya** (fresh, active)
- `hr12@vhc.in` / `12345678` — **Sachin** (fresh, active)
- `hr14@vhc.in` / `12345678` — **Ronak** (migrated from `hr6@vhc.in`, password unchanged from before migration; all 357 records preserved)

## Notes
- After Feb 2026 SEC-04 fix: deactivated users (`is_active=false`) are
  rejected by `get_current_user` and cannot refresh tokens. Reactivating
  a user requires them to log in fresh.
- Phase 55.4 (May 2026): deactivation now archives the user's email to
  `_deact_<utc-ts>_<original>@<domain>` so the original email becomes
  available for re-use by a brand-new account. See
  `backend/scripts/admin_user_ops.py` for the helper script.
