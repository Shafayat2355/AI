"""Unit tests for shared.utils.time_utils."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from shared.utils.time_utils import ensure_utc, from_iso8601, monotonic_ms, to_iso8601, utcnow


class TestUtcnow:
    def test_returns_timezone_aware_datetime(self) -> None:
        result = utcnow()
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)


class TestEnsureUtc:
    def test_naive_datetime_is_stamped_as_utc(self) -> None:
        naive = datetime(2026, 1, 1, 12, 0, 0)  # noqa: DTZ001
        result = ensure_utc(naive)
        assert result.tzinfo is UTC
        assert result.hour == 12

    def test_aware_datetime_in_other_timezone_is_converted(self) -> None:
        other_tz = timezone(timedelta(hours=5))
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=other_tz)
        result = ensure_utc(aware)
        assert result.tzinfo is UTC
        assert result.hour == 7

    def test_non_datetime_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            ensure_utc("not-a-datetime")  # type: ignore[arg-type]


class TestToIso8601:
    def test_uses_z_suffix_for_utc(self) -> None:
        value = datetime(2026, 3, 15, 8, 30, 0, tzinfo=UTC)
        assert to_iso8601(value) == "2026-03-15T08:30:00Z"

    def test_converts_non_utc_before_formatting(self) -> None:
        other_tz = timezone(timedelta(hours=-3))
        value = datetime(2026, 3, 15, 5, 30, 0, tzinfo=other_tz)
        assert to_iso8601(value) == "2026-03-15T08:30:00Z"


class TestFromIso8601:
    def test_parses_z_suffixed_string(self) -> None:
        result = from_iso8601("2026-03-15T08:30:00Z")
        assert result == datetime(2026, 3, 15, 8, 30, 0, tzinfo=UTC)

    def test_parses_offset_suffixed_string(self) -> None:
        result = from_iso8601("2026-03-15T08:30:00+00:00")
        assert result == datetime(2026, 3, 15, 8, 30, 0, tzinfo=UTC)

    def test_round_trip(self) -> None:
        original = utcnow()
        assert from_iso8601(to_iso8601(original)).isoformat() == to_iso8601(original).replace(
            "Z", "+00:00"
        )

    def test_malformed_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match=".*"):
            from_iso8601("not-a-date")


class TestMonotonicMs:
    def test_increases_over_time(self) -> None:
        first = monotonic_ms()
        second = monotonic_ms()
        assert second >= first
