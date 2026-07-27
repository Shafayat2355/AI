"""Generic application-service base every concrete use case builds on.

A "service" here is an application-layer orchestrator (in the hexagonal-architecture
sense used throughout ``docs/PHASE1_ARCHITECTURE.md``) that accepts one request DTO,
coordinates one or more ports, and returns one response DTO. Concrete use cases
under this package (``submit_order.py``, ``gate_risk.py``, ``evaluate_strategy.py``,
...) are expected to subclass :class:`BaseService` rather than re-implementing the
timing/logging/error-propagation wrapper themselves in every future phase.

This module is pure bootstrap/scaffolding (Phase 6) -- it contains no
trading-domain logic of its own.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from shared.errors.exceptions import PlatformError
from shared.logging.logger import get_logger
from shared.logging.timing import Timer


class BaseService[RequestT, ResponseT](ABC):
    """Base class for a single-purpose application service / use case.

    Subclasses implement :meth:`execute`; callers invoke the service via
    :meth:`__call__` (i.e. ``await my_service(request)``), which wraps
    :meth:`execute` with:

    * A :class:`~shared.logging.timing.Timer` span, so every use case's latency is
      automatically observable without each one instrumenting itself.
    * Uniform error handling: a :class:`~shared.errors.exceptions.PlatformError`
      (already a well-formed, intentional error) is re-raised untouched; any other
      exception is logged with full context before re-raising, so an unexpected
      failure is never silently swallowed.
    """

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or get_logger(self.__class__.__module__)

    @property
    def logger(self) -> logging.Logger:
        """The logger this service instance uses; override via the constructor."""
        return self._logger

    @abstractmethod
    async def execute(self, request: RequestT) -> ResponseT:
        """Perform this service's use case. Implemented by every subclass."""

    async def __call__(self, request: RequestT) -> ResponseT:
        """Run :meth:`execute` with standard timing/logging/error handling."""
        name = self.__class__.__name__
        with Timer(name, logger=self._logger):
            try:
                return await self.execute(request)
            except PlatformError:
                raise
            except Exception:
                self._logger.exception(
                    "use_case_failed",
                    extra={"channel": "application", "use_case": name},
                )
                raise


__all__ = ["BaseService"]
