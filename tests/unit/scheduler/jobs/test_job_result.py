"""Unit tests for scheduler.jobs.job_result."""

from __future__ import annotations

from scheduler.jobs.job_result import (
    JobResult,
    JobStatus,
    call_integration_point,
    now_utc,
)


class TestJobResult:
    def test_duration_seconds_computes_the_elapsed_time(self) -> None:
        started = now_utc()
        import time

        time.sleep(0.01)
        finished = now_utc()
        result = JobResult(
            job_name="x", status=JobStatus.SUCCESS, started_at=started, finished_at=finished
        )
        assert result.duration_seconds >= 0.01

    def test_succeeded_is_true_for_success(self) -> None:
        now = now_utc()
        result = JobResult(job_name="x", status=JobStatus.SUCCESS, started_at=now, finished_at=now)
        assert result.succeeded is True

    def test_succeeded_is_true_for_skipped_not_implemented(self) -> None:
        now = now_utc()
        result = JobResult(
            job_name="x",
            status=JobStatus.SKIPPED_NOT_IMPLEMENTED,
            started_at=now,
            finished_at=now,
        )
        assert result.succeeded is True

    def test_succeeded_is_false_for_failed(self) -> None:
        now = now_utc()
        result = JobResult(job_name="x", status=JobStatus.FAILED, started_at=now, finished_at=now)
        assert result.succeeded is False

    def test_context_defaults_to_empty_dict(self) -> None:
        now = now_utc()
        result = JobResult(job_name="x", status=JobStatus.SUCCESS, started_at=now, finished_at=now)
        assert result.context == {}

    def test_is_frozen(self) -> None:
        now = now_utc()
        result = JobResult(job_name="x", status=JobStatus.SUCCESS, started_at=now, finished_at=now)
        try:
            result.job_name = "y"  # type: ignore[misc]
        except Exception:
            pass
        else:
            raise AssertionError("expected JobResult to be immutable")


class TestCallIntegrationPoint:
    async def test_returns_skipped_not_implemented_when_the_attribute_is_missing(self) -> None:
        result = await call_integration_point(
            job_name="test_job",
            module_path="scheduler.jobs.job_result",  # a real, importable module...
            attribute_name="this_function_does_not_exist",  # ...that lacks this attribute
        )
        assert result.status is JobStatus.SKIPPED_NOT_IMPLEMENTED
        assert result.succeeded is True
        assert "this_function_does_not_exist" in (result.detail or "")

    async def test_returns_failed_when_the_module_does_not_exist(self) -> None:
        result = await call_integration_point(
            job_name="test_job",
            module_path="scheduler.jobs.this_module_does_not_exist",
            attribute_name="anything",
        )
        assert result.status is JobStatus.FAILED
        assert result.succeeded is False

    async def test_returns_success_and_calls_the_target_when_it_exists(self) -> None:
        calls = {"count": 0}

        async def _fake_target(*, foo: int) -> str:
            calls["count"] += 1
            return f"foo-was-{foo}"

        import scheduler.jobs.job_result as job_result_module

        job_result_module.fake_target_for_test = _fake_target  # type: ignore[attr-defined]
        try:
            result = await call_integration_point(
                job_name="test_job",
                module_path="scheduler.jobs.job_result",
                attribute_name="fake_target_for_test",
                kwargs={"foo": 42},
            )
        finally:
            del job_result_module.fake_target_for_test  # type: ignore[attr-defined]

        assert result.status is JobStatus.SUCCESS
        assert calls["count"] == 1
        assert result.context["result"] == "foo-was-42"

    async def test_returns_failed_when_the_target_raises(self) -> None:
        async def _fake_target() -> None:
            raise RuntimeError("boom")

        import scheduler.jobs.job_result as job_result_module

        job_result_module.raising_target_for_test = _fake_target  # type: ignore[attr-defined]
        try:
            result = await call_integration_point(
                job_name="test_job",
                module_path="scheduler.jobs.job_result",
                attribute_name="raising_target_for_test",
            )
        finally:
            del job_result_module.raising_target_for_test  # type: ignore[attr-defined]

        assert result.status is JobStatus.FAILED
        assert "boom" in (result.detail or "")
