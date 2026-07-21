"""Exception hierarchy for the configuration package.

Kept local to ``config/`` (rather than added to ``shared/errors/exceptions.py``) because
these errors can occur before the rest of the platform's shared error-handling
infrastructure -- which is itself configured through this package -- is available. Once
``shared/errors`` grows a concrete hierarchy, these should subclass the shared
``DomainError`` root; there is nothing there to subclass yet.
"""

from __future__ import annotations


class ConfigurationError(Exception):
    """Base class for all configuration-package errors."""


class ConfigurationValidationError(ConfigurationError):
    """Raised when a fully-loaded :class:`~config.settings.Settings` object fails a
    cross-field or cross-module validation rule that individual Pydantic field
    validators cannot express (e.g. a rule that spans two modules)."""


class ConfigurationSourceError(ConfigurationError):
    """Raised when a configuration source (an environment overlay YAML file, a
    ``.env`` file) cannot be read or parsed."""


__all__ = [
    "ConfigurationError",
    "ConfigurationValidationError",
    "ConfigurationSourceError",
]
