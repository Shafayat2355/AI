"""Hourly job: refreshes the online feature store / checks for market-data gaps.

The "Hourly jobs" category. The real refresh logic does not exist yet --
``feature_engineering/online_pipeline.py`` is still a Phase 2 scaffold stub.
Calls the integration point that future phase is expected to provide.
"""

from __future__ import annotations

from scheduler.jobs.job_result import JobResult, call_integration_point


async def run() -> JobResult:
    """Entry point called by ``scheduler.jobs.cli`` / Airflow's ``DockerOperator``."""
    return await call_integration_point(
        job_name="hourly_market_sync",
        module_path="feature_engineering.online_pipeline",
        attribute_name="refresh_online_features",
    )


__all__ = ["run"]
