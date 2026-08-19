from __future__ import annotations

import unittest

from loxbridge.addon.delta_confirm import (
    merge_added,
)


class DeltaConfirmTests(unittest.TestCase):

    def test_added_is_merged_into_baseline(
        self,
    ) -> None:
        baseline = {
            "existing": {
                "Check": "existing=\\v",
            },
        }

        current = {
            "existing": {
                "Check": "existing=\\v",
            },
            "new_event": {
                "Check": "new_event=\\v",
            },
        }

        merged = merge_added(
            baseline=baseline,
            current=current,
            added_keys=("new_event",),
        )

        self.assertEqual(
            set(merged),
            {
                "existing",
                "new_event",
            },
        )

    def test_removed_baseline_item_is_kept(
        self,
    ) -> None:
        baseline = {
            "old_raw": {
                "Check": "old_raw=\\v",
            },
        }

        current = {
            "new_event": {
                "Check": "new_event=\\v",
            },
        }

        merged = merge_added(
            baseline=baseline,
            current=current,
            added_keys=("new_event",),
        )

        self.assertIn(
            "old_raw",
            merged,
        )

        self.assertIn(
            "new_event",
            merged,
        )

    def test_existing_definition_is_not_replaced(
        self,
    ) -> None:
        baseline = {
            "temperature": {
                "Unit": "°C",
            },
        }

        current = {
            "temperature": {
                "Unit": "K",
            },
            "new_event": {
                "Check": "new_event=\\v",
            },
        }

        merged = merge_added(
            baseline=baseline,
            current=current,
            added_keys=("new_event",),
        )

        self.assertEqual(
            merged["temperature"]["Unit"],
            "°C",
        )

    def test_missing_added_key_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            RuntimeError
        ):
            merge_added(
                baseline={},
                current={},
                added_keys=("missing",),
            )


if __name__ == "__main__":
    unittest.main()