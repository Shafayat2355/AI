"""Triggers the AI Training service on a nightly schedule.

The "Retraining" category: retrains the platform's model(s) against the
latest available data. The real training logic does not exist yet --
``training/trainer.py`` is still a Phase 2 scaffold stub (no `Trainer` class
or `train` function defined). This job calls the integration point it
expects that future phase to provide, via
``scheduler.jobs.job_result.call_integration_point`` -- see that function's
docstring for exactly what happens today (a documented, non-failing no-op)
versus once that phase lands.
"""

from __future__ import annotations

from scheduler.jobs.job_result import JobResult, call_integration_point


async def run() -> JobResult:
    """Entry point called by ``scheduler.jobs.cli`` / Airflow's ``DockerOperator``."""
    return await call_integration_point(
        job_name="nightly_training",
        module_path="training.trainer",
        attribute_name="run_training_job",
    )


__all__ = ["run"]
