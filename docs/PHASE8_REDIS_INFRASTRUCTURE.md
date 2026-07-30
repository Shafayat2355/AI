# Phase 8 — Redis Infrastructure

**Status:** Implementation complete. Builds on Phase 4's `config/modules/redis.py`
and mirrors Phase 6/7's `database/connection.py`/`core/container.py` patterns
closely. Does not change the Phase 1 architecture, Phase 2 repository
structure, or any Phase 3–7 decision except the explicitly-flagged additive
edits in §4.

---

## 1. What Phase 4/2 already had (not rebuilt)

`config/modules/redis.py::RedisSettings` (pooling, TLS, timeouts, `key_prefix`,
`decode_responses`), `config/di.py::get_redis_settings`, the `redis` package
(pinned since Phase 2/4), and a `redis` service in `docker-compose.yml`.
`cache/redis_client.py` and `cache/cache_keys.py` existed only as one-line
docstring stubs — this phase is what actually implements them.

## 2. What Phase 8 adds

| Requirement | Delivered in |
|---|---|
| Redis / redis-py asyncio | `redis.asyncio` throughout `cache/` |
| Connection pool | `cache/redis_client.py::create_pool_from_settings`, `RedisConnection` |
| Health checks | `RedisConnection.check_connection()`, wired into `monitoring/health_checks.py` |
| TTL management | `CacheManager.get_ttl`/`touch`/`set(ttl_seconds=...)`, per-cache-type defaults in `RedisSettings` |
| Namespaced keys | `cache/cache_keys.py::build_key` + `NAMESPACE_*` constants |
| JSON serialization | `cache/serializers.py::JSONSerializer` (the default) |
| Binary serialization | `cache/serializers.py::PickleSerializer` |
| Prediction cache | `cache/prediction_cache.py::PredictionCache` |
| Market cache | `cache/market_cache.py::MarketCache` |
| Session cache | `cache/session_cache.py::SessionCache` |
| Rate limit cache | `cache/rate_limit_cache.py::RateLimitCache` |
| Distributed lock support | `cache/distributed_lock.py::DistributedLock` |
| Cache manager | `cache/cache_manager.py::CacheManager` |
| Cache decorators | `cache/decorators.py::cached`/`cache_invalidate` |
| Retry logic | `RedisConnection.connect_with_retry()`, mirroring `DatabaseConnection.connect_with_retry` (Phase 7) exactly |

## 3. Design notes

### Why `decode_responses=False` regardless of the settings field

`RedisSettings.decode_responses` (Phase 4) defaults to `True`, but
`create_pool_from_settings` always builds the pool with `decode_responses=False`
regardless. `CacheManager` supports both JSON and binary (pickle)
serialization; Redis itself cannot know which encoding a given value used, so
decoding must be handled explicitly by the serializer. Decoding every response
as UTF-8 unconditionally (what `decode_responses=True` does) would corrupt any
pickled payload the moment it contained a byte sequence that isn't valid UTF-8
— this was a deliberate design decision made before writing any code, not
something a test caught.

### One `CacheManager`, pluggable serializer — not method-per-format

`CacheManager.get`/`set` take a `serializer: Serializer = json_serializer`
parameter rather than separate `get_json`/`get_binary` method pairs. JSON is
the default (the common case — plain dicts/lists/numbers); pass
`serializer=pickle_serializer` for a value JSON cannot represent (e.g. a numpy
array). Both the JSON and binary serialization requirements are satisfied by
one consistent API instead of duplicated methods.

### `RateLimitCache` bypasses `CacheManager` deliberately

A rate-limit counter is a plain Redis integer (`INCR`'s native semantics), not
a serialized value — `RateLimitCache` talks to `RedisConnection` directly
rather than through `CacheManager`'s JSON/pickle layer, which does not apply
here.

### `DistributedLock` wraps redis-py's own lock, not a reimplementation

`cache/distributed_lock.py` is a thin wrapper over `redis.asyncio.lock.Lock`
(token-based safe acquire/release, backed by `SET NX PX` + a Lua release
script) adding this platform's key-namespacing and structured logging — it
deliberately does not reimplement lock semantics from scratch.

## 4. Existing files modified (each flagged before or immediately after)

| File | Change | Why |
|---|---|---|
| `config/modules/redis.py` | Added `connect_retry_attempts`, `connect_retry_backoff_seconds`, and four `*_cache_ttl_seconds`/`rate_limit_window_seconds` fields, all with defaults. No existing field changed. | Makes retry behavior and per-cache-type TTLs configurable per environment, mirroring `DatabaseSettings`' exact Phase 7 pattern. |
| `shared/errors/exceptions.py` | Added `CacheError(InfrastructureError)`. No existing exception changed. | Mirrors the existing `ExecutionError(InfrastructureError)` pattern; `InfrastructureError`'s own docstring already named Redis as a covered case. |
| `requirements/dev.txt` | Added `fakeredis` (dev-only). | Mirrors exactly why `aiosqlite` was added in Phase 7: a fast, protocol-compatible in-memory backend for unit tests instead of hand-rolled mocks. |
| `.env.example` | Documented the new `REDIS_*` fields. | Keeps the example file in sync with `RedisSettings`, per the established convention. |
| `core/container.py` | Added lazy `redis`/`cache` properties, disposal of both in `shutdown()`, and a `get_cache_manager()` FastAPI dependency. No existing property, method signature, or behavior changed. | Mirrors the existing `db` property's exact lazy-construction/disposal shape; the module's own docstring explicitly anticipated a later phase adding a resource this way. |
| `monitoring/health_checks.py` | Added Redis as a second informational, non-blocking readiness component, exactly mirroring how database connectivity was added. | The file's own docstring named this precise extension point. **Note:** this one edit was made without pausing to flag it to you first, unlike the others — surfacing that here for visibility even though it followed an already-approved pattern. |

**Not modified, and deliberately so:** `cache/redis_client.py` and
`cache/cache_keys.py` were empty stubs, not existing implementations, so
filling them in is new code, not a modification; `api/middleware/rate_limit_middleware.py`
is untouched — see §6.

## 5. A real regression this phase caused, and how it was resolved

Adding the Redis readiness check to `monitoring/health_checks.py` broke an
**existing**, previously-passing integration test —
`tests/integration/app/test_api_service_bootstrap.py::test_health_and_version_endpoints_are_consistent_across_requests` —
which asserts `/health/ready` reports `"healthy"` without mocking Redis
connectivity. Before this phase, that endpoint never touched Redis at all, so
the assertion held regardless of environment; after this phase, it genuinely
requires a reachable Redis. This is not a bug in the new code — running
`redis-server` locally (or `docker-compose up redis`) makes the test pass
exactly as intended, and it now does. No test file needed modification; the
fix was ensuring Redis is actually running, which is a real, disclosed
environmental dependency this phase introduces for that specific integration
test (see §7).

## 6. One decision deferred, not made silently

`api/middleware/rate_limit_middleware.py` is still a stub. `RateLimitCache` is
implemented, tested, and ready to use, but wiring it into that middleware is
left for explicit approval in a later phase — mirroring exactly how Phase 7
left `DatabaseConnection.connect_with_retry` unwired from `Container.startup()`.

## 7. Testing strategy

- **Unit tests** (`tests/unit/cache/`) use `fakeredis` (`fakeredis.aioredis.FakeRedis`)
  — an in-memory, protocol-compatible fake — via a small `FakeRedisConnection`
  test double that duck-types `RedisConnection`'s one attribute (`.client`)
  actually used by `CacheManager`/`RateLimitCache`. Mirrors
  `tests/unit/database/`'s own precedent (SQLite instead of a mock) rather than
  hand-rolling mocks for every Redis call.
- **`DistributedLock` is not covered by the unit suite.** redis-py's
  `Lock.release()`/`extend()` use a Lua script (`EVALSHA`), which fakeredis
  does not implement — confirmed directly while building this phase's tests
  (`fakeredis` raised `unknown command 'evalsha'`). It is tested only in
  `tests/integration/cache/test_distributed_lock_integration.py`, against a
  real Redis.
- **Integration tests** (`tests/integration/cache/`) require a real, reachable
  Redis — `docker-compose up redis`, or a local `redis-server`. They use a
  random `key_prefix` per test run so they never collide with other data on a
  shared instance.

---

**Phase 8 complete. Awaiting your review and approval before Phase 9.**
