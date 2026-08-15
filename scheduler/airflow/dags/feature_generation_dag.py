"""Feature generation: run the batch/offline feature pipeline against the
latest historical data.

Runs at 01:30 UTC -- after ``data_validation_dag`` (01:00), before
``retraining_dag`` (02:00). See
``docs/PHASE10_WORKFLOW_ORCHESTRATION.md`` "Scheduling strategy".
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG

from scheduler.airflow.dag_common import DEFAULT_ARGS, build_job_task

with DAG(
    dag_id="feature_generation",
    description="Batch/offline feature pipeline run.",
    default_args=DEFAULT_ARGS,
    schedule="30 1 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["nightly", "data-pipeline"],
) as dag:
    build_job_task(dag=dag, task_id="feature_generation", job_module_name="feature_generation_job")
