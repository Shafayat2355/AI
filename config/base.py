"""Shared foundations reused by every settings module: the repository-root path, the
default ``.env`` location, and the common ``BaseSettings`` configuration every module
class inherits so they are all configured identically (case-insensitive env var
matching, UTF-8 ``.env`` decoding, no accidental silent typos via ``extra="forbid"``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from pydantic_settings import BaseSettings, SettingsConfigDict

#: Absolute path to the repository root (parent of the ``config`` package).
BASE_DIR: Path = Path(__file__).resolve().parent.parent

#: Absolute path to the environment-overlay directory (``config/environments``).
ENVIRONMENTS_DIR: Path = Path(__file__).resolve().parent / "environments"

#: Default local ``.env`` file location, matching ``.env.example`` at the repo root.
DEFAULT_DOTENV_PATH: Path = BASE_DIR / ".env"


def module_settings_config(env_prefix: str, **overrides: Any) -> SettingsConfigDict:
    """Build the :class:`SettingsConfigDict` shared by every settings module.

    Every module gets the same ``.env`` file, the same case-insensitive matching, and
    the same ``extra="forbid"`` strictness so a typo'd keyword argument passed to a
    settings class during tests or manual/DI construction fails loudly instead of being
    silently swallowed. (Note this does not catch a mistyped *environment variable*
    name -- ``pydantic-settings`` only ever looks up the exact prefixed names it
    expects, so an unrecognized env var is simply never read, not rejected; unmatched
    fields fall back to their declared defaults, which :mod:`config.validation`
    partially guards against for the fields that matter most.)
    ``overrides`` lets an individual module adjust specific keys (for example
    ``SecuritySettings`` sets ``env_prefix="SECURITY_"`` but also needs to read the
    unprefixed legacy ``JWT_SECRET`` variable via a field alias, which does not require
    an override here -- overrides exist for genuine per-module exceptions only).
    """
    config: dict[str, Any] = {
        "env_prefix": env_prefix,
        "env_file": str(DEFAULT_DOTENV_PATH),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "forbid",
        "validate_default": True,
        "populate_by_name": True,
    }
    config.update(overrides)
    return cast(SettingsConfigDict, config)


class ModuleBaseSettings(BaseSettings):
    """Common base for every domain settings module.

    Deliberately does **not** set ``env_prefix`` itself -- each concrete module
    supplies its own prefix via :func:`module_settings_config` so the class can still
    be introspected/instantiated standalone (for dependency injection or ad-hoc
    scripts) with the correct variable names.
    """

    model_config = module_settings_config(env_prefix="")


__all__ = [
    "BASE_DIR",
    "ENVIRONMENTS_DIR",
    "DEFAULT_DOTENV_PATH",
    "module_settings_config",
    "ModuleBaseSettings",
]
