# VHC Talent OS — Test Credentials

> Keep this file in sync whenever an account is created or a password changes.

| Role | Email | Password | Notes |
|------|-------|----------|-------|
| Admin | admin@vhc.in | VhcAdmin@2024 | Full access |
| Recruiter | hr6@vhc.in | 12345678 | Pipeline / candidate bank |
| Accounts | accounts@vhc.in | **changed by the user on 2026-09-18** | Bills & Invoices module (`/accounts/bills`). The seeded `VhcAccounts@2026` no longer works — ask the user, or re-seed with `ACCOUNTS_USER_PASSWORD=... python3 -m scripts.reset_billing_module --keep-data` (`--keep-data` leaves billing data untouched) |

## Temporary QA logins (2026-09-20) — delete when finished
| Role | Email | Password | Notes |
|------|-------|----------|-------|
| Accounts | qa_accounts_tmp@vhc.in | QaRevenue@2026 | Throwaway. Proves Accounts sees every number |
| Employer | qa_employer_tmp@vhc.in | QaRevenue@2026 | Throwaway. Co-manager of **Faridabad team** only — proves branch scoping |

Created by `python3 -m scripts.qa_role_users create`; remove with
`python3 -m scripts.qa_role_users remove` (also cleans the Faridabad co-manager list).

## Billing / invoice mail identity (2026-09-17)
- Invoices are sent **from** `VHC Accounts <accounts@ventureshrd.com>` (Resend-verified domain),
  **reply-to** `accounts@vhc.in`, and `accounts@vhc.in` is **always BCC'd**.
- `vhc.in` is NOT verified in Resend (403 "domain is not verified"), so sending directly from
  `accounts@vhc.in` fails. Once the domain is added at https://resend.com/domains, switch
  `BILLING_SENDER_EMAIL=accounts@vhc.in` in `backend/.env` and restart the backend.

## Auth endpoints
- `POST /api/auth/login` → `{ access_token, user }`
- `GET /api/auth/me`
- `POST /api/auth/reset-password`
