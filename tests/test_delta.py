from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from loxbridge.addon.delta import (
    compare_states,
    input_state_from_xml,
    output_state_from_xml,
)


class DeltaTests(unittest.TestCase):

    def test_identical_states_are_unchanged(
        self,
    ) -> None:
        baseline = {
            "led_obyvak_onoff": {
                "Analog": "true",
                "Check": "led_obyvak_onoff=\\v",
            },
        }

        current = {
            "led_obyvak_onoff": {
                "Check": "led_obyvak_onoff=\\v",
                "Analog": "true",
            },
        }

        result = compare_states(
            baseline,
            current,
        )

        self.assertEqual(
            result.added,
            (),
        )
        self.assertEqual(
            result.removed,
            (),
        )
        self.assertEqual(
            result.changed,
            (),
        )
        self.assertEqual(
            result.unchanged,
            ("led_obyvak_onoff",),
        )
        self.assertFalse(
            result.has_changes
        )

    def test_detects_added_command(
        self,
    ) -> None:
        baseline = {}

        current = {
            "zasuvka_garaz_onoff": {
                "Check": (
                    "zasuvka_garaz_onoff=\\v"
                ),
            },
        }

        result = compare_states(
            baseline,
            current,
        )

        self.assertEqual(
            result.added,
            ("zasuvka_garaz_onoff",),
        )
        self.assertTrue(
            result.has_changes
        )

    def test_detects_removed_command(
        self,
    ) -> None:
        baseline = {
            "stara_zasuvka_onoff": {
                "Check": (
                    "stara_zasuvka_onoff=\\v"
                ),
            },
        }

        current = {}

        result = compare_states(
            baseline,
            current,
        )

        self.assertEqual(
            result.removed,
            ("stara_zasuvka_onoff",),
        )
        self.assertTrue(
            result.has_changes
        )

    def test_detects_changed_command(
        self,
    ) -> None:
        baseline = {
            "teplota_obyvak": {
                "Analog": "true",
                "Unit": "°C",
            },
        }

        current = {
            "teplota_obyvak": {
                "Analog": "true",
                "Unit": "K",
            },
        }

        result = compare_states(
            baseline,
            current,
        )

        self.assertEqual(
            len(result.changed),
            1,
        )

        change = result.changed[0]

        self.assertEqual(
            change.key,
            "teplota_obyvak",
        )
        self.assertEqual(
            change.before["Unit"],
            "°C",
        )
        self.assertEqual(
            change.after["Unit"],
            "K",
        )
        self.assertTrue(
            result.has_changes
        )

    def test_reads_input_state_from_xml(
        self,
    ) -> None:
        root = ET.fromstring(
            """
            <VirtualInUdp>
                <VirtualInUdpCmd
                    Title="LED Obývák"
                    Check="led_obyvak_onoff=\\v"
                    Analog="true"
                />
                <VirtualInUdpCmd
                    Title="LED Obývák - Press 1x"
                    Check="led_obyvak_input_1_press_1x=\\v"
                    Analog="false"
                />
            </VirtualInUdp>
            """
        )

        state = input_state_from_xml(
            root
        )

        self.assertEqual(
            set(state),
            {
                "led_obyvak_onoff",
                "led_obyvak_input_1_press_1x",
            },
        )

        self.assertEqual(
            state[
                "led_obyvak_onoff"
            ]["Analog"],
            "true",
        )

        self.assertEqual(
            state[
                "led_obyvak_input_1_press_1x"
            ]["Analog"],
            "false",
        )

    def test_reads_boolean_output_state_from_xml(
        self,
    ) -> None:
        root = ET.fromstring(
            """
            <VirtualOut>
                <VirtualOutCmd
                    Title="LED Obývák"
                    CmdOn="led_obyvak_onoff=1"
                    CmdOff="led_obyvak_onoff=0"
                    Analog="false"
                />
            </VirtualOut>
            """
        )

        state = output_state_from_xml(
            root
        )

        self.assertEqual(
            set(state),
            {
                "led_obyvak_onoff",
            },
        )

        self.assertEqual(
            state[
                "led_obyvak_onoff"
            ]["CmdOn"],
            "led_obyvak_onoff=1",
        )

        self.assertEqual(
            state[
                "led_obyvak_onoff"
            ]["CmdOff"],
            "led_obyvak_onoff=0",
        )

    def test_reads_analog_output_state_from_xml(
        self,
    ) -> None:
        root = ET.fromstring(
            """
            <VirtualOut>
                <VirtualOutCmd
                    Title="LED Koupelna - RGB"
                    CmdOn="led_koupelna_rgb=&lt;v.3&gt;"
                    CmdOff=""
                    Analog="true"
                />
            </VirtualOut>
            """
        )

        state = output_state_from_xml(
            root
        )

        self.assertEqual(
            set(state),
            {
                "led_koupelna_rgb",
            },
        )

        self.assertEqual(
            state[
                "led_koupelna_rgb"
            ]["CmdOn"],
            "led_koupelna_rgb=<v.3>",
        )

    def test_duplicate_xml_key_is_rejected(
        self,
    ) -> None:
        root = ET.fromstring(
            """
            <VirtualInUdp>
                <VirtualInUdpCmd
                    Check="led_obyvak_onoff=\\v"
                />
                <VirtualInUdpCmd
                    Check="led_obyvak_onoff=\\v"
                />
            </VirtualInUdp>
            """
        )

        with self.assertRaises(
            RuntimeError
        ):
            input_state_from_xml(
                root
            )


if __name__ == "__main__":
    unittest.main()