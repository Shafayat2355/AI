"""Unit tests for shared.logging.correlation."""

from __future__ import annotations

import re

from shared.logging.correlation import (
    bind_context,
    correlation_context,
    generate_id,
    get_correlation_id,
    get_log_context,
    get_request_id,
    propagate_context,
    propagate_context_async,
    set_correlation_id,
    set_request_id,
)
from tests.unit.logging.conftest import run_async

_HEX32 = re.compile(r"^[0-9a-f]{32}$")


class TestGenerateId:
    def test_generates_a_32_char_hex_string(self) -> None:
        assert _HEX32.match(generate_id())

    def test_generates_unique_values(self) -> None:
        assert generate_id() != generate_id()


class TestCorrelationIdAccessors:
    def test_defaults_to_none(self) -> None:
        assert get_correlation_id() is None

    def test_set_then_get_round_trips(self) -> None:
        set_correlation_id("abc123")
        assert get_correlation_id() == "abc123"

    def test_request_id_defaults_to_none(self) -> None:
        assert get_request_id() is None

    def test_set_request_id_round_trips(self) -> None:
        set_request_id("req-1")
        assert get_request_id() == "req-1"


class TestCorrelationContext:
    def test_generates_a_correlation_id_when_none_given(self) -> None:
        with correlation_context() as correlation_id:
            assert correlation_id is not None
            assert get_correlation_id() == correlation_id

    def test_uses_the_supplied_correlation_id(self) -> None:
        with correlation_context("supplied-id") as correlation_id:
            assert correlation_id == "supplied-id"
            assert get_correlation_id() == "supplied-id"

    def test_resets_correlation_id_on_exit(self) -> None:
        with correlation_context("supplied-id"):
            pass
        assert get_correlation_id() is None

    def test_binds_request_id_when_given(self) -> None:
        with correlation_context("c1", request_id="r1"):
            assert get_request_id() == "r1"
        assert get_request_id() is None

    def test_leaves_request_id_untouched_when_not_given(self) -> None:
        set_request_id("outer-request")
        with correlation_context("c1"):
            assert get_request_id() == "outer-request"
        assert get_request_id() == "outer-request"

    def test_resets_correlation_id_even_if_block_raises(self) -> None:
        try:
            with correlation_context("c1"):
                raise ValueError("boom")
        except ValueError:
            pass
        assert get_correlation_id() is None

    def test_nested_contexts_restore_the_outer_value(self) -> None:
        with correlation_context("outer"):
            with correlation_context("inner"):
                assert get_correlation_id() == "inner"
            assert get_correlation_id() == "outer"


class TestBindContext:
    def test_defaults_to_empty_mapping(self) -> None:
        assert get_log_context() == {}

    def test_merges_fields_for_the_block(self) -> None:
        with bind_context(account_id="acc-1", symbol="BTCUSDT"):
            assert get_log_context() == {"account_id": "acc-1", "symbol": "BTCUSDT"}
        assert get_log_context() == {}

    def test_nested_binds_accumulate(self) -> None:
        with bind_context(account_id="acc-1"):
            with bind_context(symbol="BTCUSDT"):
                assert get_log_context() == {"account_id": "acc-1", "symbol": "BTCUSDT"}
            assert get_log_context() == {"account_id": "acc-1"}

    def test_inner_bind_overrides_same_key(self) -> None:
        with bind_context(symbol="BTCUSDT"):
            with bind_context(symbol="ETHUSDT"):
                assert get_log_context()["symbol"] == "ETHUSDT"
            assert get_log_context()["symbol"] == "BTCUSDT"


class TestPropagateContext:
    def test_sync_wrapper_sees_the_context_captured_at_decoration_time(self) -> None:
        with correlation_context("captured-id"):

            @propagate_context
            def read_correlation_id() -> str | None:
                return get_correlation_id()

        # Outside the `with` block entirely -- context would otherwise be None.
        assert get_correlation_id() is None
        assert read_correlation_id() == "captured-id"

    def test_sync_wrapper_restores_caller_context_after_returning(self) -> None:
        with correlation_context("captured-id"):

            @propagate_context
            def noop() -> None:
                return None

        set_correlation_id("caller-context")
        noop()
        assert get_correlation_id() == "caller-context"

    def test_async_wrapper_sees_the_context_captured_at_decoration_time(self) -> None:
        with correlation_context("captured-id"):

            @propagate_context_async
            async def read_correlation_id() -> str | None:
                return get_correlation_id()

        assert run_async(read_correlation_id()) == "captured-id"
