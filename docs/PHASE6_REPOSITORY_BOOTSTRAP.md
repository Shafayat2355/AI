# Phase 6 — Repository Bootstrap

**Status:** Implementation complete. Builds on the Phase 4 configuration system
and the Phase 5 logging system; does not change the Phase 1 architecture or the
Phase 2 repository structure, and introduces no new top-level packages beyond
what Phase 2 already scaffolded.

---

## 1. What this phase built

| Requirement | Delivered in |
|---|---|
| Base interfaces (repositories) | `core/ports/base_repository.py` — `RepositoryPort[EntityT, IdT]` |
| Base repositories | `database/repositories/base_repository.py` — `SQLAlchemyRepository[ModelT, IdT]` |
| Base services | `core/use_cases/base_service.py` — `BaseService[RequestT, ResponseT]` |
| Dependency Injection container | `core/container.py` — `Container`, `get_container`, `reset_container`, `get_db_session` |
| Utilities | `shared/utils/time_utils.py`, `shared/utils/serialization.py` |
| Constants | `shared/constants.py` — already complete as of Phase 3; unchanged |
| Enums | `shared/enums.py` — `HealthStatus`, `ServiceLifecycleState` |
| Shared models | `shared/models.py` — `BaseSchema`, `ComponentHealth`, `HealthCheckResponse`, `VersionResponse` |
| Common validators | `shared/validators.py` |
| Application startup | `app/api_service/main.py` — `create_app()`, `lifespan()` |
| Health endpoint | `monitoring/health_checks.py` — `GET /health/live`, `GET /health/ready` |
| Version endpoint | `monitoring/health_checks.py` — `GET /version` |
| Configuration initialization | Already complete (Phase 4); wired into `lifespan()` via `get_settings()` |
| Logging initialization | Already complete (Phase 5); wired into `lifespan()` via `configure_logging()` |
| Graceful startup | `app/api_service/main.py::lifespan` — configures logging, then `Container.startup()` |
| Graceful shutdown | `app/api_service/main.py::lifespan` — `Container.shutdown()` bounded by `ApplicationSettings.graceful_shutdown_timeout_seconds` |
| Basic FastAPI server | `app/api_service/main.py` — `create_app()` / module-level `app` |
| Pytest configuration | `pyproject.toml` — added `asyncio_mode = "auto"` |
| Pre-commit hooks | Already complete (Phase 3); unchanged |
| Ruff configuration | Already complete (Phase 3); unchanged |
| Black configuration | **Not added — see §5** |
| MyPy configuration | Already complete (Phase 3); unchanged |
| CI readiness | See §6 |
| Unit tests | `tests/unit/{shared,core,database,monitoring,app}/` |
| Integration tests | `tests/integration/{app,database}/` |
| Documentation | This file |

---

## 2. How it fits together

```
uvicorn app.api_service.main:app
   │
   ▼
create_app(settings)                      (app/api_service/main.py)
   - builds FastAPI(..., lifespan=lifespan)
   - adds CORSMiddleware (from APISettings)
   - adds RequestContextMiddleware          (Phase 5, unchanged)
   - register_exception_handlers(app)       (Phase 5, unchanged)
   - app.include_router(health_router)      (monitoring/health_checks.py)
   │
   ▼  (on process start, via FastAPI's lifespan protocol)
lifespan(app)
   - configure_logging(settings.logging, settings.environment)   (Phase 5)
   - container = get_container(settings)    (core/container.py)
   - await container.startup()              -> ServiceLifecycleState.READY
   - app.state.container = container
   │
   ▼  (serves traffic)
GET /health/live   -> always healthy if the process is running
GET /health/ready  -> HealthStatus.aggregate([container state, db reachability])
GET /version       -> ApplicationSettings.{name,version,description} + environment
   │
   ▼  (on SIGTERM / process stop)
lifespan(app) resumes after `yield`
   - asyncio.wait_for(container.shutdown(), timeout=graceful_shutdown_timeout_seconds)
       - DatabaseConnection.dispose()        (database/connection.py)
   - reset_container()
```

A concrete use case (a later phase's `core/use_cases/submit_order.py`, etc.)
subclasses `BaseService[RequestT, ResponseT]` and is invoked as
`await my_service(request)`, which wraps `execute()` with a `Timer` span and
uniform `PlatformError` propagation — see `core/use_cases/base_service.py`.

A concrete repository (a later phase's `database/repositories/order_repository.py`,
etc.) subclasses `SQLAlchemyRepository[ModelT, IdT]` with its own mapped model —
see `database/repositories/base_repository.py`. Its session comes from
`core.container.get_db_session`, a FastAPI dependency backed by the process-wide
`Container`'s single `DatabaseConnection`.

---

## 3. Using it in a service

```python
# app/<x>_service/main.py -- every other service's composition root follows the
# exact same shape as app/api_service/main.py

from fastapi import FastAPI
from api.error_handlers import register_exception_handlers
from api.middleware.exception_middleware import RequestContextMiddleware
from core.container import get_container
from monitoring.health_checks import router as health_router
from config.settings import get_settings

def create_app(settings=None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(lifespan=lifespan)  # see app/api_service/main.py for lifespan
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    return app
```

```python
# a future concrete use case
from core.use_cases.base_service import BaseService

class SubmitOrder(BaseService[SubmitOrderRequest, SubmitOrderResponse]):
    def __init__(self, orders: RepositoryPort[Order, UUID], **kwargs) -> None:
        super().__init__(**kwargs)
        self._orders = orders

    async def execute(self, request: SubmitOrderRequest) -> SubmitOrderResponse:
        ...  # timing/logging/error-propagation already handled by __call__
```

```python
# a future concrete repository
from database.repositories.base_repository import SQLAlchemyRepository
from database.models.order import OrderModel  # a later phase's mapped model

class OrderRepository(SQLAlchemyRepository[OrderModel, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OrderModel)
    # add order-specific query methods here; CRUD is inherited
```

```python
# FastAPI route wiring, using the DI container's session provider
from fastapi import Depends
from core.container import get_db_session

@router.get("/orders/{order_id}")
async def get_order(order_id: UUID, session: AsyncSession = Depends(get_db_session)):
    ...
```

---

## 4. Notable design decisions

- **Readiness is deliberately soft on the database in this phase.** No service
  depends on the database yet (no concrete repository/use case exists as of
  Phase 6), so `GET /health/ready` reports database unreachability as
  `HealthStatus.DEGRADED`, never `UNHEALTHY` — an unreachable DB does not, by
  itself, fail the readiness probe today. `DatabaseConnection.check_connection()`
  is implemented and exercised so a later phase that adds a hard database
  dependency only needs to change how its status feeds into
  `HealthStatus.aggregate()`, not add new plumbing.

- **Liveness checks nothing beyond "this handler executed."** A liveness probe
  that depends on downstream services causes Kubernetes to restart a perfectly
  healthy process just because a dependency is briefly unavailable — that
  distinction is why `/health/live` and `/health/ready` are separate endpoints
  rather than one.

- **`Container` builds resources lazily, not eagerly.** `DatabaseConnection` is
  created on first access to `Container.db`, not in `Container.__init__` — a
  service that never touches the database (none do yet) never pays for an
  engine it doesn't use, and `Container.shutdown()` is a safe no-op if `db` was
  never accessed.

- **PEP 695 generics, matching existing convention.** `RepositoryPort[EntityT,
  IdT]`, `BaseService[RequestT, ResponseT]`, and `SQLAlchemyRepository[ModelT,
  IdT]` all use Python 3.12's `class Foo[T]:` syntax rather than
  `typing.Generic`/`TypeVar`, matching the pattern already established in
  `shared/logging/correlation.py`'s `propagate_context[**P, R]`.

- **The engine-building code adapts to the SQLite backend used by tests.**
  `database/connection.py::_engine_kwargs` omits `pool_size`/`max_overflow`/etc.
  for a `sqlite` backend, since SQLAlchemy's SQLite dialect pool does not accept
  them — this is what lets `database/connection.py`, `database/base.py`, and
  `database/repositories/base_repository.py` all be integration-tested against
  a real, fast, in-memory database (`sqlite+aiosqlite:///:memory:`) instead of
  requiring a live Postgres instance just to run `pytest`.

- **`Container.get_container()` is a per-process singleton, matching
  `SettingsFactory.create`'s existing caching shape** (see
  `config/factory.py`). `tests/conftest.py` adds one new autouse fixture that
  resets both singletons (`SettingsFactory.clear_cache()` and
  `reset_container()`) before and after every test, so test order never
  matters — the same isolation guarantee
  `tests/unit/config/conftest.py::isolated_environment` already provides for
  environment variables, extended process-wide.

- **`BaseService.__call__` re-raises `PlatformError` untouched but logs and
  re-raises anything else.** An already-well-formed domain error (Phase 3's
  `PlatformError` hierarchy) needs no extra handling; an unexpected exception
  is logged with full context (`use_case_failed`, `channel=application`) so it
  is never silently swallowed, before propagating to `api/error_handlers.py`'s
  generic-500 handler exactly as Phase 5 already handles it.

---

## 5. Black configuration — intentionally not added

The task list for this phase includes "Complete Black configuration." Phase 3
already made and documented a different, incompatible choice:
`docs/CODING_STANDARDS.md` §"Formatting" states *"`ruff format` is
authoritative — never hand-format against it"*, and `.pre-commit-config.yaml`
runs `ruff-format`, not Black. Adding a Black configuration would either be
unused dead configuration or would conflict with the standard Phase 3 already
established. Per this task's instruction to preserve Phase 3 Engineering
Standards and not silently reorganize prior decisions, this phase leaves
formatting as **`ruff format`-only** and flags the conflict here rather than
introducing Black. If Black is genuinely wanted going forward, that is a Phase
3 policy change and should be made explicitly, not smuggled in as a Phase 6
side effect.

---

## 6. CI readiness

`.github/workflows/ci.yml` exists but is a placeholder (a single comment, no
actual workflow steps), predating this phase. Making it a real, runnable
workflow — checking out the repo, installing `requirements/dev.txt`, and
running `ruff check .`, `mypy .`, and `pytest` — was judged to be a change to
CI/deployment configuration outside the "framework code" scope of this task
(“Implement only the missing parts of Phase 6” / repository-bootstrap code),
and is flagged here rather than silently modified. Every command a real
workflow would run has been executed manually against this phase's changes;
see the final report for exact output. If Phase 6 approval includes wiring up
`ci.yml`, that's a small, well-scoped follow-up.

---

## 7. Known pre-existing issues (not introduced by this phase)

Running `mypy .` and `ruff check .` across the *entire* repository still
surfaces a small number of pre-existing issues from Phase 2 that this phase
did not touch and does not fix:

- Five Phase 2 scaffold docstrings (`app/*_service/main.py` other than
  `api_service`, `feature_engineering/definitions/technical_indicators.py`)
  exceed the 100-column limit.
- `ruff format --check .` flags 16 pre-existing files elsewhere in the repo as
  needing reformatting. This is a version-drift issue, not a real formatting
  problem: `requirements/dev.txt` pins an unversioned `ruff` (installs latest),
  while `.pre-commit-config.yaml` pins `ruff-pre-commit rev: v0.5.0` — the two
  ruff versions format slightly differently. Not introduced by, or fixed by,
  this phase.

Every file this phase created or modified is 100% clean under `ruff check`,
`ruff format --check`, and `mypy` in isolation — see the final report for the
exact commands and output.
