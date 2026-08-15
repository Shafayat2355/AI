"""Model evaluation job: evaluates a trained/candidate model against
promotion criteria (backtest results, drift checks).

The "Model evaluation" category. The real evaluation/promotion logic does not
exist yet -- ``mlops/promotion_policy.py`` is still a Phase 2 scaffold stub.
Calls the integration point that future phase is expected to provide.
"""

from __future__ import annotations

from scheduler.jobs.job_result import JobResult, call_integration_point


async def run() -> JobResult:
    """Entry point called by ``scheduler.jobs.cli`` / Airflow's ``DockerOperator``."""
    return await call_integration_point(
        job_name="model_evaluation",
        module_path="mlops.promotion_policy",
        attribute_name="evaluate_candidate_model",
    )


__all__ = ["run"]
