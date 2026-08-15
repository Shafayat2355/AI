"""Alert sweep job: runs the platform's own readiness check
(``monitoring.health_checks.readiness``) and escalates to a
``CRITICAL``-level structured log line if anything is degraded or unhealthy.

The "Alert jobs" category. Reuses ``monitoring.health_checks.readiness``
directly rather than re-implementing the database/Redis/Kafka connectivity
checks it already performs -- one place decides what "healthy" means.

Dispatch today is twofold: a structured ``CRITICAL`` log line (per
``docs/CODING_STANDARDS.md`` Sec 12: "CRITICAL -- risk breach, kill-switch
engaged -- must also alert") *and* returning
:data:`~scheduler.jobs.job_result.JobStatus.FAILED` -- deliberately, even
though nothing about running the sweep itself went wrong -- so the
Airflow task genuinely fails and shows red in the UI, which is what actually
notifies an operator via Airflow's own on-failure alerting
(``scheduler/airflow/dag_common.py``'s ``on_failure_callback``) today.
``alerts/alert_manager.py`` and ``alerts/channels/*.py`` are still Phase 2
scaffold stubs; routing through a real Slack/PagerDuty channel instead of
Airflow's own failure notification is a natural enhancement once that module
exists, not a prerequisite for this job to be useful now.
"""

from __future__ import annotations

from core.container import get_container
from monitoring.health_checks import readiness
from scheduler.jobs.job_result import JobResult, JobStatus, now_utc
from shared.enums import HealthStatus
from shared.logging.logger import get_logger

_logger = get_logger("scheduler.jobs.alert_sweep")


async def run() -> JobResult:
    """Entry point called by ``scheduler.jobs.cli`` / Airflow's ``DockerOperator``."""
    started_at = now_utc()
    job_name = "alert_sweep"
    container = get_container()
    health = await readiness(container)

    if health.status is HealthStatus.HEALTHY:
        finished_at = now_utc()
        return JobResult(
            job_name=job_name,
            status=JobStatus.SUCCESS,
            started_at=started_at,
            finished_at=finished_at,
            detail="all components healthy",
        )

    degraded_components = {
        component.name: component.status.value
        for component in health.components
        if component.status is not HealthStatus.HEALTHY
    }
    _logger.critical(
        "platform_health_degraded",
        extra={
            "channel": "application",
            "overall_status": health.status.value,
            "degraded_components": degraded_components,
        },
    )
    finished_at = now_utc()
    return JobResult(
        job_name=job_name,
        # Deliberately FAILED, not SUCCESS -- see module docstring: this is
        # what makes the Airflow task itself the alert.
        status=JobStatus.FAILED,
        started_at=started_at,
        finished_at=finished_at,
        detail=f"platform health degraded: {health.status.value} ({degraded_components})",
        context={"degraded_components": degraded_components},
    )


__all__ = ["run"]
