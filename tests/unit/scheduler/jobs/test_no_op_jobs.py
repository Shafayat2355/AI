"""Unit tests covering every job module in ``scheduler.jobs`` whose real
integration point is still a Phase 2 scaffold stub -- each should report a
documented, non-failing ``JobStatus.SKIPPED_NOT_IMPLEMENTED`` outcome, not
raise or report ``FAILED``.

This list shrinks as later phases implement the integration points behind
these jobs; a job leaves ``_NO_OP_JOB_MODULES`` at the moment its target
module becomes real, and gains coverage elsewhere instead:

* ``database_backup_job``, ``cleanup_job``, ``alert_sweep_job`` -- implemented
  in Phase 10, covered by their own dedicated test modules.
* ``historical_sync_job``, ``data_validation_job``, ``feature_generation_job``,
  ``hourly_market_sync_job`` -- implemented in Phase 11 (Feast feature store);
  their integration points are covered by ``tests/unit/datasets/``,
  ``tests/unit/feature_engineering/``, and
  ``tests/integration/feature_engineering/``.
* ``nightly_training_job``, ``model_evaluation_job`` -- implemented in Phase 12
  (ML training/model management); covered by ``tests/unit/training/``,
  ``tests/unit/models/`` and ``tests/integration/training/``.

Those jobs now require live infrastructure (a database, a populated feature
store) to run, so they are exercised through their integration points rather
than by calling ``run()`` with nothing wired up -- see
``TestImplementedJobsAreNoLongerNoOps`` below for the invariant that keeps
this file honest about which is which.
"""

from __future__ import annotations

import importlib

import pytest

from scheduler.jobs import (
    eod_reconciliation_job,
    periodic_backtest_job,
)
from scheduler.jobs.job_result import JobStatus

_NO_OP_JOB_MODULES = [
    (eod_reconciliation_job, "eod_reconciliation", "portfolio.portfolio_manager"),
    (periodic_backtest_job, "periodic_backtest", "backtesting.replay_engine"),
]

#: Integration points implemented by Phase 11/12. Importable, callable targets
#: -- the point of asserting on these is that a job must not silently regress
#: back to a no-op stub once its real implementation lands.
_IMPLEMENTED_INTEGRATION_POINTS = [
    ("datasets.historical.ohlcv_store", "sync_latest_history"),
    ("datasets.schemas.dataset_schema", "validate_latest_data"),
    ("feature_engineering.offline_pipeline", "run_batch_feature_generation"),
    ("feature_engineering.online_pipeline", "run_online_materialization"),
    ("training.trainer", "run_training_job"),
    ("mlops.promotion_policy", "evaluate_candidate_model"),
]


@pytest.mark.parametrize(
    ("module", "expected_job_name", "expected_module_path"), _NO_OP_JOB_MODULES
)
class TestGracefulNoOpJobs:
    async def test_reports_skipped_not_implemented(
        self, module: object, expected_job_name: str, expected_module_path: str
    ) -> None:
        result = await module.run()  # type: ignore[attr-defined]
        assert result.status is JobStatus.SKIPPED_NOT_IMPLEMENTED

    async def test_is_considered_succeeded_for_airflow_purposes(
        self, module: object, expected_job_name: str, expected_module_path: str
    ) -> None:
        result = await module.run()  # type: ignore[attr-defined]
        assert result.succeeded is True

    async def test_reports_the_expected_job_name(
        self, module: object, expected_job_name: str, expected_module_path: str
    ) -> None:
        result = await module.run()  # type: ignore[attr-defined]
        assert result.job_name == expected_job_name

    async def test_detail_names_the_missing_integration_point(
        self, module: object, expected_job_name: str, expected_module_path: str
    ) -> None:
        result = await module.run()  # type: ignore[attr-defined]
        assert expected_module_path in (result.detail or "")


class TestImplementedJobsAreNoLongerNoOps:
    """Guards the boundary the module docstring describes: every integration
    point Phase 11/12 implemented must actually exist and be callable, so a
    job cannot quietly fall back to ``SKIPPED_NOT_IMPLEMENTED`` after its
    implementation landed."""

    @pytest.mark.parametrize(("module_path", "function_name"), _IMPLEMENTED_INTEGRATION_POINTS)
    def test_the_integration_point_exists_and_is_callable(
        self, module_path: str, function_name: str
    ) -> None:
        module = importlib.import_module(module_path)
        assert callable(getattr(module, function_name))

    @pytest.mark.parametrize(("module_path", "function_name"), _IMPLEMENTED_INTEGRATION_POINTS)
    def test_the_integration_point_is_not_in_the_no_op_list(
        self, module_path: str, function_name: str
    ) -> None:
        no_op_targets = {target for _, _, target in _NO_OP_JOB_MODULES}
        assert module_path not in no_op_targets
