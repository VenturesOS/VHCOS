# Test Credentials

## Admin
- Email: `admin@vhc.in`
- Password: `VhcAdmin@2024`

## Notes
- After Feb 2026 SEC-04 fix: deactivated users (`is_active=false`) are
  rejected by `get_current_user` and cannot refresh tokens. Reactivating
  a user requires them to log in fresh.
