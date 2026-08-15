"""Database backup job: runs ``pg_dump`` against the platform's own PostgreSQL
database, using the exact same connection settings the application itself
uses (``config.settings.get_settings().postgres``) -- no separate connection
string maintained for backups.

Requires the ``pg_dump`` client binary to be present in whatever
image/container this module actually runs in (see
``docker/scheduler_jobs.Dockerfile``, which installs ``postgresql-client``) --
this module does not, and cannot, install it itself.
"""

from __future__ import annotations

import asyncio.subprocess
import os
from pathlib import Path

from config.settings import get_settings
from scheduler.jobs.job_result import JobResult, JobStatus, now_utc
from shared.logging.audit import log_audit_event
from shared.logging.logger import get_logger

_logger = get_logger("scheduler.jobs.database_backup")

#: Where backups are written inside the container. Mount a persistent volume
#: here in the real deployment (see docker-compose.yml's ``airflow-scheduler``
#: service, which shares this path via a named volume) -- a backup that only
#: exists inside a container's writable layer is not a backup.
DEFAULT_BACKUP_DIR = Path(os.environ.get("DATABASE_BACKUP_DIR", "/var/backups/postgres"))


async def create_backup(backup_dir: Path | None = None) -> JobResult:
    """Run ``pg_dump`` against the configured Postgres database, writing a
    timestamped, custom-format dump file to ``backup_dir``.

    Uses ``pg_dump``'s custom format (``-Fc``) rather than plain SQL -- it's
    compressed and supports selective/parallel restore via ``pg_restore``,
    which a plain ``.sql`` dump does not.
    """
    started_at = now_utc()
    job_name = "database_backup"
    settings = get_settings()
    postgres = settings.postgres
    target_dir = backup_dir or DEFAULT_BACKUP_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    dump_path = target_dir / f"{postgres.database}-{timestamp}.dump"

    env = {
        **os.environ,
        "PGPASSWORD": postgres.password.get_secret_value(),
    }
    command = [
        "pg_dump",
        "-h",
        postgres.host,
        "-p",
        str(postgres.port),
        "-U",
        postgres.user,
        "-d",
        postgres.database,
        "-Fc",
        "-f",
        str(dump_path),
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
    except FileNotFoundError as exc:
        finished_at = now_utc()
        _logger.error(
            "database_backup_pg_dump_not_found",
            extra={"channel": "application", "job_name": job_name},
            exc_info=True,
        )
        return JobResult(
            job_name=job_name,
            status=JobStatus.FAILED,
            started_at=started_at,
            finished_at=finished_at,
            detail=f"pg_dump binary not found: {exc}",
        )

    finished_at = now_utc()

    if process.returncode != 0:
        _logger.error(
            "database_backup_failed",
            extra={
                "channel": "application",
                "job_name": job_name,
                "return_code": process.returncode,
                "stderr": stderr.decode("utf-8", errors="replace"),
            },
        )
        return JobResult(
            job_name=job_name,
            status=JobStatus.FAILED,
            started_at=started_at,
            finished_at=finished_at,
            detail=f"pg_dump exited with code {process.returncode}",
            context={"stderr": stderr.decode("utf-8", errors="replace")},
        )

    size_bytes = dump_path.stat().st_size
    log_audit_event(
        action="database_backup_created",
        actor="scheduler.jobs.database_backup",
        resource=str(dump_path),
        outcome="success",
        size_bytes=size_bytes,
    )
    return JobResult(
        job_name=job_name,
        status=JobStatus.SUCCESS,
        started_at=started_at,
        finished_at=finished_at,
        detail=f"backup written to {dump_path}",
        context={"path": str(dump_path), "size_bytes": size_bytes},
    )


async def run() -> JobResult:
    """Entry point called by ``scheduler.jobs.cli`` / Airflow's ``DockerOperator``."""
    return await create_backup()


__all__ = ["create_backup", "run"]
