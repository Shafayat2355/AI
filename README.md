# AI Trading Platform

Institutional-grade, event-driven AI trading platform. See [`docs/PHASE1_ARCHITECTURE.md`](docs/PHASE1_ARCHITECTURE.md) for the approved system architecture and [`docs/PHASE2_REPOSITORY_STRUCTURE.md`](docs/PHASE2_REPOSITORY_STRUCTURE.md) for the full repository layout and the purpose of every file.

## Status
Phase 1 (Architecture) — approved.
Phase 2 (Repository Structure) — this scaffold. No business logic implemented yet.

## Architecture Summary
Event-Driven, Domain-Oriented Microservices (EDMA): Hexagonal internals per service, Kafka as the event backbone, CQRS on the market-data/order-state boundary. Full rationale in `docs/PHASE1_ARCHITECTURE.md`.

## Repository Layout
See `docs/PHASE2_REPOSITORY_STRUCTURE.md` for the complete, annotated directory tree.

## Local Development
```
make setup      # bootstrap venv, install deps, install pre-commit hooks
make up         # start Kafka, Postgres, Redis via docker-compose
make test       # run unit + integration tests
make lint       # ruff + mypy
```

## Environments
- `dev` — local development
- `paper` — simulated trading against live market data
- `live` — real venue connectivity (isolated network, manual deploy approval)

## Contributing
See `.github/PULL_REQUEST_TEMPLATE.md` and `.pre-commit-config.yaml` for required checks before opening a PR.
