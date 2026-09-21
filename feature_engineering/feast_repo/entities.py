"""Feast entity definitions.

One entity for this platform's whole feature set: the trading symbol. Every
feature view in ``feature_views.py`` joins on it, which is what lets
``feature_store_client.get_online_features``/``get_historical_features`` serve
any combination of feature views for the same ``entity_rows``/``entity_df``
without the caller needing to know which view a given feature came from.
"""

from __future__ import annotations

from feast import Entity
from feast.value_type import ValueType

SYMBOL = Entity(
    name="symbol",
    join_keys=["symbol"],
    value_type=ValueType.STRING,
    description="Trading symbol/instrument identifier, e.g. 'BTCUSDT'.",
)

__all__ = ["SYMBOL"]
