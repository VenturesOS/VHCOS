# Analytics & Fix Spec — Locked Decisions (2026-09-08)

Answers from user for Section 10 Open Decisions of the Emergent Fix &
Analytics Redesign Specification. These are the authoritative source of
truth for the analytics rebuild.

## 1. Daily Digest event→points source
Mongo collection. Confirm actual collection name by grepping the codebase
before building the analytics data layer (candidates: `daily_digest_points`,
`kpi_events`, `daily_digest_config`, or hard-coded map in a service file).

## 2. Interview KPIs — two separate metrics
- **Interview Scheduled** = candidate stage `shortlisted` (interview
  scheduled, may not have attended yet).
- **Interview Completed** = candidate stage `interviewed` (candidate
  actually attended and interview is complete).
Both count separately in the KPI Summary and both feed conversion
calculations independently.

## 3. Active Job = statuses `open` + `in_progress` only
Any job in status `closed`, `filled`, `archived`, `on_hold`, `paused`, or
any other non-`open`/`in_progress` state is **not** an Active Job.
Teams cards, dashboard counts, and any "active" filter must apply this
definition centrally.

## 4. Candidate pipeline stages (canonical order)
User confirmed the full stage enum:
`Sourced → Submitted → Shortlisted → Interviewed → Offered → Hired → Joined`
plus terminal `On Hold` and `Rejected`.

**Active Pipeline** (for KPI Summary snapshot count) = candidates in
stages `Sourced, Submitted, Shortlisted, Interviewed, Offered`. Excludes
`Hired`, `Joined`, `On Hold`, `Rejected` (Hired/Joined are terminal
success; On Hold/Rejected are terminal non-active).

## 5. Annual leaderboard window
Calendar year — **Jan 1 → Dec 31**. Cumulative points reset every 1 Jan.

## 6. Targets
**Quarterly** targets exist per employee. Target-management collection
still TBD; propose `employee_targets` with `{employee_id, year, quarter,
kpi, target_value, updated_by, updated_at}`. Admin UI to edit later.

## 7. Composite Performance Score weighting
Admin-configurable weights stored in a settings collection (proposed
`performance_settings` with `{key: 'composite_weights', activity_pct,
conversion_pct, outcome_pct, updated_by, updated_at}`). Ship MVP with
default weights Activity 40 / Conversion 30 / Outcome 30 and expose an
admin editor later.

## Notes
- Where the spec conflicts with these decisions, these decisions win.
- Any additional questions surfaced during implementation must be
  brought back to the user, not guessed.
