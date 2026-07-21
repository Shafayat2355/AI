"""Unit tests for config.loader."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from config.environment import Environment
from config.exceptions import ConfigurationSourceError
from config.loader import (
    bootstrap_environment,
    flatten_overlay,
    load_dotenv_values,
    load_overlay_file,
)

pytestmark = pytest.mark.usefixtures("isolated_environment")


class TestFlattenOverlay:
    def test_flattens_known_sections_with_prefixes(self) -> None:
        raw = {"redis": {"host": "cache.internal", "port": 6380}}
        assert flatten_overlay(raw) == {
            "REDIS_HOST": "cache.internal",
            "REDIS_PORT": "6380",
        }

    def test_root_level_keys_pass_through_unprefixed(self) -> None:
        raw = {"environment": "paper", "debug": False}
        assert flatten_overlay(raw) == {"ENVIRONMENT": "paper", "DEBUG": "false"}

    def test_unknown_section_ignored(self) -> None:
        raw = {"not_a_real_module": {"foo": "bar"}}
        assert flatten_overlay(raw) == {}

    def test_boolean_rendered_lowercase(self) -> None:
        raw = {"database": {"echo": True}}
        assert flatten_overlay(raw) == {"DATABASE_ECHO": "true"}

    def test_list_rendered_comma_separated(self) -> None:
        raw = {"kafka": {"bootstrap_servers": ["a:9092", "b:9092"]}}
        assert flatten_overlay(raw) == {"KAFKA_BOOTSTRAP_SERVERS": "a:9092,b:9092"}

    def test_non_mapping_section_raises(self) -> None:
        raw = {"redis": "not-a-mapping"}
        with pytest.raises(ConfigurationSourceError, match="must be a mapping"):
            flatten_overlay(raw)

    def test_postgresql_alias_maps_to_postgres_prefix(self) -> None:
        raw = {"postgresql": {"host": "db"}}
        assert flatten_overlay(raw) == {"POSTGRES_HOST": "db"}


class TestLoadOverlayFile:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_overlay_file(tmp_path / "does-not-exist.yaml") == {}

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.yaml"
        path.write_text("# just a comment\n", encoding="utf-8")
        assert load_overlay_file(path) == {}

    def test_parses_and_flattens(self, tmp_path: Path) -> None:
        path = tmp_path / "overlay.yaml"
        path.write_text("redis:\n  host: cache\n  port: 6380\n", encoding="utf-8")
        assert load_overlay_file(path) == {"REDIS_HOST": "cache", "REDIS_PORT": "6380"}

    def test_non_mapping_top_level_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ConfigurationSourceError, match="top-level mapping"):
            load_overlay_file(path)

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "invalid.yaml"
        path.write_text("redis: [unclosed\n", encoding="utf-8")
        with pytest.raises(ConfigurationSourceError, match="Could not parse"):
            load_overlay_file(path)


class TestLoadDotenvValues:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_dotenv_values(tmp_path / "missing.env") == {}

    def test_parses_key_value_pairs(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")
        assert load_dotenv_values(path) == {"FOO": "bar", "BAZ": "qux"}

    def test_keys_with_no_value_are_dropped(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text("FOO=\nBAR=set\n", encoding="utf-8")
        result = load_dotenv_values(path)
        assert result.get("BAR") == "set"
        assert result.get("FOO") == ""  # explicit empty string is a real value, not dropped


class TestBootstrapEnvironment:
    def test_yaml_overlay_applied_when_nothing_else_set(self, tmp_path: Path) -> None:
        env_dir = tmp_path / "environments"
        env_dir.mkdir()
        (env_dir / "dev.yaml").write_text("redis:\n  host: yaml-host\n", encoding="utf-8")
        dotenv_path = tmp_path / ".env-does-not-exist"

        applied = bootstrap_environment(
            Environment.DEV, dotenv_path=dotenv_path, environments_dir=env_dir
        )

        assert applied["REDIS_HOST"] == "yaml-host"
        assert os.environ.get("REDIS_HOST") == "yaml-host"

    def test_dotenv_overrides_yaml(self, tmp_path: Path) -> None:
        env_dir = tmp_path / "environments"
        env_dir.mkdir()
        (env_dir / "dev.yaml").write_text("redis:\n  host: yaml-host\n", encoding="utf-8")
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text("REDIS_HOST=dotenv-host\n", encoding="utf-8")

        applied = bootstrap_environment(
            Environment.DEV, dotenv_path=dotenv_path, environments_dir=env_dir
        )

        assert applied["REDIS_HOST"] == "dotenv-host"

    def test_real_os_environ_outranks_both(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_dir = tmp_path / "environments"
        env_dir.mkdir()
        (env_dir / "dev.yaml").write_text("redis:\n  host: yaml-host\n", encoding="utf-8")
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text("REDIS_HOST=dotenv-host\n", encoding="utf-8")
        monkeypatch.setenv("REDIS_HOST", "real-env-host")

        applied = bootstrap_environment(
            Environment.DEV, dotenv_path=dotenv_path, environments_dir=env_dir
        )

        assert "REDIS_HOST" not in applied  # already set, loader must not touch it
        assert os.environ["REDIS_HOST"] == "real-env-host"

    def test_missing_overlay_file_is_not_an_error(self, tmp_path: Path) -> None:
        env_dir = tmp_path / "environments"
        env_dir.mkdir()
        dotenv_path = tmp_path / ".env-does-not-exist"

        applied = bootstrap_environment(
            Environment.LIVE, dotenv_path=dotenv_path, environments_dir=env_dir
        )

        assert applied["ENVIRONMENT"] == "live"

    def test_environment_variable_defaulted_when_absent(self, tmp_path: Path) -> None:
        env_dir = tmp_path / "environments"
        env_dir.mkdir()
        dotenv_path = tmp_path / ".env-does-not-exist"

        applied = bootstrap_environment(
            Environment.PAPER, dotenv_path=dotenv_path, environments_dir=env_dir
        )

        assert applied["ENVIRONMENT"] == "paper"
