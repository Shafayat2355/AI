"""Common base Pydantic models shared by API schemas and event payloads.

``BaseSchema`` is the one base class every DTO in ``api/schemas/*`` and every
event payload in ``core/domain/events/*`` is expected to inherit from (mirroring
how ``config/base.py``'s ``ModuleBaseSettings`` centralizes settings-model
behavior) so they all reject unknown fields and serialize consistently, without
each module repeating the same ``model_config``.

``HealthCheckResponse`` and ``VersionResponse`` back ``monitoring/health_checks.py``'s
endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from shared.enums import HealthStatus
from shared.utils.time_utils import utcnow_iso8601


class BaseSchema(BaseModel):
    """Base class for every request/response DTO and event payload.

    ``extra="forbid"`` catches a typo'd field name (in a request body or an event
    payload) at validation time instead of silently dropping it, matching
    ``config/base.py``'s ``ModuleBaseSettings`` rationale. ``populate_by_name``
    lets a model define a Python-friendly field name alongside a wire-format alias
    (e.g. a ``camelCase`` API field) without breaking construction from either.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)


class ComponentHealth(BaseSchema):
    """The health of one dependency/subsystem, as reported by a readiness check."""

    name: str = Field(description="Identifier of the checked component, e.g. 'database'.")
    status: HealthStatus = Field(description="This component's own health status.")
    detail: str | None = Field(
        default=None, description="Optional human-readable detail, e.g. an error summary."
    )


class HealthCheckResponse(BaseSchema):
    """Response body for both the liveness and readiness endpoints.

    ``components`` is empty for a liveness check (which only asserts the process
    is running) and populated for a readiness check (see
    ``monitoring/health_checks.py``).
    """

    status: HealthStatus = Field(description="Aggregate health status.")
    checked_at: str = Field(
        default_factory=utcnow_iso8601, description="ISO-8601 UTC timestamp of this check."
    )
    components: list[ComponentHealth] = Field(
        default_factory=list, description="Per-dependency breakdown, if any were checked."
    )


class VersionResponse(BaseSchema):
    """Response body for the ``/version`` endpoint."""

    name: str = Field(description="Application name, from ApplicationSettings.name.")
    version: str = Field(description="Deployed application version.")
    description: str = Field(description="Short human-readable description.")
    environment: str = Field(description="Active deployment environment (dev|paper|live).")


__all__ = ["BaseSchema", "ComponentHealth", "HealthCheckResponse", "VersionResponse"]
