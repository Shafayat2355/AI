# Phase 10 — Workflow Orchestration

**Status:** Implementation complete. Extends Phase 2's `scheduler/` scaffold
(fills in three existing stubs, adds eight new sibling modules) and Phase
6–9's infrastructure (`core.container`, `cache`, `database`, `shared.logging`,
`shared.errors`). Does not change any prior phase's decisions except the
explicitly-flagged additive edits in §5.

---

## 1. What Phase 10 adds

| Requirement | Delivered in |
|---|---|
| Daily jobs | `scheduler/jobs/eod_reconciliation_job.py` + `scheduler/airflow/dags/daily_jobs_dag.py` |
| Hourly jobs | `scheduler/jobs/hourly_market_sync_job.py` + `hourly_jobs_dag.py` |
| Retraining | `scheduler/jobs/nightly_training_job.py` + `retraining_dag.py` |
| Historical sync | `scheduler/jobs/historical_sync_job.py` + `historical_sync_dag.py` |
| Data validation | `scheduler/jobs/data_validation_job.py` + `data_validation_dag.py` |
| Feature generation | `scheduler/jobs/feature_generation_job.py` + `feature_generation_dag.py` |
| Backtesting jobs | `scheduler/jobs/periodic_backtest_job.py` + `backtesting_dag.py` |
| Model evaluation | `scheduler/jobs/model_evaluation_job.py` + `model_evaluation_dag.py` |
| Cleanup | `scheduler/jobs/cleanup_job.py` + `cleanup_dag.py` |
| Database backup | `scheduler/jobs/database_backup_job.py` + `database_backup_dag.py` |
| Alert jobs | `scheduler/jobs/alert_sweep_job.py` + `alert_jobs_dag.py` |
| Airflow DAG structure | `scheduler/airflow/dags/` (11 DAGs) + `dag_common.py` |
| Airflow configuration | `requirements/airflow.txt`, `docker/airflow.Dockerfile` |
| Docker Compose integration | `docker-compose.yml` (5 new services) |
| Scheduling strategy | §8 below |
| Tests | `tests/unit/scheduler/jobs/`, `tests/integration/scheduler/jobs/`, `tests/unit/scheduler/airflow/` |
| Documentation | This file |

---

## 2. Architecture: two packages, two environments, one image boundary

```
scheduler/jobs/          <- the actual job LOGIC (pure Python, this repo's
                             own dependencies: sqlalchemy, redis-py, ...)
scheduler/airflow/       <- Airflow DAG DEFINITIONS ONLY (apache-airflow's
                             classes, nothing else)
```

`scheduler/jobs/*.py` is technology-agnostic — nothing in it knows Airflow
exists. Each module exposes one `async def run() -> JobResult`. This is
deliberate: it means these jobs are equally invokable by Airflow, by
`scheduler/job_scheduler.py`'s APScheduler-based in-process scheduler (still
an unfilled Phase 2 stub, untouched by this phase — see §6), by a cron entry
calling `python -m scheduler.jobs.cli <job>` directly, or by a unit test —
the orchestration technology never leaks into the job logic itself.

`scheduler/airflow/dags/*.py` contains nothing but `DAG`/operator
construction — every actual task runs via `DockerOperator` against a
**separate image** built from `docker/scheduler_jobs.Dockerfile`, which *does*
install this repo's own `requirements/base.txt`. Airflow's own container
(`docker/airflow.Dockerfile`) never does.

## 3. Why the two images are strictly isolated (a confirmed, not assumed, problem)

Before writing any DAG code, installing `apache-airflow==2.10.4` into this
repo's own dev environment was tried directly, to see whether it could simply
be added to `requirements/dev.txt`:

```
$ pip install "apache-airflow==2.10.4" --constraint <official constraints file>
...
$ python -c "import sqlalchemy; print(sqlalchemy.__version__)"
1.4.54
$ python -c "import pydantic, fastapi"
ImportError: ...typing_extensions...
```

Airflow 2.10.4's own pinned constraints force `sqlalchemy` down to `1.4.x`
and a `typing_extensions` version incompatible with `pydantic` v2 — installing
it alongside this repo's own stack breaks `pydantic`/`fastapi` imports
outright, not in some edge case. This is why:

- `requirements/airflow.txt` exists as a **separate** file, never referenced
  by `requirements/base.txt` or `dev.txt`.
- Every DAG task runs via `DockerOperator` against a different image
  (`scheduler-jobs`) rather than importing `scheduler.jobs` into Airflow's
  own Python process.
- `mypy.ini` has a dedicated `[mypy-scheduler.airflow.*]` exclusion — that
  package is type-checked separately, via a second, isolated virtual
  environment (see §9 "Testing strategy").

## 4. Docker Compose integration

Five new services, all additive — nothing existing changed:

- **`airflow-postgres`** — Airflow's *own* metadata database, a separate
  container and volume from the app's own `postgres` service. Deliberately
  not a second database inside the same Postgres instance: this keeps
  Airflow's internal schema/migrations fully isolated from
  `database/migrations/` (Alembic), which the app's own Postgres is
  exclusively reserved for.
- **`airflow-init`** — one-shot: runs `airflow db migrate`, seeds the
  `host_repo_path` Variable (see §6), creates an admin user.
- **`airflow-webserver`** / **`airflow-scheduler`** — `LocalExecutor`
  (sufficient for this phase's scope; no Celery/Redis-backed executor
  needed). `airflow-scheduler` bind-mounts the host's own `docker.sock` —
  see §6 for why.
- **`scheduler-jobs`** — not a standing service. `profiles: ["build-only"]`
  keeps `docker compose up` from starting it as a persistent container; `make
  airflow-up` (or `docker compose build scheduler-jobs`) builds the image
  every DAG task actually runs.

## 5. Existing files modified (flagged before or immediately after)

| File | Change | Why |
|---|---|---|
| `scheduler/jobs/eod_reconciliation_job.py`, `nightly_training_job.py`, `periodic_backtest_job.py` | Filled in (were one-line Phase 2 stubs). | These files existed exactly as the intended home for the "Daily jobs", "Retraining", and "Backtesting jobs" categories, per their own pre-existing docstrings. |
| `mypy.ini` | Added `[mypy-scheduler.airflow.*]` exclusion. | That package requires `apache-airflow`, which cannot be installed in this repo's own dev environment (§3) — it's type-checked in the isolated Airflow venv instead. |
| `docker-compose.yml` | Added 5 new service blocks + 1 new volume. No existing service changed. | Phase 10 explicitly requires Docker Compose integration. |
| `.env.example` | Added `DATABASE_BACKUP_DIR`. | The one new environment variable this phase introduces (`scheduler/jobs/database_backup_job.py` reads it via `os.environ`, not `config.settings.Settings`, since it's an operational path setting). |
| `Makefile` | Added `airflow-up`, `airflow-down`, `dags-lint` targets. | Additive only. |
| `README.md` | Added the Phase 10 status line. | Matches the existing per-phase convention. |

**Not modified:** `scheduler/job_scheduler.py` (still an unfilled stub —
this phase adds Airflow as *a* scheduling mechanism, not the only possible
one; see §2), `alerts/alert_manager.py` and `alerts/channels/*.py` (still
Phase 2 stubs — `alert_sweep_job.py` uses Airflow's own failure notification
today instead; see its docstring), `core/container.py`, `database/`,
`cache/` (all used as-is, exactly as Phase 6–8 left them).

## 6. Docker-outside-of-Docker (DooD) and two real bugs found while wiring it

`airflow-scheduler` mounts the host's own `/var/run/docker.sock` so
`DockerOperator` can ask the **host's** Docker daemon to start each task's
container as a sibling of Airflow's own container, rather than nesting
Docker-in-Docker. This produces two non-obvious correctness requirements,
both discovered (not assumed) while building this phase's DAGs, and both now
covered by regression tests in `tests/unit/scheduler/airflow/test_dags.py`:

1. **`env_file` and Jinja templating.** `DockerOperator.template_fields`
   includes `env_file`, and `template_ext` includes `.env` —
   Airflow's generic template-*file* resolution machinery therefore tries to
   open whatever path `env_file` holds and replace the field's value with
   that file's *rendered contents*, not just validate the path. Confirmed via
   `DagBag`: parsing a DAG using a plain `env_file` path raised
   `jinja2.exceptions.TemplateNotFound` before the mounted path existed, and
   even once it exists this would silently replace the intended host *path*
   string with the file's raw *contents* — the opposite of what `docker run
   --env-file <path>` needs. Fixed with `_PlatformDockerOperator`, a thin
   `DockerOperator` subclass excluding `env_file` from `template_fields`.

2. **A host path is not a container path.** `DockerOperator` talks to the
   **host's** Docker daemon, so `env_file`'s value must be a path the *host*
   filesystem recognizes — a hardcoded in-container path (e.g.
   `/opt/airflow/host_repo/.env`) is meaningless to the host daemon. Fixed by
   reading the real host path from an Airflow Variable
   (`host_repo_path`), populated by docker-compose's own `${PWD}`
   interpolation at container start — the standard way for a container to
   learn the host path it was bind-mounted from. A further, related bug: an
   unseeded `Variable.get()` without a default raises and aborts parsing
   `DagBag`-wide, breaking *every* DAG in the package at once over one
   temporarily-missing Variable. Fixed with `default_var=None` and a visibly
   wrong placeholder path (`/UNSET_HOST_REPO_PATH_VARIABLE/.env`) instead —
   a task that actually runs against it fails obviously, while DAG parsing
   itself never breaks.

## 7. The "not yet implemented" pattern

Most of this phase's job categories are meant to trigger real work in modules
that do not have a callable implementation yet as of Phase 10 —
`training/`, `datasets/`, `feature_engineering/`, `backtesting/`, and
`mlops/` are still Phase 2 scaffold stubs (a one-line docstring each). Rather
than raise on every run until whichever future phase implements the target
module — training operators to ignore permanently-red DAGs — each such job
calls its expected integration point through
`scheduler.jobs.job_result.call_integration_point`, which reports a distinct,
non-failing `SKIPPED_NOT_IMPLEMENTED` status (not `SUCCESS`, not `FAILED`)
when the target module exists but doesn't yet expose the expected callable,
and logs a clear `WARNING` naming exactly what's missing. The moment a future
phase adds the real function (e.g. `training.trainer.run_training_job`),
these jobs call it with zero code changes on this side.

Three jobs are **not** placeholders — they have real, working
implementations using infrastructure that already exists:

- **`database_backup_job`** — real `pg_dump` via `asyncio.create_subprocess_exec`.
- **`cleanup_job`** — real Postgres `VACUUM` (dialect-aware: `VACUUM
  (ANALYZE)` for Postgres, plain `VACUUM` for SQLite — the parenthesized
  form is Postgres-specific and a test caught this the first time) + a real
  Redis key-count sweep via `SCAN`.
- **`alert_sweep_job`** — reuses `monitoring.health_checks.readiness`
  directly and deliberately returns `FAILED` (not `SUCCESS`) when the
  platform is degraded, specifically so the Airflow task itself goes red —
  today's real alert channel, since `alerts/alert_manager.py` is still a
  stub (see `on_job_failure` in `dag_common.py` for the same reasoning
  applied DAG-wide).

## 8. Scheduling strategy

```
00:30  historical_sync   ─┐
01:00  data_validation    │  nightly data/training pipeline --
01:30  feature_generation │  each 30-60 min apart (see note below)
02:00  retraining        ─┘
03:00  cleanup              (after retraining, before backup)
06:00  database_backup      (after cleanup, so it backs up a vacuumed DB)
22:00  daily_jobs (EOD reconciliation)   -- after market close

hourly, on the hour:  hourly_jobs
every 5 minutes:      alert_jobs

Sunday 04:00  backtesting        ─┐  weekly, not nightly -- see below
Sunday 05:00  model_evaluation   ─┘
```

- **Nightly pipeline ordering is enforced by spacing, not an explicit
  cross-DAG dependency** (e.g. `ExternalTaskSensor`, or Airflow 2.4+
  Datasets). A deliberate, documented simplification for this phase — each
  DAG is independent and 30-60 minutes is comfortable headroom for a normal
  run, but a genuinely long-running `historical_sync` could still overlap
  `data_validation`'s start. Upgrading to explicit dependencies (Datasets are
  the more modern Airflow-native mechanism) is a natural next step once
  real run-time data is available to size the risk.
- **Backtesting/model evaluation are weekly, not nightly** — a full backtest
  suite is heavier than a training run, and a strategy's backtest result
  doesn't meaningfully change day-to-day the way retraining's *inputs* do.
- **Alert jobs run every 5 minutes with zero retries** (`_ALERT_ARGS`
  overrides `DEFAULT_ARGS`) — alerting is only useful if timely; retrying
  twice with a 5-minute backoff each would make a real outage take up to 15
  minutes to surface, which defeats the purpose.
- **Every other DAG uses 2 retries with exponential backoff** (`DEFAULT_ARGS`)
  — a transient DB/Redis blip should self-heal without paging anyone.

## 9. Testing strategy

Two fully separate environments, matching the isolation in §3:

- **`tests/unit/scheduler/jobs/`** and **`tests/integration/scheduler/jobs/`**
  run in the main app venv (`make test`) against real SQLite (matching Phase
  6/7's own precedent) and a **real Redis** (`docker-compose up redis`, or a
  local `redis-server` — not mocked; `cleanup_job`/`alert_sweep_job` exercise
  the genuine `cache.redis_client.RedisConnection`). `database_backup_job`'s
  tests exercise the real `FileNotFoundError` path (no `pg_dump` binary
  installed in this dev environment) plus a mocked-subprocess success/failure
  path.
- **`tests/unit/scheduler/airflow/`** requires the **isolated** Airflow
  environment (`requirements/airflow.txt`) and is run via `make dags-lint`,
  never `make test` — importing it in the main venv would hit the exact
  breakage described in §3. Validates DAG structure (imports cleanly, no
  cycles, correct task/schedule/retries) via Airflow's own `DagBag`; it
  cannot exercise an actual task *run*, which needs a real Docker daemon and
  the `scheduler-jobs` image built (neither available in the sandbox this
  phase was built in — a real deployment exercises this via `make
  airflow-up`).
- Both venvs' `mypy`/`ruff` runs are clean; the app venv's `mypy .` correctly
  skips `scheduler.airflow.*` (§5), and a second `mypy` run inside the
  isolated Airflow venv confirms that package is clean on its own terms.

---

**Phase 10 complete. Awaiting your review and approval before Phase 11.**
