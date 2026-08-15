"""Shared result type and integration-point helper for every module in
``scheduler.jobs``.

Every job in this package returns a :class:`JobResult` (not a bare ``None`` or
a raised exception for "not applicable") so a caller -- an Airflow
``DockerOperator``'s exit code, a unit test, another job composing several
sub-steps -- has one consistent shape to inspect regardless of which job ran.

:func:`call_integration_point` exists because most of this phase's job
categories (retraining, historical sync, data validation, feature generation,
backtesting, model evaluation) are meant to trigger real work in modules that
do not have a callable implementation yet as of Phase 10 --
``training/``, ``datasets/``, ``feature_engineering/``, ``backtesting/``, and
``mlops/`` are still Phase 2 scaffold stubs (a one-line docstring each, no
class or function defined). Rather than have those jobs raise on every run
until whichever future phase implements the target module -- which would make
every Airflow DAG for those categories permanently red, training operators to
ignore real failures -- each job calls its real integration point through this
helper, which reports a distinct, non-failing
:data:`JobStatus.SKIPPED_NOT_IMPLEMENTED` outcome when the target module
exists but does not yet expose the expected callable, and logs a clear
``WARNING`` naming exactly what is missing. The moment a future phase adds the
real function, these jobs call it with zero code changes on this side.
"""

from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from shared.logging.logger import get_logger

_logger = get_logger("scheduler.jobs")


class JobStatus(StrEnum):
    """Outcome of one job run."""

    SUCCESS = "success"
    FAILED = "failed"
    #: The job's real integration point does not exist yet (see module
    #: docstring) -- a documented, expected no-op, not a failure.
    SKIPPED_NOT_IMPLEMENTED = "skipped_not_implemented"


@dataclass(frozen=True)
class JobResult:
    """The outcome of one job run, returned by every ``scheduler.jobs.*run()``."""

    job_name: str
    status: JobStatus
    started_at: datetime
    finished_at: datetime
    detail: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    @property
    def succeeded(self) -> bool:
        """Whether Airflow (or any other caller) should treat this run as
        successful -- true for both a real success and a documented
        not-yet-implemented no-op, false only for an actual failure."""
        return self.status is not JobStatus.FAILED


def now_utc() -> datetime:
    return datetime.now(UTC)


async def call_integration_point(
    *,
    job_name: str,
    module_path: str,
    attribute_name: str,
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
) -> JobResult:
    """Import ``module_path``, look up ``attribute_name`` on it, and ``await``
    calling it with ``args``/``kwargs``.

    Returns :data:`JobStatus.SKIPPED_NOT_IMPLEMENTED` (not a raised exception)
    when the module can be imported but does not yet define
    ``attribute_name`` -- the expected state of every AI/data-pipeline
    integration point as of Phase 10, per this module's docstring. A genuine
    import failure (the module itself does not exist -- a typo, or a package
    renamed) or an exception raised by the callable itself both still
    surface as :data:`JobStatus.FAILED`, since those indicate an actual defect
    rather than "not built yet."
    """
    started_at = now_utc()
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        finished_at = now_utc()
        _logger.error(
            "job_integration_module_import_failed",
            extra={
                "channel": "application",
                "job_name": job_name,
                "module_path": module_path,
            },
            exc_info=True,
        )
        return JobResult(
            job_name=job_name,
            status=JobStatus.FAILED,
            started_at=started_at,
            finished_at=finished_at,
            detail=f"failed to import {module_path!r}: {exc}",
        )

    target: Callable[..., Awaitable[Any]] | None = getattr(module, attribute_name, None)
    if target is None:
        finished_at = now_utc()
        _logger.warning(
            "job_integration_point_not_implemented",
            extra={
                "channel": "application",
                "job_name": job_name,
                "module_path": module_path,
                "attribute_name": attribute_name,
            },
        )
        return JobResult(
            job_name=job_name,
            status=JobStatus.SKIPPED_NOT_IMPLEMENTED,
            started_at=started_at,
            finished_at=finished_at,
            detail=(
                f"{module_path}.{attribute_name} is not implemented yet -- "
                f"this job is a documented no-op until that phase lands"
            ),
        )

    try:
        result = await target(*args, **(kwargs or {}))
    except Exception as exc:
        finished_at = now_utc()
        _logger.error(
            "job_integration_point_raised",
            extra={
                "channel": "application",
                "job_name": job_name,
                "module_path": module_path,
                "attribute_name": attribute_name,
            },
            exc_info=True,
        )
        return JobResult(
            job_name=job_name,
            status=JobStatus.FAILED,
            started_at=started_at,
            finished_at=finished_at,
            detail=f"{module_path}.{attribute_name} raised: {exc}",
        )

    finished_at = now_utc()
    return JobResult(
        job_name=job_name,
        status=JobStatus.SUCCESS,
        started_at=started_at,
        finished_at=finished_at,
        detail=f"{module_path}.{attribute_name} completed",
        context={"result": result} if result is not None else {},
    )


__all__ = ["JobResult", "JobStatus", "call_integration_point", "now_utc"]
