# Phase 2 — Complete Repository Structure

Scaffold only: every directory and file below exists in the repository with a header comment/docstring stating its purpose. **No business logic is implemented** — this satisfies Phase 2 scope. Root tooling files (Makefile, docker-compose.yml, pyproject.toml, ruff.toml, mypy.ini, .pre-commit-config.yaml, requirements/*) contain real configuration, since configuration is structure, not application logic.

## Full Directory Tree

```
.
|-- .env.example
|-- .github
|   |-- ISSUE_TEMPLATE
|   |   |-- bug_report.md
|   |   `-- feature_request.md
|   |-- PULL_REQUEST_TEMPLATE.md
|   `-- workflows
|       |-- backtest-regression.yml
|       |-- cd-live.yml
|       |-- cd-paper.yml
|       `-- ci.yml
|-- .gitignore
|-- .pre-commit-config.yaml
|-- LICENSE
|-- Makefile
|-- README.md
|-- ai
|   |-- __init__.py
|   |-- inference
|   |   |-- __init__.py
|   |   |-- canary_router.py
|   |   |-- model_loader.py
|   |   `-- predictor.py
|   |-- mlops
|   |   |-- __init__.py
|   |   |-- drift_detector.py
|   |   |-- experiment_tracker.py
|   |   `-- promotion_policy.py
|   |-- models
|   |   |-- __init__.py
|   |   |-- model_definitions
|   |   |   |-- __init__.py
|   |   |   `-- lstm_price_model.py
|   |   `-- registry_client.py
|   `-- training
|       |-- __init__.py
|       |-- hyperparameter_search.py
|       |-- trainer.py
|       `-- validation.py
|-- alerts
|   |-- __init__.py
|   |-- alert_manager.py
|   `-- channels
|       |-- __init__.py
|       |-- pagerduty_channel.py
|       `-- slack_channel.py
|-- api
|   |-- __init__.py
|   |-- auth
|   |   |-- __init__.py
|   |   |-- oauth_provider.py
|   |   `-- rbac.py
|   |-- middleware
|   |   |-- __init__.py
|   |   |-- auth_middleware.py
|   |   `-- rate_limit_middleware.py
|   |-- routers
|   |   |-- __init__.py
|   |   |-- auth_router.py
|   |   |-- orders_router.py
|   |   |-- portfolio_router.py
|   |   `-- strategies_router.py
|   `-- schemas
|       |-- __init__.py
|       `-- request_response_models.py
|-- app
|   |-- __init__.py
|   |-- api_service
|   |   |-- __init__.py
|   |   `-- main.py
|   |-- backtesting_service
|   |   |-- __init__.py
|   |   `-- main.py
|   |-- dashboard_service
|   |   |-- __init__.py
|   |   `-- main.py
|   |-- execution_service
|   |   |-- __init__.py
|   |   `-- main.py
|   |-- inference_service
|   |   |-- __init__.py
|   |   `-- main.py
|   |-- main.py
|   |-- market_data_service
|   |   |-- __init__.py
|   |   `-- main.py
|   |-- portfolio_service
|   |   |-- __init__.py
|   |   `-- main.py
|   |-- risk_service
|   |   |-- __init__.py
|   |   `-- main.py
|   |-- scheduler_service
|   |   |-- __init__.py
|   |   `-- main.py
|   |-- strategy_service
|   |   |-- __init__.py
|   |   `-- main.py
|   |-- training_service
|   |   |-- __init__.py
|   |   `-- main.py
|   `-- websocket_service
|       |-- __init__.py
|       `-- main.py
|-- backtesting
|   |-- __init__.py
|   |-- performance_metrics.py
|   |-- replay_engine.py
|   `-- report_generator.py
|-- cache
|   |-- __init__.py
|   |-- cache_keys.py
|   `-- redis_client.py
|-- config
|   |-- __init__.py
|   |-- config_client.py
|   |-- environments
|   |   |-- dev.yaml
|   |   |-- live.yaml
|   |   `-- paper.yaml
|   `-- settings.py
|-- core
|   |-- __init__.py
|   |-- domain
|   |   |-- __init__.py
|   |   |-- entities
|   |   |   |-- __init__.py
|   |   |   |-- account.py
|   |   |   |-- order.py
|   |   |   |-- position.py
|   |   |   |-- strategy_signal.py
|   |   |   `-- tick.py
|   |   |-- events
|   |   |   |-- __init__.py
|   |   |   |-- market_events.py
|   |   |   |-- order_events.py
|   |   |   |-- portfolio_events.py
|   |   |   `-- risk_events.py
|   |   `-- value_objects
|   |       |-- __init__.py
|   |       |-- money.py
|   |       |-- symbol.py
|   |       `-- time_range.py
|   |-- ports
|   |   |-- __init__.py
|   |   |-- event_publisher_port.py
|   |   |-- feature_store_port.py
|   |   |-- market_data_port.py
|   |   |-- model_registry_port.py
|   |   |-- order_repository_port.py
|   |   `-- portfolio_repository_port.py
|   `-- use_cases
|       |-- __init__.py
|       |-- evaluate_strategy.py
|       |-- gate_risk.py
|       |-- reconcile_portfolio.py
|       |-- run_backtest.py
|       `-- submit_order.py
|-- dashboard
|   |-- __init__.py
|   |-- static
|   |   `-- .gitkeep
|   |-- templates
|   |   `-- .gitkeep
|   `-- views.py
|-- database
|   |-- __init__.py
|   |-- base.py
|   |-- connection.py
|   |-- migrations
|   |   |-- env.py
|   |   `-- versions
|   |       `-- .gitkeep
|   `-- repositories
|       |-- __init__.py
|       |-- account_repository.py
|       |-- order_repository.py
|       `-- portfolio_repository.py
|-- datasets
|   |-- __init__.py
|   |-- historical
|   |   |-- __init__.py
|   |   |-- corporate_actions.py
|   |   `-- ohlcv_store.py
|   |-- loaders
|   |   |-- __init__.py
|   |   `-- training_dataset_loader.py
|   `-- schemas
|       `-- dataset_schema.py
|-- deployment
|   |-- helm
|   |   `-- .gitkeep
|   |-- k8s
|   |   |-- base
|   |   |   `-- .gitkeep
|   |   `-- overlays
|   |       |-- dev
|   |       |   `-- .gitkeep
|   |       |-- live
|   |       |   `-- .gitkeep
|   |       `-- paper
|   |           `-- .gitkeep
|   `-- terraform
|       `-- .gitkeep
|-- docker
|   |-- api.Dockerfile
|   |-- base.Dockerfile
|   |-- execution.Dockerfile
|   |-- inference.Dockerfile
|   `-- training.Dockerfile
|-- docker-compose.override.yml
|-- docker-compose.yml
|-- docs
|   |-- PHASE1_ARCHITECTURE.md
|   |-- adr
|   |   `-- 0001-event-driven-microservices.md
|   |-- api
|   |   `-- openapi.yaml
|   `-- runbooks
|       |-- dr-failover.md
|       `-- incident-response.md
|-- execution
|   |-- __init__.py
|   |-- execution_port.py
|   |-- order_manager.py
|   `-- order_state_machine.py
|-- feature_engineering
|   |-- __init__.py
|   |-- definitions
|   |   |-- __init__.py
|   |   |-- statistical_features.py
|   |   `-- technical_indicators.py
|   |-- feature_store_client.py
|   |-- offline_pipeline.py
|   `-- online_pipeline.py
|-- live_trading
|   |-- __init__.py
|   |-- broker_gateway.py
|   `-- fix_session_manager.py
|-- market_data
|   |-- __init__.py
|   |-- feed_adapters
|   |   |-- __init__.py
|   |   |-- fix_feed_adapter.py
|   |   `-- vendor_feed_adapter.py
|   |-- normalizer.py
|   `-- publisher.py
|-- monitoring
|   |-- __init__.py
|   |-- health_checks.py
|   `-- metrics_exporter.py
|-- mypy.ini
|-- paper_trading
|   |-- __init__.py
|   |-- simulator.py
|   `-- slippage_model.py
|-- portfolio
|   |-- __init__.py
|   |-- ledger.py
|   |-- pnl_calculator.py
|   `-- portfolio_manager.py
|-- pyproject.toml
|-- requirements
|   |-- base.txt
|   |-- dev.txt
|   |-- prod.txt
|   `-- training.txt
|-- risk
|   |-- __init__.py
|   |-- circuit_breaker.py
|   |-- limit_rules.py
|   `-- risk_manager.py
|-- ruff.toml
|-- scheduler
|   |-- __init__.py
|   |-- job_scheduler.py
|   `-- jobs
|       |-- __init__.py
|       |-- eod_reconciliation_job.py
|       |-- nightly_training_job.py
|       `-- periodic_backtest_job.py
|-- scripts
|   |-- deploy.sh
|   |-- run_migrations.sh
|   |-- seed_test_data.sh
|   `-- setup_dev_env.sh
|-- shared
|   |-- __init__.py
|   |-- constants.py
|   |-- errors
|   |   |-- __init__.py
|   |   `-- exceptions.py
|   |-- logging
|   |   |-- __init__.py
|   |   |-- correlation.py
|   |   `-- logger.py
|   |-- messaging
|   |   |-- __init__.py
|   |   |-- kafka_consumer.py
|   |   |-- kafka_producer.py
|   |   `-- schema_registry.py
|   `-- utils
|       |-- __init__.py
|       |-- serialization.py
|       `-- time_utils.py
|-- strategies
|   |-- __init__.py
|   |-- base_strategy.py
|   |-- implementations
|   |   |-- __init__.py
|   |   |-- mean_reversion_strategy.py
|   |   `-- momentum_strategy.py
|   `-- strategy_registry.py
|-- tests
|   |-- __init__.py
|   |-- conftest.py
|   |-- e2e
|   |   `-- .gitkeep
|   |-- fixtures
|   |   `-- .gitkeep
|   |-- integration
|   |   `-- .gitkeep
|   `-- unit
|       `-- .gitkeep
`-- websocket
    |-- __init__.py
    |-- connection_manager.py
    |-- server.py
    `-- session_store.py

93 directories, 237 files
```

## File-by-File Purpose

### Root Configuration & Governance

| Path | Purpose |
|---|---|
| `README.md` | Project overview, architecture summary, quick start, links to docs/PHASE1 and PHASE2 documents. |
| `LICENSE` | Proprietary/institutional license terms governing use of this codebase. |
| `Makefile` | Common developer commands: make install, make test, make lint, make run-<service>, make migrate. |
| `docker-compose.yml` | Local multi-service stack: Kafka, Postgres, Redis, and all app services wired together for dev. |
| `docker-compose.override.yml` | Local-only overrides (hot reload, exposed debug ports) layered on top of docker-compose.yml. |
| `pyproject.toml` | Project metadata, dependency groups, build system, and tool configuration (ruff/mypy/pytest) in one place. |
| `ruff.toml` | Linting and formatting rules enforced across the codebase (style, import order, complexity limits). |
| `mypy.ini` | Static type-checking configuration; strict mode for core/ and shared/, relaxed for scripts/. |
| `.pre-commit-config.yaml` | Git hooks running ruff, mypy, and secret-scanning before every commit. |
| `.gitignore` | Excludes venvs, caches, model artifacts, local .env files, and IDE metadata from version control. |
| `.env.example` | Template of required environment variables (no real secrets) for local setup. |

### requirements/

| Path | Purpose |
|---|---|
| `requirements/base.txt` | Core runtime dependencies shared by every service. |
| `requirements/dev.txt` | Developer tooling: pytest, ruff, mypy, pre-commit, coverage. |
| `requirements/prod.txt` | Pinned production dependency set generated from base.txt for reproducible builds. |
| `requirements/training.txt` | Heavy ML/GPU dependencies (torch, sklearn, etc.) isolated so lightweight services don't need them. |

### .github/

| Path | Purpose |
|---|---|
| `.github/ISSUE_TEMPLATE/bug_report.md` | Structured template for reporting defects (steps to reproduce, environment, severity). |
| `.github/ISSUE_TEMPLATE/feature_request.md` | Structured template for proposing new features or modules. |
| `.github/PULL_REQUEST_TEMPLATE.md` | Checklist for PR authors: tests added, docs updated, backtest regression run, risk review if applicable. |
| `.github/workflows/backtest-regression.yml` | Runs the backtesting suite against a fixed dataset to catch strategy/model regressions before merge. |
| `.github/workflows/cd-live.yml` | Deploys to the live-trading environment; requires manual approval gate. |
| `.github/workflows/cd-paper.yml` | Builds and deploys services to the paper-trading environment on merge to main. |
| `.github/workflows/ci.yml` | Runs lint, type-check, and unit/integration tests on every push and pull request. |

### docs/

| Path | Purpose |
|---|---|
| `docs/adr/0001-event-driven-microservices.md` | Architecture Decision Record capturing why EDMA was chosen over monolith/MVC/plain microservices. |
| `docs/api/openapi.yaml` | OpenAPI specification for the external-facing API Layer endpoints. |
| `docs/runbooks/dr-failover.md` | Step-by-step runbook for executing a disaster-recovery region failover. |
| `docs/runbooks/incident-response.md` | Step-by-step operator runbook for responding to a live-trading incident or risk breach. |

### app/ — Composition Roots (Service Entrypoints)

| Path | Purpose |
|---|---|
| `app/__init__.py` | Marks app/ as a package. |
| `app/api_service/__init__.py` | Marks package. |
| `app/api_service/main.py` | Wires the API Layer (routers, middleware, auth); starts the external-facing API service process. |
| `app/backtesting_service/__init__.py` | Marks package. |
| `app/backtesting_service/main.py` | Wires the Backtesting replay engine; starts the Backtesting service process. |
| `app/dashboard_service/__init__.py` | Marks package. |
| `app/dashboard_service/main.py` | Wires the operator Dashboard app; starts the Dashboard service process. |
| `app/execution_service/__init__.py` | Marks package. |
| `app/execution_service/main.py` | Wires Order Execution, and selects Paper or Live adapter based on config; starts the Execution service process. |
| `app/inference_service/__init__.py` | Marks package. |
| `app/inference_service/main.py` | Wires AI Inference, model loader, and online Feature Store client; starts the Inference service process. |
| `app/main.py` | Generic entrypoint dispatcher used by local dev to launch any single service by name. |
| `app/market_data_service/__init__.py` | Marks package. |
| `app/market_data_service/main.py` | Wires Market Data adapters, config, and messaging; starts the Market Data service process. |
| `app/portfolio_service/__init__.py` | Marks package. |
| `app/portfolio_service/main.py` | Wires Portfolio Manager, ledger repository, and DB; starts the Portfolio service process. |
| `app/risk_service/__init__.py` | Marks package. |
| `app/risk_service/main.py` | Wires Risk Manager, limit rules, and the fast breach-alert path; starts the Risk service process. |
| `app/scheduler_service/__init__.py` | Marks package. |
| `app/scheduler_service/main.py` | Wires the job Scheduler and registered jobs; starts the Scheduler service process. |
| `app/strategy_service/__init__.py` | Marks package. |
| `app/strategy_service/main.py` | Wires Strategy Engine use cases and Kafka topics; starts the Strategy service process. |
| `app/training_service/__init__.py` | Marks package. |
| `app/training_service/main.py` | Wires AI Training job runner and MLOps registry client; starts the Training service process (GPU pool). |
| `app/websocket_service/__init__.py` | Marks package. |
| `app/websocket_service/main.py` | Wires WebSocket Engine, Kafka consumers, and Cache; starts the WebSocket service process. |

### core/ — Framework-Agnostic Domain Logic (Hexagonal Core)

| Path | Purpose |
|---|---|
| `core/__init__.py` | Marks package. |
| `core/domain/__init__.py` | Marks package. |
| `core/domain/entities/__init__.py` | Marks package. |
| `core/domain/entities/account.py` | Account entity: balances, account type (paper/live), risk profile reference. |
| `core/domain/entities/order.py` | Order entity: identity, state machine fields, invariants — no framework/DB dependencies. |
| `core/domain/entities/position.py` | Position entity: symbol, quantity, average cost, unrealized P&L invariants. |
| `core/domain/entities/strategy_signal.py` | Strategy signal entity: the intent produced by a strategy before risk gating. |
| `core/domain/entities/tick.py` | Tick entity: normalized market data point shared across the pipeline. |
| `core/domain/events/__init__.py` | Marks package. |
| `core/domain/events/market_events.py` | Event schemas for market.ticks.* and related market data events. |
| `core/domain/events/order_events.py` | Event schemas for orders.fills, orders.status, and order lifecycle events. |
| `core/domain/events/portfolio_events.py` | Event schemas for portfolio.updates events. |
| `core/domain/events/risk_events.py` | Event schemas for risk.approved / risk.rejected and breach notifications. |
| `core/domain/value_objects/__init__.py` | Marks package. |
| `core/domain/value_objects/money.py` | Immutable Money value object avoiding float rounding errors in P&L/order math. |
| `core/domain/value_objects/symbol.py` | Immutable Symbol value object with validation (exchange, ticker format). |
| `core/domain/value_objects/time_range.py` | Immutable TimeRange value object used by historical queries and backtests. |
| `core/ports/__init__.py` | Marks package. |
| `core/ports/event_publisher_port.py` | Abstract interface for publishing domain events, implemented by shared/messaging. |
| `core/ports/feature_store_port.py` | Abstract interface for online/offline feature retrieval. |
| `core/ports/market_data_port.py` | Abstract interface for any market data source, implemented by concrete feed adapters. |
| `core/ports/model_registry_port.py` | Abstract interface for the MLOps model registry, implemented by ai/mlops. |
| `core/ports/order_repository_port.py` | Abstract interface for persisting/retrieving orders, implemented by database/repositories. |
| `core/ports/portfolio_repository_port.py` | Abstract interface for the portfolio ledger store. |
| `core/use_cases/__init__.py` | Marks package. |
| `core/use_cases/evaluate_strategy.py` | Use case orchestrating signal + rule evaluation into a strategy intent. |
| `core/use_cases/gate_risk.py` | Use case orchestrating pre-trade risk checks against current exposure and limits. |
| `core/use_cases/reconcile_portfolio.py` | Use case orchestrating end-of-day ledger reconciliation. |
| `core/use_cases/run_backtest.py` | Use case orchestrating a full backtest replay using the shared strategy/risk logic. |
| `core/use_cases/submit_order.py` | Use case orchestrating order submission through the execution port. |

### shared/ — Cross-Cutting Adapters

| Path | Purpose |
|---|---|
| `shared/__init__.py` | Marks package. |
| `shared/constants.py` | Cross-service constants (topic names, header keys, default timeouts). |
| `shared/errors/__init__.py` | Marks package. |
| `shared/errors/exceptions.py` | Shared exception hierarchy (DomainError, RiskBreachError, ExecutionError, etc.). |
| `shared/logging/__init__.py` | Marks package. |
| `shared/logging/correlation.py` | Correlation-ID generation/propagation helpers for cross-service tracing. |
| `shared/logging/logger.py` | Structured JSON logger factory used by every service. |
| `shared/messaging/__init__.py` | Marks package. |
| `shared/messaging/kafka_consumer.py` | Thin wrapper around the Kafka consumer client with idempotent-processing helpers. |
| `shared/messaging/kafka_producer.py` | Thin wrapper around the Kafka producer client with schema validation and retries. |
| `shared/messaging/schema_registry.py` | Client for registering/validating event schemas against the schema registry. |
| `shared/utils/__init__.py` | Marks package. |
| `shared/utils/serialization.py` | Common (de)serialization helpers for event payloads. |
| `shared/utils/time_utils.py` | Timezone-safe timestamp helpers used across market data and reporting. |

### config/

| Path | Purpose |
|---|---|
| `config/__init__.py` | Marks package. |
| `config/config_client.py` | Client that subscribes to config.updated events for hot-reloading configuration without redeploy. |
| `config/environments/dev.yaml` | Dev environment configuration overlay (local endpoints, relaxed limits). |
| `config/environments/live.yaml` | Live-trading environment configuration overlay (strict limits, real endpoints). |
| `config/environments/paper.yaml` | Paper-trading environment configuration overlay. |
| `config/settings.py` | Typed settings loader (env vars + environment YAML) used by every service at boot. |

### database/

| Path | Purpose |
|---|---|
| `database/__init__.py` | Marks package. |
| `database/base.py` | ORM declarative base and session-scoping utilities. |
| `database/connection.py` | Database connection/session factory shared by repository implementations. |
| `database/migrations/env.py` | Migration tool environment configuration. |
| `database/migrations/versions/.gitkeep` | Placeholder keeping the empty migrations/versions directory in version control. |
| `database/repositories/__init__.py` | Marks package. |
| `database/repositories/account_repository.py` | Concrete repository for account/balance persistence. |
| `database/repositories/order_repository.py` | Concrete implementation of core/ports/order_repository_port.py against the SQL database. |
| `database/repositories/portfolio_repository.py` | Concrete implementation of core/ports/portfolio_repository_port.py against the SQL database. |

### cache/

| Path | Purpose |
|---|---|
| `cache/__init__.py` | Marks package. |
| `cache/cache_keys.py` | Centralized cache key naming conventions to avoid key collisions across services. |
| `cache/redis_client.py` | Redis client factory with connection pooling shared by all consumers of Cache. |

### market_data/

| Path | Purpose |
|---|---|
| `market_data/__init__.py` | Marks package. |
| `market_data/feed_adapters/__init__.py` | Marks package. |
| `market_data/feed_adapters/fix_feed_adapter.py` | Adapter connecting to a FIX-protocol market data feed. |
| `market_data/feed_adapters/vendor_feed_adapter.py` | Adapter connecting to a market data vendor's streaming API. |
| `market_data/normalizer.py` | Normalizes vendor-specific tick formats into the shared core Tick entity. |
| `market_data/publisher.py` | Publishes normalized ticks to the market.ticks.* Kafka topics. |

### websocket/

| Path | Purpose |
|---|---|
| `websocket/__init__.py` | Marks package. |
| `websocket/connection_manager.py` | Tracks active client connections and handles subscribe/unsubscribe requests. |
| `websocket/server.py` | WebSocket server entrypoint that fans out Kafka events to connected clients. |
| `websocket/session_store.py` | Persists connection/session state in Cache to support reconnect without data loss. |

### feature_engineering/

| Path | Purpose |
|---|---|
| `feature_engineering/__init__.py` | Marks package. |
| `feature_engineering/definitions/__init__.py` | Marks package. |
| `feature_engineering/definitions/statistical_features.py` | Shared definitions of statistical/derived features used by both training and inference. |
| `feature_engineering/definitions/technical_indicators.py` | Shared definitions of technical indicators (moving averages, RSI, etc.) used by both training and inference. |
| `feature_engineering/feature_store_client.py` | Client implementing core/ports/feature_store_port.py for reading/writing feature values. |
| `feature_engineering/offline_pipeline.py` | Computes batch features for AI Training from Historical Data. |
| `feature_engineering/online_pipeline.py` | Computes low-latency features for AI Inference from streaming ticks. |

### datasets/

| Path | Purpose |
|---|---|
| `datasets/__init__.py` | Marks package. |
| `datasets/historical/__init__.py` | Marks package. |
| `datasets/historical/corporate_actions.py` | Applies split/dividend adjustments to historical price series. |
| `datasets/historical/ohlcv_store.py` | Read/write interface to the time-series OHLCV store. |
| `datasets/loaders/__init__.py` | Marks package. |
| `datasets/loaders/training_dataset_loader.py` | Assembles labeled training datasets from historical data and features. |
| `datasets/schemas/dataset_schema.py` | Schema definitions/validation for dataset tables used in training and backtesting. |

### ai/

| Path | Purpose |
|---|---|
| `ai/__init__.py` | Marks package. |
| `ai/inference/__init__.py` | Marks package. |
| `ai/inference/canary_router.py` | Routes a configurable percentage of traffic to a challenger model version. |
| `ai/inference/model_loader.py` | Loads model artifacts from the MLOps registry into the serving process. |
| `ai/inference/predictor.py` | Runs model inference against online features and publishes inference.signal events. |
| `ai/mlops/__init__.py` | Marks package. |
| `ai/mlops/drift_detector.py` | Monitors live prediction distributions for drift against training-time baselines. |
| `ai/mlops/experiment_tracker.py` | Records experiment parameters, metrics, and lineage for each training run. |
| `ai/mlops/promotion_policy.py` | Encodes the criteria a candidate model must meet to be promoted to champion. |
| `ai/models/__init__.py` | Marks package. |
| `ai/models/model_definitions/__init__.py` | Marks package. |
| `ai/models/model_definitions/lstm_price_model.py` | Model architecture definition (structure only, no training logic). |
| `ai/models/registry_client.py` | Client implementing core/ports/model_registry_port.py against the MLOps registry. |
| `ai/training/__init__.py` | Marks package. |
| `ai/training/hyperparameter_search.py` | Hyperparameter search/tuning logic invoked by the trainer. |
| `ai/training/trainer.py` | Orchestrates a single training run: load data, fit model, evaluate. |
| `ai/training/validation.py` | Holdout validation and metric computation for trained models. |

### strategies/

| Path | Purpose |
|---|---|
| `strategies/__init__.py` | Marks package. |
| `strategies/base_strategy.py` | Abstract base class defining the strategy interface (on_signal, on_tick, produce_intent). |
| `strategies/implementations/__init__.py` | Marks package. |
| `strategies/implementations/mean_reversion_strategy.py` | Concrete mean-reversion strategy implementation. |
| `strategies/implementations/momentum_strategy.py` | Concrete momentum-based strategy implementation. |
| `strategies/strategy_registry.py` | Registers and resolves strategy implementations by name/version from Configuration. |

### risk/

| Path | Purpose |
|---|---|
| `risk/__init__.py` | Marks package. |
| `risk/circuit_breaker.py` | Kill-switch logic that halts new orders platform-wide on severe breach conditions. |
| `risk/limit_rules.py` | Definitions of individual limit rules (position size, drawdown, concentration). |
| `risk/risk_manager.py` | Core risk gating logic: evaluates strategy intents against limits and exposure. |

### portfolio/

| Path | Purpose |
|---|---|
| `portfolio/__init__.py` | Marks package. |
| `portfolio/ledger.py` | Double-entry style ledger recording all position and cash movements. |
| `portfolio/pnl_calculator.py` | Computes realized/unrealized P&L from ledger entries. |
| `portfolio/portfolio_manager.py` | Consumes fills and maintains the authoritative in-memory/DB-backed portfolio state. |

### execution/

| Path | Purpose |
|---|---|
| `execution/__init__.py` | Marks package. |
| `execution/execution_port.py` | Shared abstract interface implemented identically by paper_trading and live_trading adapters. |
| `execution/order_manager.py` | Coordinates order submission, tracks lifecycle, and routes to the active execution adapter. |
| `execution/order_state_machine.py` | Defines valid order state transitions (new -> partial -> filled/cancelled/rejected). |

### paper_trading/

| Path | Purpose |
|---|---|
| `paper_trading/__init__.py` | Marks package. |
| `paper_trading/simulator.py` | Simulates order fills against live market data without touching a real venue. |
| `paper_trading/slippage_model.py` | Models realistic slippage/latency for simulated fills. |

### live_trading/

| Path | Purpose |
|---|---|
| `live_trading/__init__.py` | Marks package. |
| `live_trading/broker_gateway.py` | Real venue/broker connectivity implementing the execution_port interface. |
| `live_trading/fix_session_manager.py` | Manages FIX session lifecycle (logon, heartbeats, failover) with the live venue. |

### backtesting/

| Path | Purpose |
|---|---|
| `backtesting/__init__.py` | Marks package. |
| `backtesting/performance_metrics.py` | Computes Sharpe, drawdown, win rate, and other backtest performance metrics. |
| `backtesting/replay_engine.py` | Replays historical data through the real Strategy/Risk logic to evaluate performance. |
| `backtesting/report_generator.py` | Generates a human-readable backtest report from performance metrics. |

### scheduler/

| Path | Purpose |
|---|---|
| `scheduler/__init__.py` | Marks package. |
| `scheduler/job_scheduler.py` | Core scheduling loop that triggers registered jobs on cron/event schedules. |
| `scheduler/jobs/__init__.py` | Marks package. |
| `scheduler/jobs/eod_reconciliation_job.py` | Triggers end-of-day portfolio reconciliation. |
| `scheduler/jobs/nightly_training_job.py` | Triggers the AI Training service on a nightly schedule. |
| `scheduler/jobs/periodic_backtest_job.py` | Triggers periodic backtests against the current champion model/strategy. |

### monitoring/

| Path | Purpose |
|---|---|
| `monitoring/__init__.py` | Marks package. |
| `monitoring/health_checks.py` | Liveness/readiness probe handlers used by Kubernetes. |
| `monitoring/metrics_exporter.py` | Exposes service metrics (latency, throughput, error rate) for scraping. |

### alerts/

| Path | Purpose |
|---|---|
| `alerts/__init__.py` | Marks package. |
| `alerts/alert_manager.py` | Evaluates alert rules and routes notifications to the appropriate channel(s). |
| `alerts/channels/__init__.py` | Marks package. |
| `alerts/channels/pagerduty_channel.py` | Sends paging alerts to PagerDuty for on-call escalation. |
| `alerts/channels/slack_channel.py` | Sends alert notifications to Slack. |

### api/

| Path | Purpose |
|---|---|
| `api/__init__.py` | Marks package. |
| `api/auth/__init__.py` | Marks package. |
| `api/auth/oauth_provider.py` | OIDC/OAuth2 integration for identity verification. |
| `api/auth/rbac.py` | Role/attribute-based access control checks (trader/risk-officer/admin tiers). |
| `api/middleware/__init__.py` | Marks package. |
| `api/middleware/auth_middleware.py` | Validates JWTs and attaches identity/role context to each request. |
| `api/middleware/rate_limit_middleware.py` | Applies per-client rate limiting at the API edge. |
| `api/routers/__init__.py` | Marks package. |
| `api/routers/auth_router.py` | Endpoints for login, token refresh, and session management. |
| `api/routers/orders_router.py` | Endpoints for submitting/querying orders (paper and live, per permission). |
| `api/routers/portfolio_router.py` | Read endpoints for positions, balances, and P&L. |
| `api/routers/strategies_router.py` | Endpoints for listing/configuring available strategies. |
| `api/schemas/__init__.py` | Marks package. |
| `api/schemas/request_response_models.py` | Request/response DTOs used by the API routers. |

### dashboard/

| Path | Purpose |
|---|---|
| `dashboard/__init__.py` | Marks package. |
| `dashboard/static/.gitkeep` | Placeholder for static assets (CSS/JS) directory. |
| `dashboard/templates/.gitkeep` | Placeholder for server-rendered template files. |
| `dashboard/views.py` | Operator dashboard view handlers reading from the API Layer's read endpoints. |

### tests/

| Path | Purpose |
|---|---|
| `tests/__init__.py` | Marks package. |
| `tests/conftest.py` | Shared pytest fixtures (test DB, test Kafka, fake clock) available to all test suites. |
| `tests/e2e/.gitkeep` | Placeholder for end-to-end tests running the full signal-to-fill pipeline against paper trading. |
| `tests/fixtures/.gitkeep` | Placeholder for shared test fixtures and sample market data. |
| `tests/integration/.gitkeep` | Placeholder for integration tests exercising Kafka/DB/Cache together. |
| `tests/unit/.gitkeep` | Placeholder for unit tests (one per core/ and module component). |

### docker/

| Path | Purpose |
|---|---|
| `docker/api.Dockerfile` | Container image definition for the API service. |
| `docker/base.Dockerfile` | Common base image layer (Python runtime, shared system deps) other Dockerfiles build from. |
| `docker/execution.Dockerfile` | Container image definition for the Order Execution service. |
| `docker/inference.Dockerfile` | Container image definition for the AI Inference service. |
| `docker/training.Dockerfile` | Container image definition for the AI Training service (GPU base image). |

### deployment/

| Path | Purpose |
|---|---|
| `deployment/helm/.gitkeep` | Placeholder for Helm charts packaging the platform's services. |
| `deployment/k8s/base/.gitkeep` | Placeholder for base Kubernetes manifests shared across environments. |
| `deployment/k8s/overlays/dev/.gitkeep` | Placeholder for dev-environment Kustomize overlay. |
| `deployment/k8s/overlays/live/.gitkeep` | Placeholder for live-environment Kustomize overlay (isolated namespace/network policy). |
| `deployment/k8s/overlays/paper/.gitkeep` | Placeholder for paper-environment Kustomize overlay. |
| `deployment/terraform/.gitkeep` | Placeholder for infrastructure-as-code definitions (clusters, networking, managed data services). |

### scripts/

| Path | Purpose |
|---|---|
| `scripts/deploy.sh` | Wraps CI/CD deploy steps for manual/local invocation. |
| `scripts/run_migrations.sh` | Applies pending database migrations against the target environment. |
| `scripts/seed_test_data.sh` | Loads sample market/account data for local development and demos. |
| `scripts/setup_dev_env.sh` | One-shot script to bootstrap a local dev environment (venv, deps, pre-commit, docker-compose up). |


---
**Phase 2 complete. No implementation code included. Awaiting approval before Phase 3.**
