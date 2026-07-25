"""Audit logging -- the immutable record of trade/risk/portfolio-affecting actions.

Per ``docs/PHASE1_ARCHITECTURE.md`` Sec 6 and ``docs/CODING_STANDARDS.md`` Sec 12,
order- and risk-path activity is part of the platform's audit trail and must never
be sampled or dropped, regardless of ``LoggingSettings.sample_rate``. This module is
the one place that guarantee is implemented, so no domain code has to remember it.
"""

from __future__ import annotations

import logging
from typing import Any, Final

from shared.logging.logger import NEVER_SAMPLE_ATTR, get_logger

#: Dedicated logger name -- lets log shipping/routing treat the audit channel
#: distinctly from ordinary application logs (separate index, longer retention).
AUDIT_LOGGER_NAME: Final[str] = "audit"

_audit_logger = get_logger(AUDIT_LOGGER_NAME)


def log_audit_event(
    *,
    action: str,
    actor: str,
    resource: str,
    outcome: str,
    **context: Any,
) -> None:
    """Record one audit event.

    Args:
        action: what was attempted, e.g. ``"submit_order"``, ``"override_risk_limit"``.
        actor: who performed it, e.g. a user id, service name, or ``"system"``.
        resource: what it was performed on, e.g. an order ID or account ID.
        outcome: ``"success"``, ``"rejected"``, ``"failed"``, etc.
        **context: any additional structured fields relevant to this event
            (amount, symbol, previous/new values, ...).
    """
    _audit_logger.info(
        "audit_event",
        extra={
            "channel": "audit",
            "action": action,
            "actor": actor,
            "resource": resource,
            "outcome": outcome,
            NEVER_SAMPLE_ATTR: True,
            **context,
        },
    )


def get_audit_logger() -> logging.Logger:
    """Return the underlying audit logger, for callers that need direct access
    (e.g. to attach an additional dedicated handler in a later phase)."""
    return _audit_logger


__all__ = ["AUDIT_LOGGER_NAME", "get_audit_logger", "log_audit_event"]
