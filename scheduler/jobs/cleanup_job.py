"""Cleanup job: routine housekeeping against the platform's own Postgres and
Redis -- a Postgres ``VACUUM (ANALYZE)`` (reclaims space from dead rows /
refreshes the query planner's statistics; a plain ``VACUUM`` against any other
dialect, e.g. this repo's own SQLite-backed dev/test setup) plus a Redis
key-count sanity log per namespace.

Deliberately does *not* attempt to purge soft-deleted domain rows past a
retention window -- that requires knowing which concrete mapped models exist
and which retention policy applies to each, and no concrete trading-domain
model (an ``Order``, a ``Position``) exists yet as of Phase 10 (see
``database/repositories/order_repository.py``, still a Phase 2 stub). Once a
real model using ``database.mixins.SoftDeleteMixin`` exists, extending this
job to also sweep it is a natural, additive next step -- not implemented here
to avoid inventing a retention policy for a table that does not exist.
"""

from __future__ import annotations

from sqlalchemy import text

from cache.cache_keys import (
    NAMESPACE_LOCK,
    NAMESPACE_MARKET,
    NAMESPACE_PREDICTION,
    NAMESPACE_RATE_LIMIT,
    NAMESPACE_SESSION,
)
from config.settings import get_settings
from core.container import get_container
from scheduler.jobs.job_result import JobResult, JobStatus, now_utc
from shared.logging.logger import get_logger

_logger = get_logger("scheduler.jobs.cleanup")

_NAMESPACES_TO_REPORT = (
    NAMESPACE_PREDICTION,
    NAMESPACE_MARKET,
    NAMESPACE_SESSION,
    NAMESPACE_RATE_LIMIT,
    NAMESPACE_LOCK,
)


async def vacuum_database() -> dict[str, str]:
    """Run ``VACUUM`` against the whole database.

    ``VACUUM`` cannot run inside a transaction block, so this opens its own
    connection with ``AUTOCOMMIT`` isolation rather than using the normal
    request-scoped session pattern the rest of the app uses.

    Dialect-aware: Postgres accepts (and this uses, for the freshness benefit
    to the query planner) the ``VACUUM (ANALYZE)`` form; SQLite's ``VACUUM``
    does not accept that parenthesized-options syntax at all and raises a
    syntax error on it -- confirmed while building this phase's test suite,
    which runs against SQLite per this codebase's own established test
    convention (Phase 6/7). Any other dialect falls back to plain ``VACUUM``,
    the one form the SQL standard actually guarantees.
    """
    container = get_container()
    engine = container.db.engine
    vacuum_statement = "VACUUM (ANALYZE)" if engine.dialect.name == "postgresql" else "VACUUM"
    async with engine.connect() as connection:
        autocommit_connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
        await autocommit_connection.execute(text(vacuum_statement))
    return {"vacuum": "completed", "statement": vacuum_statement}


async def report_cache_key_counts() -> dict[str, int]:
    """Log (and return) how many keys currently exist per namespace, via
    ``SCAN`` (never ``KEYS``, which blocks the whole Redis instance on a large
    keyspace) -- purely observational, does not delete anything itself."""
    container = get_container()
    client = container.redis.client
    settings = get_settings()
    counts: dict[str, int] = {}
    for namespace in _NAMESPACES_TO_REPORT:
        prefix = f"{settings.redis.key_prefix.rstrip(':')}:{namespace}:*"
        count = 0
        async for _ in client.scan_iter(match=prefix, count=500):
            count += 1
        counts[namespace] = count
    _logger.info("cache_key_counts_reported", extra={"channel": "application", **counts})
    return counts


async def run() -> JobResult:
    """Entry point called by ``scheduler.jobs.cli`` / Airflow's ``DockerOperator``."""
    started_at = now_utc()
    job_name = "cleanup"
    try:
        vacuum_result = await vacuum_database()
        cache_counts = await report_cache_key_counts()
    except Exception as exc:
        finished_at = now_utc()
        _logger.error(
            "cleanup_job_failed",
            extra={"channel": "application", "job_name": job_name},
            exc_info=True,
        )
        return JobResult(
            job_name=job_name,
            status=JobStatus.FAILED,
            started_at=started_at,
            finished_at=finished_at,
            detail=f"cleanup failed: {exc}",
        )

    finished_at = now_utc()
    return JobResult(
        job_name=job_name,
        status=JobStatus.SUCCESS,
        started_at=started_at,
        finished_at=finished_at,
        detail="database vacuumed, cache key counts reported",
        context={"vacuum": vacuum_result, "cache_key_counts": cache_counts},
    )


__all__ = ["report_cache_key_counts", "run", "vacuum_database"]
