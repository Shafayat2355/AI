"""Unit tests for config.environment."""

from __future__ import annotations

import pytest

from config.environment import Environment, resolve_environment


class TestEnvironmentEnum:
    def test_has_exactly_three_members(self) -> None:
        assert {member.value for member in Environment} == {"dev", "paper", "live"}

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("dev", Environment.DEV),
            ("paper", Environment.PAPER),
            ("live", Environment.LIVE),
            ("DEV", Environment.DEV),
            ("Paper", Environment.PAPER),
            ("development", Environment.DEV),
            ("local", Environment.DEV),
            ("staging", Environment.PAPER),
            ("stage", Environment.PAPER),
            ("simulation", Environment.PAPER),
            ("production", Environment.LIVE),
            ("prod", Environment.LIVE),
        ],
    )
    def test_accepts_case_insensitive_values_and_aliases(
        self, value: str, expected: Environment
    ) -> None:
        assert Environment(value) is expected

    def test_unknown_value_raises(self) -> None:
        with pytest.raises(ValueError, match="testing"):
            Environment("testing")

    def test_str_returns_canonical_value(self) -> None:
        assert str(Environment.PAPER) == "paper"

    @pytest.mark.parametrize(
        ("member", "is_dev", "is_paper", "is_live", "is_production_like"),
        [
            (Environment.DEV, True, False, False, False),
            (Environment.PAPER, False, True, False, True),
            (Environment.LIVE, False, False, True, True),
        ],
    )
    def test_predicate_properties(
        self,
        member: Environment,
        is_dev: bool,
        is_paper: bool,
        is_live: bool,
        is_production_like: bool,
    ) -> None:
        assert member.is_dev is is_dev
        assert member.is_paper is is_paper
        assert member.is_live is is_live
        assert member.is_production_like is is_production_like


class TestResolveEnvironment:
    def test_explicit_value_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "live")
        assert resolve_environment("dev") is Environment.DEV

    def test_falls_back_to_environment_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "paper")
        assert resolve_environment() is Environment.PAPER

    def test_defaults_to_dev_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert resolve_environment() is Environment.DEV

    def test_accepts_environment_instance(self) -> None:
        assert resolve_environment(Environment.LIVE) is Environment.LIVE
