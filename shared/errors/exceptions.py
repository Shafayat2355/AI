"""Shared exception hierarchy used across the platform.

Every domain-specific exception raised anywhere in the codebase derives from
:class:`PlatformError` (per ``docs/CODING_STANDARDS.md`` Sec 11: "All domain-specific
exceptions derive from the shared hierarchy ... never raise a bare ``Exception``").
This module defines the root and the small set of general-purpose branches every
service needs; individual domain folders (``risk/``, ``execution/``, ``portfolio/``,
...) are expected to add their own specific subclasses of these as that logic is
implemented in later phases (e.g. a future ``risk/`` module raising
``RiskBreachError`` -- listed here as the concrete example this hierarchy was always
meant to support, per the original Phase 2 scaffold note).

Each exception carries an ``error_code`` (a short, stable, machine-readable string --
safe to expose to API clients and to key alerts/dashboards off of) and an optional
``context`` mapping of structured details (never secrets/credentials -- see
``docs/CODING_STANDARDS.md`` Sec 14). :meth:`PlatformError.to_log_context` turns
that into a dict ready to pass as a logging call's ``extra=`` argument, and
``api/error_handlers.py`` uses ``http_status`` to translate an exception into a
response without every raise-site needing to know about HTTP at all.
"""

from __future__ import annotations

from typing import Any


class PlatformError(Exception):
    """Root of every exception this platform raises intentionally.

    Never raise this class directly -- raise the most specific subclass that
    describes what went wrong so callers can catch narrowly and
    ``api/error_handlers.py`` can map it to the right response.
    """

    #: Short, stable, machine-readable identifier. Subclasses override this;
    #: it is also safe to surface to an external API caller.
    error_code: str = "platform_error"

    #: Default HTTP status used when this error reaches
    #: ``api/error_handlers.py`` with no more specific mapping registered.
    http_status: int = 500

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def to_log_context(self) -> dict[str, Any]:
        """Structured fields ready for ``logger.error(..., extra=err.to_log_context())``."""
        return {
            "error_code": self.error_code,
            "error_message": self.message,
            **self.context,
        }

    def __str__(self) -> str:
        return self.message


# --------------------------------------------------------------------------- #
# Broad categories -- catch one of these when you only care about the class of
# failure, not the exact cause.
# --------------------------------------------------------------------------- #


class DomainError(PlatformError):
    """A business-rule violation: the request was well-formed and authorized, but
    violates a rule of the trading domain itself (a risk limit, an invalid order
    state transition, an unsupported strategy configuration, ...)."""

    error_code = "domain_error"
    http_status = 422


class InfrastructureError(PlatformError):
    """A failure in a dependency the platform relies on but does not govern the
    business rules of: the database, Kafka, Redis, an exchange/vendor API, disk."""

    error_code = "infrastructure_error"
    http_status = 503


# --------------------------------------------------------------------------- #
# Common concrete errors needed across services (API layer, repositories, ...).
# --------------------------------------------------------------------------- #


class ValidationError(DomainError):
    """Input was structurally valid but fails a business validation rule not
    already expressed as a Pydantic field constraint."""

    error_code = "validation_error"
    http_status = 400


class NotFoundError(DomainError):
    """The requested resource (order, account, strategy, model version, ...) does
    not exist."""

    error_code = "not_found"
    http_status = 404


class ConflictError(DomainError):
    """The request conflicts with the resource's current state (e.g. cancelling an
    order that has already filled)."""

    error_code = "conflict"
    http_status = 409


class AuthenticationError(PlatformError):
    """The caller's identity could not be established (missing/invalid/expired
    credentials). Distinct from :class:`AuthorizationError` -- this is "who are
    you", not "you can't do that"."""

    error_code = "authentication_error"
    http_status = 401


class AuthorizationError(PlatformError):
    """The caller is known but lacks permission for the requested action (see
    ``docs/CODING_STANDARDS.md`` Sec 14, ``api/auth/rbac.py``)."""

    error_code = "authorization_error"
    http_status = 403


class RateLimitExceededError(PlatformError):
    """The caller exceeded ``api/middleware/rate_limit_middleware.py``'s allowed
    request rate."""

    error_code = "rate_limit_exceeded"
    http_status = 429


# --------------------------------------------------------------------------- #
# Trading-domain-specific errors. Concrete implementations of risk/execution
# logic in later phases are expected to raise these (or their own subclasses of
# them) rather than defining an unrelated new hierarchy.
# --------------------------------------------------------------------------- #


class RiskBreachError(DomainError):
    """A trade intent was rejected because it violates a risk limit (position
    size, drawdown, exposure, ...). Per ``docs/PHASE1_ARCHITECTURE.md`` Sec 10, the
    Risk Manager fails closed -- this exception is the expected, not exceptional,
    outcome of a rejected trade and should be handled distinctly from an
    unexpected system failure."""

    error_code = "risk_breach"
    http_status = 422


class ExecutionError(InfrastructureError):
    """An order could not be submitted, modified, or cancelled at the venue/adapter
    level (``execution/``, ``paper_trading/``, ``live_trading/``)."""

    error_code = "execution_error"
    http_status = 502


__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "ConflictError",
    "DomainError",
    "ExecutionError",
    "InfrastructureError",
    "NotFoundError",
    "PlatformError",
    "RateLimitExceededError",
    "RiskBreachError",
    "ValidationError",
]
