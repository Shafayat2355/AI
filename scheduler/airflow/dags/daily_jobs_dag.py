"""Daily jobs: end-of-day portfolio reconciliation.

Runs at 22:00 UTC -- after the trading day's major market close, before
``database_backup_dag`` (06:00) and the nightly data/training pipeline
(00:30-02:00) that follows it into the next calendar day. See
``docs/PHASE10_WORKFLOW_ORCHESTRATION.md`` "Scheduling strategy" for the full
daily/nightly ordering across every DAG in this package.
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG

from scheduler.airflow.dag_common import DEFAULT_ARGS, build_job_task

with DAG(
    dag_id="daily_jobs",
    description="End-of-day portfolio reconciliation.",
    default_args=DEFAULT_ARGS,
    schedule="0 22 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["daily", "reconciliation"],
) as dag:
    build_job_task(dag=dag, task_id="eod_reconciliation", job_module_name="eod_reconciliation_job")
