"""Fixtures shared by every test module under tests/integration/config/."""

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
