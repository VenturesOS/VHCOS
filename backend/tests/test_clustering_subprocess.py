"""
Regression: /api/clustering/run now spawns an isolated subprocess instead
of running numpy/scikit work inside the Gunicorn worker.

The actual subprocess is patched to a no-op so the test stays fast and
doesn't mutate the cluster DB.
"""
from unittest.mock import patch, MagicMock

from routes.clustering import _run_clustering_blocking


def test_run_clustering_blocking_uses_subprocess():
    """The clustering job must run in a child process (memory isolation),
    not inside the Gunicorn worker's own Python heap."""
    fake_completed = MagicMock()
    fake_completed.returncode = 0
    fake_completed.stdout = "{'status': 'ok', 'n': 1, 'k': 25}"
    fake_completed.stderr = ""

    with patch("routes.clustering.subprocess.run", return_value=fake_completed) as mock_run:
        _run_clustering_blocking(k=25, pca_dim=32)

        # 1. subprocess.run was called exactly once
        assert mock_run.call_count == 1
        # 2. The command shells out to the same Python interpreter
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0].endswith("python") or "python" in called_cmd[0]
        # 3. The clustering script is invoked via its module path
        assert "-m" in called_cmd
        assert "scripts.cluster_candidates" in called_cmd
        # 4. The k + pca_dim params are passed through
        assert "--k" in called_cmd and "25" in called_cmd
        assert "--pca-dim" in called_cmd and "32" in called_cmd
        # 5. A timeout is set (we don't want a runaway child)
        assert mock_run.call_args.kwargs.get("timeout", 0) > 0


def test_run_clustering_blocking_handles_failed_subprocess():
    """If the subprocess exits non-zero, we must log + return gracefully
    (don't propagate — BackgroundTasks would swallow the exception anyway)."""
    fake_failed = MagicMock()
    fake_failed.returncode = 1
    fake_failed.stdout = ""
    fake_failed.stderr = "boom"

    with patch("routes.clustering.subprocess.run", return_value=fake_failed):
        # Must not raise
        _run_clustering_blocking(k=25, pca_dim=32)


def test_run_clustering_blocking_handles_timeout():
    """A runaway clustering child should be killed and the parent should
    move on gracefully (no exception propagating to BackgroundTasks)."""
    import subprocess as _sp
    with patch("routes.clustering.subprocess.run",
               side_effect=_sp.TimeoutExpired(cmd="x", timeout=1)):
        # Must not raise
        _run_clustering_blocking(k=25, pca_dim=32)
