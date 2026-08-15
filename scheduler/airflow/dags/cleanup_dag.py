"""Cleanup: routine Postgres/Redis housekeeping (VACUUM, cache key-count sanity check).

Runs at 03:00 UTC -- after ``retraining_dag`` (02:00), before
``database_backup_dag`` (06:00): a freshly-vacuumed database backs up faster
and smaller. See ``docs/PHASE10_WORKFLOW_ORCHESTRATION.md`` "Scheduling
strategy".
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG

from scheduler.airflow.dag_common import DEFAULT_ARGS, build_job_task

with DAG(
    dag_id="cleanup",
    description="Postgres VACUUM + Redis cache key-count sanity check.",
    default_args=DEFAULT_ARGS,
    schedule="0 3 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["daily", "housekeeping"],
) as dag:
    build_job_task(dag=dag, task_id="cleanup", job_module_name="cleanup_job")
