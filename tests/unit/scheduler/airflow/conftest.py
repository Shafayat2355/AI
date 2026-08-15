"""Fixtures for scheduler/airflow DAG structure tests.

Runs ONLY in the isolated Airflow environment (see
requirements/airflow.txt / docs/PHASE10_WORKFLOW_ORCHESTRATION.md) --
apache-airflow is not, and must not become, a dependency of this repo's own
requirements/dev.txt (see scheduler/airflow/dag_common.py's module docstring
for why). ``make test`` never runs this directory; use `make dags-lint` (a
separate venv) instead.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

DAGS_FOLDER = str(Path(__file__).resolve().parents[4] / "scheduler" / "airflow" / "dags")


@pytest.fixture(autouse=True, scope="session")
def _airflow_home(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Point AIRFLOW_HOME at a throwaway directory and run a real `airflow db
    migrate` once for the whole test session, so Variable.get(...) has a real
    metastore to query instead of raising for every DAG parse."""
    home = tmp_path_factory.mktemp("airflow_home")
    os.environ["AIRFLOW_HOME"] = str(home)
    os.environ["AIRFLOW__CORE__LOAD_EXAMPLES"] = "false"
    os.environ["AIRFLOW__CORE__DAGS_FOLDER"] = DAGS_FOLDER

    from airflow.utils.db import initdb

    initdb()

    from airflow.models import Variable

    Variable.set("host_repo_path", "/home/deploy/AI")

    yield
