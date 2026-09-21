# Phase 11 — Feast Feature Store

**Status:** Implementation complete. Fills in Phase 2's `feature_engineering/`,
`datasets/` and `core/domain/entities/tick.py` scaffold stubs and extends
Phase 6–10 infrastructure (`core.container`, `database`, `cache`,
`shared.logging`, `shared.errors`, `scheduler.jobs`). Additive only — no prior
phase's public API was changed. Additive edits to earlier phases are listed in
§10.

> **Context.** Phase 11 was specified as already complete when Phase 12 was
> commissioned, but no Phase 11 commit existed: `feature_engineering/`,
> `datasets/`, `training/`, `models/`, `mlops/` and `inference/` contained only
> one-line docstring stubs from the Phase 2 scaffold, and `feast` was not a
> dependency. Phase 11 was therefore implemented here as a prerequisite for
> Phase 12. See `docs/PHASE12_ML_TRAINING_MODEL_MANAGEMENT.md` for the layer
> built on top of it.

---

## 1. What Phase 11 adds

| Requirement | Delivered in |
|---|---|
| Feature store port (hexagonal boundary) | `core/ports/feature_store_port.py` |
| Feast-backed adapter | `feature_engineering/feature_store_client.py` |
| Entity definitions | `feature_engineering/feast_repo/entities.py` |
| Feature view definitions | `feature_engineering/feast_repo/feature_views.py` |
| Feast config from `Settings` (no `feature_store.yaml`) | `feature_engineering/feast_repo/repo_builder.py` |
| Technical indicator features | `feature_engineering/definitions/technical_indicators.py` |
| Statistical features | `feature_engineering/definitions/statistical_features.py` |
| Offline (batch) feature pipeline | `feature_engineering/offline_pipeline.py` |
| Online (materialization) pipeline | `feature_engineering/online_pipeline.py` |
| OHLCV domain entity | `core/domain/entities/tick.py` |
| OHLCV persistence | `database/repositories/ohlcv_bar_repository.py` |
| OHLCV store + synthetic backfill | `datasets/historical/ohlcv_store.py` |
| Dataset schema/feature validation | `datasets/schemas/dataset_schema.py` |
| Migration (`ohlcv_bars`) | `database/migrations/versions/e3544c59d3bd_phase11_ohlcv_bars.py` |
| Configuration | `config/modules/feature_engineering.py`, `.env.example` |
| Container wiring | `core/container.py` (`feature_store` property) |
| Tests | `tests/unit/feature_engineering/`, `tests/unit/datasets/`, `tests/integration/feature_engineering/` |

---

## 2. Architecture

```
                        ┌──────────────────────────────┐
  Phase 7 PostgreSQL ──▶│ datasets/historical/         │
      (ohlcv_bars)      │   ohlcv_store.OHLCVStore     │
                        └──────────────┬───────────────┘
                                       │ list[OHLCVBar]
                                       ▼
                        ┌──────────────────────────────┐
                        │ feature_engineering/          │
                        │   offline_pipeline            │──┐
                        │   (definitions/*.py)          │  │ writes
                        └──────────────────────────────┘  │
                                                           ▼
                                            ohlcv_features.parquet
                                              (Feast FileSource)
                                                           │
                        ┌──────────────────────────────────┴───────┐
                        │        feast.FeatureStore                │
                        │  registry.db  ·  offline=file            │
                        └───────┬──────────────────────┬───────────┘
              get_historical_   │                      │ materialize()
              features()        │                      ▼
                                │            Phase 8 Redis (online store)
                                │                      │
                                ▼                      ▼ get_online_features()
                  training/ (Phase 12)          inference/ (Phase 12)
```

Every consumer depends on **`core.ports.feature_store_port.FeatureStorePort`**,
never on `feast` directly. `feature_engineering/feature_store_client.py` is the
only module in the repository that imports `feast`; the composition root
(`core.container.Container.feature_store`) wires the concrete adapter in. This
is the same hexagonal rule `core/ports/event_publisher_port.py` established in
Phase 9.

---

## 3. Feature definitions

Two feature views share one offline source, mirroring
`feature_engineering/definitions/`'s own module split:

| View | Features |
|---|---|
| `technical_indicators` | `sma_20`, `ema_12`, `momentum_10`, `rsi_14`, `macd`, `macd_signal`, `macd_histogram`, `bollinger_band_width_20`, `atr_14` |
| `statistical_features` | `log_return_1`, `volatility_20`, `zscore_20`, `skewness_20`, `volume_zscore_20`, `high_low_range_ratio` |

Both join on the single `symbol` entity, so a caller can request any mix of
features for the same `entity_rows`/`entity_df` without knowing which view a
feature came from. `all_feature_refs()` returns the full list used by default.

Every function in `definitions/` is **pure and deterministic** — a
chronologically-ordered per-symbol series in, an index-aligned series out, no
I/O. This is what Phase 12's reproducibility guarantee ultimately rests on.

### RSI: three distinct cases

`relative_strength_index` distinguishes cases a blanket `fillna` would
conflate, because feeding a plausible-looking wrong value into training is
worse than feeding a `NaN` that gets dropped:

| Window | Result |
|---|---|
| Gains, no losses | `100.0` (maximum strength) |
| Losses, no gains | `0.0` |
| Completely flat (0 gain, 0 loss) | `50.0` (neutral) |
| Fewer than `window` bars | `NaN` — left for the loader to drop |

---

## 4. No `feature_store.yaml`

Feast is normally configured by a YAML file plus a Python definitions file on
disk, applied via the `feast` CLI. This phase instead constructs
`feast.RepoConfig` programmatically from this platform's own `Settings`
(`feature_engineering/feast_repo/repo_builder.py`) and calls `store.apply(...)`
in-process.

Every value Feast needs — registry path, offline store, online store — already
exists in `FeatureEngineeringSettings`/`RedisSettings`. Duplicating them into a
YAML file would create a second, silently-divergent source of configuration
truth. The Feast registry file and the offline parquet still live on disk,
because that is how Feast's file-based backends work.

**Online store backends:**

| `FEATURE_ONLINE_STORE_BACKEND` | Used for |
|---|---|
| `redis` (default) | Reuses the same Phase 8 Redis instance; namespaced by Feast's own `project` name, so it cannot collide with `cache/cache_keys.py` namespaces |
| `sqlite` | Local dev and CI, where no Redis is running |

Both go through the same client code path.

---

## 5. Point-in-time correctness

The single most important property of this layer. For training,
`get_historical_features` returns, for each `(symbol, event_timestamp)` row,
the feature value that was current **as of that timestamp** — never a value
computed later.

This is why training goes through Feast rather than a plain SQL join against
the features table: a naive join would happily attach today's `sma_20` to a row
timestamped six months ago, and the resulting model would look excellent in
backtest and fail in production. This is verified against the real store in
`tests/integration/feature_engineering/test_feast_feature_store_integration.py::TestHistoricalRetrieval::test_is_point_in_time_correct`.

---

## 6. Training/serving consistency

Both retrieval paths read the **same feature view definitions**, computed once
by `offline_pipeline.py` into one parquet file. Consistency is therefore a
property of the architecture rather than something each caller maintains by
hand.

Three additional checks back this up:

- `datasets/schemas/dataset_schema.check_training_serving_consistency()` —
  flags features present at training but absent at serving (one-directional;
  extra serving features are fine).
- `detect_missing_features()` — used by `inference/predictor.py` to validate an
  online payload before predicting.
- `BaselineDirectionModel._align_columns()` (Phase 12) — raises on a payload
  missing a trained feature, rather than predicting on a misaligned array.

---

## 7. Source data

`market_data/feed_adapters/` remains a Phase 2 stub — no live exchange feed is
wired up. `datasets/historical/ohlcv_store.sync_latest_history()` therefore
backfills with a **deterministic, seeded synthetic random walk**, clearly named
and documented as such.

> **This is not real market data and is not represented as such.** It exists so
> the feature/training/evaluation pipeline has real rows to run against end to
> end.

Because every consumer reads through `OHLCVStore`/`OHLCVBarRepository` and
never touches the generator directly, replacing this with a real
`market_data/feed_adapters` source requires no change to any downstream module.

The generator is seeded on `(seed, symbol)`, making it reproducible per symbol —
a prerequisite for Phase 12's reproducibility requirement.

---

## 8. Scheduler integration

Phase 10 already created the job modules and a `call_integration_point` helper
that no-ops gracefully while its target is a stub. Phase 11 implements four of
those targets; **no scheduler code was modified**:

| Job (Phase 10) | Integration point (Phase 11) |
|---|---|
| `historical_sync_job` | `datasets.historical.ohlcv_store.sync_latest_history` |
| `data_validation_job` | `datasets.schemas.dataset_schema.validate_latest_data` |
| `feature_generation_job` | `feature_engineering.offline_pipeline.run_batch_feature_generation` |
| `hourly_market_sync_job` | `feature_engineering.online_pipeline` |

`tests/unit/scheduler/jobs/test_no_op_jobs.py` was updated to move these out of
its no-op list, and gained `TestImplementedJobsAreNoLongerNoOps` to prevent a
job silently regressing to a stub.

---

## 9. Practical examples

**Backfill history, compute features, materialize:**

```bash
python -m scheduler.jobs.cli historical_sync_job
python -m scheduler.jobs.cli feature_generation_job
```

```python
from feature_engineering.online_pipeline import run_online_materialization
await run_online_materialization(lookback_hours=24)
```

**Retrieve historical (training) features:**

```python
import pandas as pd
from core.container import get_container

entity_df = pd.DataFrame({
    "symbol": ["BTCUSDT", "BTCUSDT"],
    "event_timestamp": [ts1, ts2],           # tz-aware
})
features = get_container().feature_store.get_historical_features(entity_df)
```

**Retrieve online (serving) features:**

```python
online = get_container().feature_store.get_online_features([{"symbol": "BTCUSDT"}])
online["sma_20"]     # -> [27128.80...]
```

An entity with nothing materialized returns `None` in each slot — an expected
cold-start outcome, not an exception.

---

## 10. Additive edits to earlier phases

| File | Change |
|---|---|
| `shared/errors/exceptions.py` | Added `FeatureStoreError`, `FeatureValidationError` |
| `core/container.py` | Added `feature_store` property + `get_feature_store()` dependency |
| `config/settings.py`, `config/modules/__init__.py` | Compose `FeatureEngineeringSettings` additions |
| `config/modules/feature_engineering.py` | Added `feast_project_name`, `historical_retrieval_timeout_seconds` |
| `database/migrations/env.py` | Import mapped models so autogenerate sees them |
| `requirements/training.txt` | Added `feast`, `pyarrow` |
| `docker/scheduler_jobs.Dockerfile` | Install `training.txt` (feature/training jobs need it) |
| `pyproject.toml` | Added new source dirs to Ruff `src` |
| `.env.example` | `FEATURE_*` additions |

No existing public API was changed or removed.

---

## 11. Testing

| Suite | Tests | Notes |
|---|---|---|
| `tests/unit/feature_engineering/` | 16 | Closed-form indicator values, alignment, determinism |
| `tests/unit/datasets/` | 32 | Entity invariants, generator reproducibility, schema validation, label leakage |
| `tests/integration/feature_engineering/` | 12 | **Real Feast** — apply, historical, materialize, online, consistency |

Integration tests drive a genuine Feast registry/offline/online store — no
mocks. Unit tests that need a feature store use a small in-test
`FeatureStorePort` implementation rather than a mock object, keeping them
honest about the interface contract.

**Infrastructure limitation:** the integration suite uses Feast's `sqlite`
online backend so it runs without external services. The Redis backend is
selected by the same `build_repo_config` branch and exercises identical client
code, but additionally requires Phase 8 infrastructure to be running.

---

## 12. Operational considerations

- **Cadence.** Offline feature generation runs when new OHLCV history lands;
  materialization should run *more* frequently to keep the online store fresh
  for live inference. They are separate modules for exactly this reason.
- **Full recompute.** `OfflineFeaturePipeline.run()` recomputes from the full
  available history and overwrites the parquet rather than appending. Simple
  and correct at current volume (hourly bars, a few symbols); revisit if
  symbol count or frequency grows substantially.
- **Warm-up rows.** The first ~26 rows per symbol carry `NaN` (bounded by
  MACD's slow span). They are deliberately left in the parquet and dropped by
  the training dataset loader, so the policy lives with the consumer.
- **`apply()` is idempotent.** Safe on every process start and before each
  batch run.

## 13. Failure recovery

| Failure | Behaviour | Recovery |
|---|---|---|
| Registry/offline store unreachable | `FeatureStoreError` (503) | Job reports `FAILED`; re-run after restoring storage |
| No OHLCV history | `FeatureStoreError` with `symbols_requested` context | Run `historical_sync_job` first |
| Online store stale/unmaterialized | `get_online_features` returns `None` slots; `inference/predictor.py` raises `FeatureValidationError` | Run materialization |
| Gap/quality issue in history | `validate_latest_data` raises `FeatureValidationError` listing per-symbol issues | Inspect and re-sync the affected symbol |
| Feature view renamed/dropped | `TrainingDatasetSchema.validate()` raises with `missing_columns` | Never silently trains on fewer features |
