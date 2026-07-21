"""Security settings, backing ``api/auth/`` and ``api/middleware/``.

Environment variables use the ``SECURITY_`` prefix. ``jwt_secret`` also accepts the
original ``.env.example`` variable ``JWT_SECRET`` as a fallback alias, so existing
local ``.env`` files created before this phase keep working without edits.

Secrets are never given non-empty defaults here beyond the explicit, obviously-fake
local-development values documented in ``.env.example`` and ``config/environments/dev.yaml``.
``config.validation`` refuses to start a ``paper``/``live`` process with a dev-shaped
secret still in place.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import NoDecode

from config.base import ModuleBaseSettings, module_settings_config

#: Sentinel value shipped in .env.example / dev.yaml; config.validation rejects it
#: outside dev so a forgotten override can never reach paper/live.
INSECURE_DEFAULT_SECRET = "changeme"  # noqa: S105 - sentinel value, not a real credential


class SecuritySettings(ModuleBaseSettings):
    """Authentication/authorization configuration."""

    model_config = module_settings_config(env_prefix="SECURITY_")

    jwt_secret: SecretStr = Field(
        default=SecretStr(INSECURE_DEFAULT_SECRET),
        validation_alias=AliasChoices("SECURITY_JWT_SECRET", "JWT_SECRET"),
        description="HMAC signing secret for issued JWTs. Must be overridden outside dev.",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm.")
    jwt_access_token_expiry_minutes: int = Field(
        default=15, description="Access token lifetime.", ge=1
    )
    jwt_refresh_token_expiry_days: int = Field(
        default=7, description="Refresh token lifetime.", ge=1
    )
    jwt_issuer: str = Field(default="ai-trading-platform", description="JWT 'iss' claim.")
    password_hash_scheme: str = Field(
        default="bcrypt", description="passlib scheme used to hash stored credentials."
    )
    min_password_length: int = Field(
        default=12, description="Minimum accepted password length.", ge=8
    )
    mfa_required_for_trading: bool = Field(
        default=True,
        description="Require MFA for any trade-affecting action, per PHASE1_ARCHITECTURE §13.",
    )
    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1"],
        description="Hostnames accepted in the Host header (TrustedHostMiddleware).",
    )
    secure_cookies: bool = Field(
        default=False, description="Set the Secure flag on cookies. Forced True outside dev."
    )

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def _split_allowed_hosts(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("jwt_algorithm")
    @classmethod
    def _validate_jwt_algorithm(cls, value: str) -> str:
        allowed = {"HS256", "HS384", "HS512", "RS256", "RS384", "RS512"}
        normalized = value.strip().upper()
        if normalized not in allowed:
            raise ValueError(f"jwt_algorithm must be one of {sorted(allowed)}, got {value!r}")
        return normalized


__all__ = ["SecuritySettings", "INSECURE_DEFAULT_SECRET"]
