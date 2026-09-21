# Phase 12 — ML Training & Model Management

**Status:** Implementation complete. Fills in Phase 2's `training/`, `models/`,
`mlops/` and `inference/` scaffold stubs and builds on Phase 11's Feast feature
store plus Phase 6–10 infrastructure. Additive only — no prior phase's public
API was changed. Additive edits to earlier phases are listed in §13.

> **Prerequisite.** Phase 12 requires Phase 11, which did not exist when this
> work started (see `docs/PHASE11_FEAST_FEATURE_STORE.md` §Context) and was
> implemented first.

---

## 1. What Phase 12 adds

| Requirement | Delivered in |
|---|---|
| Training pipeline | `training/trainer.py` (`ModelTrainer`) |
| Dataset generation from Feast historical features | `datasets/loaders/training_dataset_loader.py` |
| Feature/target preparation, labelling | `training_dataset_loader.build_labels()` |
| Train/validation/test splitting | `training/trainer.chronological_split()` |
| Model training abstraction | `models/model_definitions/lstm_price_model.py` |
| Baseline prediction model | `BaselineDirectionModel` |
| Model evaluation + metrics | `training/validation.py` (`ModelEvaluator`) |
| Hyperparameter search | `training/hyperparameter_search.py` |
| Model versioning + registry | `core/ports/model_registry_port.py`, `models/registry_client.py` |
| Model artifact storage | `core/ports/model_artifact_store_port.py`, `models/artifact_store.py` |
| Model metadata / experiment lineage | `mlops/experiment_tracker.py` |
| Promotion + rollback | `models/registry_client.py`, `mlops/promotion_policy.py` |
| Model loading | `inference/model_loader.py` |
| Inference interface | `inference/predictor.py` |
| Reproducibility | `TrainingConfig`, `TRAINING_RANDOM_SEED` |
| Training configuration | `config/modules/training.py`, `.env.example` |
| Migration (registry tables) | `database/migrations/versions/3d0f3957e9be_phase12_model_registry.py` |
| Kafka lifecycle events | `shared/messaging/events.py`, `topics.py` |
| Scheduler integration | `training.trainer.run_training_job`, `mlops.promotion_policy.evaluate_candidate_model` |
| Tests | `tests/unit/{models,training,inference}/`, `tests/integration/{models,training}/` |

---

## 2. Architecture

```
  Phase 11 Feast ──get_historical_features()──▶ TrainingDatasetLoader
   (point-in-time)                                      │ TrainingDataset
                                                        ▼
                                              chronological_split()
                                                        │
                                                        ▼
                                           BaselineDirectionModel.fit()
                                                        │
                                       ┌────────────────┴────────────────┐
                                       ▼                                 ▼
                              ModelEvaluator                  ModelArtifactStorePort
                            (validation + test)                (file:// artifact)
                                       │                                 │
                                       └────────────┬────────────────────┘
                                                    ▼
                                         ModelRegistryPort
                                    (Phase 7 PostgreSQL tables)
                                                    │
                                    PromotionPolicy │ thresholds
                                                    ▼
                                            PRODUCTION version
                                                    │
                         ModelLoader ◀──────────────┘
                              │
                              ▼
   Phase 11 Feast ──get_online_features()──▶ Predictor ──▶ PredictionEvent (Phase 9 Kafka)
        (Redis)
```

Four ports keep business logic independent of any ML library or storage
backend:

| Port | Implementation |
|---|---|
| `FeatureStorePort` (Phase 11) | `FeastFeatureStoreClient` |
| `ModelRegistryPort` | `PostgresModelRegistry` |
| `ModelArtifactStorePort` | `LocalFilesystemArtifactStore` |
| `EventPublisherPort` (Phase 9) | `KafkaProducer` |

`ModelTrainer`, `PromotionPolicy`, `ModelLoader` and `Predictor` take these as
constructor arguments and never import a concrete adapter.

---

## 3. Baseline model — scope and honest limits

`models/model_definitions/lstm_price_model.py` contains a **scikit-learn
`GradientBoostingClassifier`**, not an LSTM. The filename comes from the Phase 2
scaffold; nothing else in the repository imported it. The rationale is in the
module docstring, summarised:

- The Feast feature set is **tabular** (per-bar rolling-window summaries), which
  is what gradient boosting suits. An LSTM's advantage — learning temporal
  structure from a raw sequence — does not apply once the sequence has been
  hand-summarised into features.
- It trains **deterministically** on CPU under a fixed seed, which the
  reproducibility requirement needs and a hand-rolled PyTorch loop makes much
  harder to guarantee bit-for-bit.
- `scikit-learn` was already declared in `requirements/training.txt`.

**Prediction target:** binary — does the bar `label_horizon_bars` ahead close
above this bar's close?

> ### No accuracy claim is made
>
> This baseline exists to prove the training/registry/inference **infrastructure**
> works end to end. It is not a trading strategy, has no demonstrated predictive
> edge, and its measured accuracy (~0.51 on seeded synthetic random-walk data —
> i.e. approximately chance, exactly as a random walk should produce) must not be
> read as a performance result. Model infrastructure and model performance are
> deliberately separate concerns; only the former is delivered here.
>
> The default promotion thresholds (`0.52` accuracy / `0.50` F1) sit just above
> the 0.50 no-skill line for a binary problem. They are **infrastructure
> smoke-test thresholds**, not production trading gates.

---

## 4. Leakage prevention

Two independent guards, at different layers:

1. **Feature level (Phase 11).** Feast point-in-time retrieval never attaches a
   feature value computed after a row's `event_timestamp`.
2. **Label level.** `build_labels()` timestamps each row with **its own** bar,
   not the labelled future bar, so the row's features are exactly what was
   knowable at that moment. Trailing rows with no future bar are dropped.
3. **Split level.** `chronological_split()` splits **by position, never by
   shuffling.** Shuffling a time series before splitting lets the model train on
   rows occurring after its own validation/test rows — a subtler form of the same
   lookahead problem.

Each is directly asserted:
`test_each_rows_timestamp_is_its_own_bar_never_the_future_bar`,
`test_splits_are_strictly_ordered_in_time_with_no_overlap`,
`test_is_point_in_time_correct`.

---

## 5. Model lifecycle

```
CREATED ──▶ TRAINED ──▶ VALIDATED ──▶ STAGED ──▶ PRODUCTION ──▶ ARCHIVED
              │             │
              └──▶ FAILED ◀─┘
```

Enforced in `PostgresModelRegistry`, which raises `ModelStateError` on an
illegal transition. Key invariants, each covered by a test:

| Invariant | Enforced by |
|---|---|
| A model cannot reach `PRODUCTION` without recorded test metrics | `promote_version` requires `VALIDATED`/`STAGED` |
| Exactly one `PRODUCTION` version per model at any time | `promote_version` archives the incumbent |
| The current `PRODUCTION` version cannot be archived directly | `archive_version` raises `ModelStateError` |
| Rollback restores the **prior champion**, not an arbitrary archived version | `was_production` flag + `archived_at` ordering |
| Version numbers are monotonic per model, from 1 | `reserve_version` |

`record_evaluation` advances `TRAINED → VALIDATED` when test-split metrics are
recorded — but deliberately does **not** decide promotion. That decision lives
in `mlops/promotion_policy.py`, which reads the recorded metrics back.

### Database tables

`training_runs`, `model_versions`, `model_evaluations` — created by migration
`3d0f3957e9be`, using the existing Phase 7 `Base`/mixins. No second database
layer.

`model_versions.training_run_id` and `model_evaluations.model_version_id` are
real foreign keys. `training_runs.model_version_id` is intentionally an
unconstrained UUID: a bidirectional FK pair would force a deferred constraint
for no benefit.

---

## 6. Artifact storage

`ModelArtifactStorePort` owns **bytes**; `ModelRegistryPort` owns **metadata**.
`ModelTrainer` stores the artifact first, then registers the resulting
`artifact_uri`.

`LocalFilesystemArtifactStore` writes `{root}/{model_name}/{version}/model.bin`
and returns a `file://` URI. Every signature treats `artifact_uri` as opaque, so
an S3 backend can be added as a second implementation — selected by
`TRAINING_ARTIFACT_STORE_BACKEND` — without touching `trainer.py`,
`registry_client.py` or `model_loader.py`. An unrecognised URI scheme raises
rather than being treated as a local path.

> **Design note (bug found by the integration suite).** An earlier design saved
> the artifact under a placeholder version `0`, registered that URI, re-saved
> under the assigned version, then deleted the placeholder — leaving the registry
> pointing at a deleted file whenever anything failed in between. Inference failed
> on it. `reserve_version()` was added to the port so the version number is known
> *before* the single write. Guarded by
> `test_writes_a_loadable_artifact_at_the_registered_uri`.

---

## 7. Reproducibility

`TrainingConfig` records everything needed to reproduce a run, persisted on
`training_runs`:

| Recorded | Source |
|---|---|
| Random seed | `TRAINING_RANDOM_SEED` |
| Feature refs | Feast feature views actually requested |
| Dataset window | `dataset_start` / `dataset_end` |
| Split ratios | `train`/`validation`/`test` |
| Hyperparameters | `n_estimators`, `max_depth`, `learning_rate` |
| Library versions | Python, scikit-learn, numpy, pandas |
| Timestamps | `started_at`, `completed_at` |

Determinism holds at every layer: seeded synthetic data generation → pure
feature functions → positional splitting → fixed `random_state`. Asserted end to
end by `test_is_reproducible_for_a_fixed_seed`.

`mlops/experiment_tracker.py` reads this lineage back as one `ExperimentReport`.
It deliberately writes nothing new — the registry tables already hold everything,
and a parallel store would drift.

---

## 8. Inference

`Predictor.predict()`:

1. Loads the current `PRODUCTION` version via `ModelLoader`.
2. Retrieves online features for the symbol (Phase 11 → Redis).
3. Validates the payload — missing features or unset (`None`) values raise
   `FeatureValidationError` rather than predicting on garbage.
4. Runs a **real model prediction**.
5. Returns `PredictionResult` including `model_version`.
6. Publishes a `PredictionEvent` (best-effort).

There are no hardcoded buy/sell outputs anywhere in this path. Guarded by
`test_different_feature_inputs_can_change_the_prediction`, which fails if the
prediction ever becomes constant.

`PredictionResult` reports `predicted_class` (0/1) and `probability_up`, never a
trade instruction — turning a probability into an order is the strategy/risk
layer's job, not inference's.

---

## 9. Scheduler integration

Phase 10's job modules and `call_integration_point` helper were reused as-is;
**no scheduler code was modified.** Phase 12 implements two targets:

| Job (Phase 10) | Integration point (Phase 12) |
|---|---|
| `nightly_training_job` | `training.trainer.run_training_job` |
| `model_evaluation_job` | `mlops.promotion_policy.evaluate_candidate_model` |

Both resolve dependencies from `core.container.Container`, matching every other
integration point. Training failures raise `TrainingError`, which the helper
surfaces as a failed job run.

---

## 10. Kafka lifecycle events

One additive topic (`mlops.model_lifecycle`) and one event class
(`ModelLifecycleEvent`), keyed by `model_name` so one model's transitions stay
ordered. Transitions: `training_started`, `training_completed`,
`training_failed`, `model_registered`, `model_promoted`.

The specific transition is a `payload["transition"]` field rather than a class
per transition — every transition shares an envelope, and consumers typically
want all of them.

Publication is **best-effort**: a broker outage logs a warning and never fails a
training run or a prediction. Verified by
`test_a_failing_publisher_does_not_fail_the_prediction`.

---

## 11. Configuration

`config/modules/training.py`, prefix `TRAINING_`. Kept separate from
`AIModelSettings` (which governs inference-time lookup) because this governs the
training *run*.

| Variable | Default | Purpose |
|---|---|---|
| `TRAINING_RANDOM_SEED` | `42` | Reproducibility |
| `TRAINING_TRAIN_SPLIT` | `0.70` | Split ratio |
| `TRAINING_VALIDATION_SPLIT` | `0.15` | Split ratio |
| `TRAINING_TEST_SPLIT` | `0.15` | Split ratio |
| `TRAINING_LABEL_HORIZON_BARS` | `1` | Bars ahead to predict |
| `TRAINING_ARTIFACT_STORE_BACKEND` | `local` | `local`; `s3` reserved |
| `TRAINING_ARTIFACT_STORE_DIR` | `/var/lib/.../model_artifacts` | Artifact root |
| `TRAINING_MIN_PROMOTION_ACCURACY` | `0.52` | Promotion gate (see §3) |
| `TRAINING_MIN_PROMOTION_F1` | `0.50` | Promotion gate |
| `TRAINING_N_ESTIMATORS` | `200` | Hyperparameter |
| `TRAINING_MAX_DEPTH` | `3` | Hyperparameter |
| `TRAINING_LEARNING_RATE` | `0.05` | Hyperparameter |

A model validator rejects splits that do not sum to 1.0 at startup.

---

## 12. Practical examples

**1 — Run a training job**

```bash
python -m scheduler.jobs.cli nightly_training_job
```

```python
from training.trainer import run_training_job
result = await run_training_job(model_name="baseline-momentum", symbol="BTCUSDT")
# {'model_version': 1, 'test_accuracy': 0.5135, 'test_f1': 0.4462, 'promotable': True, ...}
```

**2 — Register a model** (normally done by the trainer)

```python
version_number = await registry.reserve_version("baseline-momentum")
uri = artifact_store.save("baseline-momentum", version_number, model.serialize())
version = await registry.register_version(
    model_name="baseline-momentum", version=version_number, artifact_uri=uri,
    training_run_id=run_id, feature_refs=dataset.feature_refs, config=config,
)
```

**3 — Evaluate a model**

```python
metrics = ModelEvaluator().evaluate(model, test_features, test_labels, split="test")
await registry.record_evaluation(version.id, metrics)   # TRAINED -> VALIDATED
```

**4 — Promote a model**

```bash
python -m scheduler.jobs.cli model_evaluation_job
```

```python
promoted = await PromotionPolicy(registry, settings).evaluate_and_promote("baseline-momentum")
# None if no candidate, or if it failed the configured thresholds
```

**5 — Roll back a model**

```python
restored = await registry.rollback_production("baseline-momentum")
await session.commit()
```

**6 — Load a model**

```python
loader = ModelLoader(registry, container.artifact_store)
loaded = await loader.load_production("baseline-momentum")
loaded.version.version        # 1
```

**7 — Run inference**

```python
predictor = Predictor(loader, container.feature_store, container.kafka_producer)
result = await predictor.predict("baseline-momentum", "BTCUSDT")
# PredictionResult(predicted_class=0, probability_up=0.49713, model_version=1, ...)
```

---

## 13. Additive edits to earlier phases

| File | Change |
|---|---|
| `shared/errors/exceptions.py` | Added `ModelRegistryError`, `ModelStateError`, `TrainingError`, `ModelValidationError` |
| `shared/messaging/events.py` | Added `ModelLifecycleEvent` + registry entry |
| `shared/messaging/topics.py` | Added `MODEL_LIFECYCLE` topic |
| `core/container.py` | Added `artifact_store` property + `get_artifact_store()` |
| `config/settings.py`, `config/modules/__init__.py` | Compose `TrainingSettings` |
| `database/migrations/env.py` | Import registry models for autogenerate |
| `mypy.ini` | `ignore_missing_imports` for `sklearn.*`, `feast.*` (no stubs published) |
| `pyproject.toml` | Ruff `src` dirs; pytest `--import-mode=importlib` (see §14) |
| `.env.example` | `TRAINING_*` additions |

**Earlier-phase tests updated** (behaviour changes, not regressions):

| Test | Why |
|---|---|
| `tests/unit/messaging/test_topics.py` | Asserted exactly 8 topics; now asserts the original 8 remain (subset) |
| `tests/unit/messaging/test_events.py` | Asserted exactly 8 event classes; now asserts registry/class-list agreement |
| `tests/unit/scheduler/jobs/test_no_op_jobs.py` | 6 integration points are no longer stubs |
| `tests/unit/scheduler/jobs/test_cli.py` | Used `nightly_training_job` as its no-op example |
| `tests/integration/scheduler/.../test_cli_end_to_end_integration.py` | Used `historical_sync_job` as its no-op example |
| `tests/integration/database/test_alembic_migration_integration.py` | Asserted head *is* the baseline revision |

Each was rewritten to assert the underlying invariant rather than a value that
changes every phase.

---

## 14. Testing

| Suite | Tests | Infrastructure |
|---|---|---|
| `tests/unit/models/` | 21 | None |
| `tests/unit/training/` | 18 | None |
| `tests/unit/inference/` | 13 | None |
| `tests/integration/models/` | 23 | Real SQLite |
| `tests/integration/training/` | 11 | Real Feast + SQLite + filesystem |

Integration tests are **not mock-based**: real synthetic history → real feature
computation → real Feast → real registry → real artifacts → real training →
real promotion → real inference. Unit tests needing a port use small in-test
implementations rather than mock objects.

**pytest import mode.** `tests/unit/` and `tests/integration/` contain
same-named directories (`models`, `training`, `cache`, `messaging`, …). Under
pytest's default `prepend` mode these collide in `sys.modules` once two contain
same-named modules. `--import-mode=importlib` (set in `pyproject.toml`) gives
each test module a path-derived name, avoiding `__init__.py` files or renames.

### Infrastructure-dependent limitations

Explicitly, so results are not over-read:

| Not exercised here | Why | Covered by |
|---|---|---|
| **Redis** online store | No Redis in this environment | Feast `sqlite` backend, same client path |
| **PostgreSQL** registry | No Postgres in this environment | SQLite; migration verified separately |
| **Kafka** lifecycle events | No broker | Unit tests assert best-effort behaviour |

The 25 suite failures on this environment are Redis/Kafka connection errors
**identical to those on the clean Phase 10 baseline** — verified by diffing
failure sets. Phase 11/12 introduced zero regressions.

---

## 15. Operational considerations

- **Promotion is never automatic on training success.** Training reports
  `promotable`; only `PromotionPolicy` promotes, and only against configured
  thresholds. Tightening a threshold takes effect on the next evaluation with no
  code change.
- **Feature staleness.** Inference refuses to predict on an unmaterialized
  payload rather than silently using stale values. Materialization cadence is an
  operational obligation, not a nicety.
- **Artifact retention.** Nothing garbage-collects archived artifacts; they are
  what rollback depends on. Add retention deliberately.
- **Registry is the source of truth** for which version is live — not the
  filesystem. An artifact present on disk is not a production model.
- **Training needs history.** `run_training_job` fails fast with a message
  naming `sync_latest_history` if none is present.

## 16. Failure recovery

| Failure | Behaviour | Recovery |
|---|---|---|
| Training raises | `training_failed` event; `TrainingError`; job `FAILED` | Nothing registered; fix and re-run |
| Dataset too small to split | `TrainingError` with row count | Widen `scheduled_training_lookback_bars` |
| Candidate below threshold | Logged, `None` returned, stays `VALIDATED` | Retrain or adjust thresholds |
| Bad model reached production | `rollback_production()` restores prior champion | Then archive the bad version |
| No prior champion to roll back to | `ModelStateError` | Promote a known-good version explicitly |
| Artifact missing/corrupt | `ModelRegistryError` / `TrainingError` on load | Roll back; retrain to regenerate |
| Kafka down | Warning logged; training/inference unaffected | Events are advisory, not transactional |
| Online features unset | `FeatureValidationError` | Re-materialize (Phase 11 §12) |
