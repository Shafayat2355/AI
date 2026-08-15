"""Data validation job: checks historical/feature data for gaps, nulls, and
corporate-action inconsistencies.

The "Data validation" category. The real validation logic does not exist yet
-- ``datasets/schemas/dataset_schema.py`` is still a Phase 2 scaffold stub.
Calls the integration point that future phase is expected to provide.
"""

from __future__ import annotations

from scheduler.jobs.job_result import JobResult, call_integration_point


async def run() -> JobResult:
    """Entry point called by ``scheduler.jobs.cli`` / Airflow's ``DockerOperator``."""
    return await call_integration_point(
        job_name="data_validation",
        module_path="datasets.schemas.dataset_schema",
        attribute_name="validate_latest_data",
    )


__all__ = ["run"]
