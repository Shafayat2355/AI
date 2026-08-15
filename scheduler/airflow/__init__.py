"""Airflow DAG definitions for this platform's scheduled/orchestrated workflows.

Every DAG in ``scheduler/airflow/dags/`` and the shared helpers in
``dag_common.py`` require ``apache-airflow`` to import -- deliberately not a
dependency of this repo's own ``requirements/base.txt``/``requirements/dev.txt``
(see ``dag_common.py``'s module docstring for why installing it there breaks
the app's own dependency stack outright). This package is only ever imported
by the dedicated Airflow container built from
``docker/scheduler_jobs.Dockerfile``'s sibling ``docker/airflow.Dockerfile``,
which has its own isolated dependency set
(``requirements/airflow.txt``).
"""
