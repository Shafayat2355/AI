"""Unit tests for shared.models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.enums import HealthStatus
from shared.models import BaseSchema, ComponentHealth, HealthCheckResponse, VersionResponse


class _Sample(BaseSchema):
    name: str


class TestBaseSchema:
    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            _Sample(name="ok", extra_field="nope")  # type: ignore[call-arg]

    def test_strips_whitespace_on_str_fields(self) -> None:
        assert _Sample(name="  padded  ").name == "padded"


class TestComponentHealth:
    def test_detail_defaults_to_none(self) -> None:
        component = ComponentHealth(name="database", status=HealthStatus.HEALTHY)
        assert component.detail is None


class TestHealthCheckResponse:
    def test_components_default_to_empty_list(self) -> None:
        response = HealthCheckResponse(status=HealthStatus.HEALTHY)
        assert response.components == []

    def test_checked_at_is_populated_automatically(self) -> None:
        response = HealthCheckResponse(status=HealthStatus.HEALTHY)
        assert response.checked_at.endswith("Z")

    def test_carries_component_breakdown(self) -> None:
        response = HealthCheckResponse(
            status=HealthStatus.DEGRADED,
            components=[
                ComponentHealth(name="database", status=HealthStatus.DEGRADED, detail="slow"),
            ],
        )
        assert response.components[0].name == "database"
        assert response.components[0].detail == "slow"


class TestVersionResponse:
    def test_round_trips_all_fields(self) -> None:
        response = VersionResponse(
            name="ai-trading-platform",
            version="0.1.0",
            description="An AI trading platform.",
            environment="dev",
        )
        dumped = response.model_dump()
        assert dumped["name"] == "ai-trading-platform"
        assert dumped["environment"] == "dev"
