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

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
