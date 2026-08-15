"""Unit tests covering every job module in ``scheduler.jobs`` whose real
integration point is a Phase 2 scaffold stub as of Phase 10 -- each should
report a documented, non-failing ``JobStatus.SKIPPED_NOT_IMPLEMENTED``
outcome, not raise or report ``FAILED``.

``database_backup_job``, ``cleanup_job``, and ``alert_sweep_job`` are not
included here -- they have real, working implementations as of this phase
and are tested in their own dedicated test modules instead.
"""

from __future__ import annotations

import pytest

from scheduler.jobs import (
    data_validation_job,
    eod_reconciliation_job,
    feature_generation_job,
    historical_sync_job,
    hourly_market_sync_job,
    model_evaluation_job,
    nightly_training_job,
    periodic_backtest_job,
)
from scheduler.jobs.job_result import JobStatus

_NO_OP_JOB_MODULES = [
    (eod_reconciliation_job, "eod_reconciliation", "portfolio.portfolio_manager"),
    (nightly_training_job, "nightly_training", "training.trainer"),
    (periodic_backtest_job, "periodic_backtest", "backtesting.replay_engine"),
    (hourly_market_sync_job, "hourly_market_sync", "feature_engineering.online_pipeline"),
    (historical_sync_job, "historical_sync", "datasets.historical.ohlcv_store"),
    (data_validation_job, "data_validation", "datasets.schemas.dataset_schema"),
    (feature_generation_job, "feature_generation", "feature_engineering.offline_pipeline"),
    (model_evaluation_job, "model_evaluation", "mlops.promotion_policy"),
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
