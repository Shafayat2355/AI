"""Alert jobs: sweep the platform's own readiness check and fail loudly
(see ``scheduler.jobs.alert_sweep_job``) if anything is degraded.

Runs every 5 minutes -- the highest-frequency DAG in this package, since
alerting is only useful if it's timely. Deliberately not tied to the
nightly/weekly pipeline's own schedule.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG

from scheduler.airflow.dag_common import DEFAULT_ARGS, build_job_task

# Alerting should not itself retry-and-wait the way a data/training job should
# -- a degraded system should be reported within roughly one sweep interval,
# not after two retries with a 5-minute backoff each (this DAG's own
# DEFAULT_ARGS override reflects that).
_ALERT_ARGS = {**DEFAULT_ARGS, "retries": 0, "execution_timeout": timedelta(minutes=2)}

with DAG(
    dag_id="alert_jobs",
    description="Readiness sweep; fails (and alerts) if the platform is degraded.",
    default_args=_ALERT_ARGS,
    schedule=timedelta(minutes=5),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["alerting", "high-frequency"],
) as dag:
    build_job_task(dag=dag, task_id="alert_sweep", job_module_name="alert_sweep_job")
