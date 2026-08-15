# Isolated Airflow image (scheduler + webserver both use this). Installs ONLY
# requirements/airflow.txt -- never requirements/base.txt or dev.txt.
#
# This isolation is load-bearing, not a style choice: confirmed while building
# Phase 10 that installing apache-airflow==2.10.4 alongside this repo's own
# sqlalchemy>=2/pydantic>=2/fastapi stack breaks the latter outright (Airflow's
# pinned constraints force sqlalchemy down to 1.4.x and a typing_extensions
# incompatible with pydantic v2). See scheduler/airflow/dag_common.py's module
# docstring for the full explanation and docs/PHASE10_WORKFLOW_ORCHESTRATION.md
# Sec 3 for the exact reproduction.
#
# Airflow tasks never import this platform's own code directly -- every DAG
# task runs via DockerOperator against docker/scheduler_jobs.Dockerfile's
# image instead (see scheduler/airflow/dag_common.py). This image therefore
# only ever needs Airflow itself, its Docker provider, and this repo's DAG
# *definitions* (plain Python using only Airflow's own classes -- no app
# dependency).
FROM apache/airflow:2.10.4-python3.12

COPY requirements/airflow.txt /tmp/requirements/airflow.txt
RUN pip install --no-cache-dir --constraint \
    "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.4/constraints-3.12.txt" \
    -r /tmp/requirements/airflow.txt

# Preserve the real scheduler.airflow.* package path -- the DAG files import
# `from scheduler.airflow.dag_common import ...`, which requires `scheduler`
# to exist as a top-level importable package, not just a directory of DAG
# files. Airflow's DAGS_FOLDER only controls which directory Airflow *scans*
# for DAG files; it is independent of PYTHONPATH/what's importable.
COPY scheduler/__init__.py /opt/airflow/app/scheduler/__init__.py
COPY scheduler/airflow /opt/airflow/app/scheduler/airflow
ENV PYTHONPATH=/opt/airflow/app
ENV AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/app/scheduler/airflow/dags
