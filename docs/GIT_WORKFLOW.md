# Git Workflow

Covers how work moves from an idea to a released version of the platform. Pairs with
`docs/CODING_STANDARDS.md` (what "good" code looks like) and `docs/CONTRIBUTING.md` (the
contributor-facing how-to).

---

## 1. Git Workflow (Overview)

We use **trunk-based development with short-lived feature branches**, gated by CI, mirroring the
three environments defined in Phase 1/2 (`dev` → `paper` → `live`):

```
feature/xyz ──┐
              ├─▶ main ──▶ CI (lint, type-check, unit+integration tests, backtest regression)
fix/xyz ──────┘             │
                             ├─▶ auto-deploy to `paper` environment
                             │
                             └─▶ manual-approval gate ──▶ deploy to `live` environment
```

- `main` is always deployable to `paper`. It is never force-pushed.
- Nothing reaches the `live` environment without passing through `paper` first and an explicit
  human approval (see `.github/workflows/cd-live.yml`, created in Phase 2).
- Long-lived divergent branches are avoided — the longer a branch lives apart from `main`, the more
  it drifts from the approved architecture and standards.

## 2. Branch Strategy

| Branch pattern | Purpose | Lives off | Merges to |
|---|---|---|---|
| `main` | Always-releasable trunk | — | — |
| `feature/<short-desc>` | New functionality | `main` | `main` (via PR) |
| `fix/<short-desc>` | Bug fix | `main` | `main` (via PR) |
| `hotfix/<short-desc>` | Urgent live-environment fix | `main` (or last release tag) | `main` +
  cherry-picked/tagged directly for emergency release |
| `chore/<short-desc>` | Tooling, deps, docs, CI config | `main` | `main` (via PR) |
| `release/<version>` | Optional stabilization branch cut just before a release when final
  regression/backtest validation is needed | `main` | tagged and merged back to `main` |

Rules:
- Branch names are lowercase, hyphen-separated, and reference an issue where one exists:
  `feature/risk-manager-drawdown-limit`, `fix/execution-order-state-race`.
- Delete a branch once its PR is merged — no long-lived personal branches.
- Never commit directly to `main` — even a one-line docs fix goes through a PR (fast to review, but
  still reviewed).

## 3. Commit Message Convention (Conventional Commits)

Format:
```
<type>(<scope>): <short summary, imperative mood, no trailing period>

<optional body — what/why, not how>

<optional footer — BREAKING CHANGE:, Refs #123>
```

**Types:**

| Type | Use for |
|---|---|
| `feat` | A new capability (new strategy, new endpoint, new module) |
| `fix` | A bug fix |
| `docs` | Documentation-only changes (this phase's commits, for example) |
| `style` | Formatting only, no logic change (rare — ruff format handles most of this) |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf` | Performance improvement |
| `test` | Adding or correcting tests |
| `build` | Build system, dependencies, Docker |
| `ci` | CI/CD pipeline changes |
| `chore` | Everything else maintenance-related |
| `revert` | Reverts a previous commit |

**Scope** is the top-level folder most affected: `risk`, `execution`, `api`, `ai`/`training`,
`docs`, `deployment`, etc.

**Examples:**
```
feat(risk): add configurable max-drawdown circuit breaker

fix(execution): correct partial-fill state transition race condition

docs(phase3): add engineering standards and git workflow

feat(api)!: require MFA header on live order endpoints

BREAKING CHANGE: clients submitting live orders must include an
X-MFA-Token header; paper-trading endpoints are unaffected.
```

- A `!` after the type/scope (or a `BREAKING CHANGE:` footer) marks a breaking change — this is
  what drives the **major** version bump under SemVer (§5).
- Squash-merge PRs into a single Conventional Commit on `main` where the PR contains many small
  "wip" commits; preserve individual commits only when each is independently meaningful.

## 4. Pull Request Guidelines

- One logical change per PR — a PR titled "risk: add drawdown limit" should not also refactor
  unrelated portfolio code.
- PR description follows `.github/PULL_REQUEST_TEMPLATE.md` (Phase 2): what changed, why, how it
  was tested, and the checklist below.
- **Required before requesting review:**
  - `make lint` and `make typecheck` pass locally (CI re-verifies).
  - Tests added/updated for the change; `make test` passes.
  - If the change touches the risk/execution/portfolio path, the backtest regression suite
    (`.github/workflows/backtest-regression.yml`) has been run.
  - No unrelated formatting churn.
- **Required reviewers:** at least one reviewer for any change; at least one reviewer with
  domain ownership of the affected folder (e.g. a Risk Manager change is reviewed by someone
  familiar with `risk/` and `docs/PHASE1_ARCHITECTURE.md` §12 Risk Manager) for anything touching
  `risk/`, `execution/`, `portfolio/`, or `live_trading/`.
- **Merge method:** squash-merge, Conventional Commit message as the final commit (§3).
- A PR that changes approved Phase 1 architecture or Phase 2 repository structure must call that
  out explicitly in its description and get sign-off before merge — per the standing rule carried
  from this phase's instructions.

## 5. Semantic Versioning (SemVer)

Format: `MAJOR.MINOR.PATCH` (e.g. `1.4.2`), applied as a Git tag on `main` at release time.

| Bump | When |
|---|---|
| **MAJOR** | Breaking change to a public contract: API Layer request/response shape, Kafka event
  schema, execution port interface, or anything requiring coordinated upgrade of dependent
  services/clients. |
| **MINOR** | Backward-compatible new functionality: a new strategy, a new endpoint, a new optional
  config field, a new model version behind the existing inference contract. |
| **PATCH** | Backward-compatible bug fix, performance improvement, or internal refactor with no
  external contract change. |

- Pre-1.0 (`0.x.y`) is used for the initial build-out phases — breaking changes are still called
  out via `!`/`BREAKING CHANGE:` but do not require a major bump under `0.x` by SemVer convention;
  the platform moves to `1.0.0` at the first version deployed to the `live` environment.
- Event schemas and the execution port are versioned independently where practical (e.g.
  `market.ticks.v2`) so a MAJOR platform bump isn't forced by every schema evolution — see the
  schema registry component in `docs/PHASE1_ARCHITECTURE.md` §7 Message Queue.

## 6. Release Strategy

1. Merges accumulate on `main`; every merge auto-deploys to `paper` (continuous deployment to the
   non-live environment).
2. When a release is ready to reach `live`: cut a `release/<version>` branch (optional but
   recommended once the platform is past early build-out), run the full backtest regression suite
   and integration/e2e suite against it, and tag `vMAJOR.MINOR.PATCH` on the commit that passes.
3. `cd-live.yml` triggers on the tag, but requires the manual approval gate defined in Phase 1's
   security architecture — no tag auto-deploys to `live` unbounded.
4. Release notes are generated from Conventional Commit history since the last tag (features,
   fixes, breaking changes called out separately) and stored under `docs/releases/` (introduced
   when the first release is cut).
5. Hotfixes to `live` follow an abbreviated path: `hotfix/<desc>` branched from the current live
   tag, minimal diff, expedited review (still required, never skipped), tagged as a new PATCH,
   and back-merged into `main` immediately so `main` never diverges from what's actually running
   live.
6. Rollback: because Order Execution/Live Trading run behind the versioned execution port and
   MLOps handles model rollback independently (`docs/PHASE1_ARCHITECTURE.md` §14), a bad release is
   rolled back by redeploying the previous tag — never by manually patching the running
   environment.

---

*This document is normative from Phase 4 onward. No branches, tags, or CI changes are created by
this phase — it is the standard other phases and contributors are expected to follow.*
