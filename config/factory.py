"""Configuration factory.

``SettingsFactory`` is the single place that turns "which environment do we want" into
a fully-loaded, validated :class:`config.settings.Settings` instance. It owns:

* Running :func:`config.loader.bootstrap_environment` before construction, so the
  YAML overlay and ``.env`` file are merged into ``os.environ`` exactly once per
  environment before any ``BaseSettings`` subclass reads it.
* Caching one ``Settings`` instance per resolved :class:`~config.environment.Environment`
  so repeated calls (e.g. once per request via DI) do not re-parse the environment.
* Rolling back its own previously-applied overlay values before bootstrapping a
  *different* environment, so switching environments within one process (as
  happens routinely in this test suite, and in any tool that inspects more than
  one environment, e.g. a "validate every environment" CLI) never leaks one
  environment's YAML-derived defaults into another. Because
  :func:`~config.loader.bootstrap_environment` only ever fills in *missing*
  variables via ``setdefault``, without this rollback a variable it set for
  environment A would still be present -- and therefore never re-filled -- when
  bootstrapping environment B. Real, genuinely pre-existing process environment
  variables (actual deployment secrets, or a test's own ``monkeypatch.setenv``
  calls) are never touched, since the factory only ever removes keys it itself
  applied.
* Giving tests a clean way to force a fresh instance (``force_reload=True``) after
  changing environment variables mid-test.
"""

from __future__ import annotations

import os
import threading

from config.environment import Environment, resolve_environment
from config.loader import bootstrap_environment
from config.settings import Settings


class SettingsFactory:
    """Thread-safe factory/cache for :class:`~config.settings.Settings` instances,
    keyed by resolved :class:`~config.environment.Environment`.
    """

    _cache: dict[Environment, Settings] = {}
    _lock = threading.Lock()
    _bootstrapped_environment: Environment | None = None
    _loader_applied_keys: dict[str, str] = {}

    @classmethod
    def create(
        cls,
        environment: Environment | str | None = None,
        *,
        force_reload: bool = False,
    ) -> Settings:
        """Return the cached :class:`Settings` for ``environment``, building and
        validating it first if this is the first request for that environment (or
        ``force_reload=True``).
        """
        resolved = resolve_environment(environment)
        with cls._lock:
            if force_reload:
                cls._cache.pop(resolved, None)
            cached = cls._cache.get(resolved)
            if cached is not None:
                return cached

            needs_new_bootstrap = (
                cls._bootstrapped_environment is not None
                and cls._bootstrapped_environment != resolved
            )
            if needs_new_bootstrap:
                cls._rollback_previous_bootstrap()

            applied = bootstrap_environment(resolved)
            cls._loader_applied_keys.update(applied)
            cls._bootstrapped_environment = resolved

            settings = Settings(environment=resolved)
            cls._cache[resolved] = settings
            return settings

    @classmethod
    def _rollback_previous_bootstrap(cls) -> None:
        """Remove every environment variable the factory itself set on a prior
        bootstrap call, so a subsequent bootstrap for a different environment starts
        from a clean slate. Only removes a key if its current value still matches
        what the loader set -- if something else (a test, an operator) has since
        overwritten it, that value is left alone rather than clobbered.
        """
        for key, applied_value in cls._loader_applied_keys.items():
            if os.environ.get(key) == applied_value:
                del os.environ[key]
        cls._loader_applied_keys.clear()

    @classmethod
    def clear_cache(cls, environment: Environment | str | None = None) -> None:
        """Drop cached instance(s). Intended for test teardown/fixtures.

        Clears every cached environment when ``environment`` is ``None``, otherwise
        only the specified one. Also rolls back any pending loader-applied
        environment variables and resets bootstrap tracking, so the next call to
        :meth:`create` -- for any environment -- starts clean.
        """
        with cls._lock:
            if environment is None:
                cls._cache.clear()
            else:
                cls._cache.pop(resolve_environment(environment), None)
            cls._rollback_previous_bootstrap()
            cls._bootstrapped_environment = None


__all__ = ["SettingsFactory"]
