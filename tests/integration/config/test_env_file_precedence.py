"""Integration test for the full configuration source precedence chain, using
temporary overlay/.env files but the real :class:`~config.modules.redis.RedisSettings`
and :func:`~config.loader.bootstrap_environment`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config.environment import Environment
from config.loader import bootstrap_environment
from config.modules.redis import RedisSettings

pytestmark = pytest.mark.usefixtures("isolated_environment")


class TestFullPrecedenceChain:
    def test_precedence_env_beats_dotenv_beats_yaml_beats_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_dir = tmp_path / "environments"
        env_dir.mkdir()
        (env_dir / "dev.yaml").write_text(
            "redis:\n  host: yaml-host\n  port: 6001\n  db: 1\n", encoding="utf-8"
        )
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text("REDIS_HOST=dotenv-host\nREDIS_PORT=6002\n", encoding="utf-8")
        monkeypatch.setenv("REDIS_HOST", "real-env-host")

        bootstrap_environment(Environment.DEV, dotenv_path=dotenv_path, environments_dir=env_dir)
        settings = RedisSettings()

        # REDIS_HOST: real env var wins over both .env and yaml.
        assert settings.host == "real-env-host"
        # REDIS_PORT: not in real env, .env wins over yaml.
        assert settings.port == 6002
        # REDIS_DB: only present in yaml, nothing else set it.
        assert settings.db == 1

    def test_field_untouched_by_any_source_keeps_class_default(
        self, tmp_path: Path
    ) -> None:
        env_dir = tmp_path / "environments"
        env_dir.mkdir()
        (env_dir / "dev.yaml").write_text("redis:\n  host: yaml-host\n", encoding="utf-8")
        dotenv_path = tmp_path / ".env-missing"

        bootstrap_environment(Environment.DEV, dotenv_path=dotenv_path, environments_dir=env_dir)
        settings = RedisSettings()

        assert settings.host == "yaml-host"
        assert settings.max_connections == 50  # untouched -- class default
