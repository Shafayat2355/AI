"""Unified CLI entrypoint for every job in ``scheduler.jobs``.

This is what Airflow's ``DockerOperator`` actually runs inside the platform's
own container/image (see ``scheduler/airflow/dag_common.py``):

    python -m scheduler.jobs.cli <job_module_name>

...also usable directly from a shell for a manual/local run of any job,
without Airflow involved at all. Dynamically imports
``scheduler.jobs.<job_module_name>`` and calls its module-level ``run()``
coroutine, rather than maintaining a separate hardcoded registry that could
drift out of sync with the actual job modules.

Exit code is the whole point of this module existing: ``0`` for
:data:`~scheduler.jobs.job_result.JobResult.succeeded` (a real success *or* a
documented not-yet-implemented no-op), ``1`` for an actual failure -- that
exit code is exactly what Airflow's ``DockerOperator`` uses to decide whether
a task run succeeded, so this file is the one place that mapping lives.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys

from config.settings import get_settings
from scheduler.jobs.job_result import JobResult
from shared.logging.logger import configure_logging, get_logger

_logger = get_logger("scheduler.jobs.cli")


async def dispatch(job_module_name: str) -> JobResult:
    """Import ``scheduler.jobs.<job_module_name>`` and await its ``run()``."""
    module = importlib.import_module(f"scheduler.jobs.{job_module_name}")
    run_fn = getattr(module, "run", None)
    if run_fn is None:
        raise AttributeError(
            f"scheduler.jobs.{job_module_name} has no module-level run() coroutine"
        )
    result: JobResult = await run_fn()
    return result


def _result_to_log_fields(result: JobResult) -> dict[str, object]:
    return {
        "channel": "application",
        "job_name": result.job_name,
        "status": result.status.value,
        "duration_seconds": round(result.duration_seconds, 3),
        "detail": result.detail,
    }


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns the process exit code (does not call ``sys.exit``
    itself, so tests can call this directly and inspect the return value)."""
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: python -m scheduler.jobs.cli <job_module_name>", file=sys.stderr)
        return 2

    settings = get_settings()
    configure_logging(settings.logging, settings.environment)

    job_module_name = args[0]
    try:
        result = asyncio.run(dispatch(job_module_name))
    except Exception:
        _logger.error(
            "job_dispatch_failed",
            extra={"channel": "application", "job_module_name": job_module_name},
            exc_info=True,
        )
        return 1

    log_level = _logger.info if result.succeeded else _logger.error
    log_level("job_run_completed", extra=_result_to_log_fields(result))
    # Also printed as JSON to stdout -- Airflow surfaces task stdout directly in
    # its UI, so this is what an operator actually sees without digging through
    # the structured log sink.
    print(
        json.dumps(
            {
                "job_name": result.job_name,
                "status": result.status.value,
                "duration_seconds": round(result.duration_seconds, 3),
                "detail": result.detail,
            }
        )
    )
    return 0 if result.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
