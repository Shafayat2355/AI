"""Structural tests for every DAG in ``scheduler/airflow/dags/``.

Verifies each DAG parses without error, has exactly the expected task(s), a
schedule, and (per ``dag_common.build_job_task``) is wired to run through
``PLATFORM_JOBS_IMAGE`` with the fixed ``on_failure_callback``. Does not (and
cannot, in this environment -- see
``docs/PHASE10_WORKFLOW_ORCHESTRATION.md`` Sec 3/9) exercise an actual task
run, which requires a real Docker daemon and the built
``trading-platform-scheduler-jobs`` image.
"""

from __future__ import annotations

from airflow.models import DagBag

from scheduler.airflow.dag_common import PLATFORM_JOBS_IMAGE, on_job_failure
from tests.unit.scheduler.airflow.conftest import DAGS_FOLDER

_EXPECTED_DAGS = {
    "daily_jobs": ("eod_reconciliation", "eod_reconciliation_job"),
    "hourly_jobs": ("hourly_market_sync", "hourly_market_sync_job"),
    "retraining": ("nightly_training", "nightly_training_job"),
    "historical_sync": ("historical_sync", "historical_sync_job"),
    "data_validation": ("data_validation", "data_validation_job"),
    "feature_generation": ("feature_generation", "feature_generation_job"),
    "backtesting": ("periodic_backtest", "periodic_backtest_job"),
    "model_evaluation": ("model_evaluation", "model_evaluation_job"),
    "cleanup": ("cleanup", "cleanup_job"),
    "database_backup": ("database_backup", "database_backup_job"),
    "alert_jobs": ("alert_sweep", "alert_sweep_job"),
}


def _load_dagbag() -> DagBag:
    return DagBag(dag_folder=DAGS_FOLDER, include_examples=False)


class TestEveryDagParsesCleanly:
    def test_no_import_errors(self) -> None:
        dagbag = _load_dagbag()
        assert dagbag.import_errors == {}

    def test_exactly_the_expected_dags_are_found(self) -> None:
        dagbag = _load_dagbag()
        assert set(dagbag.dags.keys()) == set(_EXPECTED_DAGS.keys())


class TestEveryDagHasExactlyOneCorrectlyWiredTask:
    def test_each_dag_has_exactly_one_task(self) -> None:
        dagbag = _load_dagbag()
        for dag_id, dag in dagbag.dags.items():
            assert len(dag.tasks) == 1, f"{dag_id} should have exactly one task"

    def test_each_task_id_matches_the_expected_convention(self) -> None:
        dagbag = _load_dagbag()
        for dag_id, (expected_task_id, _) in _EXPECTED_DAGS.items():
            task = dagbag.dags[dag_id].tasks[0]
            assert task.task_id == expected_task_id

    def test_each_task_invokes_the_expected_job_module_via_the_cli(self) -> None:
        dagbag = _load_dagbag()
        for dag_id, (_, expected_job_module) in _EXPECTED_DAGS.items():
            task = dagbag.dags[dag_id].tasks[0]
            assert task.command == ["python", "-m", "scheduler.jobs.cli", expected_job_module]

    def test_each_task_runs_the_platform_jobs_image(self) -> None:
        dagbag = _load_dagbag()
        for dag_id in _EXPECTED_DAGS:
            task = dagbag.dags[dag_id].tasks[0]
            assert task.image == PLATFORM_JOBS_IMAGE

    def test_each_task_has_the_shared_failure_callback(self) -> None:
        dagbag = _load_dagbag()
        for dag_id in _EXPECTED_DAGS:
            task = dagbag.dags[dag_id].tasks[0]
            assert task.on_failure_callback is on_job_failure

    def test_env_file_resolves_to_a_real_path_not_a_jinja_expression(self) -> None:
        # Regression test for the bug found while building this phase: env_file
        # must never contain a literal unrendered "{{" -- see
        # dag_common._PlatformDockerOperator's docstring.
        dagbag = _load_dagbag()
        for dag_id in _EXPECTED_DAGS:
            task = dagbag.dags[dag_id].tasks[0]
            assert "{{" not in task.env_file
            assert task.env_file.endswith("/.env")


class TestEveryDagHasNoCatchupAndAStartDate:
    def test_catchup_is_disabled(self) -> None:
        dagbag = _load_dagbag()
        for dag_id, dag in dagbag.dags.items():
            assert dag.catchup is False, f"{dag_id} should not backfill past runs"

    def test_has_a_start_date(self) -> None:
        dagbag = _load_dagbag()
        for dag in dagbag.dags.values():
            assert dag.start_date is not None


class TestSchedulingStrategy:
    """Verifies the documented nightly-pipeline ordering actually matches what
    each DAG is scheduled to do -- see
    docs/PHASE10_WORKFLOW_ORCHESTRATION.md "Scheduling strategy"."""

    def test_nightly_pipeline_dags_run_in_the_documented_order(self) -> None:
        dagbag = _load_dagbag()
        ordered_dag_ids = [
            "historical_sync",
            "data_validation",
            "feature_generation",
            "retraining",
        ]
        cron_expressions = [
            str(dagbag.dags[dag_id].schedule_interval) for dag_id in ordered_dag_ids
        ]
        assert cron_expressions == ["30 0 * * *", "0 1 * * *", "30 1 * * *", "0 2 * * *"]

    def test_alert_jobs_runs_more_frequently_than_every_other_dag(self) -> None:
        from datetime import timedelta

        dagbag = _load_dagbag()
        alert_schedule = dagbag.dags["alert_jobs"].schedule_interval
        assert alert_schedule == timedelta(minutes=5)

    def test_weekly_dags_run_on_sunday(self) -> None:
        dagbag = _load_dagbag()
        for dag_id in ("backtesting", "model_evaluation"):
            cron = str(dagbag.dags[dag_id].schedule_interval)
            assert cron.endswith(" 0"), f"{dag_id} should be scheduled for Sunday (cron day 0)"
