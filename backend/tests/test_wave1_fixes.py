"""Regressions for spec 2026-09-08 fixes.

5.13 — Teams: active_jobs_count derived on read (not stored as static 0),
       using `ACTIVE_JOB_STATUSES` (open, in_progress, active).
5.1  — Jobs: when a candidate reaches `joined` and the job's headcount is
       met, the job's `status` transitions to `filled` so the job leaves
       the active view.
"""
from __future__ import annotations


def test_active_job_statuses_constant_is_authoritative():
    from routes.teams import ACTIVE_JOB_STATUSES
    # user Section 10 decision + backwards compatibility with current data
    assert set(ACTIVE_JOB_STATUSES) == {"open", "in_progress", "active"}


def test_teams_response_model_defaults_active_jobs_count_to_zero():
    from routes.teams import TeamResponse
    t = TeamResponse(
        id="t1", name="Team A", employer_id="e1",
        recruiter_ids=[], company_ids=[],
        created_at="2026-09-08T00:00:00+00:00",
    )
    assert t.active_jobs_count == 0


def test_job_auto_fill_logic_uses_headcount_from_multiple_field_names():
    """The auto-fill code accepts `headcount`, `positions`, or `vacancies`
    as the target-hires field so it works across legacy job docs. This test
    documents the fallback order and locks it in — changing the priority
    should be an explicit product decision."""
    from routes import applications as app_mod
    # import path check — the auto-fill lives inside update_application
    import inspect
    src = inspect.getsource(app_mod)
    # canonical priority: headcount → positions → vacancies → 1
    idx_headcount = src.find('job_doc.get("headcount")')
    idx_positions = src.find('job_doc.get("positions")')
    idx_vacancies = src.find('job_doc.get("vacancies")')
    assert idx_headcount != -1 and idx_positions != -1 and idx_vacancies != -1
    assert idx_headcount < idx_positions < idx_vacancies


def test_job_auto_fill_only_runs_on_joined_stage():
    """Sanity: the auto-fill block is gated on `new_stage == "joined"` — a
    move to `hired` or `offered` must NOT retire the job."""
    from routes import applications as app_mod
    import inspect
    src = inspect.getsource(app_mod.update_application)
    assert 'if new_stage == "joined":' in src


def test_job_auto_fill_skips_already_terminal_statuses():
    """The guard against overwriting `filled` / `archived` / `closed` is
    important because a re-open + rejoin loop would otherwise flap the job
    back to `filled` on every replay."""
    from routes import applications as app_mod
    import inspect
    src = inspect.getsource(app_mod.update_application)
    assert '("filled", "archived", "closed")' in src
