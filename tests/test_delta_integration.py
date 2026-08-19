from __future__ import annotations

import unittest

from loxbridge.addon.delta import (
    input_state_from_xml,
    output_state_from_xml,
)
from loxbridge.addon.udp_output_xml_generator import (
    DEFAULT_IP,
    DEFAULT_PORT,
    create_root,
    generate_commands,
)
from loxbridge.addon.udp_xml_generator import (
    DEFAULT_CONFIG_PATH,
    generate_xml,
    load_config,
)


class DeltaIntegrationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(
            DEFAULT_CONFIG_PATH
        )

    def test_real_normal_input_xml_can_be_read(
        self,
    ) -> None:
        root, stats = generate_xml(
            self.config,
            mode="normal",
        )

        state = input_state_from_xml(
            root
        )

        self.assertEqual(
            len(state),
            stats["generated"],
        )

        self.assertEqual(
            len(state),
            299,
        )

        self.assertIn(
            "led_koupelna_input_1_press_1x",
            state,
        )

        self.assertIn(
            "led_obyvak_input_1_press_2x",
            state,
        )

        self.assertNotIn(
            "led_obyvak_input_2_press_1x",
            state,
        )

        self.assertEqual(
            state[
                "led_koupelna_input_1_press_1x"
            ]["Analog"],
            "false",
        )

    def test_real_output_xml_can_be_read(
        self,
    ) -> None:
        root = create_root(
            ip=DEFAULT_IP,
            port=DEFAULT_PORT,
            title="LoxBridge - Homey Outputs",
        )

        stats = generate_commands(
            root=root,
            config=self.config,
        )

        state = output_state_from_xml(
            root
        )

        self.assertEqual(
            len(state),
            stats["generated"],
        )

        self.assertEqual(
            len(state),
            163,
        )

        self.assertIn(
            "led_koupelna_rgb",
            state,
        )

        self.assertIn(
            "led_koupelna_white",
            state,
        )

        self.assertEqual(
            state[
                "led_koupelna_rgb"
            ]["CmdOn"],
            "led_koupelna_rgb=<v.3>",
        )


if __name__ == "__main__":
    unittest.main()