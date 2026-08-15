"""Data validation: check historical/feature data for gaps, nulls, and
corporate-action inconsistencies.

Runs at 01:00 UTC -- after ``historical_sync_dag`` (00:30), before
``feature_generation_dag`` (01:30). See
``docs/PHASE10_WORKFLOW_ORCHESTRATION.md`` "Scheduling strategy".
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG

from scheduler.airflow.dag_common import DEFAULT_ARGS, build_job_task

with DAG(
    dag_id="data_validation",
    description="Validate historical/feature data quality.",
    default_args=DEFAULT_ARGS,
    schedule="0 1 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["nightly", "data-pipeline"],
) as dag:
    build_job_task(dag=dag, task_id="data_validation", job_module_name="data_validation_job")
