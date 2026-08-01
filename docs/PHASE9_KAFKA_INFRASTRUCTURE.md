# Phase 9 — Kafka Infrastructure

Producer, consumer, topic catalog/provisioning, event schemas, serialization,
retry logic, dead-letter queues, and consumer groups for the platform's
event-driven backbone, built on `aiokafka`.

## 1. What Phase 4/2 already had (not rebuilt)

- `config/modules/kafka.py` — `KafkaSettings` (bootstrap servers, client id,
  security/SASL, producer acks/max-in-flight, consumer group id, session
  timeout) already existed, fully implemented, from Phase 4.
- `docker-compose.yml` already ran a single-broker `confluentinc/cp-kafka`
  container on `9092`, with `zookeeper` as its dependency.
- `.env.example` already documented the core `KAFKA_*` variables.
- `shared/messaging/{kafka_producer,kafka_consumer,schema_registry}.py` and
  `core/ports/event_publisher_port.py` existed as one-line docstring stubs —
  the exact shape Phase 2's scaffold left for this phase to fill in.
- `shared/utils/serialization.py` already existed and already named Kafka
  event payloads as an intended consumer of its `dumps`/`dumps_bytes`/`loads`
  helpers (`Decimal`/`datetime`/`Enum`/`UUID`-aware JSON encoding).
- `shared/logging/retry.py`'s `log_retries_async` decorator (exponential
  backoff + jitter, structured retry logging) already existed and needed no
  changes — this phase's producer/consumer retry logic is built directly on it.

None of the above needed to change to build this phase, except the two fixes
in Sec 5.

## 2. What Phase 9 adds

**New files:**

- `shared/messaging/topics.py` — the topic catalog: one `Topic` per logical
  category (`market_data`, `trades`, `predictions`, `orders`, `executions`,
  `portfolio`, `alerts`, `logs`), each with a physical topic name, partition
  key description, retention default, and DLQ eligibility. See the module's
  own docstring for exactly how each of the eight requested categories maps
  onto `docs/PHASE1_ARCHITECTURE.md`'s existing dot-hierarchical naming
  (`inference.signal`, `orders.fills`, `portfolio.updates` were already
  reserved there; the other five are new, freshly documented at declaration).
- `shared/messaging/events.py` — `BaseEvent` envelope (`event_id`,
  `schema_version`, `occurred_at`, `correlation_id`, `source_service`,
  `payload`) plus one concrete subclass per topic category, all Pydantic
  models. `payload` stays an open `dict[str, Any]` deliberately — see Sec 6.
- `shared/messaging/event_codec.py` — `encode`/`decode`, built on
  `shared.utils.serialization`, not a second wire format.
- `shared/messaging/dlq.py` — `DeadLetterEnvelope` + `build_dlq_envelope`,
  what actually gets published to a topic's `.dlq` counterpart.
- `shared/messaging/schema_registry.py` — an in-process schema-version
  compatibility check (not an external Confluent-Schema-Registry client — see
  Sec 6 for why that's a deliberate, documented scope decision).
- `shared/messaging/kafka_producer.py` — `KafkaProducer(EventPublisherPort)`:
  lazy client construction and lazy `start()`, retrying publish failures via
  `log_retries_async`, routing to DLQ on exhaustion, `check_connection()` for
  health checks, `dispose()` for shutdown.
- `shared/messaging/kafka_consumer.py` — `KafkaConsumer`: consumer-group
  membership, manual offset commit only after successful handling or DLQ
  hand-off, bounded in-process handler retry, malformed-payload dead-lettering
  with the raw bytes preserved.
- `shared/messaging/topic_manager.py` — `TopicManager`: idempotent topic
  provisioning (`ensure_topic`, `ensure_all`) and inspection
  (`list_topic_names`) via `AIOKafkaAdminClient`, meant to run once at
  deploy/bootstrap time, not on the hot path.
- `core/ports/event_publisher_port.py` — filled in: `EventPublisherPort(ABC)`
  with one abstract method, `publish`. `core` depends on this; it never
  imports `shared.messaging.kafka_producer` directly (hexagonal boundary, per
  `docs/PHASE1_ARCHITECTURE.md` Sec 5 and `core/ports/base_repository.py`'s
  existing precedent).
- `tests/unit/messaging/*` (77 tests) and `tests/integration/messaging/*`
  (12 tests) — see Sec 7.

**Existing files modified** (each flagged and explained in Sec 5):

- `config/modules/kafka.py`, `shared/errors/exceptions.py`,
  `core/container.py`, `monitoring/health_checks.py`, `requirements/base.txt`,
  `.env.example`, `README.md`, `tests/unit/monitoring/test_health_checks.py`.

## 3. Design notes

### Two-stage laziness on every real Kafka client, not one

`AIOKafkaProducer`, `AIOKafkaConsumer`, and `AIOKafkaAdminClient` all call
`asyncio.get_running_loop()` at **construction**, not just at `start()` —
unlike `redis.asyncio.Redis`, which does neither eagerly. `Container.db` and
`Container.redis` are synchronous, lazily-evaluated properties (construct on
first access, whenever that happens to be); `Container.kafka_producer` had to
match that exact shape to fit the same DI pattern. If `KafkaProducer.__init__`
constructed the real `AIOKafkaProducer` eagerly, any access to
`container.kafka_producer` from outside a running event loop — which this
codebase's own call sites and its own test suite legitimately do, between
`asyncio.run()` calls — would raise `RuntimeError: no running event loop`
before a single message was ever published.

This was not a hypothetical: it was caught by this phase's own unit test
suite (`tests/unit/monitoring/test_health_checks.py`, patching
`type(container.kafka_producer)` outside `asyncio.run()`), fixed by deferring
the real client's construction out of `__init__` and into `start()` /
`_ensure_started()` on all three classes (`KafkaProducer`, `KafkaConsumer`,
`TopicManager`), each exposing the real object behind a small `_client`
property that asserts it's been started first. See Sec 5 for the parallel
fix this same testing pass found in `KafkaSettings`.

### One producer instance, many consumer instances — not symmetric with Redis

`Container.kafka_producer` is a process-wide singleton, same as `Container.db`
/ `Container.redis`. `KafkaConsumer` is **not** wired into `Container` at all.
A producer is stateless enough (one client, many topics) to share safely
across every part of a process that wants to publish. A consumer is bound to
one `group_id` and one set of subscribed topics — sharing one consumer
instance across unrelated subscribers would either force them into the same
consumer group (wrong: they'd split partitions instead of each seeing every
message) or require one `KafkaConsumer` per subscriber anyway, at which point
a shared singleton buys nothing. Each subscribing service/worker constructs
its own `KafkaConsumer(settings, topics, handler, dlq_producer, group_id=...)`
and drives its own `run()` loop.

### DLQ hand-off reuses the producer wrapper, not a second raw client

`KafkaConsumer` takes a `KafkaProducer` (the same class `Container` uses) as
its `dlq_producer`, and calls its `_send_to_dlq`/`_client` internals directly
rather than opening a second, separate `AIOKafkaProducer` connection just for
dead-lettering. This means a DLQ hand-off from the consumer side gets
identical error-mapping and connection-lifecycle handling to every other
publish in the platform, and a process only ever needs to manage the lifetime
of one producer connection even when it's also consuming.

### Manual offset commit is the whole point, not an implementation detail

`KafkaSettings.enable_auto_commit=False` (Phase 4 default, unchanged) plus
`KafkaConsumer._commit()` calling `consumer.commit()` explicitly, only after
`_process_one` either hands the message to the caller's handler successfully
or dead-letters it, is what makes "Consumer Groups" in this phase's task list
mean something more than just joining one: it's what gives an at-least-once
delivery guarantee real teeth. A message is never marked delivered by the
committed offset until it has been handled or preserved in a DLQ — a crash
between decode and commit causes redelivery on restart, not silent loss.

## 4. Existing files modified (each flagged before or immediately after)

| File | What changed | Why |
|---|---|---|
| `config/modules/kafka.py` | Added 9 new fields (`connect_retry_attempts`, `connect_retry_backoff_seconds`, `producer_retry_max_attempts`, `producer_retry_backoff_seconds`, `consumer_max_retry_attempts`, `consumer_retry_backoff_seconds`, `dlq_topic_suffix`, `topic_num_partitions`, `topic_replication_factor`). Also fixed `producer_compression_type` default from `"snappy"` to `"gzip"`. | New fields: additive, mirror the existing `RedisSettings`/`DatabaseSettings` retry-field pattern exactly; nothing existing removed or renamed. The `"snappy"` default was a genuine pre-existing bug this phase's own tests surfaced — see Sec 5.1. |
| `shared/errors/exceptions.py` | Added `MessagingError(InfrastructureError)`, appended to `__all__`. | Every other Phase 7/8 infrastructure module (`CacheError`) has its own typed exception; messaging needed the same so callers catch one type instead of raw `aiokafka` exceptions or `pydantic.ValidationError`. |
| `core/container.py` | Added `_kafka_producer` slot, `kafka_producer` lazy property, disposal in `shutdown()`, `get_kafka_producer()` FastAPI dependency, added to `__all__`. | This is the composition root; nothing in `shared.messaging` wires itself into the app without it, exactly like `cache`/`db` before it. |
| `monitoring/health_checks.py` | Added Kafka as a third informational (non-blocking) readiness component, mirroring the DB/Redis checks already there. | Consistency: every other Phase 7/8 infrastructure dependency this platform depends on is already surfaced at `/health/ready`; Kafka not being checked would be a silent blind spot. |
| `requirements/base.txt` | Added `aiokafka`. Left the pre-existing `confluent-kafka` line untouched. | You asked for `aiokafka` specifically (asyncio-native, matches every other async client in this stack — `asyncpg`, `redis.asyncio`). `confluent-kafka` was declared in Phase 2's scaffold and nothing in the codebase used it; removing an existing declaration wasn't part of implementing this phase, so it's left for an explicit later decision rather than silently dropped. |
| `.env.example` | Documented the 9 new `KAFKA_*` variables (commented, with defaults shown), matching the existing convention for optional variables in this file. | Keeps this file the single source of truth for every settings field, as it already was for the Phase 4 fields. |
| `README.md` | Added one status line for Phase 9. | Matches the existing per-phase status line convention. Phase 7/8 status lines were already missing before this change (confirmed via `git log`, not something this phase introduced) — left alone as out of scope for this phase. |
| `tests/unit/monitoring/test_health_checks.py` | Extended the readiness tests to also mock Kafka connectivity, and added one new test for the Kafka-unreachable case. | Directly necessitated by the `monitoring/health_checks.py` change above — without mocking, those tests would genuinely try to reach `localhost:9092`, which isn't running in the unit test environment, and fail for a reason unrelated to what they're testing. |

## 5. Two real problems this phase's own tests found, and how they were resolved

Both were caught by this phase's *own* unit test suite while it was being
written, not discovered later — consistent with `docs/PHASE8_REDIS_INFRASTRUCTURE.md`
Sec 5's precedent of disclosing this kind of thing rather than quietly folding
the fix into the diff.

### 5.1 — `producer_compression_type` defaulted to a codec this repo can't run

`KafkaSettings.producer_compression_type` (Phase 4) defaulted to `"snappy"`.
Constructing a real `AIOKafkaProducer` with that default raises immediately —
`RuntimeError: Compression library for snappy not found` — because neither
`python-snappy` nor `cramjam` is installed or declared anywhere in
`requirements/*.txt`. This was invisible through Phase 4–8 because nothing
before this phase ever actually constructed a real Kafka producer; the field
existed only as inert configuration. Fixed by changing the default to
`"gzip"` (stdlib `zlib`-backed, zero new dependencies) rather than adding a
new native compression dependency for a setting nothing had exercised yet.

### 5.2 — Real Kafka clients need a running event loop to even construct

Documented in full in Sec 3 above ("Two-stage laziness"). Summary: fixed by
deferring `AIOKafkaProducer`/`AIOKafkaConsumer`/`AIOKafkaAdminClient`
construction out of `__init__` and into each class's `start()` /
`_ensure_started()`.

## 6. Decisions made, not made silently

- **`payload: dict[str, Any]`, not per-topic typed domain models.** No
  `core/domain` entities (`Order`, `Position`, ...) exist yet as of this
  phase — `core/container.py`'s own Phase 6 docstring already establishes this
  precedent for other layers. Modeling `core/domain` first and then typing
  each event's `payload` against it is future work; making up domain shapes
  now, before `core/domain` exists, would mean maintaining two competing
  models of the same concepts.
- **No external Confluent Schema Registry.** `docs/PHASE1_ARCHITECTURE.md`
  Sec 3.20 mentions "schema registry enforces backward-compatible event
  schemas," which usually implies an external service governing Avro/Protobuf
  schemas. This platform's events are Pydantic-JSON, not Avro/Protobuf, and no
  such service is provisioned in `docker-compose.yml`. `schema_registry.py`
  is the in-process equivalent — version tracking and forward-compatible
  validation against `EVENT_TYPE_REGISTRY` — with the same two-method surface
  a real external client would need, so swapping one in later (if
  multi-language producers are introduced) doesn't require touching callers.
- **`docker-compose.yml`'s `KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092`
  is a known caveat, not fixed here.** A client connecting from the host
  machine (as `tests/integration/messaging` does, via `localhost:9092`)
  completes the initial bootstrap connection fine, but the broker's advertised
  metadata then points to the hostname `kafka`, which doesn't resolve outside
  the Docker network — a well-known Compose/Kafka gotcha. This is Phase 2's
  file; addressing it (typically via a second listener,
  e.g. `PLAINTEXT://localhost:9092` for host access alongside
  `PLAINTEXT://kafka:9092` for in-network access) is an infrastructure change
  outside this phase's scope; flagged here so whoever runs
  `make up && make test` next isn't surprised by it.

## 7. Testing strategy

- **Unit (`tests/unit/messaging/`, 77 tests)**: no real broker. Real
  `AIOKafka*` client objects are never constructed — fake objects are injected
  directly in place of `self._producer`/`self._consumer`/`self._admin` (see
  Sec 3's laziness fix, which is exactly what makes this injection possible
  without needing an event loop at fixture-setup time). Covers: topic catalog
  invariants, event envelope defaults/independence, encode/decode round-trips
  and every malformed-input path, DLQ envelope construction, schema
  compatibility rules, producer publish/retry/DLQ/health-check/dispose,
  consumer happy-path/retry/DLQ/malformed-message/commit-skip-on-autocommit,
  and topic-manager provisioning/idempotency/error-mapping.
- **Integration (`tests/integration/messaging/`, 12 tests)**: real broker
  required (`docker-compose up kafka` / `make up`), no mocking — matching
  `tests/integration/cache/`'s established convention exactly, including its
  "no skip-if-unreachable" stance. Covers: topic provisioning against the real
  admin protocol, a genuine publish → consume round-trip (including
  same-partition-key ordering), a real DLQ round-trip (publish → handler
  permanently fails → consumed off the actual `.dlq` topic by a second,
  independent consumer), and the DI container's `kafka_producer` wiring
  end-to-end (lazy singleton, disposal, the `get_kafka_producer()` dependency).
  Not run to completion in this environment (no Kafka broker reachable here);
  collection was verified (all 12 tests collect with no import/syntax errors)
  and one was run far enough to confirm it fails with a genuine
  `KafkaConnectionError` — the expected, correct failure mode without a
  broker — rather than any defect in the test or the code under test.

Phase 9 complete. Awaiting your review and approval before Phase 10.
