from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from loxbridge.json_view import to_jsonable


class Color(str, Enum):
    RED = "red"
    BLUE = "blue"


@dataclass(frozen=True)
class Inner:
    label: str
    color: Color


@dataclass(frozen=True)
class Outer:
    id: str
    items: tuple[Inner, ...]
    path: Path
    extra: dict


class ToJsonableTests(unittest.TestCase):
    def test_primitives_pass_through(self) -> None:
        self.assertEqual(to_jsonable("x"), "x")
        self.assertEqual(to_jsonable(1), 1)
        self.assertEqual(to_jsonable(1.5), 1.5)
        self.assertEqual(to_jsonable(True), True)
        self.assertIsNone(to_jsonable(None))

    def test_enum_becomes_value(self) -> None:
        self.assertEqual(to_jsonable(Color.RED), "red")

    def test_path_becomes_string(self) -> None:
        self.assertEqual(
            to_jsonable(Path("/tmp/x.yaml")), "/tmp/x.yaml"
        )

    def test_tuple_becomes_list(self) -> None:
        self.assertEqual(to_jsonable((1, 2, 3)), [1, 2, 3])

    def test_list_stays_list(self) -> None:
        self.assertEqual(to_jsonable([1, 2]), [1, 2])

    def test_dict_keys_and_values_converted(self) -> None:
        result = to_jsonable({"a": Color.BLUE, "b": (1, 2)})
        self.assertEqual(result, {"a": "blue", "b": [1, 2]})

    def test_flat_dataclass(self) -> None:
        result = to_jsonable(Inner(label="x", color=Color.RED))
        self.assertEqual(result, {"label": "x", "color": "red"})

    def test_nested_dataclass_with_tuple_and_path(
        self,
    ) -> None:
        outer = Outer(
            id="o1",
            items=(
                Inner(label="a", color=Color.RED),
                Inner(label="b", color=Color.BLUE),
            ),
            path=Path("/x/y.yaml"),
            extra={"nested": Color.RED},
        )

        result = to_jsonable(outer)

        self.assertEqual(
            result,
            {
                "id": "o1",
                "items": [
                    {"label": "a", "color": "red"},
                    {"label": "b", "color": "blue"},
                ],
                "path": "/x/y.yaml",
                "extra": {"nested": "red"},
            },
        )

    def test_result_is_actually_json_dumpable(self) -> None:
        outer = Outer(
            id="o1",
            items=(Inner(label="a", color=Color.RED),),
            path=Path("/x"),
            extra={},
        )

        # Tohle by bez to_jsonable() vyhodilo TypeError kvůli Enum
        # a dataclass instancím.
        dumped = json.dumps(to_jsonable(outer))
        self.assertIn('"color": "red"', dumped)


if __name__ == "__main__":
    unittest.main()
