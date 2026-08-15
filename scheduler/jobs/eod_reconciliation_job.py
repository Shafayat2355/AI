"""Triggers end-of-day portfolio reconciliation.

The "Daily jobs" category: reconciles the platform's own recorded portfolio
state (``portfolio.portfolio_manager``) against what actually happened during
the trading day. The real reconciliation logic does not exist yet --
``portfolio/portfolio_manager.py`` is still a Phase 2 scaffold stub, since no
concrete ``Order``/``Position`` domain model exists yet (see
``scheduler/jobs/cleanup_job.py``'s module docstring for the same underlying
reason). This job calls the integration point it expects that future phase to
provide, via ``scheduler.jobs.job_result.call_integration_point`` -- see that
function's docstring for exactly what happens today (a documented,
non-failing no-op) versus once that phase lands (this job starts doing real
work with zero changes here).
"""

from __future__ import annotations

from scheduler.jobs.job_result import JobResult, call_integration_point


async def run() -> JobResult:
    """Entry point called by ``scheduler.jobs.cli`` / Airflow's ``DockerOperator``."""
    return await call_integration_point(
        job_name="eod_reconciliation",
        module_path="portfolio.portfolio_manager",
        attribute_name="reconcile_end_of_day",
    )


__all__ = ["run"]
