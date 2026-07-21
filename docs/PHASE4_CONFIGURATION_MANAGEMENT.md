# Phase 4 — Configuration Management

Status: **complete**. This document describes the configuration system implemented
in `config/`, how it composes with the rest of the platform, and how to operate it.

## 1. Goals and constraints

Phase 4 turns `config/` from a Phase 2 scaffold (docstring stubs only) into a real,
typed, validated, environment-aware configuration system, without altering any
approved repository structure:

- The three deployment environments remain **`dev` / `paper` / `live`**, exactly as
  named in `config/environments/` and `docs/PHASE2_REPOSITORY_STRUCTURE.md`. `paper`
  is the simulated-trading environment; `live` is the real-venue, production
  environment. No fourth "testing" deployment environment was introduced — automated
  tests run against `dev` semantics with values overridden via environment variables
  (see §7).
- No files were renamed or moved. `config/settings.py` and `config/config_client.py`
  keep their original names and roles per `docs/CODING_STANDARDS.md` §13; they were
  filled in, not replaced with something structurally different.
- Every new environment variable was added to `.env.example`, and the original Phase
  2 variables (`ENVIRONMENT`, `KAFKA_BOOTSTRAP_SERVERS`, `DATABASE_URL`, `REDIS_URL`,
  `JWT_SECRET`, `MARKET_DATA_VENDOR_API_KEY`) still work unchanged.

## 2. Package layout

```
config/
├── __init__.py            # public exports: Settings, get_settings, Environment, ConfigClient
├── environment.py         # Environment enum (dev/paper/live) + resolve_environment()
├── exceptions.py          # ConfigurationError hierarchy
├── base.py                # shared BaseSettings config, path constants
├── modules/                # one file per configuration domain (see §3)
│   ├── application.py, database.py, postgresql.py, redis.py, kafka.py,
│   │   binance.py, ai_models.py, feature_engineering.py, logging.py,
│   │   monitoring.py, api.py, websocket.py, security.py
├── loader.py               # YAML overlay + .env merge -> os.environ (see §4)
├── validation.py           # cross-module validation rules (see §5)
├── factory.py              # SettingsFactory: bootstrap + cache (see §6)
├── settings.py             # root Settings composition + get_settings()
├── config_client.py        # hot-reload registry for runtime-tunable values (see §8)
├── di.py                   # FastAPI-compatible Depends() providers (see §9)
└── environments/
    ├── dev.yaml, paper.yaml, live.yaml   # non-secret, per-environment overlays
```

## 3. Configuration modules

Each domain owns one file in `config/modules/`, one Pydantic Settings v2 class, and
one environment-variable prefix. Every module is independently instantiable (useful
for unit tests and for narrow dependency injection) and is also composed as a field
on the root `Settings` in `settings.py`.

| Module | Class | Env prefix | Purpose |
|---|---|---|---|
| `application.py` | `ApplicationSettings` | `APP_` | Service metadata, debug flag, timezone |
| `database.py` | `DatabaseSettings` | `DATABASE_` | SQLAlchemy engine/pool knobs, optional full DSN override |
| `postgresql.py` | `PostgreSQLSettings` | `POSTGRES_` | Discrete Postgres connection identity, DSN builder |
| `redis.py` | `RedisSettings` | `REDIS_` | Redis connection/pool config, DSN builder |
| `kafka.py` | `KafkaSettings` | `KAFKA_` | Broker list, security protocol, producer/consumer tuning |
| `binance.py` | `BinanceSettings` | `BINANCE_` | REST/WebSocket endpoints, credentials, testnet switch |
| `ai_models.py` | `AIModelSettings` | `AI_MODEL_` | Registry URI, inference limits, canary routing, drift thresholds |
| `feature_engineering.py` | `FeatureEngineeringSettings` | `FEATURE_` | Online/offline feature store config |
| `logging.py` | `LoggingSettings` | `LOG_` | Log level, JSON formatting, correlation id, rotation |
| `monitoring.py` | `MonitoringSettings` | `MONITORING_` | Metrics, tracing, health-check cadence |
| `api.py` | `APISettings` | `API_` | HTTP bind address, CORS, rate limits, docs toggle |
| `websocket.py` | `WebSocketSettings` | `WEBSOCKET_` | WS bind address, heartbeat, connection limits |
| `security.py` | `SecuritySettings` | `SECURITY_` | JWT config, password policy, MFA, allowed hosts |

Backward-compatible aliases (so a pre-Phase-4 `.env` still works):

- `DatabaseSettings.url` reads `DATABASE_URL` directly (field name + prefix already
  resolve to that name).
- `RedisSettings.url` reads `REDIS_URL` the same way.
- `BinanceSettings.api_key` / `api_secret` also accept `MARKET_DATA_VENDOR_API_KEY` /
  `MARKET_DATA_VENDOR_API_SECRET`.
- `SecuritySettings.jwt_secret` also accepts `JWT_SECRET`.

## 4. Layered loading and precedence

`config/loader.py` merges three sources into `os.environ` before any settings class
reads it, **highest precedence first**:

1. **Real process environment variables** — whatever the shell, container runtime, or
   secrets manager already injected. Never overwritten.
2. **`.env` file** — local developer convenience (git-ignored).
3. **`config/environments/{dev,paper,live}.yaml`** — non-secret, environment-tier
   defaults (e.g. `paper.yaml` turns on SASL/TLS; `live.yaml` disables API docs).
4. **Each module's own `Field(default=...)`** — applied by Pydantic itself if nothing
   above supplied a value.

`bootstrap_environment()` only ever *fills in missing* variables via
`os.environ.setdefault` semantics — it can never clobber a real deployment secret.
YAML overlay sections map to module prefixes (e.g. `redis.host` → `REDIS_HOST`); see
`config.loader._SECTION_ENV_PREFIXES`.

## 5. Validation

Two layers:

- **Field-level** (in each module): types, numeric ranges, enum membership (e.g.
  `LoggingSettings.level` must be one of `DEBUG|INFO|WARNING|ERROR|CRITICAL`;
  `KafkaSettings.security_protocol` must be a real protocol name).
- **Cross-module** (`config/validation.py`, run once via `Settings.model_post_init`):
  rules that span more than one module or depend on the resolved environment, e.g.
  - `application.debug` must be `False` outside `dev`.
  - `security.jwt_secret` / `postgres.password` must not still be the shipped
    placeholder outside `dev`.
  - `api.cors_allowed_origins` must not contain `"*"` outside `dev`.
  - `api.docs_enabled` must be `False` in `live`.
  - `binance.api_key`/`api_secret` must be set, and `binance.use_testnet` must be
    `False`, in `live`.
  - `security.secure_cookies` must be `True`, and `postgres.sslmode` must not be
    `disable`/`allow`, outside `dev`.
  - `monitoring.tracing_exporter_endpoint` is required whenever
    `monitoring.tracing_enabled` is `True`.

  All violations are collected and raised together in a single
  `ConfigurationValidationError`, so a misconfigured deploy fails fast at boot with a
  complete list of what to fix, not one error at a time.

## 6. Loader, factory, and DI

- **`config/factory.py` — `SettingsFactory`**: the only place that combines
  "which environment" with "build and validate a `Settings`". Caches one instance per
  environment (thread-safe), and rolls back its own previously-applied overlay
  variables before bootstrapping a *different* environment in the same process (so
  switching environments mid-process — as this test suite and any
  multi-environment CLI tooling does — never leaks one environment's YAML defaults
  into another).
- **`config/settings.py` — `get_settings()`**: the function most code should call.
  Thin wrapper around `SettingsFactory.create()`, kept in `settings.py` because that
  is the module `docs/CODING_STANDARDS.md` §13 already designates as the platform's
  settings entry point.
- **`config/di.py`**: one `Depends()`-compatible provider per module
  (`get_redis_settings`, `get_kafka_settings`, ...) plus `get_settings()` for the full
  tree. Handlers should depend on the narrowest module they need. Not yet wired into
  `app/*_service/main.py` — those files are still Phase 2 stubs; this phase only
  had to make the providers available for that later wiring.

## 7. Testing

- `tests/unit/config/` — one module's worth of behavior per file: `Environment`
  enum/aliases, the exception hierarchy, every settings module's defaults/overrides/
  validation, the loader's YAML-flattening and precedence logic in isolation,
  `SettingsFactory` caching/rollback, `ConfigClient`, and the DI providers.
- `tests/integration/config/` — exercises the *real* YAML overlays shipped in
  `config/environments/` end-to-end through `SettingsFactory` for all three
  environments (including the "boot must fail without secrets" and "boot succeeds
  once secrets are supplied" paths for `paper`/`live`), the fully-composed settings
  tree, DI wiring identity, and the full env-var/`.env`/YAML precedence chain via
  temporary files.
- Every test that touches `os.environ` or the factory cache uses the
  `isolated_environment` fixture (`tests/{unit,integration}/config/conftest.py`),
  which snapshots/restores `os.environ` and clears `SettingsFactory`'s cache before
  and after each test, so tests never leak state into each other regardless of run
  order.
- There is no separate "testing" deployment environment: tests construct `Settings`
  directly (or via the factory against `dev`) with `pytest.MonkeyPatch.setenv`
  supplying whatever a given test needs, matching
  `docs/PHASE3_ENGINEERING_STANDARDS.md`'s existing testing strategy.

Run:

```
pip install -r requirements/dev.txt
pytest tests/unit/config tests/integration/config -v
```

## 8. Hot-reloadable values (`config_client.py`)

Per `docs/CODING_STANDARDS.md` §13, a small set of values (risk limits, feature
flags, strategy parameters) are meant to change at runtime via a `config.updated`
event stream, without a redeploy — distinct from everything above, which is fixed
for the lifetime of a process.

`ConfigClient` implements that contract as a thread-safe, in-process registry:
`register(key, initial_value)`, `get(key)`, `subscribe(key, callback)`,
`apply_update(event)` (rejects stale/out-of-order versions), `snapshot()`. It is
deliberately transport-agnostic — it does not import `confluent-kafka` or depend on
`shared/messaging/` directly, because that Kafka wiring does not exist yet in this
scaffold and `config/` must stay a low-level module other layers depend on, not the
other way around (Clean Architecture dependency direction). When the `config.updated`
Kafka consumer is implemented in a later phase, it only needs to call
`get_config_client().apply_update(event)` for every consumed message.

## 9. Operational reference

### 9.1 Precedence example

```
# config/environments/paper.yaml sets:
#   security.secure_cookies: true
# A real deployment additionally sets, via its secrets manager:
export SECURITY_JWT_SECRET="<real secret>"
```

Both are honored: the YAML supplies the non-secret default, the real environment
variable supplies the secret that must never appear in a checked-in file.

### 9.2 Adding a new configuration value

1. Add the field to the relevant module in `config/modules/` (with a `description=`
   and appropriate validation).
2. Add the corresponding variable to `.env.example` under that module's section.
3. If it needs a non-default value in a given environment, add it to that
   environment's YAML overlay under the matching section name.
4. If the value's correctness depends on the environment or another module, add a
   rule to `config/validation.py`.
5. Add/extend unit tests in `tests/unit/config/test_modules.py`.

### 9.3 Adding a new configuration module

1. Create `config/modules/<name>.py` following the pattern in any existing module
   (own `env_prefix`, `ModuleBaseSettings` base, field validators as needed).
2. Export it from `config/modules/__init__.py`.
3. Add it as a field on `Settings` in `config/settings.py`.
4. Add its section name → prefix mapping to `config.loader._SECTION_ENV_PREFIXES`.
5. Add a DI provider in `config/di.py`.
6. Add unit tests (`tests/unit/config/test_modules.py`) and, if it participates in
   cross-module rules, integration coverage.

## 10. Known scope boundaries

- `config/di.py` providers are defined but not yet imported by any `app/*_service`
  entrypoint — those remain Phase 2 stubs pending their own implementation phase.
- `config_client.py` defines the hot-reload contract but has no live Kafka consumer
  wired to it yet — `shared/messaging/` does not exist yet either; that integration
  is for the phase that implements the messaging layer.
- Production secret values are never generated or stored by this phase — they must
  be injected as real process environment variables by whatever secrets manager is
  used at deploy time, per `docs/PHASE1_ARCHITECTURE.md` §13.
