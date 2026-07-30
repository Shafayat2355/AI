"""Pluggable (de)serialization for cache values.

``cache/cache_manager.py``'s ``get``/``set`` always store/retrieve raw ``bytes``
against Redis (see ``cache/redis_client.py``'s module docstring for why) and
delegate the actual encoding to one of these -- :data:`json_serializer` for
plain-data values (dicts, lists, numbers, strings -- the common case, and the
default), :data:`pickle_serializer` for arbitrary Python objects a JSON
encoder cannot represent (e.g. a numpy array or a dataclass instance a model
prediction might return).
"""

from __future__ import annotations

import json
import pickle  # noqa: S403 - see PickleSerializer's docstring for the accepted trade-off
from typing import Any, Protocol


class Serializer(Protocol):
    """Contract a cache value codec must satisfy."""

    def dumps(self, value: Any) -> bytes:
        """Encode ``value`` to bytes for storage in Redis."""
        ...

    def loads(self, data: bytes) -> Any:
        """Decode bytes previously produced by :meth:`dumps` back to a Python value."""
        ...


class JSONSerializer:
    """Encodes/decodes values as UTF-8 JSON. The default serializer -- use this
    unless the value genuinely cannot be represented as JSON."""

    def dumps(self, value: Any) -> bytes:
        return json.dumps(value, default=str).encode("utf-8")

    def loads(self, data: bytes) -> Any:
        return json.loads(data.decode("utf-8"))


class PickleSerializer:
    """Encodes/decodes arbitrary Python objects via :mod:`pickle`.

    Security trade-off, accepted deliberately: ``pickle.loads`` can execute
    arbitrary code if fed attacker-controlled bytes. This is safe here only
    because every value this serializer decodes was itself written by this same
    process (or a sibling instance of the same trusted service) through
    :meth:`dumps` -- never used to decode a value that originated from external,
    untrusted input. Do not use :data:`pickle_serializer` for any cache entry an
    external client can influence the *content* of (as opposed to merely the
    cache *key*, which is fine).
    """

    def dumps(self, value: Any) -> bytes:
        return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)

    def loads(self, data: bytes) -> Any:
        return pickle.loads(data)  # noqa: S301 - see class docstring


json_serializer = JSONSerializer()
pickle_serializer = PickleSerializer()

__all__ = [
    "JSONSerializer",
    "PickleSerializer",
    "Serializer",
    "json_serializer",
    "pickle_serializer",
]
