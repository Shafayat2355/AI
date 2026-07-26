"""Cross-service enumerations that describe process/component state.

Distinct from domain enumerations (order side, order status, ...), which belong to
``core/domain`` once modeled in a later phase. These describe the *platform's own*
operational state -- health-check results and service lifecycle -- and are needed
by every service's bootstrap/monitoring wiring (``monitoring/health_checks.py``,
``core/container.py``, ``app/*_service/main.py``), independent of any trading logic.
"""

from __future__ import annotations

from enum import StrEnum


class HealthStatus(StrEnum):
    """Result of a single health check, or the aggregate of several.

    Aggregation rule (see ``monitoring/health_checks.py``): the overall status is
    the worst of its components -- any ``UNHEALTHY`` component makes the whole
    result ``UNHEALTHY``; otherwise any ``DEGRADED`` component makes it ``DEGRADED``.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

    @property
    def is_healthy(self) -> bool:
        """Whether this status should be treated as passing (HTTP 200) by a probe."""
        return self is not HealthStatus.UNHEALTHY

    @classmethod
    def aggregate(cls, statuses: list[HealthStatus]) -> HealthStatus:
        """Combine several component statuses into one overall status."""
        if any(status is cls.UNHEALTHY for status in statuses):
            return cls.UNHEALTHY
        if any(status is cls.DEGRADED for status in statuses):
            return cls.DEGRADED
        return cls.HEALTHY


class ServiceLifecycleState(StrEnum):
    """A service process's position in its startup/shutdown lifecycle.

    Set by the composition root (``app/*_service/main.py``'s lifespan handler) as
    it moves through :func:`core.container.Container` startup/shutdown, and read by
    ``monitoring/health_checks.py`` so a readiness probe can fail fast while the
    process is still starting up or already draining, without waiting for a
    downstream dependency check to time out.
    """

    STARTING = "starting"
    READY = "ready"
    DRAINING = "draining"
    STOPPED = "stopped"

    @property
    def accepts_traffic(self) -> bool:
        """Whether a load balancer should be allowed to route new work here."""
        return self is ServiceLifecycleState.READY


__all__ = ["HealthStatus", "ServiceLifecycleState"]
