"""Hourly jobs: refresh the online feature store / check for market-data gaps.

Runs on the hour, every hour -- the highest-frequency DAG in this package
short of ``alert_jobs_dag`` (every 5 minutes).
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG

from scheduler.airflow.dag_common import DEFAULT_ARGS, build_job_task

with DAG(
    dag_id="hourly_jobs",
    description="Hourly online feature store refresh / market-data gap check.",
    default_args=DEFAULT_ARGS,
    schedule="0 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["hourly", "feature-store"],
) as dag:
    build_job_task(dag=dag, task_id="hourly_market_sync", job_module_name="hourly_market_sync_job")
