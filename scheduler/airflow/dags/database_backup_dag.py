"""Database backup: pg_dump the platform's own PostgreSQL database.

Runs at 06:00 UTC -- after ``cleanup_dag`` (03:00, so the backup captures a
freshly-vacuumed database) and well clear of the 00:30-02:00 nightly
data/training pipeline. See
``docs/PHASE10_WORKFLOW_ORCHESTRATION.md`` "Scheduling strategy".
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG

from scheduler.airflow.dag_common import DEFAULT_ARGS, build_job_task

with DAG(
    dag_id="database_backup",
    description="Daily pg_dump backup of the platform's PostgreSQL database.",
    default_args=DEFAULT_ARGS,
    schedule="0 6 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["daily", "housekeeping", "backup"],
) as dag:
    build_job_task(dag=dag, task_id="database_backup", job_module_name="database_backup_job")
