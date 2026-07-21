"""Configuration loader.

Resolves the layered configuration sources described in
``docs/CODING_STANDARDS.md`` §13 into the process environment, in precedence order
(highest wins):

1. Real process environment variables (``os.environ`` as already set by the shell,
   container runtime, or the secrets manager referenced in
   ``docs/PHASE1_ARCHITECTURE.md`` §13) -- never overridden by this loader.
2. The local ``.env`` file (developer convenience; ``.env`` is git-ignored).
3. The environment overlay YAML (``config/environments/{dev,paper,live}.yaml``) --
   non-secret, environment-tier defaults.
4. Each settings module's own ``Field(default=...)`` -- applied by Pydantic itself if
   nothing above supplied a value.

This module only ever *adds missing* environment variables (via
``os.environ.setdefault``); it never overwrites a variable that is already present, so
a real deployment's injected secrets can never be shadowed by a checked-in default.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from config.base import DEFAULT_DOTENV_PATH, ENVIRONMENTS_DIR
from config.environment import Environment
from config.exceptions import ConfigurationSourceError

#: Maps a top-level YAML overlay section name to the environment-variable prefix used
#: by the corresponding settings module in ``config/modules/``. Keys not listed here
#: (there are none expected) are ignored by the flattener rather than raising, since a
#: forward-compatible overlay file authored for a not-yet-added module should not break
#: the loader for every other module.
_SECTION_ENV_PREFIXES: dict[str, str] = {
    "application": "APP_",
    "database": "DATABASE_",
    "postgres": "POSTGRES_",
    "postgresql": "POSTGRES_",
    "redis": "REDIS_",
    "kafka": "KAFKA_",
    "binance": "BINANCE_",
    "ai_models": "AI_MODEL_",
    "feature_engineering": "FEATURE_",
    "logging": "LOG_",
    "monitoring": "MONITORING_",
    "api": "API_",
    "websocket": "WEBSOCKET_",
    "security": "SECURITY_",
}

#: Root-level (unprefixed) keys an overlay file may set directly.
_ROOT_LEVEL_KEYS: frozenset[str] = frozenset({"environment", "debug"})


def _scalar_to_env_string(value: Any) -> str:
    """Render a parsed YAML scalar/sequence as the string pydantic-settings expects."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(_scalar_to_env_string(item) for item in value)
    return str(value)


def flatten_overlay(raw: dict[str, Any]) -> dict[str, str]:
    """Flatten a parsed environment-overlay YAML document into environment-variable
    name/value pairs, using each section's registered prefix.

    Example::

        {"redis": {"host": "cache.internal", "port": 6380}}

    becomes::

        {"REDIS_HOST": "cache.internal", "REDIS_PORT": "6380"}
    """
    flattened: dict[str, str] = {}
    for section, contents in raw.items():
        if section in _ROOT_LEVEL_KEYS:
            flattened[section.upper()] = _scalar_to_env_string(contents)
            continue
        prefix = _SECTION_ENV_PREFIXES.get(section)
        if prefix is None:
            continue
        if not isinstance(contents, dict):
            raise ConfigurationSourceError(
                f"Environment overlay section {section!r} must be a mapping, "
                f"got {type(contents).__name__}"
            )
        for key, value in contents.items():
            env_key = f"{prefix}{str(key).upper()}"
            flattened[env_key] = _scalar_to_env_string(value)
    return flattened


def load_overlay_file(path: Path) -> dict[str, str]:
    """Parse one environment-overlay YAML file into flattened env-var pairs.

    Returns an empty mapping if the file does not exist or is empty (both are valid
    states -- a brand-new environment may rely entirely on module defaults).
    """
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationSourceError(f"Could not read overlay file {path}: {exc}") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigurationSourceError(f"Could not parse overlay file {path}: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigurationSourceError(
            f"Overlay file {path} must contain a top-level mapping, got {type(raw).__name__}"
        )
    return flatten_overlay(raw)


def load_dotenv_values(path: Path) -> dict[str, str]:
    """Read a ``.env``-format file into a plain string dict, dropping unset keys.

    Uses ``python-dotenv`` directly (rather than relying solely on each
    ``BaseSettings``' own ``env_file`` loading) so the loader can merge it with the
    YAML overlay *before* any settings module is constructed, giving precise control
    over precedence between the two non-OS-environ sources.
    """
    if not path.exists():
        return {}
    return {key: value for key, value in dotenv_values(path).items() if value is not None}


def bootstrap_environment(
    environment: Environment,
    *,
    dotenv_path: Path = DEFAULT_DOTENV_PATH,
    environments_dir: Path = ENVIRONMENTS_DIR,
) -> dict[str, str]:
    """Populate ``os.environ`` with the merged, precedence-ordered configuration for
    ``environment`` and return the merged mapping that was applied.

    Only fills in variables that are not already present in ``os.environ`` --
    genuine deployment-injected environment variables always win. Safe to call more
    than once (e.g. once per test, after resetting ``os.environ``); already-set
    variables from a previous call are left untouched, matching ``setdefault``
    semantics.
    """
    overlay_path = environments_dir / f"{environment.value}.yaml"
    merged: dict[str, str] = load_overlay_file(overlay_path)
    merged.update(load_dotenv_values(dotenv_path))  # .env outranks the YAML overlay
    merged.setdefault("ENVIRONMENT", environment.value)

    applied: dict[str, str] = {}
    for key, value in merged.items():
        if key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied


__all__ = [
    "flatten_overlay",
    "load_overlay_file",
    "load_dotenv_values",
    "bootstrap_environment",
]
