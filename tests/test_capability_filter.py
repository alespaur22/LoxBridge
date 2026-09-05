from __future__ import annotations

import unittest

from loxbridge.capability_filter import (
    IGNORED_CAPABILITIES,
    IGNORED_CAPABILITY_PREFIXES,
    SUPPORTED_TYPES,
    should_include_capability,
)


def _capability(**overrides) -> dict:
    base = {
        "id": "measure_temperature",
        "type": "number",
        "getable": True,
        "setable": False,
    }
    base.update(overrides)
    return base


class ShouldIncludeCapabilityTests(unittest.TestCase):
    def test_valid_capability_is_included(self) -> None:
        self.assertTrue(
            should_include_capability(_capability())
        )

    def test_missing_id_is_excluded(self) -> None:
        self.assertFalse(
            should_include_capability(_capability(id=""))
        )

    def test_not_getable_is_excluded(self) -> None:
        self.assertFalse(
            should_include_capability(
                _capability(getable=False)
            )
        )
        self.assertFalse(
            should_include_capability(
                _capability(getable=None)
            )
        )

    def test_unsupported_type_is_excluded(self) -> None:
        self.assertFalse(
            should_include_capability(
                _capability(type="unknown_type")
            )
        )

    def test_every_supported_type_is_accepted(self) -> None:
        for capability_type in SUPPORTED_TYPES:
            with self.subTest(capability_type=capability_type):
                self.assertTrue(
                    should_include_capability(
                        _capability(type=capability_type)
                    )
                )

    def test_ignored_capability_id_is_excluded(self) -> None:
        for capability_id in IGNORED_CAPABILITIES:
            with self.subTest(capability_id=capability_id):
                self.assertFalse(
                    should_include_capability(
                        _capability(id=capability_id)
                    )
                )

    def test_ignored_prefix_is_excluded(self) -> None:
        for prefix in IGNORED_CAPABILITY_PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertFalse(
                    should_include_capability(
                        _capability(id=f"{prefix}foo")
                    )
                )


if __name__ == "__main__":
    unittest.main()
