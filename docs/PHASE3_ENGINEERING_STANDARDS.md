# Phase 3 — Engineering Standards

**Status:** Documentation only. No business logic, no application code, and no changes to the
Phase 1 architecture or Phase 2 repository structure are introduced by this phase.

This document is the index and canonical home for the standards that don't have a more specific
home elsewhere, plus a map of where every requested topic actually lives.

## Repository Review Note

Before writing this phase, the current repository (`github.com/Shafayat2355/AI`) was reviewed.
One structural drift from the Phase 2 approved layout was observed: the Phase 2 document groups
`training/`, `inference/`, `models/`, and `mlops/` under a single top-level `ai/` package, but the
live repository currently has them as separate top-level folders (`training/`, `inference/`,
`models/`, `mlops/`). **No file was changed to reconcile this** — Phase 3 is documentation-only and
this phase does not touch approved structure. Flagging it here for visibility; if you'd like it
reconciled (either by updating Phase 2's document to match reality, or by moving folders back under
`ai/`), that should be a deliberate, approved change in its own right, not a side effect of this
phase. The standards below are written to apply correctly either way.

## Where Each Required Topic Lives

| Topic | Document |
|---|---|
| Coding Standards | `docs/CODING_STANDARDS.md` §1 |
| Naming Conventions | `docs/CODING_STANDARDS.md` §2 |
| Folder Conventions | `docs/CODING_STANDARDS.md` §3 |
| Import Conventions | `docs/CODING_STANDARDS.md` §4 |
| Dependency Rules | `docs/CODING_STANDARDS.md` §5 |
| SOLID Principles | `docs/CODING_STANDARDS.md` §6 |
| Clean Architecture Rules | `docs/CODING_STANDARDS.md` §7 |
| Dependency Injection Guidelines | `docs/CODING_STANDARDS.md` §8 |
| Repository Pattern Guidelines | `docs/CODING_STANDARDS.md` §9 |
| Service Layer Guidelines | `docs/CODING_STANDARDS.md` §10 |
| Error Handling Strategy | `docs/CODING_STANDARDS.md` §11 |
| Logging Strategy | `docs/CODING_STANDARDS.md` §12 |
| Configuration Management | `docs/CODING_STANDARDS.md` §13 |
| Security Coding Guidelines | `docs/CODING_STANDARDS.md` §14 |
| Testing Strategy | This document, §1 |
| Documentation Strategy | This document, §2 |
| Code Review Checklist | `docs/CONTRIBUTING.md` |
| Git Workflow | `docs/GIT_WORKFLOW.md` §1 |
| Branch Strategy | `docs/GIT_WORKFLOW.md` §2 |
| Commit Message Convention | `docs/GIT_WORKFLOW.md` §3 |
| Pull Request Guidelines | `docs/GIT_WORKFLOW.md` §4 |
| Semantic Versioning | `docs/GIT_WORKFLOW.md` §5 |
| Release Strategy | `docs/GIT_WORKFLOW.md` §6 |

---

## 1. Testing Strategy

Four layers, matching `tests/unit/`, `tests/integration/`, `tests/e2e/`, and the backtest
regression suite already scaffolded in Phase 2:

### 1.1 Unit Tests (`tests/unit/`)
- Scope: a single class/function in isolation — `core/domain/`, `core/use_cases/`, domain-folder
  managers (`RiskManager`, `PortfolioManager`, etc.).
- Dependencies: all ports are faked/mocked in-memory (per `docs/CODING_STANDARDS.md` §8) — no
  Kafka, no DB, no network, no real clock (inject a fake clock for time-dependent logic).
- Speed: the entire unit suite should run in seconds, so it runs on every save/pre-commit.
- Ownership: written by whoever writes the corresponding logic, in the same PR.

### 1.2 Integration Tests (`tests/integration/`)
- Scope: one adapter against its real dependency — a repository against a real (test) Postgres, a
  Kafka producer/consumer against a real (test) Kafka via `docker-compose`, the feature store
  client against Redis.
- Purpose: prove the adapter actually satisfies the port contract it implements, not just that the
  domain logic is correct in isolation.
- Run in CI on every PR (`.github/workflows/ci.yml`), using the services defined in
  `docker-compose.yml`.

### 1.3 End-to-End Tests (`tests/e2e/`)
- Scope: the full signal-to-fill pipeline (`docs/PHASE1_ARCHITECTURE.md` §6 Event Flow) exercised
  against the **paper trading** environment only.
- Purpose: catch integration gaps between services that unit/integration tests, being scoped to
  one module, cannot see — e.g. an event schema mismatch between Strategy Engine and Risk Manager.
- Run before any promotion toward `live` (see `docs/GIT_WORKFLOW.md` §6 Release Strategy); not
  required on every commit given their cost, but required before a release tag.

### 1.4 Backtest Regression
- Scope: strategy logic, risk rule changes, and newly promoted models, replayed against a fixed
  historical dataset via `backtesting/replay_engine.py`.
- Purpose: the platform's equivalent of a performance regression test — a strategy or model change
  that silently degrades Sharpe ratio, drawdown, or win rate is caught here before it reaches
  paper or live, not after.
- Trigger: `.github/workflows/backtest-regression.yml`, required for any PR touching
  `strategies/`, `risk/`, `ai/training` (or `training/`), or `ai/inference` (or `inference/`).

### 1.5 General Rules
- A bug fix includes a regression test that fails before the fix and passes after.
- Flaky tests are fixed or quarantined immediately, never ignored — a flaky test in the risk/
  execution path erodes exactly the confidence the whole test strategy exists to provide.
- Test data/fixtures live in `tests/fixtures/`, versioned like any other code, never pulled live
  from production/paper systems into a test run.

## 2. Documentation Strategy

- **Phase documents** (`docs/PHASE1_ARCHITECTURE.md`, `docs/PHASE2_REPOSITORY_STRUCTURE.md`, this
  document, and future phase documents) are the historical record of approved decisions — they are
  amended only through the same explain-first, approval-gated process used to create them, per the
  standing instruction carried through every phase of this project.
- **Standards documents** (`docs/CODING_STANDARDS.md`, `docs/GIT_WORKFLOW.md`,
  `docs/CONTRIBUTING.md`) are living documents — they may be refined over time via a normal
  `docs`-scoped PR (`docs/GIT_WORKFLOW.md` §3), since they describe *how* to build, not *what was
  approved to be built*.
- **Architecture Decision Records** (`docs/adr/`) capture the reasoning behind any significant
  design choice made after Phase 1, numbered sequentially. A new ADR is required whenever a
  decision would be expensive to reverse or contradicts an existing document (e.g. deviating from
  EDMA for one module, changing an event schema in a breaking way).
- **Runbooks** (`docs/runbooks/`) are operational, not architectural — written for whoever is
  on-call, assuming no prior context beyond "something is on fire." They're updated whenever an
  incident reveals a gap.
- **API documentation** (`docs/api/openapi.yaml`) is kept in sync with `api/routers/` as a review
  requirement (`docs/CONTRIBUTING.md` Code Review Checklist), not as a separate later task.
- **In-code documentation:** every module has a one-line purpose docstring (established in Phase
  2); public classes/functions get a short docstring explaining intent when the name alone isn't
  self-explanatory — avoid restating the type signature in prose.
- **No orphaned docs:** a document that no longer reflects the code it describes is either updated
  or explicitly marked deprecated with a pointer to its replacement — never left silently stale.

---

**Phase 3 complete. No code, no architecture changes, no repository-structure changes. Awaiting
your review and approval before Phase 4.**
