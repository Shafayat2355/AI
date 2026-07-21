"""Fixtures shared by every test module under tests/unit/config/.

Every test that touches environment variables or the :class:`~config.factory.SettingsFactory`
cache uses ``isolated_environment`` so tests never leak state into one another or
depend on run order.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from config.factory import SettingsFactory


@pytest.fixture
def isolated_environment() -> Iterator[None]:
    """Snapshot ``os.environ`` before a test and restore it exactly afterward, and
    clear the :class:`SettingsFactory` cache both before and after."""
    snapshot = dict(os.environ)
    SettingsFactory.clear_cache()
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snapshot)
        SettingsFactory.clear_cache()
