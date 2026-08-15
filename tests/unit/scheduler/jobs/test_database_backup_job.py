"""Unit tests for scheduler.jobs.database_backup_job."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scheduler.jobs.database_backup_job import create_backup, run
from scheduler.jobs.job_result import JobStatus


class TestPgDumpNotFound:
    async def test_reports_failed_when_pg_dump_binary_is_missing(self, tmp_path: Path) -> None:
        # No mocking here -- this sandbox genuinely does not have pg_dump
        # installed, so this exercises the real FileNotFoundError path.
        result = await create_backup(backup_dir=tmp_path)
        assert result.status is JobStatus.FAILED
        assert "pg_dump" in (result.detail or "").lower()


class _FakeProcess:
    def __init__(self, returncode: int, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", self._stderr


class TestSuccessPath:
    async def test_reports_success_and_writes_context_when_pg_dump_succeeds(
        self, tmp_path: Path
    ) -> None:
        async def _fake_create_subprocess_exec(*args: object, **kwargs: object) -> _FakeProcess:
            # Simulate pg_dump's real effect: a file appears at -f's target.
            dump_path = Path(args[args.index("-f") + 1])  # type: ignore[arg-type]
            dump_path.write_bytes(b"fake dump contents")
            return _FakeProcess(returncode=0)

        with patch("asyncio.create_subprocess_exec", _fake_create_subprocess_exec):
            result = await create_backup(backup_dir=tmp_path)

        assert result.status is JobStatus.SUCCESS
        assert result.context["size_bytes"] == len(b"fake dump contents")
        assert Path(result.context["path"]).exists()


class TestFailurePath:
    async def test_reports_failed_when_pg_dump_exits_nonzero(self, tmp_path: Path) -> None:
        async def _fake_create_subprocess_exec(*args: object, **kwargs: object) -> _FakeProcess:
            return _FakeProcess(returncode=1, stderr=b"connection refused")

        with patch("asyncio.create_subprocess_exec", _fake_create_subprocess_exec):
            result = await create_backup(backup_dir=tmp_path)

        assert result.status is JobStatus.FAILED
        assert "connection refused" in result.context["stderr"]


class TestRun:
    async def test_run_delegates_to_create_backup(self, tmp_path: Path) -> None:
        # No pg_dump available -- confirms run() is wired to create_backup()
        # and surfaces its (failing, in this sandbox) result end-to-end.
        result = await run()
        assert result.job_name == "database_backup"
