"""Unit tests for scheduler.jobs.alert_sweep_job."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from pydantic import SecretStr

from config.modules.database import DatabaseSettings
from config.modules.redis import RedisSettings
from config.settings import Settings
from core.container import get_container, reset_container
from scheduler.jobs.alert_sweep_job import run
from scheduler.jobs.job_result import JobStatus


class TestRun:
    async def test_reports_failed_when_redis_is_unreachable(self) -> None:
        # reset_container() first: the autouse fixture in conftest.py already
        # built a (working) container before this test ran -- get_container()
        # is a lazy singleton that ignores new settings once already
        # constructed, so the singleton must be torn down before rebuilding
        # it with these deliberately-broken settings.
        reset_container()
        broken_settings = Settings(redis=RedisSettings(host="127.0.0.1", port=1))
        get_container(broken_settings)

        result = await run()

        assert result.status is JobStatus.FAILED
        assert "degraded" in (result.detail or "")
        assert "redis" in result.context["degraded_components"]

    async def test_context_lists_which_components_are_degraded(self) -> None:
        reset_container()
        broken_settings = Settings(redis=RedisSettings(host="127.0.0.1", port=1))
        get_container(broken_settings)

        result = await run()

        assert "redis" in result.context["degraded_components"]

    async def test_reports_success_when_everything_is_reachable(self) -> None:
        # Explicit SQLite for the database (Settings() alone defaults to a
        # real Postgres DSN, unreachable in a test environment -- see
        # tests/unit/scheduler/jobs/conftest.py) + the real Redis this test
        # suite runs against (see docs/PHASE10_WORKFLOW_ORCHESTRATION.md
        # "Testing strategy"). Kafka connectivity is mocked rather than
        # requiring a real broker just to exercise this job's trivial
        # healthy-vs-degraded branch -- the degraded-path tests above already
        # exercise the real Redis/DB connectivity checks end-to-end.
        reset_container()
        healthy_settings = Settings(
            database=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:"))
        )
        container = get_container(healthy_settings)
        await container.startup()
        with patch.object(
            container.kafka_producer, "check_connection", AsyncMock(return_value=True)
        ):
            result = await run()

        assert result.status is JobStatus.SUCCESS
        assert result.detail == "all components healthy"
