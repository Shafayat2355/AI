"""Configuration package: typed, validated, environment-aware settings for every
service in the platform.

Public surface:

* :func:`config.settings.get_settings` -- the one function most code needs.
* :class:`config.settings.Settings` -- the composed settings type, for type hints.
* :class:`config.environment.Environment` -- the dev/paper/live enum.
* :mod:`config.di` -- FastAPI-compatible ``Depends()`` providers.
* :mod:`config.modules` -- individual settings classes, for standalone use/testing.
* :func:`config.config_client.get_config_client` -- hot-reloadable value registry.

See ``docs/PHASE4_CONFIGURATION_MANAGEMENT.md`` for the full design write-up.
"""

from config.config_client import ConfigClient, get_config_client
from config.environment import Environment, resolve_environment
from config.exceptions import (
    ConfigurationError,
    ConfigurationSourceError,
    ConfigurationValidationError,
)
from config.settings import Settings, get_settings

__all__ = [
    "Settings",
    "get_settings",
    "Environment",
    "resolve_environment",
    "ConfigClient",
    "get_config_client",
    "ConfigurationError",
    "ConfigurationSourceError",
    "ConfigurationValidationError",
]
