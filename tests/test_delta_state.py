from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from loxbridge.addon.delta_state import (
    STATE_SCHEMA_VERSION,
    create_state_document,
    load_state,
    save_state,
)


class DeltaStateTests(unittest.TestCase):

    def test_create_state_document(
        self,
    ) -> None:
        document = create_state_document(
            inputs={
                "led_obyvak_onoff": {
                    "Check": (
                        "led_obyvak_onoff=\\v"
                    ),
                    "Analog": "true",
                },
            },
            outputs={
                "led_koupelna_rgb": {
                    "CmdOn": (
                        "led_koupelna_rgb=<v.3>"
                    ),
                    "Analog": "true",
                },
            },
        )

        self.assertEqual(
            document["schema_version"],
            STATE_SCHEMA_VERSION,
        )

        self.assertIn(
            "led_obyvak_onoff",
            document["inputs"],
        )

        self.assertIn(
            "led_koupelna_rgb",
            document["outputs"],
        )

    def test_save_and_load_state(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = (
                Path(temp)
                / "loxone_imported_state.json"
            )

            inputs = {
                "led_obyvak_onoff": {
                    "Check": (
                        "led_obyvak_onoff=\\v"
                    ),
                    "Analog": "true",
                },
            }

            outputs = {
                "led_obyvak_onoff": {
                    "CmdOn": (
                        "led_obyvak_onoff=1"
                    ),
                    "CmdOff": (
                        "led_obyvak_onoff=0"
                    ),
                },
            }

            save_state(
                path,
                inputs=inputs,
                outputs=outputs,
            )

            loaded_inputs, loaded_outputs = (
                load_state(path)
            )

            self.assertEqual(
                loaded_inputs,
                inputs,
            )

            self.assertEqual(
                loaded_outputs,
                outputs,
            )

    def test_saved_state_has_schema_version(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = (
                Path(temp)
                / "loxone_imported_state.json"
            )

            save_state(
                path,
                inputs={},
                outputs={},
            )

            document = json.loads(
                path.read_text(
                    encoding="utf-8",
                )
            )

            self.assertEqual(
                document["schema_version"],
                STATE_SCHEMA_VERSION,
            )

    def test_missing_state_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = (
                Path(temp)
                / "missing.json"
            )

            with self.assertRaises(
                RuntimeError
            ):
                load_state(path)

    def test_wrong_schema_version_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = (
                Path(temp)
                / "state.json"
            )

            path.write_text(
                json.dumps(
                    {
                        "schema_version": 999,
                        "inputs": {},
                        "outputs": {},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(
                RuntimeError
            ):
                load_state(path)


if __name__ == "__main__":
    unittest.main()