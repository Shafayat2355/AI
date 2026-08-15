"""Historical sync job: backfills/refreshes historical OHLCV data.

The "Historical sync" category. The real sync logic does not exist yet --
``datasets/historical/ohlcv_store.py`` is still a Phase 2 scaffold stub.
Calls the integration point that future phase is expected to provide.
"""

from __future__ import annotations

from scheduler.jobs.job_result import JobResult, call_integration_point


async def run() -> JobResult:
    """Entry point called by ``scheduler.jobs.cli`` / Airflow's ``DockerOperator``."""
    return await call_integration_point(
        job_name="historical_sync",
        module_path="datasets.historical.ohlcv_store",
        attribute_name="sync_latest_history",
    )


__all__ = ["run"]
