# Coding Standards

Applies to every Python file under `app/`, `core/`, `shared/`, `config/`, `database/`, `cache/`,
`market_data/`, `websocket/`, `feature_engineering/`, `datasets/`, `ai/` (or its current top-level
equivalents `training/`, `inference/`, `models/`, `mlops/` — see the note in
`docs/PHASE3_ENGINEERING_STANDARDS.md`), `strategies/`, `risk/`, `portfolio/`, `execution/`,
`paper_trading/`, `live_trading/`, `backtesting/`, `scheduler/`, `monitoring/`, `alerts/`, `api/`,
`dashboard/`, `tests/`. Enforced automatically by `ruff`, `mypy`, and `pre-commit` (already
configured at repo root from Phase 2) — this document explains the rules those tools enforce, plus
rules no linter can check.

---

## 1. Coding Standards

- **Python version:** 3.11+, use modern syntax (`match`, `X | Y` unions, `dataclasses`/`pydantic`
  models over hand-rolled `__init__` boilerplate).
- **Line length:** 100 columns (matches `ruff.toml`).
- **Formatting:** `ruff format` is authoritative — never hand-format against it.
- **Typing:** every public function/method has full type hints. `core/` and `shared/` are held to
  `disallow_untyped_defs` (see `mypy.ini`); other packages should follow the same bar even where not
  yet enforced.
- **Immutability by default:** domain entities and value objects (`core/domain/`) prefer frozen
  dataclasses / immutable pydantic models. Mutation is explicit and localized (e.g. an aggregate's
  own method), never a bag of public setters.
- **No silent `except:`** — always catch a specific exception type; see §11 Error Handling.
- **No business logic in `__init__.py`** — these files exist only to mark packages / define the
  public re-export surface of a package.
- **One responsibility per module file** — a file in `risk/`, `portfolio/`, etc. should be
  understandable without needing to read three others; if a file is doing two unrelated things,
  split it.
- **Pure functions where possible** — especially in `feature_engineering/definitions/` and
  `backtesting/performance_metrics.py`: same input, same output, no hidden I/O. This is what makes
  backtests and live inference reproducible.
- **No `print()`** anywhere outside `scripts/` — use the shared logger (§12).

## 2. Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Modules / files | `snake_case.py` | `order_state_machine.py` |
| Packages / directories | `snake_case` | `feature_engineering/` |
| Classes | `PascalCase` | `RiskManager`, `OrderRepositoryPort` |
| Functions / methods | `snake_case`, verb-first | `evaluate_strategy()`, `gate_risk()` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_POSITION_SIZE` |
| Private members | leading underscore | `_internal_cache` |
| Ports (abstract interfaces) | suffix `Port` | `MarketDataPort`, `ModelRegistryPort` |
| Concrete adapters implementing a port | suffix describing the tech/venue | `KafkaEventPublisher`,
  `PostgresOrderRepository` |
| Use cases | verb phrase matching the business action | `SubmitOrder`, `ReconcilePortfolio` |
| Domain events | past-tense noun phrase | `OrderFilled`, `RiskBreached`, `TickReceived` |
| Kafka topics | dot-namespaced, present participle for streams | `market.ticks.<symbol>`,
  `orders.fills`, `risk.approved` |
| Test files | mirror the module under test, prefix `test_` | `test_risk_manager.py` |
| Environment variables | `UPPER_SNAKE_CASE` | `DATABASE_URL`, `KAFKA_BOOTSTRAP_SERVERS` |

Names describe **what**, not **how** — `OrderRepositoryPort`, not `OrderDbInterface`; the port must
stay technology-agnostic even if today's only implementation is Postgres.

## 3. Folder Conventions

- Each top-level folder corresponds to exactly one Phase 1 architectural module (Market Data,
  Risk Manager, Portfolio Manager, etc.) or one cross-cutting concern (`shared/`, `config/`,
  `database/`, `cache/`). Do not introduce a new top-level folder without amending
  `docs/PHASE2_REPOSITORY_STRUCTURE.md` first — folder structure is Phase 2's approved artifact.
- `core/` never imports from any domain-specific folder (`risk/`, `execution/`, etc.) — dependency
  flows one way, from domain folders inward toward `core/`, never the reverse. See §5 and §7.
- `app/<x>_service/` contains **only** wiring (dependency construction, startup/shutdown) — no
  business logic. If you find yourself writing an `if` that decides trading behavior inside
  `app/`, that logic belongs in the corresponding domain folder instead.
- Tests mirror source layout: a file at `risk/risk_manager.py` has its unit test at
  `tests/unit/risk/test_risk_manager.py`.
- Anything reusable across 3+ domain folders belongs in `shared/`, not copy-pasted.

## 4. Import Conventions

- **Absolute imports only** from the repo root (e.g. `from core.domain.entities.order import Order`),
  never relative dot-imports (`from ..order import Order`) — absolute imports make grep-based
  refactors and dependency audits reliable.
- **Import order** (enforced by ruff's `I` rules): standard library → third-party → first-party
  (`core`, `shared`, then the specific domain package), each group alphabetized, one blank line
  between groups.
- **No wildcard imports** (`from x import *`) anywhere.
- **No circular imports** — if two folders need each other's types, extract the shared type into
  `core/domain/` or `shared/` instead of importing sideways.
- A domain folder (e.g. `execution/`) may import from `core/` and `shared/` freely, but **must not**
  import concrete adapters from another domain folder (e.g. `execution/` must not import
  `database.repositories.order_repository` directly — it depends on
  `core.ports.order_repository_port.OrderRepositoryPort` and receives a concrete implementation via
  dependency injection at the `app/` composition root).

## 5. Dependency Rules

1. `core/` depends on nothing outside the standard library and `shared/` primitives — no Kafka
   client, no ORM, no HTTP framework may ever be imported inside `core/domain/` or `core/ports/`.
2. Domain folders (`risk/`, `portfolio/`, `execution/`, `strategies/`, etc.) depend on `core/` and
   `shared/`, and receive their adapters (repository, event publisher, etc.) as constructor
   arguments — they never import a concrete adapter module directly.
3. Adapter folders (`database/`, `cache/`, `market_data/feed_adapters/`, `live_trading/`,
   `paper_trading/`) implement `core/ports/` interfaces and may freely depend on external libraries.
4. `app/` is the only layer allowed to import from every other layer — it is the composition root
   that wires concrete adapters into domain use cases.
5. No package may depend on `tests/`. No package outside `scripts/` may depend on `scripts/`.
6. `requirements/training.txt` (heavy ML/GPU deps) is only ever imported by `ai/training` (or its
   current top-level equivalent, `training/`) and `ai/models` — no other service's runtime should
   pull in `torch` just to import a shared type; shared types live in `core/domain/`.

## 6. SOLID Principles — applied to this repository

- **Single Responsibility:** each domain folder owns exactly one Phase 1 module's responsibility.
  `risk_manager.py` gates trades; it does not also compute P&L (that's `portfolio/pnl_calculator.py`).
- **Open/Closed:** new strategies are added by creating a new file in
  `strategies/implementations/` that extends `base_strategy.py` — existing strategy code is never
  edited to add a new strategy. Same pattern for new risk rules (`risk/limit_rules.py`) and new
  execution venues (new adapter implementing `execution/execution_port.py`).
- **Liskov Substitution:** `paper_trading/simulator.py` and `live_trading/broker_gateway.py` both
  implement `execution/execution_port.py` and must be fully interchangeable from
  `execution/order_manager.py`'s point of view — this is what makes "promote a strategy from paper
  to live" a config change, not a code change.
- **Interface Segregation:** ports in `core/ports/` are small and single-purpose
  (`MarketDataPort`, `OrderRepositoryPort`, `ModelRegistryPort` are separate interfaces) — no
  "God interface" that forces an adapter to implement methods it doesn't need.
- **Dependency Inversion:** high-level modules (`strategies/`, `risk/`) depend on abstractions
  (`core/ports/`), never on low-level modules (`database/`, `live_trading/`) — enforced by §5.

## 7. Clean Architecture Rules

Concentric layers, dependencies point inward only:

```
app/ (frameworks & drivers / composition root)
  → domain folders (risk/, portfolio/, strategies/, execution/, ...)  (interface adapters)
      → core/use_cases  (application business rules)
          → core/domain  (enterprise business rules — entities, value objects, events)
```

- `core/domain/` has zero knowledge that Kafka, Postgres, or FastAPI exist.
- `core/use_cases/` orchestrates domain entities via `core/ports/` interfaces only.
- Domain folders implement the use cases for their bounded context and translate between
  `core/domain/` entities and whatever wire format their adapters need.
- `app/` is the only place allowed to know concrete technology choices end-to-end (which DB driver,
  which Kafka client, which model registry implementation).
- A change to the persistence technology (e.g. swap Postgres for another RDBMS) should require
  changes only inside `database/repositories/` and the `app/` wiring — never inside `core/` or the
  domain folders.

## 8. Dependency Injection Guidelines

- Constructor injection only — no service locator pattern, no global singletons reached for via
  import-time side effects.
- Every domain class that needs an adapter (repository, publisher, cache) declares it as a typed
  constructor parameter against the **port**, e.g. a `RiskManager` takes a
  `PortfolioRepositoryPort`, not a concrete `PostgresPortfolioRepository`.
- Wiring happens exactly once, in `app/<x>_service/main.py`, where concrete adapters are
  constructed and passed down. No domain or adapter module constructs its own dependencies.
- Test code injects fakes/in-memory implementations of the same ports — this is the entire reason
  ports exist (§6 Dependency Inversion) and is what keeps `tests/unit/` free of Kafka/DB/Redis.
- Configuration values (limits, symbols, feature flags) are injected via `config/settings.py` /
  `config/config_client.py` — never read directly from `os.environ` inside domain code.

## 9. Repository Pattern Guidelines

- Every persistent aggregate (`Order`, `Position`/`Account` via the ledger) has exactly one
  repository interface in `core/ports/` and exactly one primary implementation in
  `database/repositories/`.
- Repository methods are named by intent, not by SQL shape: `get_open_orders_for_account(...)`,
  not `query(...)`.
- Repositories return/accept `core/domain/entities` — never leak ORM model objects or raw rows
  across the port boundary.
- No business logic inside a repository — validation, invariants, and calculations belong in the
  domain entity or a use case, not in `database/repositories/*.py`.
- A repository method does exactly one unit of work; multi-step transactions are composed by a use
  case calling the repository within a transaction boundary, not by chaining repository calls that
  each open their own transaction.

## 10. Service Layer Guidelines

- "Services" in this repo are the `core/use_cases/*.py` orchestrators plus the domain-folder
  managers (`RiskManager`, `PortfolioManager`, `OrderManager`) — collectively the application/service
  layer between `app/` wiring and `core/domain/` entities.
- A service method should read as the business process it represents (e.g. `gate_risk(intent) ->
  RiskDecision`), coordinating repositories/publishers/entities — it does not contain low-level
  I/O details (those live in adapters it calls through ports).
- Services are stateless between calls where possible; any necessary in-memory state (e.g. Risk
  Manager's real-time exposure cache) is explicitly documented as such and backed by `cache/` for
  recoverability, not held only in process memory.
- Cross-cutting concerns (logging, correlation IDs, metrics) are applied via shared decorators/
  middleware from `shared/`, not hand-rolled per service.

## 11. Error Handling Strategy

- All domain-specific exceptions derive from the shared hierarchy in
  `shared/errors/exceptions.py` (e.g. `DomainError` → `RiskBreachError`, `ExecutionError`,
  `InvalidOrderStateError`) — never raise a bare `Exception` or a stdlib exception from domain code.
- **Fail closed on uncertainty in the risk/execution path:** if the Risk Manager cannot confirm
  current exposure, it raises/returns a rejection rather than allowing a trade through — see
  `docs/PHASE1_ARCHITECTURE.md` §10.
- Exceptions crossing a service boundary are translated at the adapter edge into the appropriate
  wire representation (HTTP error at `api/`, a `risk.rejected`/`orders.status` event at the
  messaging edge) — internal exception types never leak into external payloads.
- Every `except` clause either: (a) handles the error meaningfully and continues, (b) re-raises a
  more specific domain exception with context, or (c) logs at the correct severity and re-raises —
  never a silent `pass`.
- Idempotency: consumers of Kafka events must handle re-delivery (at-least-once) without
  double-processing — dedup by event ID before mutating state (see
  `docs/PHASE1_ARCHITECTURE.md` §10 Fault Tolerance).

## 12. Logging Strategy

- Use `shared/logging/logger.py` exclusively — never `logging.getLogger` ad hoc or `print`.
- Every log line is structured (JSON), includes `correlation_id`
  (`shared/logging/correlation.py`) propagated from the originating event/request, `service_name`,
  and `severity`.
- Log levels: `DEBUG` (local dev detail), `INFO` (normal lifecycle events — order submitted, fill
  received), `WARNING` (recoverable anomaly — stale feature, retried call), `ERROR` (operation
  failed, needs investigation), `CRITICAL` (risk breach, kill-switch engaged — must also alert, see
  `alerts/`).
- Never log secrets, API keys, or full account credentials — `shared/logging/logger.py` redaction
  rules apply to any field matching the sensitive-key patterns.
- Order- and risk-path logs are treated as part of the audit trail (`docs/PHASE1_ARCHITECTURE.md`
  §6 Event Flow) — they must never be sampled/dropped, only debug-level application logs may be.

## 13. Configuration Management

- All configuration is loaded through `config/settings.py` (typed, validated at boot) — no module
  reads `os.environ` directly except `config/settings.py` itself.
- Environment overlays (`config/environments/dev.yaml`, `paper.yaml`, `live.yaml`) hold
  environment-specific values; secrets are never committed — they come from the secrets manager
  referenced in `docs/PHASE1_ARCHITECTURE.md` §13, injected as environment variables at deploy time.
- Hot-reloadable values (risk limits, feature flags, strategy parameters) are read through
  `config/config_client.py`, which subscribes to `config.updated` — code must not cache such values
  beyond a single use without registering for update notification.
- `.env.example` is the single source of truth for which environment variables exist; add to it
  whenever a new variable is introduced.

## 14. Security Coding Guidelines

- No credentials, API keys, or tokens in source, config committed to git, or logs — use the
  secrets manager / environment injection only (see `.env.example` for the variable, never the
  value).
- All external input (API Layer request bodies, vendor feed payloads) is validated against a typed
  schema (`api/schemas/`, `core/domain/events/`) before use — never trust a payload shape.
- Authorization checks (`api/auth/rbac.py`) happen in middleware, not scattered ad hoc across
  routers — every new endpoint in `api/routers/` must declare its required role/permission.
- Any action that affects a live account (order submission, limit override) requires the elevated
  auth tier from `docs/PHASE1_ARCHITECTURE.md` §13 — never gate this only in the UI.
- Dependencies are pinned (`requirements/prod.txt`) and scanned in CI; do not add a new third-party
  package without checking it against the project's dependency policy in
  `docs/PHASE3_ENGINEERING_STANDARDS.md`.
- SQL access goes only through repositories using parameterized queries/ORM — no raw string-
  interpolated SQL anywhere.

---

*This document is normative for all new code from Phase 4 onward. It does not itself add any
business logic or modify existing scaffold files.*
