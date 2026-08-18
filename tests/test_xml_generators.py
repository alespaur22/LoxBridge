from __future__ import annotations

import json
import unittest
from pathlib import Path

from loxbridge.addon.udp_output_xml_generator import (
    create_root as create_output_root,
    generate_commands,
)
from loxbridge.addon.udp_xml_generator import generate_xml
from loxbridge.generate import build_generated_config


ROOT = Path(__file__).resolve().parents[1]
EXPORT_PATH = ROOT / "exports" / "homey_devices.json"


class XmlGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        export_data = json.loads(
            EXPORT_PATH.read_text(encoding="utf-8")
        )

        cls.config, _ = build_generated_config(
            current_config={
                "homey": {
                    "ip": "192.0.2.10",
                    "token": "test-token",
                },
                "loxone": {
                    "ip": "192.0.2.20",
                    "port": 7001,
                },
            },
            export_data=export_data,
        )

    def test_output_generator_keeps_known_counts(self) -> None:
        root = create_output_root(
            "192.0.2.30",
            7002,
            "LoxBridge - Homey Outputs",
        )

        stats = generate_commands(
            root,
            self.config,
        )

        self.assertEqual(
            stats["generated"],
            163,
        )
        self.assertEqual(
            stats["synthetic_rgb"],
            4,
        )
        self.assertEqual(
            stats["synthetic_lumitech"],
            13,
        )
        self.assertEqual(
            stats["synthetic_dimmer"],
            3,
        )
        self.assertEqual(
            stats["synthetic_white"],
            1,
        )

        commands = root.findall(
            "VirtualOutCmd"
        )

        by_title = {
            command.get("Title"): command
            for command in commands
        }

        self.assertEqual(
            by_title[
                "LED Koupelna - White"
            ].get("CmdOn"),
            "led_koupelna_white=<v.3>",
        )

    def test_normal_inputs_replace_fibaro_voltage_with_events(
        self,
    ) -> None:
        root, stats = generate_xml(
            self.config,
            mode="normal",
        )

        self.assertEqual(
            root.get("Title"),
            "LoxBridge - Homey Inputs",
        )
        self.assertEqual(
            root.get("Port"),
            "7001",
        )

        self.assertEqual(
            stats["normalized"],
            0,
        )

        # 4 raw vstupy LED Obývák +
        # 4 raw vstupy LED Postel.
        self.assertEqual(
            stats["replaced_raw"],
            8,
        )

        # Fibaro Obývák 5
        # + Fibaro Postel 5
        # + Shelly Koupelna 4.
        self.assertEqual(
            stats["events"],
            14,
        )

        self.assertEqual(
            stats["generated"],
            287,
        )

        commands = root.findall(
            "VirtualInUdpCmd"
        )

        by_check = {
            command.get("Check"): command
            for command in commands
        }

        fibaro_press = by_check[
            "led_obyvak_input_1_press_2x=\\v"
        ]

        self.assertEqual(
            fibaro_press.get("Analog"),
            "false",
        )

        self.assertNotIn(
            "led_obyvak_measure_voltage_input1=\\v",
            by_check,
        )

        # Nepoužívané Fibaro Inputy 2-4
        # se už jako eventy negenerují.
        self.assertNotIn(
            "led_obyvak_input_2_press_1x=\\v",
            by_check,
        )

        self.assertNotIn(
            "led_postel_input_4_release=\\v",
            by_check,
        )

        # Shelly RGBW Koupelna / Input 1.
        shelly_press = by_check[
            "led_koupelna_input_1_press_1x=\\v"
        ]

        self.assertEqual(
            shelly_press.get("Analog"),
            "false",
        )

        self.assertIn(
            "led_koupelna_input_1_press_2x=\\v",
            by_check,
        )

        self.assertIn(
            "led_koupelna_input_1_press_3x=\\v",
            by_check,
        )

        self.assertIn(
            "led_koupelna_input_1_hold=\\v",
            by_check,
        )

    def test_raw_inputs_keep_original_fibaro_voltage(
        self,
    ) -> None:
        root, stats = generate_xml(
            self.config,
            mode="raw",
        )

        self.assertEqual(
            stats["normalized"],
            0,
        )

        checks = {
            command.get("Check")
            for command in root.findall(
                "VirtualInUdpCmd"
            )
        }

        self.assertIn(
            "led_obyvak_measure_voltage_input1=\\v",
            checks,
        )

        self.assertIn(
            "led_obyvak_measure_voltage_input4=\\v",
            checks,
        )

        self.assertNotIn(
            "led_obyvak_input_1_press_2x=\\v",
            checks,
        )

        self.assertNotIn(
            "led_koupelna_input_1_press_1x=\\v",
            checks,
        )


if __name__ == "__main__":
    unittest.main()
