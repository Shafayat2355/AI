"""Shared pytest fixtures (test DB, test Kafka, fake clock) available to all test suites.

Only genuinely cross-suite fixtures belong here -- anything specific to one area
(e.g. ``tests/unit/config/conftest.py``'s ``isolated_environment``) stays scoped to
that directory's own ``conftest.py``, per the existing convention in this test
suite.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from config.factory import SettingsFactory
from core.container import reset_container


@pytest.fixture(autouse=True)
def _reset_process_wide_singletons() -> Iterator[None]:
    """Reset every process-wide singleton this test suite could otherwise leak
    between tests: the :class:`~config.factory.SettingsFactory` cache and the
    :class:`~core.container.Container` singleton.

    Runs before *and* after every test (autouse) so test order never matters --
    matches the isolation guarantee ``tests/unit/config/conftest.py``'s
    ``isolated_environment`` fixture already provides for environment variables.
    """
    SettingsFactory.clear_cache()
    reset_container()
    yield
    SettingsFactory.clear_cache()
    reset_container()
