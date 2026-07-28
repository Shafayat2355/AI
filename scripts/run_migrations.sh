#!/usr/bin/env bash
# Applies pending database migrations against the target environment.
#
# Usage: ENVIRONMENT=paper ./scripts/run_migrations.sh [alembic-args...]
# Defaults to `alembic upgrade head`; any arguments are passed through to
# `alembic` verbatim, e.g. `./scripts/run_migrations.sh downgrade -1`.
#
# Reads DATABASE_URL / POSTGRES_* from the environment (or a loaded .env) the
# same way the application itself does -- see database/migrations/env.py.

set -euo pipefail

if [ "$#" -eq 0 ]; then
  alembic upgrade head
else
  alembic "$@"
fi
