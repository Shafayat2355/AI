"""Historical sync: backfill/refresh historical OHLCV data.

Runs at 00:30 UTC -- first step of the nightly data/training pipeline (see
``docs/PHASE10_WORKFLOW_ORCHESTRATION.md`` "Scheduling strategy"): historical
sync, then ``data_validation_dag`` (01:00), then ``feature_generation_dag``
(01:30), then ``retraining_dag`` (02:00). Each is spaced 30-60 minutes apart
rather than chained via an explicit cross-DAG sensor/dependency -- a
deliberate, documented simplification for this phase; see the docs section
above for the trade-off and what upgrading to explicit dependencies would look
like.
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG

from scheduler.airflow.dag_common import DEFAULT_ARGS, build_job_task

with DAG(
    dag_id="historical_sync",
    description="Backfill/refresh historical OHLCV data.",
    default_args=DEFAULT_ARGS,
    schedule="30 0 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["nightly", "data-pipeline"],
) as dag:
    build_job_task(dag=dag, task_id="historical_sync", job_module_name="historical_sync_job")
