"""Triggers periodic backtests against the current champion model/strategy.

The "Backtesting jobs" category: replays historical data through the current
champion strategy/model to confirm performance hasn't regressed. The real
replay logic does not exist yet -- ``backtesting/replay_engine.py`` is still
a Phase 2 scaffold stub. This job calls the integration point it expects that
future phase to provide, via
``scheduler.jobs.job_result.call_integration_point`` -- see that function's
docstring for exactly what happens today versus once that phase lands.
"""

from __future__ import annotations

from scheduler.jobs.job_result import JobResult, call_integration_point


async def run() -> JobResult:
    """Entry point called by ``scheduler.jobs.cli`` / Airflow's ``DockerOperator``."""
    return await call_integration_point(
        job_name="periodic_backtest",
        module_path="backtesting.replay_engine",
        attribute_name="run_scheduled_backtest",
    )


__all__ = ["run"]
