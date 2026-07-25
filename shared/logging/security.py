"""Security logging -- authentication, authorization, and abuse-related events.

Separate from :mod:`shared.logging.audit`: audit logs record *what the platform did*
on behalf of a request (trades, risk decisions); security logs record *things done
to or against the platform's access controls* (login attempts, permission denials,
rate-limit breaches, suspicious activity). Both are exempt from sampling.
"""

from __future__ import annotations

import logging
from typing import Any, Final, Literal

from shared.logging.logger import NEVER_SAMPLE_ATTR, get_logger

SECURITY_LOGGER_NAME: Final[str] = "security"

_security_logger = get_logger(SECURITY_LOGGER_NAME)

SecuritySeverity = Literal["info", "warning", "critical"]

_SEVERITY_TO_LEVEL: Final[dict[SecuritySeverity, int]] = {
    "info": logging.INFO,
    "warning": logging.WARNING,
    "critical": logging.CRITICAL,
}


def log_security_event(
    *,
    event_type: str,
    severity: SecuritySeverity = "info",
    actor: str | None = None,
    **context: Any,
) -> None:
    """Record one security event.

    Args:
        event_type: e.g. ``"login_failed"``, ``"permission_denied"``,
            ``"mfa_challenge_failed"``, ``"rate_limit_exceeded"``.
        severity: ``"info"`` for routine/expected denials, ``"warning"`` for repeated
            or suspicious activity, ``"critical"`` for a confirmed breach requiring
            immediate paging (this level should also trigger ``alerts/alert_manager.py``
            once that module is wired up).
        actor: the identity involved, if known (never log the raw credential/token).
        **context: additional structured fields (ip_address, endpoint, account_id, ...).
    """
    _security_logger.log(
        _SEVERITY_TO_LEVEL[severity],
        "security_event",
        extra={
            "channel": "security",
            "event_type": event_type,
            "actor": actor,
            NEVER_SAMPLE_ATTR: True,
            **context,
        },
    )


def get_security_logger() -> logging.Logger:
    """Return the underlying security logger, for direct access if needed."""
    return _security_logger


__all__ = ["SECURITY_LOGGER_NAME", "SecuritySeverity", "get_security_logger", "log_security_event"]
