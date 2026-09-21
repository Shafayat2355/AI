"""Integration test: ``scheduler.jobs.cli.main`` end-to-end against real
infrastructure -- the full chain (CLI arg parsing -> job dispatch -> real
DB/Redis operations -> structured JSON stdout -> process exit code), not just
each piece in isolation (covered by ``tests/unit/scheduler/jobs/``).

Requires a reachable Redis (``docker-compose up redis``, or a local
``redis-server``) -- see ``docs/PHASE10_WORKFLOW_ORCHESTRATION.md`` "Testing
strategy". Uses SQLite for the database, matching this codebase's own Phase
6/7 precedent for fast, Docker-independent tests.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from pydantic import SecretStr

from config.modules.database import DatabaseSettings
from config.settings import Settings
from core.container import get_container, reset_container
from scheduler.jobs.cli import main


@pytest.fixture(autouse=True)
def _sqlite_container() -> Iterator[None]:
    reset_container()
    get_container(
        Settings(database=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")))
    )
    yield
    reset_container()


class TestCleanupJobEndToEnd:
    def test_exits_zero_and_prints_the_expected_json_shape(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = main(["cleanup_job"])

        assert exit_code == 0
        # main() also runs configure_logging(), whose console handler shares
        # stdout with our explicit JSON print -- only the last line is JSON.
        last_line = capsys.readouterr().out.strip().splitlines()[-1]
        payload = json.loads(last_line)
        assert payload["job_name"] == "cleanup"
        assert payload["status"] == "success"
        assert payload["duration_seconds"] >= 0


class TestGracefulNoOpJobEndToEnd:
    def test_exits_zero_for_a_not_yet_implemented_job(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # eod_reconciliation_job's integration point (portfolio.portfolio_manager)
        # is still a scaffold stub. historical_sync_job was used here until
        # Phase 11 implemented datasets.historical.ohlcv_store -- it now needs a
        # real database and is covered by tests/integration/training/ instead.
        exit_code = main(["eod_reconciliation_job"])

        assert exit_code == 0
        # main() also runs configure_logging(), whose console handler shares
        # stdout with our explicit JSON print -- only the last line is JSON.
        last_line = capsys.readouterr().out.strip().splitlines()[-1]
        payload = json.loads(last_line)
        assert payload["status"] == "skipped_not_implemented"


class TestUnreachableInfraEndToEnd:
    def test_alert_sweep_exits_nonzero_when_redis_is_unreachable(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from config.modules.redis import RedisSettings

        reset_container()
        get_container(
            Settings(
                database=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")),
                redis=RedisSettings(host="127.0.0.1", port=1),
            )
        )

        exit_code = main(["alert_sweep_job"])

        assert exit_code == 1
        # main() also runs configure_logging(), whose console handler shares
        # stdout with our explicit JSON print -- only the last line is JSON.
        last_line = capsys.readouterr().out.strip().splitlines()[-1]
        payload = json.loads(last_line)
        assert payload["status"] == "failed"
