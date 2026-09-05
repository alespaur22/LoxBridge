from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from loxbridge.instances import (
    build_instance_from_generated_device,
    contains_identity_leak,
    load_all_instances,
    load_instance,
    save_instance,
)


def _sample_device() -> dict:
    return {
        "name": "LED Obývák",
        "slug": "led_obyvak",
        "homey_id": "4a54b6a3-4074-44f6-a109-7e41210e2ae2",
        "homey_class": "light",
        "driver_id": "homey:app:com.fibaro:FGRGBWM-442",
        "zone_name": "Obývák",
        "capabilities": {
            "onoff": {
                "key": "led_obyvak_onoff",
                "loxone_name": "LED Obývák - Zapnuto",
                "type": "boolean",
            },
            "dim": {
                "key": "led_obyvak_dim",
                "loxone_name": "LED Obývák - Jas",
                "type": "number",
            },
        },
        "loxbridge": {
            "profile": "light.rgb_tunable_white",
            "commands": [
                {
                    "key": "led_obyvak_rgb",
                    "title": "LED Obývák - RGB",
                    "kind": "rgb",
                },
                {
                    "key": "led_obyvak_lumitech",
                    "title": "LED Obývák - Lumitech",
                    "kind": "lumitech",
                },
            ],
            "events": [
                {
                    "key": "led_obyvak_input_1_press_1x",
                    "title": "LED Obývák - Input 1 - Press 1x",
                    "kind": "pulse",
                },
                {
                    "key": "led_obyvak_input_1_hold",
                    "title": "LED Obývák - Input 1 - Hold",
                    "kind": "pulse",
                },
            ],
        },
    }


class BuildInstanceTests(unittest.TestCase):
    def test_basic_fields(self) -> None:
        instance = build_instance_from_generated_device(
            _sample_device()
        )

        self.assertEqual(
            instance["homey_id"],
            "4a54b6a3-4074-44f6-a109-7e41210e2ae2",
        )
        self.assertEqual(
            instance["instance_id"],
            instance["homey_id"],
        )
        self.assertEqual(
            instance["homey_name_last_seen"], "LED Obývák"
        )
        self.assertEqual(
            instance["instance_name"], "LED Obývák"
        )
        self.assertEqual(
            instance["loxone_name_base"], "LED Obývák"
        )
        self.assertEqual(instance["key_base"], "led_obyvak")
        self.assertTrue(instance["enabled"])
        self.assertIsNone(instance["template"])
        self.assertIsNone(instance["template_version"])
        self.assertEqual(
            instance["legacy_profile"],
            "light.rgb_tunable_white",
        )
        self.assertEqual(
            instance["homey_meta"]["driver_id"],
            "homey:app:com.fibaro:FGRGBWM-442",
        )

    def test_capability_keys_and_names_preserved(self) -> None:
        instance = build_instance_from_generated_device(
            _sample_device()
        )

        self.assertEqual(
            instance["keys"]["capabilities"]["onoff"],
            "led_obyvak_onoff",
        )
        self.assertEqual(
            instance["display_names"]["capabilities"]["onoff"],
            "LED Obývák - Zapnuto",
        )
        self.assertEqual(
            instance["keys"]["capabilities"]["dim"],
            "led_obyvak_dim",
        )

    def test_command_keys_indexed_by_kind(self) -> None:
        instance = build_instance_from_generated_device(
            _sample_device()
        )

        self.assertEqual(
            instance["keys"]["commands"]["rgb"],
            "led_obyvak_rgb",
        )
        self.assertEqual(
            instance["display_names"]["commands"]["lumitech"],
            "LED Obývák - Lumitech",
        )

    def test_event_keys_indexed_by_role_with_key_base_stripped(
        self,
    ) -> None:
        instance = build_instance_from_generated_device(
            _sample_device()
        )

        self.assertEqual(
            instance["keys"]["events"]["input_1_press_1x"],
            "led_obyvak_input_1_press_1x",
        )
        self.assertEqual(
            instance["display_names"]["events"][
                "input_1_hold"
            ],
            "LED Obývák - Input 1 - Hold",
        )

    def test_missing_homey_id_raises(self) -> None:
        device = _sample_device()
        device["homey_id"] = ""

        with self.assertRaises(ValueError):
            build_instance_from_generated_device(device)

    def test_homey_id_never_leaks_into_visible_values(
        self,
    ) -> None:
        instance = build_instance_from_generated_device(
            _sample_device()
        )

        self.assertFalse(contains_identity_leak(instance))


class InstanceLeakDetectionTests(unittest.TestCase):
    def test_detects_leak_in_key(self) -> None:
        instance = build_instance_from_generated_device(
            _sample_device()
        )

        instance["keys"]["capabilities"]["onoff"] = (
            f"led_{instance['homey_id']}_onoff"
        )

        self.assertTrue(contains_identity_leak(instance))

    def test_detects_leak_in_display_name(self) -> None:
        instance = build_instance_from_generated_device(
            _sample_device()
        )

        instance["display_names"]["commands"]["rgb"] = (
            instance["homey_id"]
        )

        self.assertTrue(contains_identity_leak(instance))


class InstanceIoTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        instance = build_instance_from_generated_device(
            _sample_device()
        )

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)

            path = save_instance(instance, directory)

            self.assertEqual(
                path.name,
                "4a54b6a3-4074-44f6-a109-7e41210e2ae2.yaml",
            )

            loaded = load_instance(path)

            self.assertEqual(loaded, instance)

    def test_load_all_instances_keyed_by_homey_id(self) -> None:
        first = build_instance_from_generated_device(
            _sample_device()
        )

        second_device = _sample_device()
        second_device["name"] = "LED Postel"
        second_device["slug"] = "led_postel"
        second_device["homey_id"] = (
            "9f21c7de-1a3b-4e88-9c02-6b1f9a2d7e44"
        )

        second = build_instance_from_generated_device(
            second_device
        )

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)

            save_instance(first, directory)
            save_instance(second, directory)

            loaded = load_all_instances(directory)

        self.assertEqual(set(loaded), {first["homey_id"], second["homey_id"]})
        self.assertEqual(
            loaded[first["homey_id"]]["instance_name"],
            "LED Obývák",
        )

    def test_load_all_instances_missing_directory_returns_empty(
        self,
    ) -> None:
        missing = Path(tempfile.mkdtemp()) / "does-not-exist"

        self.assertEqual(load_all_instances(missing), {})


if __name__ == "__main__":
    unittest.main()
