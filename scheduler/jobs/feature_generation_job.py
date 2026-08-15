"""Feature generation job: runs the batch/offline feature pipeline against the
latest historical data, populating the offline Feature Store.

The "Feature generation" category. The real pipeline does not exist yet --
``feature_engineering/offline_pipeline.py`` is still a Phase 2 scaffold stub.
Calls the integration point that future phase is expected to provide.
"""

from __future__ import annotations

from scheduler.jobs.job_result import JobResult, call_integration_point


async def run() -> JobResult:
    """Entry point called by ``scheduler.jobs.cli`` / Airflow's ``DockerOperator``."""
    return await call_integration_point(
        job_name="feature_generation",
        module_path="feature_engineering.offline_pipeline",
        attribute_name="run_batch_feature_generation",
    )


__all__ = ["run"]
