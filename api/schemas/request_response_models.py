"""Request/response DTOs used by the API routers.

``ErrorResponse`` is populated by this phase (Sec "Logging System" -> global
exception handler); router-specific request/response models are added by the
phases that implement each router in ``api/routers/``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """The single JSON error shape returned by every endpoint, success or failure.

    Built by ``api/error_handlers.py`` from a ``shared.errors.exceptions.PlatformError``
    (or, for a truly unexpected exception, a generic fallback) -- never constructed by
    router code directly.
    """

    error_code: str = Field(description="Stable, machine-readable error identifier.")
    message: str = Field(description="Human-readable summary, safe to display.")
    correlation_id: str | None = Field(
        default=None, description="Correlation ID for this request, for support/log lookup."
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured detail (validation field names, limits hit, ...).",
    )


__all__ = ["ErrorResponse"]
