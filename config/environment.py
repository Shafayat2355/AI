"""Deployment/runtime environment enumeration and resolution helpers.

The platform recognizes exactly three deployment-lifecycle environments, matching the
overlay files in ``config/environments/`` and ``docs/PHASE2_REPOSITORY_STRUCTURE.md``:

* ``dev``   -- local development, relaxed limits, local service endpoints.
* ``paper`` -- simulated trading against live market data (staging-equivalent).
* ``live``  -- real venue connectivity; the platform's production environment.

Automated test runs are not a fourth deployment environment -- they run against the
``dev`` overlay with values overridden via environment variables/fixtures, per
``docs/PHASE3_ENGINEERING_STANDARDS.md`` §1.1-1.2. ``Environment.is_production_like``
is provided for code that needs to gate behavior for both ``paper`` and ``live``.
"""

from __future__ import annotations

import os
from enum import StrEnum

_ENVIRONMENT_VARIABLE_NAME = "ENVIRONMENT"
_DEFAULT_ENVIRONMENT = "dev"


class Environment(StrEnum):
    """Enumerates the platform's approved deployment/runtime environments."""

    DEV = "dev"
    PAPER = "paper"
    LIVE = "live"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value

    @property
    def is_dev(self) -> bool:
        """Whether this is the local-development environment."""
        return self is Environment.DEV

    @property
    def is_paper(self) -> bool:
        """Whether this is the simulated (paper-trading) environment."""
        return self is Environment.PAPER

    @property
    def is_live(self) -> bool:
        """Whether this is the real-venue (live-trading, production) environment."""
        return self is Environment.LIVE

    @property
    def is_production_like(self) -> bool:
        """Whether this environment carries production-grade safety requirements.

        Both ``paper`` and ``live`` route real market-data/order-state traffic through
        the full event pipeline and must not run with development conveniences (debug
        mode, permissive CORS, verbose stack traces) enabled.
        """
        return self in (Environment.PAPER, Environment.LIVE)

    @classmethod
    def _missing_(cls, value: object) -> Environment | None:
        if isinstance(value, str):
            normalized = value.strip().lower()
            for member in cls:
                if member.value == normalized:
                    return member
            # Common aliases so operators/CI scripts don't need to memorize the
            # canonical three-letter forms.
            aliases = {
                "development": cls.DEV,
                "local": cls.DEV,
                "staging": cls.PAPER,
                "stage": cls.PAPER,
                "simulation": cls.PAPER,
                "production": cls.LIVE,
                "prod": cls.LIVE,
            }
            if normalized in aliases:
                return aliases[normalized]
        return None


def resolve_environment(explicit: str | Environment | None = None) -> Environment:
    """Resolve the active :class:`Environment`.

    Precedence: an explicitly passed value wins, otherwise the ``ENVIRONMENT`` process
    environment variable is used, otherwise the platform defaults to ``dev`` so that
    running code locally without any configuration never accidentally targets a
    production-like environment.
    """
    if explicit is not None:
        return Environment(explicit)
    return Environment(os.environ.get(_ENVIRONMENT_VARIABLE_NAME, _DEFAULT_ENVIRONMENT))


__all__ = ["Environment", "resolve_environment"]
