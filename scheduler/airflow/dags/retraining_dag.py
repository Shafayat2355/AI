"""Retraining: retrain the platform's model(s) against the latest data.

Runs at 02:00 UTC -- last step of the nightly data/training pipeline, after
``feature_generation_dag`` (01:30). See
``docs/PHASE10_WORKFLOW_ORCHESTRATION.md`` "Scheduling strategy".
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG

from scheduler.airflow.dag_common import DEFAULT_ARGS, build_job_task

with DAG(
    dag_id="retraining",
    description="Nightly AI model retraining.",
    default_args=DEFAULT_ARGS,
    schedule="0 2 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["nightly", "training"],
) as dag:
    build_job_task(dag=dag, task_id="nightly_training", job_module_name="nightly_training_job")
