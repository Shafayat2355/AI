"""Unit tests for shared.enums."""

from __future__ import annotations

from shared.enums import HealthStatus, ServiceLifecycleState


class TestHealthStatus:
    def test_is_healthy_true_for_healthy_and_degraded(self) -> None:
        assert HealthStatus.HEALTHY.is_healthy
        assert HealthStatus.DEGRADED.is_healthy

    def test_is_healthy_false_for_unhealthy(self) -> None:
        assert not HealthStatus.UNHEALTHY.is_healthy

    def test_aggregate_all_healthy_is_healthy(self) -> None:
        result = HealthStatus.aggregate([HealthStatus.HEALTHY, HealthStatus.HEALTHY])
        assert result is HealthStatus.HEALTHY

    def test_aggregate_any_unhealthy_wins(self) -> None:
        result = HealthStatus.aggregate(
            [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        )
        assert result is HealthStatus.UNHEALTHY

    def test_aggregate_degraded_beats_healthy(self) -> None:
        result = HealthStatus.aggregate([HealthStatus.HEALTHY, HealthStatus.DEGRADED])
        assert result is HealthStatus.DEGRADED

    def test_aggregate_empty_list_is_healthy(self) -> None:
        assert HealthStatus.aggregate([]) is HealthStatus.HEALTHY


class TestServiceLifecycleState:
    def test_only_ready_accepts_traffic(self) -> None:
        assert ServiceLifecycleState.READY.accepts_traffic
        assert not ServiceLifecycleState.STARTING.accepts_traffic
        assert not ServiceLifecycleState.DRAINING.accepts_traffic
        assert not ServiceLifecycleState.STOPPED.accepts_traffic
