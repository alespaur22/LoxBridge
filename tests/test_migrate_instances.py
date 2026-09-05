from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from loxbridge.addon.udp_output_xml_generator import (
    create_root as create_output_root,
    generate_commands,
)
from loxbridge.addon.udp_xml_generator import generate_xml
from loxbridge.generate import build_generated_config
from loxbridge.instances import (
    contains_identity_leak,
    load_all_instances,
)
from loxbridge.migrate_instances import migrate


ROOT = Path(__file__).resolve().parents[1]
EXPORT_PATH = ROOT / "exports" / "homey_devices.json"


def _serialize_root(root: ET.Element) -> str:
    return ET.tostring(root, encoding="unicode")


class MigrateInstancesTests(unittest.TestCase):
    """Migration safety tests.

    These never touch the real config/config.generated.yaml or
    config/devices/ - everything runs against a synthetic config
    (built the same way tests/test_xml_generators.py does: real
    exports/homey_devices.json device data plus fake connection
    credentials) written to a temporary file, and instances are
    written to a temporary directory.
    """

    @classmethod
    def setUpClass(cls) -> None:
        export_data = json.loads(
            EXPORT_PATH.read_text(encoding="utf-8")
        )

        config, _ = build_generated_config(
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

        cls.config = config

        cls.tmp_dir = tempfile.TemporaryDirectory()

        tmp_path = Path(cls.tmp_dir.name)

        cls.source_path = tmp_path / "config.generated.yaml"
        cls.output_dir = tmp_path / "devices"

        with cls.source_path.open(
            "w", encoding="utf-8"
        ) as file:
            yaml.safe_dump(
                config,
                file,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
                width=120,
            )

        cls.source_bytes_before = (
            cls.source_path.read_bytes()
        )

        cls.xml_before = cls._render_xml(config)

        cls.result = migrate(
            cls.source_path,
            cls.output_dir,
        )

        cls.instances = load_all_instances(
            cls.output_dir
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp_dir.cleanup()

    @staticmethod
    def _render_xml(config: dict) -> dict[str, object]:
        input_root, input_stats = generate_xml(
            config, mode="normal"
        )

        output_root = create_output_root(
            "192.0.2.30",
            7002,
            "LoxBridge - Homey Outputs",
        )

        output_stats = generate_commands(
            output_root, config
        )

        return {
            "input_xml": _serialize_root(input_root),
            "input_stats": input_stats,
            "output_xml": _serialize_root(output_root),
            "output_stats": output_stats,
        }

    def by_name(self, name: str) -> dict:
        for device in self.config["devices"]:
            if device["name"] == name:
                return device

        raise AssertionError(f"Fixture device {name!r} not found")

    # -- safety: source file and derived XML are untouched --

    def test_source_config_bytes_unchanged(self) -> None:
        self.assertEqual(
            self.source_path.read_bytes(),
            self.source_bytes_before,
        )

    def test_xml_output_unchanged_after_migration(self) -> None:
        with self.source_path.open(
            "r", encoding="utf-8"
        ) as file:
            reloaded_config = yaml.safe_load(file)

        xml_after = self._render_xml(reloaded_config)

        self.assertEqual(
            xml_after["input_xml"], self.xml_before["input_xml"]
        )
        self.assertEqual(
            xml_after["input_stats"],
            self.xml_before["input_stats"],
        )
        self.assertEqual(
            xml_after["output_xml"],
            self.xml_before["output_xml"],
        )
        self.assertEqual(
            xml_after["output_stats"],
            self.xml_before["output_stats"],
        )

    # -- coverage: every device got migrated --

    def test_every_device_migrated_without_skips(self) -> None:
        self.assertEqual(
            self.result["device_count"],
            len(self.config["devices"]),
        )
        self.assertEqual(self.result["skipped"], [])
        self.assertEqual(
            len(self.result["written"]),
            len(self.config["devices"]),
        )
        self.assertEqual(
            len(self.instances),
            len(self.config["devices"]),
        )

    # -- lossless capture: keys and display names match the source --

    def test_capability_keys_and_names_match_source(self) -> None:
        device = self.by_name("LED Obývák")
        instance = self.instances[device["homey_id"]]

        for capability_id, capability in device[
            "capabilities"
        ].items():
            self.assertEqual(
                instance["keys"]["capabilities"][
                    capability_id
                ],
                capability["key"],
            )
            self.assertEqual(
                instance["display_names"]["capabilities"][
                    capability_id
                ],
                capability["loxone_name"],
            )

    def test_command_keys_and_names_match_source(self) -> None:
        device = self.by_name("LED Obývák")
        instance = self.instances[device["homey_id"]]

        commands = device["loxbridge"]["commands"]

        self.assertTrue(commands)

        for command in commands:
            role = command["kind"]

            self.assertEqual(
                instance["keys"]["commands"][role],
                command["key"],
            )
            self.assertEqual(
                instance["display_names"]["commands"][role],
                command["title"],
            )

    def test_event_keys_and_names_match_source(self) -> None:
        device = self.by_name("LED Koupelna")
        instance = self.instances[device["homey_id"]]

        events = device["loxbridge"]["events"]

        self.assertTrue(events)

        key_base = device["slug"]

        for event in events:
            role = event["key"][len(key_base) + 1:]

            self.assertEqual(
                instance["keys"]["events"][role],
                event["key"],
            )
            self.assertEqual(
                instance["display_names"]["events"][role],
                event["title"],
            )

    def test_identity_fields_match_source(self) -> None:
        device = self.by_name("AC Koupelna 1")
        instance = self.instances[device["homey_id"]]

        self.assertEqual(
            instance["homey_id"], device["homey_id"]
        )
        self.assertEqual(
            instance["key_base"], device["slug"]
        )
        self.assertEqual(
            instance["homey_name_last_seen"], device["name"]
        )
        self.assertEqual(
            instance["loxone_name_base"], device["name"]
        )
        self.assertEqual(
            instance["legacy_profile"],
            device["loxbridge"]["profile"],
        )

    # -- identity leak guard across the whole migrated fixture --

    def test_no_instance_leaks_homey_id_into_visible_values(
        self,
    ) -> None:
        for instance in self.instances.values():
            self.assertFalse(
                contains_identity_leak(instance),
                msg=(
                    "homey_id leaked into a visible key/name "
                    f"for instance {instance['homey_id']}"
                ),
            )


if __name__ == "__main__":
    unittest.main()
