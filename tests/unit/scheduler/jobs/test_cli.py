"""Unit tests for scheduler.jobs.cli."""

from __future__ import annotations

import pytest

from scheduler.jobs.cli import dispatch, main


class TestDispatch:
    async def test_dispatches_to_the_named_jobs_run_function(self) -> None:
        result = await dispatch("nightly_training_job")
        assert result.job_name == "nightly_training"

    async def test_raises_attribute_error_for_a_module_with_no_run_function(self) -> None:
        # job_result.py is a real, importable module in this package, but it
        # has no module-level run() coroutine -- exactly the case this should reject.
        with pytest.raises(AttributeError, match="no module-level run"):
            await dispatch("job_result")

    async def test_raises_import_error_for_a_nonexistent_module(self) -> None:
        with pytest.raises(ImportError):
            await dispatch("this_job_does_not_exist")


class TestMain:
    def test_returns_2_with_no_arguments(self) -> None:
        assert main([]) == 2

    def test_returns_2_with_too_many_arguments(self) -> None:
        assert main(["a", "b"]) == 2

    def test_returns_0_for_a_graceful_no_op_job(self) -> None:
        # periodic_backtest_job's integration point (backtesting.replay_engine)
        # is still a scaffold stub, so it exercises the graceful-no-op path.
        # nightly_training_job was used here until Phase 12 implemented
        # training.trainer -- it now needs a real database and is covered by
        # tests/integration/training/ instead.
        assert main(["periodic_backtest_job"]) == 0

    def test_returns_1_for_a_dispatch_failure(self) -> None:
        assert main(["this_job_does_not_exist"]) == 1

    def test_prints_json_result_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        main(["periodic_backtest_job"])
        captured = capsys.readouterr()
        assert '"job_name": "periodic_backtest"' in captured.out
        assert '"status": "skipped_not_implemented"' in captured.out
