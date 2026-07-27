"""Unit tests for shared.validators."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import BaseModel

from shared.validators import (
    NonBlankStr,
    PositiveFloat,
    UTCDatetime,
    non_negative,
    not_blank,
    positive,
    require_timezone_aware,
    require_utc,
    strip_and_require_not_blank,
    within_unit_interval,
)


class TestNotBlank:
    def test_accepts_non_blank_string(self) -> None:
        assert not_blank("hello") == "hello"

    @pytest.mark.parametrize("value", ["", "   ", "\t\n"])
    def test_rejects_blank_string(self, value: str) -> None:
        with pytest.raises(ValueError, match="blank"):
            not_blank(value)


class TestStripAndRequireNotBlank:
    def test_trims_whitespace(self) -> None:
        assert strip_and_require_not_blank("  hello  ") == "hello"

    def test_rejects_whitespace_only(self) -> None:
        with pytest.raises(ValueError, match="blank"):
            strip_and_require_not_blank("   ")


class TestPositive:
    def test_accepts_positive_number(self) -> None:
        assert positive(1.5) == 1.5

    @pytest.mark.parametrize("value", [0, -1, -0.001])
    def test_rejects_zero_or_negative(self, value: float) -> None:
        with pytest.raises(ValueError, match="positive"):
            positive(value)


class TestNonNegative:
    def test_accepts_zero(self) -> None:
        assert non_negative(0) == 0

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            non_negative(-1)


class TestWithinUnitInterval:
    @pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
    def test_accepts_boundaries_and_midpoint(self, value: float) -> None:
        assert within_unit_interval(value) == value

    @pytest.mark.parametrize("value", [-0.01, 1.01])
    def test_rejects_out_of_range(self, value: float) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            within_unit_interval(value)


class TestRequireTimezoneAware:
    def test_accepts_aware_datetime(self) -> None:
        value = datetime(2026, 1, 1, tzinfo=UTC)
        assert require_timezone_aware(value) is value

    def test_rejects_naive_datetime(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            require_timezone_aware(datetime(2026, 1, 1))  # noqa: DTZ001


class TestRequireUtc:
    def test_accepts_utc_datetime(self) -> None:
        value = datetime(2026, 1, 1, tzinfo=UTC)
        assert require_utc(value) is value

    def test_rejects_naive_datetime(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            require_utc(datetime(2026, 1, 1))  # noqa: DTZ001

    def test_rejects_non_utc_offset(self) -> None:
        other_tz = timezone(timedelta(hours=2))
        with pytest.raises(ValueError, match="UTC"):
            require_utc(datetime(2026, 1, 1, tzinfo=other_tz))


class TestAnnotatedTypes:
    def test_non_blank_str_field_type_strips_and_validates(self) -> None:
        class Model(BaseModel):
            name: NonBlankStr

        assert Model(name="  hi  ").name == "hi"
        with pytest.raises(Exception, match="blank"):
            Model(name="   ")

    def test_positive_float_field_type(self) -> None:
        class Model(BaseModel):
            quantity: PositiveFloat

        assert Model(quantity=2.5).quantity == 2.5
        with pytest.raises(Exception, match="positive"):
            Model(quantity=-1.0)

    def test_utc_datetime_field_type(self) -> None:
        class Model(BaseModel):
            occurred_at: UTCDatetime

        value = datetime(2026, 1, 1, tzinfo=UTC)
        assert Model(occurred_at=value).occurred_at == value
        with pytest.raises(Exception, match="UTC"):
            Model(occurred_at=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1))))
