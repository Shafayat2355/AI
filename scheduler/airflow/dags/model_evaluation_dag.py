"""Model evaluation: evaluate a candidate model against promotion criteria.

Runs weekly (Sunday 05:00 UTC), after ``backtesting_dag`` (04:00 the same
day) whose results it evaluates against promotion criteria. See
``docs/PHASE10_WORKFLOW_ORCHESTRATION.md`` "Scheduling strategy".
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG

from scheduler.airflow.dag_common import DEFAULT_ARGS, build_job_task

with DAG(
    dag_id="model_evaluation",
    description="Weekly candidate-model promotion evaluation.",
    default_args=DEFAULT_ARGS,
    schedule="0 5 * * 0",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["weekly", "mlops"],
) as dag:
    build_job_task(dag=dag, task_id="model_evaluation", job_module_name="model_evaluation_job")
