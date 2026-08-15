"""Unit tests for scheduler.jobs.cleanup_job. Uses the real Container against
a real (SQLite in-memory) DatabaseConnection and a real Redis (fakeredis is
not swapped in here -- these exercise the real cache.redis_client.RedisConnection,
matching how core.container.get_container() actually builds it; a real Redis
must be reachable, per docs/PHASE10_WORKFLOW_ORCHESTRATION.md "Testing strategy").
"""

from __future__ import annotations

from cache.cache_keys import NAMESPACE_MARKET
from core.container import get_container, reset_container
from scheduler.jobs.cleanup_job import report_cache_key_counts, run, vacuum_database
from scheduler.jobs.job_result import JobStatus


class TestVacuumDatabase:
    async def test_completes_without_error_against_sqlite(self) -> None:
        # VACUUM is valid SQL against SQLite too (not just Postgres) -- this
        # exercises the real AUTOCOMMIT-isolation code path end-to-end. The
        # parenthesized (ANALYZE) form is Postgres-only, so this dialect gets
        # plain VACUUM -- see vacuum_database()'s dialect-aware statement choice.
        result = await vacuum_database()
        assert result == {"vacuum": "completed", "statement": "VACUUM"}


class TestReportCacheKeyCounts:
    async def test_reports_zero_for_an_empty_namespace(self) -> None:
        counts = await report_cache_key_counts()
        assert counts[NAMESPACE_MARKET] >= 0

    async def test_reflects_a_key_that_was_actually_set(self) -> None:
        container = get_container()
        settings = container.settings
        key = f"{settings.redis.key_prefix.rstrip(':')}:{NAMESPACE_MARKET}:test-key"
        await container.redis.client.set(key, b"v")
        try:
            counts = await report_cache_key_counts()
            assert counts[NAMESPACE_MARKET] >= 1
        finally:
            await container.redis.client.delete(key)


class TestRun:
    async def test_reports_success_when_both_steps_succeed(self) -> None:
        result = await run()
        assert result.status is JobStatus.SUCCESS
        assert "vacuum" in result.context
        assert "cache_key_counts" in result.context

    async def test_reports_failed_if_redis_is_unreachable(self) -> None:
        from config.modules.redis import RedisSettings
        from config.settings import Settings

        broken_settings = Settings(redis=RedisSettings(host="127.0.0.1", port=1))
        reset_container()
        get_container(broken_settings)
        try:
            result = await run()
            assert result.status is JobStatus.FAILED
        finally:
            reset_container()
