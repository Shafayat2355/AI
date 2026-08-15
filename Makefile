.PHONY: setup up down test lint format typecheck migrate run-% clean

setup:
	python -m venv .venv
	. .venv/bin/activate; pip install -r requirements/base.txt -r requirements/dev.txt
	. .venv/bin/activate; pre-commit install

up:
	docker compose up -d

down:
	docker compose down

test:
	pytest tests/unit tests/integration -v

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy .

migrate:
	bash scripts/run_migrations.sh

run-%:
	python -m app.$*_service.main

airflow-up:
	docker compose build scheduler-jobs
	docker compose up -d airflow-postgres airflow-init airflow-webserver airflow-scheduler

airflow-down:
	docker compose stop airflow-webserver airflow-scheduler airflow-postgres

# Validates every DAG imports cleanly (no cycles, no syntax errors) using the
# ISOLATED Airflow environment -- never the main .venv (see
# requirements/airflow.txt and scheduler/airflow/dag_common.py for why
# apache-airflow cannot share an environment with this repo's own
# dependencies). Run once: `python -m venv .venv-airflow && .venv-airflow/bin/pip
# install -r requirements/airflow.txt`.
dags-lint:
	.venv-airflow/bin/python -m pytest tests/unit/scheduler/airflow --confcutdir=tests/unit/scheduler/airflow -v

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
