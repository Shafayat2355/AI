# Contributing

Practical, contributor-facing entry point. The full rules live in
`docs/CODING_STANDARDS.md`, `docs/GIT_WORKFLOW.md`, and `docs/PHASE3_ENGINEERING_STANDARDS.md` —
this document tells you which one to read for what, plus the day-to-day checklist.

## Before You Start

1. Read `docs/PHASE1_ARCHITECTURE.md` — understand why the platform is event-driven microservices
   before touching any module; it explains what each folder is for and why it can't call another
   folder directly.
2. Read `docs/PHASE2_REPOSITORY_STRUCTURE.md` — know where your change belongs before writing it.
   New functionality goes in the existing folder that owns that responsibility; a new top-level
   folder is a Phase 2 amendment, not something to add ad hoc.
3. Set up your environment:
   ```
   make setup
   make up      # starts Kafka, Postgres, Redis locally
   ```

## Making a Change

1. Branch from `main` following `docs/GIT_WORKFLOW.md` §2 (`feature/...`, `fix/...`, etc.).
2. Write the change following `docs/CODING_STANDARDS.md` — in particular:
   - Domain logic goes in `core/` or the owning domain folder; wiring goes in `app/`.
   - New adapters implement an existing port in `core/ports/`; don't invent a new access pattern
     for something a port already covers.
   - Any new exception derives from `shared/errors/exceptions.py`'s hierarchy.
   - Any new log statement goes through `shared/logging/logger.py`.
3. Add or update tests alongside the change (see Testing, below) — a PR without tests for new
   behavior will not be approved.
4. Run locally before opening a PR:
   ```
   make format
   make lint
   make typecheck
   make test
   ```
5. If your change touches `risk/`, `execution/`, `portfolio/`, `strategies/`, or `live_trading/`,
   also run the backtest regression suite locally or confirm CI will run it.

## Testing Expectations

- **Unit tests** (`tests/unit/`) — mirror source layout, one test file per module, fakes/in-memory
  adapters injected via the same ports the real code depends on (`docs/CODING_STANDARDS.md` §8).
  Required for all new logic in `core/`, domain folders, and `shared/`.
- **Integration tests** (`tests/integration/`) — exercise a module against real Kafka/DB/Redis
  (via `docker-compose`), verifying an adapter actually satisfies its port contract. Required for
  new repositories, new Kafka producers/consumers, new external feed adapters.
- **End-to-end tests** (`tests/e2e/`) — run the full signal-to-fill pipeline against **paper
  trading only**, never against `live`. Required for any change that touches more than one service
  in the critical path (Strategy → Risk → Execution → Portfolio).
- **Backtest regression** — required whenever strategy logic, risk rules, or a promoted model
  changes; compares performance metrics against the last known-good baseline to catch silent
  behavioral regressions.
- New code should not drop overall coverage; critical-path folders (`risk/`, `execution/`,
  `portfolio/`) are expected to stay near full branch coverage given their fail-closed
  requirements (`docs/CODING_STANDARDS.md` §11).

## Documentation Expectations

- Any new module gets a short docstring purpose statement at the top of the file, consistent with
  the Phase 2 scaffold convention.
- Any new port in `core/ports/` is documented with what contract it represents and which adapters
  are expected to implement it.
- Any new Kafka event or topic is documented in the relevant domain folder's module docstring and,
  if it's a new topic, added to `docs/PHASE1_ARCHITECTURE.md`'s event flow section (as an
  architecture-affecting change requiring the sign-off called out in `docs/GIT_WORKFLOW.md` §4).
- Any new external endpoint is added to `docs/api/openapi.yaml`.
- Runbook-worthy operational changes (new failure mode, new manual recovery step) get added to
  `docs/runbooks/`.
- Architecture Decision Records for any non-trivial design choice go in `docs/adr/`, numbered
  sequentially from `0001-event-driven-microservices.md`.

## Code Review Checklist

Reviewers (and authors, before requesting review) check:

- [ ] Change is in the correct folder per the approved Phase 2 structure; no new top-level folder
      introduced without a Phase 2 amendment.
- [ ] Dependency direction respected — domain code doesn't import concrete adapters directly
      (`docs/CODING_STANDARDS.md` §4–§5).
- [ ] `core/domain/` and `core/ports/` remain free of framework/infra imports.
- [ ] New exceptions derive from the shared hierarchy; no bare `except:`.
- [ ] Logging uses the shared logger with correlation ID; no `print()`; no secrets logged.
- [ ] Config values are read via `config/settings.py` / `config/config_client.py`, not
      `os.environ` directly.
- [ ] New/changed public functions are fully typed; `mypy` passes.
- [ ] Tests cover the new behavior at the appropriate level (unit/integration/e2e); backtest
      regression run if applicable.
- [ ] Naming follows `docs/CODING_STANDARDS.md` §2 (ports suffixed `Port`, events past-tense, etc.).
- [ ] No breaking change to an event schema, API contract, or execution port without it being
      called out in the PR description and a MAJOR version implication noted.
- [ ] Any change to Phase 1 architecture or Phase 2 structure is flagged explicitly and has
      separate sign-off — not bundled silently into an unrelated PR.
- [ ] Security: input validated at the boundary, authz checked for any new endpoint, no
      credentials committed.
- [ ] Docs updated per the Documentation Expectations above.
- [ ] Commit messages and PR title follow Conventional Commits (`docs/GIT_WORKFLOW.md` §3).

## Opening the PR

- Follow `.github/PULL_REQUEST_TEMPLATE.md`.
- Fill in what changed, why, and how it was tested — link the issue if one exists.
- Request review per `docs/GIT_WORKFLOW.md` §4 (domain-owner review required for
  risk/execution/portfolio/live_trading changes).
- Once approved and CI is green, squash-merge with a Conventional Commit message.

## Getting Help

- Architecture questions → `docs/PHASE1_ARCHITECTURE.md` and `docs/adr/`.
- "Where does this code go?" → `docs/PHASE2_REPOSITORY_STRUCTURE.md`.
- "How do I write this?" → `docs/CODING_STANDARDS.md`.
- "How do I branch/commit/release this?" → `docs/GIT_WORKFLOW.md`.
- Anything not covered by the above → raise it as a `docs`-scoped PR proposing an addition to
  `docs/PHASE3_ENGINEERING_STANDARDS.md` rather than deciding ad hoc.
