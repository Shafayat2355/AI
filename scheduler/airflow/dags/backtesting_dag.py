"""Backtesting jobs: replay historical data through the current champion
strategy/model.

Runs weekly (Sunday 04:00 UTC) rather than nightly -- a full backtest suite is
heavier and its result doesn't change meaningfully day-to-day the way a
retraining run's inputs do; see
``docs/PHASE10_WORKFLOW_ORCHESTRATION.md`` "Scheduling strategy" for the
nightly-vs-weekly cadence rationale. Runs before ``model_evaluation_dag``
(05:00 the same day), which consumes its results.
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG

from scheduler.airflow.dag_common import DEFAULT_ARGS, build_job_task

with DAG(
    dag_id="backtesting",
    description="Weekly backtest of the current champion strategy/model.",
    default_args=DEFAULT_ARGS,
    schedule="0 4 * * 0",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["weekly", "backtesting"],
) as dag:
    build_job_task(dag=dag, task_id="periodic_backtest", job_module_name="periodic_backtest_job")
