"""Integration test: Alembic migrations actually run end-to-end.

Invokes the real ``alembic`` CLI as a subprocess (not just imports ``env.py`` and
calls its functions directly) against a temp SQLite file -- this is the only way
to genuinely prove ``alembic.ini``, ``database/migrations/env.py``, and the
initial revision compose correctly, since Alembic's ``Config``/``command``
machinery reads ``alembic.ini`` from disk and resolves ``script_location``
relative to the repo root.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "ENVIRONMENT": "dev",
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "alembic_integration_test.db"


class TestAlembicUpgrade:
    def test_upgrade_head_succeeds_and_creates_the_version_table(self, db_path: Path) -> None:
        result = _run_alembic("upgrade", "head", db_path=db_path)
        assert result.returncode == 0, result.stderr
        assert db_path.exists()

    def test_current_reports_a_head_revision_after_upgrading(self, db_path: Path) -> None:
        """``current`` reports whichever revision is head, which changes every
        time a phase adds a migration -- so this asserts the invariant (an
        upgrade leaves the database at a revision marked ``head``) rather than
        pinning the specific id, which would need editing each phase."""
        _run_alembic("upgrade", "head", db_path=db_path)
        result = _run_alembic("current", db_path=db_path)
        assert result.returncode == 0, result.stderr
        assert "(head)" in result.stdout

    def test_the_initial_baseline_revision_is_in_the_applied_history(
        self, db_path: Path
    ) -> None:
        """The Phase 7 baseline must remain the root of the chain -- later
        phases extend it, never replace it."""
        _run_alembic("upgrade", "head", db_path=db_path)
        result = _run_alembic("history", db_path=db_path)
        assert result.returncode == 0, result.stderr
        assert "130f3304b3d4" in result.stdout

    def test_upgrade_is_idempotent(self, db_path: Path) -> None:
        first = _run_alembic("upgrade", "head", db_path=db_path)
        second = _run_alembic("upgrade", "head", db_path=db_path)
        assert first.returncode == 0
        assert second.returncode == 0


class TestAlembicDowngrade:
    def test_downgrade_base_removes_the_baseline(self, db_path: Path) -> None:
        _run_alembic("upgrade", "head", db_path=db_path)
        result = _run_alembic("downgrade", "base", db_path=db_path)
        assert result.returncode == 0, result.stderr

        current = _run_alembic("current", db_path=db_path)
        assert "130f3304b3d4" not in current.stdout


class TestAlembicHistory:
    def test_history_lists_the_initial_baseline(self, db_path: Path) -> None:
        result = _run_alembic("history", db_path=db_path)
        assert result.returncode == 0, result.stderr
        assert "130f3304b3d4" in result.stdout
        assert "initial baseline" in result.stdout
