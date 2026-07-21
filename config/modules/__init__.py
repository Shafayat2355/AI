"""Individual, independently-instantiable settings modules composed by
:class:`config.settings.Settings`.

Each module owns one env-var prefix and can be used standalone (e.g. for dependency
injection into a single component that only needs Redis config) or as a field on the
composed root ``Settings``.
"""

from config.modules.ai_models import AIModelSettings
from config.modules.api import APISettings
from config.modules.application import ApplicationSettings
from config.modules.binance import BinanceSettings
from config.modules.database import DatabaseSettings
from config.modules.feature_engineering import FeatureEngineeringSettings
from config.modules.kafka import KafkaSettings
from config.modules.logging import LoggingSettings
from config.modules.monitoring import MonitoringSettings
from config.modules.postgresql import PostgreSQLSettings
from config.modules.redis import RedisSettings
from config.modules.security import SecuritySettings
from config.modules.websocket import WebSocketSettings

__all__ = [
    "AIModelSettings",
    "APISettings",
    "ApplicationSettings",
    "BinanceSettings",
    "DatabaseSettings",
    "FeatureEngineeringSettings",
    "KafkaSettings",
    "LoggingSettings",
    "MonitoringSettings",
    "PostgreSQLSettings",
    "RedisSettings",
    "SecuritySettings",
    "WebSocketSettings",
]
