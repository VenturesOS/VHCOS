# Identity resolution: Emergent handoff

This branch adds extension identity suggestions, immutable capture observations,
and an administrator review screen at `/admin/identity-review`.

## Downloadable test extension

Build the separate unpacked test package from the repository root:

```bash
python backend/scripts/build_test_extension.py --out /path/to/test-artifacts
```

Optionally add `--backend-url https://your-preview.example` to prefill a custom
preview origin. Otherwise enter an Emergent preview URL in the popup. The output
is `VHC-Identity-Test-7.0.0.1.zip`; extract it and use Chrome's Load unpacked
with the folder containing `manifest.json`. Use a separate browser profile or
disable the normal VHC extension to avoid duplicate page injections.

The popup links to a local performance report with matching median/P95 times,
submission/poll timing, outcome counts, and JSON export. Manual accuracy totals
can be included in the export. Matching excludes DOM extraction/rendering;
capture timing excludes earlier AI extraction. Metrics retain the last 300 calls
and do not contain candidate details or credentials. See the bundled
`START-HERE.txt` for the complete checklist.

This build keeps the production source files untouched, removes the update URL,
uses a TEST name, defaults to manual capture and blocks known production portal
API addresses. Emergent preview domains and localhost are allowed; custom preview
origins must be explicitly supplied to the builder. Redirects fail in the test
wrapper instead of forwarding requests to another origin. The test extension
still requires this branch's backend in Emergent and an isolated test database.

## Behavior to expect

- Profile URLs are navigation metadata; they are not identity references.
- Field codes support retrieval and ranking. Evidence points are not probabilities.
- Capturing saves an observation with `action=pending_review`, an observation ID,
  and no candidate ID. It does not automatically insert or overwrite a person.
- Admin review can link an existing person, explicitly create one, defer, or
  unlink a previous decision. Review requires a reason and current revision.
- Linked historical observations help retrieve a permanent person after changes
  to their saved name, employer, role or location.
- A repeated capture operation reuses its frozen payload and original observation.
- Automatic identity confirmation remains disabled pending independent evaluation.
- CV file uploads, shortlisting and mandate evaluation are not automatically
  executed by this observation/review workflow. Review does not overwrite existing
  candidate fields. These are material changes from the old capture workflow.

## Configure the Emergent test environment

1. Import or sync this branch in Emergent and use its normal backend/frontend
   setup. Build the frontend with `yarn build` in `frontend/`.
2. Use an isolated test database. Check `backend/mongo_production_override.py`:
   an accepted override takes precedence over `MONGO_URL` and `DB_NAME`.
   Do not copy a production override into the test environment.
3. Set `EXTENSION_CHECK_EXISTING_ALLOWLIST` in the backend environment to the
   comma-separated login emails of testers. Restart the backend after changing it.
   An empty value disables badge matching. This variable does not gate the new
   observation capture behavior, which applies to all users of this backend.
4. Use an administrator account for the review screen. Point the test extension
   to the test backend base URL without appending `/api`.
5. Test the canonical `browser-extension/` folder, not the legacy `extension/`
   folder or backup folders. No extension release/version bump is included.

## Prepare test database indexes

From the repository root, with the backend Python dependencies installed, set
`STAGING_MONGO_URI` and `STAGING_DB_NAME` in the test shell, then preview:

```bash
python backend/scripts/backfill_identity_codes.py \
  --uri "$STAGING_MONGO_URI" --database "$STAGING_DB_NAME" --limit 1000
```

Dry-run is the default. Inspect counts before applying the complete migration:

```bash
python backend/scripts/backfill_identity_codes.py \
  --uri "$STAGING_MONGO_URI" --database "$STAGING_DB_NAME" \
  --apply --refresh-frequencies
```

The apply path creates matching/review indexes and candidate code signatures.
Do not publish connection strings in test reports. No database migration has
been performed as part of saving this branch.

## Offline regression commands

Run from the repository root:

```bash
python -m pytest backend/tests/test_identity_observations.py backend/tests/test_identity_capture.py backend/tests/test_identity_lookup.py backend/tests/test_identity_resolution.py backend/tests/test_identity_persistence_offline.py backend/tests/test_capture_jobs.py backend/tests/test_identity_audit.py backend/tests/test_extension_service_name_lower.py backend/tests/test_extension_preserve_contact.py -q
node --test browser-extension/tests/identity-resolution.test.cjs browser-extension/tests/identity-queue.test.cjs frontend/tests/identity-review.test.cjs
python backend/scripts/evaluate_identity_resolution.py --input backend/tests/fixtures/identity_resolution_cases.json
```

The evaluator uses synthetic examples; its release gate is expected to remain
closed because there are no independently labelled real evaluation cases.
Passing regression tests does not establish 99% production accuracy.

## Manual acceptance checks

1. Check `/api/health`: body status must be `healthy`, and `import_failures` must
   be zero. HTTP 200 alone is not sufficient.
2. Compare two same-name/same-company people with different cities. Inspect both
   suggestions and their evidence. Repeat with identical visible fields: the
   system should show uncertainty instead of confirmed identity.
3. Capture a profile. Expect `Awaiting review`; verify no candidate row was
   automatically created and existing fields were not changed.
4. Open Identity Review as admin, compare context, enter a reason and link the
   observation. Verify the original snapshot and audit history remain available.
5. Unlink/defer the observation. Verify the person remains in the database.
6. Explicitly create a new person for a different observation. Retry a stale
   review request: it must conflict instead of creating another person.
7. Retry the same capture operation after a lost response: expect the same
   observation/job. Reusing that operation with different data must conflict.
8. Review a historical observation, then test retrieval after a name/job/city
   change. Verify that historical and current context are shown separately.
9. Verify recruiters cannot access admin review APIs, and database outages are
   shown as unavailable/incomplete rather than absence from the database.
10. Validate actual Naukri card extraction and the rendered review UI in Emergent.
    The offline tests use simulated storage and DOM, not a live browser/database.

This branch is for Emergent testing. Saving it to GitHub does not deploy it or
publish an extension package. Coordinate backend, frontend and extension updates
before production use; old clients do not fully support observation responses.
