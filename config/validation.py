"""Cross-module configuration validation.

Individual field-level validation (types, ranges, allowed enums) lives on each
settings module in ``config/modules/`` via Pydantic validators, and runs automatically
on construction. This module holds rules that span *multiple* modules or depend on
the resolved :class:`~config.environment.Environment`, which a single module cannot
express on its own -- for example "debug must be off outside dev" spans
``ApplicationSettings`` and the environment, and "a placeholder JWT secret must not
reach paper/live" spans ``SecuritySettings`` and the environment.

Called once by :class:`config.factory.SettingsFactory` immediately after a
``Settings`` instance is constructed, so a misconfigured process fails fast at boot
rather than surfacing a subtle bug at request time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config.exceptions import ConfigurationValidationError
from config.modules.security import INSECURE_DEFAULT_SECRET

if TYPE_CHECKING:
    from config.settings import Settings


def validate_settings(settings: Settings) -> None:
    """Run every cross-module validation rule against a fully-constructed
    :class:`~config.settings.Settings`, raising :class:`ConfigurationValidationError`
    with every violation found (not just the first) so an operator can fix them all
    in one pass.
    """
    errors: list[str] = []
    _validate_debug_mode(settings, errors)
    _validate_secrets_not_placeholder(settings, errors)
    _validate_cors_not_wildcard_outside_dev(settings, errors)
    _validate_docs_disabled_in_live(settings, errors)
    _validate_binance_credentials_present_outside_dev(settings, errors)
    _validate_tls_enforced_outside_dev(settings, errors)
    _validate_tracing_endpoint_present_when_enabled(settings, errors)
    _validate_json_logging_outside_dev(settings, errors)

    if errors:
        joined = "; ".join(errors)
        raise ConfigurationValidationError(
            f"Configuration failed validation for environment "
            f"{settings.environment.value!r}: {joined}"
        )


def _validate_debug_mode(settings: Settings, errors: list[str]) -> None:
    if settings.environment.is_production_like and settings.application.debug:
        errors.append(
            "application.debug must be False in paper/live "
            f"(environment={settings.environment.value!r})"
        )


def _validate_secrets_not_placeholder(settings: Settings, errors: list[str]) -> None:
    if not settings.environment.is_production_like:
        return
    if settings.security.jwt_secret.get_secret_value() == INSECURE_DEFAULT_SECRET:
        errors.append(
            "security.jwt_secret is still the insecure placeholder value; set "
            "SECURITY_JWT_SECRET (or JWT_SECRET) before running paper/live"
        )
    if (
        settings.postgres.password.get_secret_value() == "trading"
        and settings.database.url is None
    ):
        errors.append(
            "postgres.password is still the insecure dev default and no DATABASE_URL "
            "override is set; configure POSTGRES_PASSWORD or DATABASE_URL before "
            "running paper/live"
        )


def _validate_cors_not_wildcard_outside_dev(settings: Settings, errors: list[str]) -> None:
    if not settings.environment.is_production_like:
        return
    if "*" in settings.api.cors_allowed_origins:
        errors.append("api.cors_allowed_origins must not contain '*' in paper/live")


def _validate_docs_disabled_in_live(settings: Settings, errors: list[str]) -> None:
    if settings.environment.is_live and settings.api.docs_enabled:
        errors.append("api.docs_enabled must be False in live")


def _validate_binance_credentials_present_outside_dev(
    settings: Settings, errors: list[str]
) -> None:
    if not settings.environment.is_production_like:
        return
    if settings.binance.api_key is None or settings.binance.api_secret is None:
        errors.append(
            "binance.api_key and binance.api_secret must both be set in paper/live"
        )
    if settings.environment.is_live and settings.binance.use_testnet:
        errors.append("binance.use_testnet must be False in live")


def _validate_tls_enforced_outside_dev(settings: Settings, errors: list[str]) -> None:
    if not settings.environment.is_production_like:
        return
    if not settings.security.secure_cookies:
        errors.append("security.secure_cookies must be True in paper/live")
    if settings.postgres.sslmode in {"disable", "allow"}:
        errors.append(
            f"postgres.sslmode={settings.postgres.sslmode!r} is too permissive for "
            "paper/live; use 'require' or stricter"
        )


def _validate_tracing_endpoint_present_when_enabled(
    settings: Settings, errors: list[str]
) -> None:
    if settings.monitoring.tracing_enabled and not settings.monitoring.tracing_exporter_endpoint:
        errors.append(
            "monitoring.tracing_exporter_endpoint is required when "
            "monitoring.tracing_enabled is True"
        )


def _validate_json_logging_outside_dev(settings: Settings, errors: list[str]) -> None:
    """JSON logging is required for ``paper``/``live`` so log shipping (Phase 5,
    ``shared/logging/logger.py``) can parse every record uniformly; the colored
    plain-text console formatter is a ``dev``-only convenience."""
    if settings.environment.is_production_like and not settings.logging.json_format:
        errors.append(
            "logging.json_format must be True in paper/live "
            f"(environment={settings.environment.value!r})"
        )


__all__ = ["validate_settings"]
