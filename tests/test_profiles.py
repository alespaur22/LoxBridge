from __future__ import annotations

import json
import unittest
from pathlib import Path

from loxbridge.generate import generate_devices


ROOT = Path(__file__).resolve().parents[1]
EXPORT_PATH = ROOT / "exports" / "homey_devices.json"


class ProfileEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        data = json.loads(
            EXPORT_PATH.read_text(encoding="utf-8")
        )

        cls.devices, _ = generate_devices(
            data["devices"]
        )

        cls.by_name = {
            device["name"]: device
            for device in cls.devices
        }

    def profile(self, name: str) -> dict:
        return self.by_name[name]["loxbridge"]

    def test_rgb_tunable_white_profile(self) -> None:
        profile = self.profile("LED Obývák")

        self.assertEqual(
            profile["profile"],
            "light.rgb_tunable_white",
        )

        commands = {
            command["kind"]: command
            for command in profile["commands"]
        }

        self.assertEqual(
            commands["rgb"]["key"],
            "led_obyvak_rgb",
        )
        self.assertEqual(
            commands["lumitech"]["key"],
            "led_obyvak_lumitech",
        )

    def test_tunable_white_group_profile(self) -> None:
        profile = self.profile("Bodovky")

        self.assertEqual(
            profile["profile"],
            "light.tunable_white",
        )
        self.assertEqual(
            profile["commands"][0]["key"],
            "bodovky_lumitech",
        )

    def test_dimmer_profile(self) -> None:
        profile = self.profile("LED Chodba")

        self.assertEqual(
            profile["profile"],
            "light.dimmer",
        )
        self.assertEqual(
            profile["commands"][0]["key"],
            "led_chodba_dimmer",
        )

    def test_rgb_white_channel_profile(self) -> None:
        profile = self.profile("LED Koupelna")

        self.assertEqual(
            profile["profile"],
            "light.rgb_white_channel",
        )

        commands = {
            command["kind"]: command
            for command in profile["commands"]
        }

        white = commands["rgb_white_white"]

        self.assertEqual(
            white["key"],
            "led_koupelna_white",
        )
        self.assertEqual(
            white["options"]["white_master_dim"],
            0.01,
        )
        self.assertFalse(
            white["options"]["use_whitemode"]
        )
        self.assertNotIn(
            "onoff.whitemode",
            white["targets"].values(),
        )

    def test_fibaro_input_bank_becomes_events(self) -> None:
        profile = self.profile("LED Obývák")

        self.assertEqual(profile["inputs"], [])

        self.assertEqual(
            profile["suppress_raw_inputs"],
            [
                "measure_voltage.input1",
                "measure_voltage.input2",
                "measure_voltage.input3",
                "measure_voltage.input4",
            ],
        )

        # Fyzicky používáme pouze Input 1.
        self.assertEqual(
            len(profile["events"]),
            5,
        )

        by_key = {
            event["key"]: event
            for event in profile["events"]
        }

        self.assertEqual(
            set(by_key),
            {
                "led_obyvak_input_1_press_1x",
                "led_obyvak_input_1_press_2x",
                "led_obyvak_input_1_press_3x",
                "led_obyvak_input_1_hold",
                "led_obyvak_input_1_release",
            },
        )

        press_1x = by_key[
            "led_obyvak_input_1_press_1x"
        ]
        press_2x = by_key[
            "led_obyvak_input_1_press_2x"
        ]
        press_3x = by_key[
            "led_obyvak_input_1_press_3x"
        ]
        hold = by_key[
            "led_obyvak_input_1_hold"
        ]
        release = by_key[
            "led_obyvak_input_1_release"
        ]

        self.assertEqual(
            press_1x["kind"],
            "pulse",
        )

        self.assertEqual(
            press_1x["trigger"]["args"],
            {
                "input": "1",
                "scene": "Key Pressed 1 time",
            },
        )

        self.assertEqual(
            press_2x["trigger"]["args"]["scene"],
            "Key Pressed 2 times",
        )

        self.assertEqual(
            press_3x["trigger"]["args"]["scene"],
            "Key Pressed 3 times",
        )

        self.assertEqual(
            hold["trigger"]["args"]["scene"],
            "Key Held Down",
        )

        self.assertEqual(
            release["trigger"]["args"]["scene"],
            "Key Released",
        )

        self.assertTrue(
            press_1x["trigger"]["card_id"].endswith(
                ":FGRGBWM-442:scene"
            )
        )

    def test_shelly_rgbw_input_1_becomes_events(self) -> None:
        profile = self.profile("LED Koupelna")

        self.assertEqual(
            len(profile["events"]),
            4,
        )

        by_key = {
            event["key"]: event
            for event in profile["events"]
        }

        self.assertEqual(
            set(by_key),
            {
                "led_koupelna_input_1_press_1x",
                "led_koupelna_input_1_press_2x",
                "led_koupelna_input_1_press_3x",
                "led_koupelna_input_1_hold",
            },
        )

        press_1x = by_key[
            "led_koupelna_input_1_press_1x"
        ]
        press_2x = by_key[
            "led_koupelna_input_1_press_2x"
        ]
        press_3x = by_key[
            "led_koupelna_input_1_press_3x"
        ]
        hold = by_key[
            "led_koupelna_input_1_hold"
        ]

        self.assertEqual(
            press_1x["trigger"]["args"],
            {
                "action": {
                    "id": 0,
                    "name": "Single Push 1",
                    "action": "single_push_1",
                },
            },
        )

        self.assertEqual(
            press_2x["trigger"]["args"]["action"],
            {
                "id": 2,
                "name": "Double Push 1",
                "action": "double_push_1",
            },
        )

        self.assertEqual(
            press_3x["trigger"]["args"]["action"],
            {
                "id": 3,
                "name": "Triple Push 1",
                "action": "triple_push_1",
            },
        )

        self.assertEqual(
            hold["trigger"]["args"]["action"],
            {
                "id": 1,
                "name": "Long Push 1",
                "action": "long_push_1",
            },
        )

        self.assertTrue(
            press_1x["trigger"]["card_id"].endswith(
                ":triggerActionEvent"
            )
        )

    def test_all_profile_targets_exist_and_are_setable(self) -> None:
        for device in self.devices:
            capabilities = device["capabilities"]
            profile = device["loxbridge"]

            for command in profile["commands"]:
                for capability_id in command["targets"].values():
                    with self.subTest(
                        device=device["name"],
                        command=command["key"],
                        capability=capability_id,
                    ):
                        self.assertIn(
                            capability_id,
                            capabilities,
                        )
                        self.assertTrue(
                            capabilities[
                                capability_id
                            ]["setable"]
                        )

            for normalized in profile["inputs"]:
                source = normalized[
                    "source_capability"
                ]

                with self.subTest(
                    device=device["name"],
                    source=source,
                ):
                    self.assertIn(
                        source,
                        capabilities,
                    )

            for event in profile.get(
                "events",
                [],
            ):
                with self.subTest(
                    device=device["name"],
                    event=event["key"],
                ):
                    self.assertEqual(
                        event["kind"],
                        "pulse",
                    )
                    self.assertIn(
                        "card_id",
                        event["trigger"],
                    )
                    self.assertIsInstance(
                        event["trigger"].get(
                            "args"
                        ),
                        dict,
                    )

    def test_ac_profile(self) -> None:
        profile = self.profile("AC Obývák")

        self.assertEqual(
            profile["profile"],
            "climate.ac",
        )


if __name__ == "__main__":
    unittest.main()
