"""Unit tests for cache.serializers."""

from __future__ import annotations

from dataclasses import dataclass

from cache.serializers import JSONSerializer, PickleSerializer, json_serializer, pickle_serializer


class TestJSONSerializer:
    def test_round_trips_a_dict(self) -> None:
        serializer = JSONSerializer()
        value = {"symbol": "BTCUSDT", "price": 65000.5, "tags": ["spot", "major"]}
        assert serializer.loads(serializer.dumps(value)) == value

    def test_round_trips_a_list(self) -> None:
        serializer = JSONSerializer()
        assert serializer.loads(serializer.dumps([1, 2, 3])) == [1, 2, 3]

    def test_round_trips_a_plain_scalar(self) -> None:
        serializer = JSONSerializer()
        assert serializer.loads(serializer.dumps(42)) == 42
        assert serializer.loads(serializer.dumps("hello")) == "hello"
        assert serializer.loads(serializer.dumps(None)) is None

    def test_dumps_returns_bytes(self) -> None:
        assert isinstance(JSONSerializer().dumps({"a": 1}), bytes)

    def test_module_level_instance_is_usable_directly(self) -> None:
        assert json_serializer.loads(json_serializer.dumps({"x": 1})) == {"x": 1}

    def test_non_json_native_values_fall_back_to_str_via_default(self) -> None:
        # `default=str` in JSONSerializer.dumps means an otherwise-unencodable
        # value degrades to its string form rather than raising.
        class _Unencodable:
            def __str__(self) -> str:
                return "unencodable-repr"

        serializer = JSONSerializer()
        assert serializer.loads(serializer.dumps(_Unencodable())) == "unencodable-repr"


@dataclass
class _Point:
    x: int
    y: int


class TestPickleSerializer:
    def test_round_trips_a_dataclass_instance(self) -> None:
        serializer = PickleSerializer()
        point = _Point(x=1, y=2)
        restored = serializer.loads(serializer.dumps(point))
        assert restored == point

    def test_round_trips_a_dict_just_like_json_would(self) -> None:
        serializer = PickleSerializer()
        value = {"a": 1, "b": [1, 2, 3]}
        assert serializer.loads(serializer.dumps(value)) == value

    def test_dumps_returns_bytes(self) -> None:
        assert isinstance(PickleSerializer().dumps({"a": 1}), bytes)

    def test_module_level_instance_is_usable_directly(self) -> None:
        point = _Point(x=5, y=6)
        assert pickle_serializer.loads(pickle_serializer.dumps(point)) == point

    def test_pickle_and_json_bytes_are_not_interchangeable(self) -> None:
        # Demonstrates why CacheManager.get/set require the *same* serializer on
        # both sides -- pickle output is not valid JSON and vice versa.
        value = {"a": 1}
        pickled = pickle_serializer.dumps(value)
        assert pickled != json_serializer.dumps(value)
