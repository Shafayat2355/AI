"""Liveness/readiness probe handlers used by Kubernetes, plus the ``/version`` endpoint.

Mounted, unprefixed (outside ``APISettings.prefix``), by every service's
composition root -- see ``app/api_service/main.py`` -- since a Kubernetes probe and
an operator checking deployed version both expect a fixed, well-known path
regardless of the service's business-API prefix.

Scope note (Phase 6): readiness here only asserts that this process's own
bootstrap completed (settings loaded, logging configured, the container reached
``READY``) -- it deliberately does not fail on database connectivity, since no
service depends on the database yet as of this phase.
:meth:`~database.connection.DatabaseConnection.check_connection` exists and is
exercised by this router as an informational, non-blocking component so a later
phase that does add a hard database dependency only needs to change how its
status feeds into the aggregate, not add new plumbing.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from config.settings import Settings, get_settings
from core.container import Container, get_container
from shared.enums import HealthStatus, ServiceLifecycleState
from shared.logging.logger import get_logger
from shared.models import ComponentHealth, HealthCheckResponse, VersionResponse

router = APIRouter(tags=["monitoring"])

_logger = get_logger("monitoring.health_checks")


@router.get("/health/live", response_model=HealthCheckResponse)
async def liveness() -> HealthCheckResponse:
    """Liveness probe: is this process running at all?

    Deliberately checks nothing beyond "this handler executed" -- a liveness probe
    that depends on downstream services causes Kubernetes to restart a perfectly
    healthy process just because a dependency is briefly unavailable. Use
    ``/health/ready`` for anything that should gate traffic.
    """
    return HealthCheckResponse(status=HealthStatus.HEALTHY)


@router.get("/health/ready", response_model=HealthCheckResponse)
async def readiness(container: Annotated[Container, Depends(get_container)]) -> HealthCheckResponse:
    """Readiness probe: should traffic be routed to this process right now?"""
    components: list[ComponentHealth] = []

    if container.state is ServiceLifecycleState.READY:
        components.append(ComponentHealth(name="container", status=HealthStatus.HEALTHY))
    else:
        components.append(
            ComponentHealth(
                name="container",
                status=HealthStatus.UNHEALTHY,
                detail=f"container state is {container.state.value!r}, expected 'ready'",
            )
        )

    db_reachable = await container.db.check_connection()
    components.append(
        ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY if db_reachable else HealthStatus.DEGRADED,
            detail=None if db_reachable else "database connectivity check failed",
        )
    )

    overall = HealthStatus.aggregate([component.status for component in components])
    if overall is not HealthStatus.HEALTHY:
        _logger.warning(
            "readiness_check_degraded",
            extra={"channel": "application", "status": overall.value},
        )
    return HealthCheckResponse(status=overall, components=components)


@router.get("/version", response_model=VersionResponse)
async def version(settings: Annotated[Settings, Depends(get_settings)]) -> VersionResponse:
    """Report the deployed application name/version/environment."""
    return VersionResponse(
        name=settings.application.name,
        version=settings.application.version,
        description=settings.application.description,
        environment=settings.environment.value,
    )


__all__ = ["router"]
