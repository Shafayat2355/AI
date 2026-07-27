"""Unit tests for shared.utils.serialization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

import pytest

from shared.utils.serialization import dumps, dumps_bytes, json_default, loads


class _Color(Enum):
    RED = "red"


@dataclass
class _Point:
    x: int
    y: int


class TestJsonDefault:
    def test_decimal_becomes_string(self) -> None:
        assert json_default(Decimal("1.50")) == "1.50"

    def test_datetime_becomes_iso8601_utc(self) -> None:
        value = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        assert json_default(value) == "2026-01-01T12:00:00Z"

    def test_enum_becomes_its_value(self) -> None:
        assert json_default(_Color.RED) == "red"

    def test_uuid_becomes_string(self) -> None:
        value = UUID("12345678-1234-5678-1234-567812345678")
        assert json_default(value) == str(value)

    def test_dataclass_becomes_dict(self) -> None:
        assert json_default(_Point(1, 2)) == {"x": 1, "y": 2}

    def test_unsupported_type_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            json_default(object())


class TestDumps:
    def test_serializes_decimal_and_datetime_together(self) -> None:
        payload = {"price": Decimal("100.25"), "at": datetime(2026, 1, 1, tzinfo=UTC)}
        result = dumps(payload)
        assert '"price": "100.25"' in result or '"price":"100.25"' in result
        assert "2026-01-01T00:00:00Z" in result

    def test_ignores_caller_supplied_default_kwarg(self) -> None:
        # Even if a caller tries to override `default`, our own mapping still runs.
        result = dumps({"amount": Decimal("5")}, default=lambda _: "wrong")
        assert "5" in result

    def test_accepts_pass_through_kwargs(self) -> None:
        result = dumps({"b": 1, "a": 2}, sort_keys=True)
        assert result.index('"a"') < result.index('"b"')


class TestDumpsBytes:
    def test_returns_utf8_bytes(self) -> None:
        result = dumps_bytes({"symbol": "BTC-USD"})
        assert isinstance(result, bytes)
        assert loads(result) == {"symbol": "BTC-USD"}


class TestLoads:
    def test_round_trips_plain_json(self) -> None:
        assert loads(dumps({"a": 1, "b": [1, 2, 3]})) == {"a": 1, "b": [1, 2, 3]}
