# Phase 5 — Logging System

**Status:** Implementation complete. Builds entirely on the Phase 4 configuration
system (`config.modules.logging.LoggingSettings`) and does not change the Phase 1
architecture or the Phase 2 repository structure.

---

## 1. What this phase built

| Requirement | Delivered in |
|---|---|
| JSON logging | `shared/logging/logger.py` — `JSONFormatter` |
| Console logging | `shared/logging/logger.py` — `PlainConsoleFormatter` |
| Colored logs (development) | `shared/logging/logger.py` — `ColoredConsoleFormatter` (TTY-aware) |
| Rotating file logs | `shared/logging/logger.py` — `configure_logging()` wires a `RotatingFileHandler` when `LoggingSettings.file_path` is set |
| Request IDs | `shared/logging/correlation.py` — `get_request_id`/`set_request_id`; `api/middleware/exception_middleware.py` generates one per request |
| Correlation IDs | `shared/logging/correlation.py` — `correlation_context()`, propagated across an inbound `X-Correlation-ID` header |
| Performance timing | `shared/logging/timing.py` — `Timer`, `timed`, `timed_async` |
| Context propagation | `shared/logging/correlation.py` — `bind_context()`, `propagate_context`/`propagate_context_async`, plus a `LogRecord` factory that injects it everywhere automatically |
| Structured logging | Every log call passes structured `extra=` fields; `JSONFormatter` renders them as first-class JSON keys, not string-interpolated text |
| Log levels | Driven entirely by `LoggingSettings.level`; standard `DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL` |
| Audit logs | `shared/logging/audit.py` — `log_audit_event()`, a dedicated never-sampled channel |
| Security logs | `shared/logging/security.py` — `log_security_event()`, a dedicated never-sampled channel |
| Exception middleware | `api/middleware/exception_middleware.py` — `RequestContextMiddleware` |
| Global exception handler | `api/error_handlers.py` — `register_exception_handlers()` |
| Custom exceptions | `shared/errors/exceptions.py` — full `PlatformError` hierarchy |
| Retry logging | `shared/logging/retry.py` — `log_retries`, `log_retries_async` |
| Metrics logging | `shared/logging/metrics_log.py` — `log_metric`, `timed_metric`, `timed_metric_async` |
| Unit tests | `tests/unit/logging/`, `tests/unit/errors/`, `tests/unit/api/` |
| Integration tests | `tests/integration/logging/`, `tests/integration/api/` |
| Documentation | This file |

---

## 2. How it fits together

```
Request arrives
   │
   ▼
RequestContextMiddleware (api/middleware/exception_middleware.py)
   - resolves/generates correlation ID + request ID
   - binds them via shared.logging.correlation.correlation_context()
   - also stamps request.state.correlation_id / .request_id (see §4)
   - times the request, logs "request_completed" on the way out
   │
   ▼
Route / domain code
   - calls shared.logging.logger.get_logger(__name__) and logs normally
   - correlation_id / request_id / any bind_context(...) fields are attached
     automatically -- nothing has to be passed explicitly
   - raises shared.errors.exceptions.PlatformError subclasses for expected
     domain failures (RiskBreachError, NotFoundError, ValidationError, ...)
   │
   ▼
api/error_handlers.py (register_exception_handlers)
   - PlatformError -> its own http_status/error_code
   - RequestValidationError -> 422 with field errors
   - anything else (bare Exception) -> generic 500, full traceback logged,
     no internal detail leaked to the client
```

## 3. Using it in a service

```python
# app/<x>_service/main.py -- composition root (a later phase's concern; shown
# here only to illustrate the intended call sequence)

from config.factory import get_settings
from shared.logging.logger import configure_logging

settings = get_settings()
configure_logging(settings.logging, settings.environment)
```

```python
# anywhere else in that process
from shared.logging.logger import get_logger
from shared.logging.correlation import bind_context
from shared.logging.timing import timed

logger = get_logger(__name__)

@timed("compute_features")
def compute_features(symbol: str) -> dict:
    with bind_context(symbol=symbol):
        logger.info("starting feature computation")
        ...
```

```python
# FastAPI service wiring (api/api_service or similar, a later phase)
from fastapi import FastAPI
from api.error_handlers import register_exception_handlers
from api.middleware.exception_middleware import RequestContextMiddleware

app = FastAPI()
app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)
```

## 4. Notable design decisions (and one Starlette gotcha)

- **Context injection uses a `LogRecord` factory, not a per-handler filter.**
  A `logging.Filter` only runs for handlers it is explicitly attached to. Since
  test tooling (and potentially other future handlers) attach their own handler
  to the root logger, a factory — which runs for every record regardless of
  which handler(s) later process it — is the only approach that reliably
  injects `correlation_id`/`request_id`/bound context everywhere.

- **`configure_logging()` only ever removes handlers it previously added
  itself** (tracked in a private `_managed_handlers` list), not every handler on
  the root logger. Blindly wiping "all root handlers" would also strip any
  handler attached before `configure_logging()` ran for a legitimate reason —
  this was caught by the test suite (`caplog`'s own capture handler was being
  silently removed) and is exactly the kind of surprising behavior a shared
  logging module should never have in production either.

- **Starlette's exception-handling layering:** a handler registered for the
  bare `Exception` type runs in Starlette's outermost `ServerErrorMiddleware`,
  *outside every user-added middleware* — including `RequestContextMiddleware`.
  Handlers for more specific types (`PlatformError`, `RequestValidationError`)
  run in the inner `ExceptionMiddleware`, *inside* user middleware. That means
  the correlation ID bound via `contextvars` inside
  `RequestContextMiddleware.dispatch()` is already unbound (the `with` block
  exited while the exception propagated) by the time a bare-`Exception` handler
  runs. The fix: the middleware also stamps `request.state.correlation_id`
  /`.request_id`, which — being on the `Request` object itself rather than a
  contextvar — survives that boundary, and `api/error_handlers.py` reads from
  `request.state` first, falling back to the contextvar.

- **Audit and security logs are structurally exempt from sampling.** Every
  record they emit carries `NEVER_SAMPLE_ATTR`, which `_SamplingFilter` checks
  before applying `LoggingSettings.sample_rate` — consistent with
  `docs/CODING_STANDARDS.md` §12 ("order- and risk-path logs ... must never be
  sampled or dropped").

- **Metrics logging is log-based, not a Prometheus client.** `log_metric()`
  emits a structured record on the `metrics` channel; a later Monitoring phase
  (`monitoring/metrics_exporter.py`) owns the actual scrape endpoint and may
  consume these same records or instrument its own counters. This phase only
  guarantees a consistent event *shape*.

- **Retry logging here is observability, not policy.** `log_retries`/
  `log_retries_async` retry-and-log with exponential backoff, but venue-specific
  circuit-breaker/backoff *policy* for `execution/`/`live_trading/` belongs to
  those modules in a later phase; they may wrap this decorator or implement
  their own logic on top of it.

## 5. Cross-module validation rule added (Phase 4's `config/validation.py`)

One new rule: `logging.json_format` must be `True` outside `dev` (`paper`/`live`
require machine-parseable JSON so log shipping works uniformly; the colored
plain-text console formatter is a `dev`-only convenience). This follows the
exact pattern of every other rule already in that file — see
`docs/PHASE3_ENGINEERING_STANDARDS.md`/`docs/CODING_STANDARDS.md` for the
general cross-module validation approach.

## 6. Known pre-existing issues (not introduced by this phase)

Running `mypy .` and `ruff check .` across the *entire* repository still surfaces
a small number of pre-existing issues from Phase 2 and Phase 4 that this phase
did not touch and does not fix, per the "do not modify Phases 1–4 without
approval" rule:

- Six Phase 2 scaffold docstrings (`app/*/main.py`, `feature_engineering/definitions/technical_indicators.py`)
  exceed the 100-column limit.
- `tests/unit/config/test_settings.py`, `test_validation.py`, and `test_modules.py`
  (Phase 4) have pre-existing `mypy` `arg-type`/`unused-ignore` findings.

Every file this phase created or modified is 100% clean under both `ruff check`
and `mypy` in isolation (see the final report for the exact commands run).
