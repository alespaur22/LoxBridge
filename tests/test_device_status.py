from __future__ import annotations

import copy
import dataclasses
import json
import unittest
from pathlib import Path

from loxbridge.capability_filter import (
    should_include_capability,
)
from loxbridge.device_status import (
    DeviceStatus,
    DeviceStatusEntry,
    DeviceStatusReport,
    compute_device_status_report,
)


ROOT = Path(__file__).resolve().parents[1]
EXPORT_PATH = ROOT / "exports" / "homey_devices.json"


def _export_device(
    homey_id: str,
    name: str,
    available: bool = True,
    **extra,
) -> dict:
    return {
        "id": homey_id,
        "name": name,
        "class": "sensor",
        "driver_id": "homey:app:test:driver",
        "available": available,
        **extra,
    }


def _instance(
    homey_id: str,
    instance_name: str,
    enabled: bool = True,
) -> dict:
    return {
        "homey_id": homey_id,
        "instance_id": homey_id,
        "instance_name": instance_name,
        "enabled": enabled,
        "keys": {"capabilities": {}, "commands": {}, "events": {}},
        "display_names": {
            "capabilities": {},
            "commands": {},
            "events": {},
        },
    }


class StatusClassificationTests(unittest.TestCase):
    def test_configured_when_in_export_and_has_instance(self) -> None:
        export_data = {
            "devices": [_export_device("a", "Bojler")]
        }
        instances = {"a": _instance("a", "Bojler")}

        report = compute_device_status_report(
            export_data, instances
        )

        self.assertEqual(len(report.entries), 1)
        entry = report.entries[0]
        self.assertEqual(entry.status, DeviceStatus.CONFIGURED)
        self.assertEqual(entry.homey_name, "Bojler")
        self.assertEqual(entry.instance_name, "Bojler")

    def test_new_when_in_export_without_instance(self) -> None:
        export_data = {
            "devices": [_export_device("a", "Nový senzor")]
        }

        report = compute_device_status_report(export_data, {})

        entry = report.entries[0]
        self.assertEqual(entry.status, DeviceStatus.NEW)
        self.assertEqual(entry.homey_name, "Nový senzor")
        self.assertIsNone(entry.instance_name)
        self.assertIsNone(entry.instance_enabled)

    def test_missing_when_instance_has_no_export_entry(self) -> None:
        instances = {"a": _instance("a", "Starý senzor")}

        report = compute_device_status_report(
            {"devices": []}, instances
        )

        entry = report.entries[0]
        self.assertEqual(entry.status, DeviceStatus.MISSING)
        self.assertIsNone(entry.homey_name)
        self.assertIsNone(entry.homey_available)
        self.assertEqual(entry.instance_name, "Starý senzor")

    def test_empty_inputs_produce_empty_report(self) -> None:
        report = compute_device_status_report({"devices": []}, {})

        self.assertEqual(report.entries, ())
        self.assertEqual(report.instance_count, 0)
        self.assertEqual(report.actual_device_count, 0)


class IndependentAxesTests(unittest.TestCase):
    """homey_available a instance_enabled jsou nezávislé na status a
    na sobě navzájem - žádná kombinace nesmí vyrobit jiný status."""

    def test_configured_available_and_enabled(self) -> None:
        export_data = {
            "devices": [
                _export_device("a", "X", available=True)
            ]
        }
        instances = {"a": _instance("a", "X", enabled=True)}

        entry = compute_device_status_report(
            export_data, instances
        ).entries[0]

        self.assertEqual(entry.status, DeviceStatus.CONFIGURED)
        self.assertTrue(entry.homey_available)
        self.assertTrue(entry.instance_enabled)

    def test_configured_offline_but_enabled(self) -> None:
        export_data = {
            "devices": [
                _export_device("a", "X", available=False)
            ]
        }
        instances = {"a": _instance("a", "X", enabled=True)}

        entry = compute_device_status_report(
            export_data, instances
        ).entries[0]

        self.assertEqual(entry.status, DeviceStatus.CONFIGURED)
        self.assertFalse(entry.homey_available)
        self.assertTrue(entry.instance_enabled)

    def test_configured_available_but_disabled(self) -> None:
        export_data = {
            "devices": [
                _export_device("a", "X", available=True)
            ]
        }
        instances = {"a": _instance("a", "X", enabled=False)}

        entry = compute_device_status_report(
            export_data, instances
        ).entries[0]

        self.assertEqual(entry.status, DeviceStatus.CONFIGURED)
        self.assertTrue(entry.homey_available)
        self.assertFalse(entry.instance_enabled)

    def test_configured_offline_and_disabled(self) -> None:
        export_data = {
            "devices": [
                _export_device("a", "X", available=False)
            ]
        }
        instances = {"a": _instance("a", "X", enabled=False)}

        entry = compute_device_status_report(
            export_data, instances
        ).entries[0]

        self.assertEqual(entry.status, DeviceStatus.CONFIGURED)
        self.assertFalse(entry.homey_available)
        self.assertFalse(entry.instance_enabled)

    def test_new_device_offline_has_no_instance_fields(self) -> None:
        export_data = {
            "devices": [
                _export_device("a", "X", available=False)
            ]
        }

        entry = compute_device_status_report(
            export_data, {}
        ).entries[0]

        self.assertEqual(entry.status, DeviceStatus.NEW)
        self.assertFalse(entry.homey_available)
        self.assertIsNone(entry.instance_enabled)


class DeterministicOrderTests(unittest.TestCase):
    def test_entries_sorted_by_homey_id_regardless_of_input_order(
        self,
    ) -> None:
        export_data = {
            "devices": [
                _export_device("c-id", "C"),
                _export_device("a-id", "A"),
                _export_device("b-id", "B"),
            ]
        }
        instances = {
            "b-id": _instance("b-id", "B"),
        }

        report = compute_device_status_report(
            export_data, instances
        )

        self.assertEqual(
            [e.homey_id for e in report.entries],
            ["a-id", "b-id", "c-id"],
        )

    def test_order_independent_of_dict_and_list_ordering(
        self,
    ) -> None:
        devices = [
            _export_device("z-id", "Z"),
            _export_device("m-id", "M"),
        ]

        instances_forward = {
            "z-id": _instance("z-id", "Z"),
            "m-id": _instance("m-id", "M"),
        }
        instances_reversed = {
            "m-id": _instance("m-id", "M"),
            "z-id": _instance("z-id", "Z"),
        }

        report_a = compute_device_status_report(
            {"devices": devices}, instances_forward
        )
        report_b = compute_device_status_report(
            {"devices": list(reversed(devices))},
            instances_reversed,
        )

        self.assertEqual(report_a.entries, report_b.entries)


class DeviceCountWarningTests(unittest.TestCase):
    def test_warns_on_exact_mismatch(self) -> None:
        export_data = {
            "device_count": 5,
            "devices": [_export_device("a", "A")],
        }

        report = compute_device_status_report(export_data, {})

        self.assertEqual(len(report.warnings), 1)
        self.assertIn("5", report.warnings[0])
        self.assertIn("1", report.warnings[0])
        self.assertEqual(report.device_count, 5)
        self.assertEqual(report.actual_device_count, 1)

    def test_no_warning_when_count_matches(self) -> None:
        export_data = {
            "device_count": 1,
            "devices": [_export_device("a", "A")],
        }

        report = compute_device_status_report(export_data, {})

        self.assertEqual(report.warnings, ())

    def test_no_warning_when_device_count_field_missing(
        self,
    ) -> None:
        export_data = {"devices": [_export_device("a", "A")]}

        report = compute_device_status_report(export_data, {})

        self.assertEqual(report.warnings, ())
        self.assertIsNone(report.device_count)


class PassthroughMetadataTests(unittest.TestCase):
    def test_reuses_existing_export_field_names_verbatim(
        self,
    ) -> None:
        export_data = {
            "exported_at": "2026-07-25T16:17:06.495Z",
            "homey_ip": "192.168.68.112",
            "device_count": 0,
            "devices": [],
        }

        report = compute_device_status_report(export_data, {})

        self.assertEqual(
            report.exported_at, "2026-07-25T16:17:06.495Z"
        )
        self.assertEqual(report.homey_ip, "192.168.68.112")

    def test_uses_instance_name_field_verbatim(self) -> None:
        export_data = {
            "devices": [_export_device("a", "A")]
        }
        instances = {
            "a": _instance("a", instance_name="Moje jméno")
        }

        entry = compute_device_status_report(
            export_data, instances
        ).entries[0]

        self.assertEqual(entry.instance_name, "Moje jméno")


class PurityTests(unittest.TestCase):
    def test_does_not_mutate_inputs(self) -> None:
        export_data = {
            "devices": [_export_device("a", "A")]
        }
        instances = {"a": _instance("a", "A")}

        export_before = copy.deepcopy(export_data)
        instances_before = copy.deepcopy(instances)

        compute_device_status_report(export_data, instances)

        self.assertEqual(export_data, export_before)
        self.assertEqual(instances, instances_before)


class ImmutabilityTests(unittest.TestCase):
    def test_entry_is_frozen(self) -> None:
        entry = DeviceStatusEntry(
            homey_id="a", status=DeviceStatus.NEW
        )

        with self.assertRaises(dataclasses.FrozenInstanceError):
            entry.homey_id = "b"  # type: ignore[misc]

    def test_report_is_frozen_and_entries_are_tuple(self) -> None:
        report = compute_device_status_report(
            {"devices": []}, {}
        )

        with self.assertRaises(dataclasses.FrozenInstanceError):
            report.instance_count = 5  # type: ignore[misc]

        self.assertIsInstance(report.entries, tuple)
        self.assertIsInstance(report.warnings, tuple)


class RealExportIntegrationTests(unittest.TestCase):
    """Sanity check proti reálnému, do gitu commitnutému fixture
    exports/homey_devices.json - stejný soubor, který používají i
    ostatní testy (tests/test_profiles.py, tests/test_xml_generators.py).
    Instance store je tu čistě lokální, konstruovaný v testu, aby test
    nezávisel na tom, jestli je na stroji reálně namigrovaný
    config/devices/ (ten je gitignored)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.export_data = json.loads(
            EXPORT_PATH.read_text(encoding="utf-8")
        )

    def test_real_export_declared_count_matches_actual(
        self,
    ) -> None:
        # Regresní pojistka na fixture data samotná - pokud by se
        # export v repu poškodil/zkrátil, tenhle test na to upozorní.
        report = compute_device_status_report(
            self.export_data, {}
        )

        self.assertEqual(report.warnings, ())
        self.assertEqual(
            report.device_count, report.actual_device_count
        )

    def test_known_device_reported_as_configured(self) -> None:
        led_obyvak_id = next(
            device["id"]
            for device in self.export_data["devices"]
            if device["name"] == "LED Obývák"
        )

        instances = {
            led_obyvak_id: _instance(
                led_obyvak_id, "LED Obývák"
            )
        }

        report = compute_device_status_report(
            self.export_data, instances
        )

        by_id = {e.homey_id: e for e in report.entries}

        self.assertEqual(
            by_id[led_obyvak_id].status,
            DeviceStatus.CONFIGURED,
        )

    def test_known_device_without_instance_reported_as_new(
        self,
    ) -> None:
        report = compute_device_status_report(
            self.export_data, {}
        )

        by_name = {
            e.homey_name: e for e in report.entries
        }

        self.assertEqual(
            by_name["LED Obývák"].status, DeviceStatus.NEW
        )

    def test_instance_without_matching_export_id_is_missing(
        self,
    ) -> None:
        fake_id = "does-not-exist-in-export"
        instances = {fake_id: _instance(fake_id, "Duch")}

        report = compute_device_status_report(
            self.export_data, instances
        )

        by_id = {e.homey_id: e for e in report.entries}

        self.assertEqual(
            by_id[fake_id].status, DeviceStatus.MISSING
        )


def _qualifying_capability(capability_id: str = "onoff") -> dict:
    return {
        "id": capability_id,
        "type": "boolean",
        "getable": True,
        "setable": True,
    }


def _non_qualifying_capability() -> dict:
    # "button" je v IGNORED_CAPABILITIES - vyloučeno bez ohledu na
    # getable/type.
    return {
        "id": "button",
        "type": "boolean",
        "getable": True,
        "setable": True,
    }


class BridgeableTests(unittest.TestCase):
    def test_true_when_device_has_qualifying_capability(self) -> None:
        export_data = {
            "devices": [
                _export_device(
                    "a",
                    "A",
                    capabilities=[_qualifying_capability()],
                )
            ]
        }

        entry = compute_device_status_report(
            export_data, {}
        ).entries[0]

        self.assertTrue(entry.bridgeable)
        self.assertEqual(entry.bridgeable_capability_count, 1)

    def test_false_when_device_has_no_qualifying_capability(
        self,
    ) -> None:
        export_data = {
            "devices": [
                _export_device(
                    "a",
                    "A",
                    capabilities=[_non_qualifying_capability()],
                )
            ]
        }

        entry = compute_device_status_report(
            export_data, {}
        ).entries[0]

        self.assertFalse(entry.bridgeable)
        self.assertEqual(entry.bridgeable_capability_count, 0)

    def test_false_when_capabilities_field_missing(self) -> None:
        export_data = {"devices": [_export_device("a", "A")]}

        entry = compute_device_status_report(
            export_data, {}
        ).entries[0]

        self.assertFalse(entry.bridgeable)
        self.assertEqual(entry.bridgeable_capability_count, 0)

    def test_none_for_missing_device(self) -> None:
        instances = {"a": _instance("a", "A")}

        entry = compute_device_status_report(
            {"devices": []}, instances
        ).entries[0]

        self.assertIsNone(entry.bridgeable)
        self.assertIsNone(entry.bridgeable_capability_count)

    def test_count_matches_direct_should_include_capability_usage(
        self,
    ) -> None:
        capabilities = [
            _qualifying_capability("onoff"),
            _qualifying_capability("dim"),
            _non_qualifying_capability(),
        ]

        export_data = {
            "devices": [
                _export_device(
                    "a", "A", capabilities=capabilities
                )
            ]
        }

        entry = compute_device_status_report(
            export_data, {}
        ).entries[0]

        expected = sum(
            1
            for capability in capabilities
            if should_include_capability(capability)
        )

        self.assertEqual(
            entry.bridgeable_capability_count, expected
        )
        self.assertEqual(entry.bridgeable, expected > 0)

    def test_bridgeable_is_independent_of_status(self) -> None:
        # Configured zařízení s 0 kvalifikujícími capabilities
        # (např. Homey capabilities se změnily po vytvoření instance)
        # zůstává status=CONFIGURED, jen bridgeable=False.
        export_data = {
            "devices": [
                _export_device("a", "A", capabilities=[])
            ]
        }
        instances = {"a": _instance("a", "A")}

        entry = compute_device_status_report(
            export_data, instances
        ).entries[0]

        self.assertEqual(entry.status, DeviceStatus.CONFIGURED)
        self.assertFalse(entry.bridgeable)


class BridgeableInvariantsOnRealExportTests(unittest.TestCase):
    """Obecné invarianty nad reálným (git-trackovaným) exportem -
    záměrně BEZ natvrdo zakódovaných jmen konkrétních dnešních
    zařízení, protože reálný dataset se může časem změnit."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.export_data = json.loads(
            EXPORT_PATH.read_text(encoding="utf-8")
        )

        # Jedna umělá "missing" instance navíc, aby test pokryl i tuhle
        # větev bez závislosti na lokálním (gitignored) config/devices/.
        cls.fake_missing_id = "does-not-exist-in-export"

        cls.instances = {
            cls.fake_missing_id: _instance(
                cls.fake_missing_id, "Duch"
            )
        }

        cls.report = compute_device_status_report(
            cls.export_data, cls.instances
        )

    def test_every_present_device_has_non_negative_count(
        self,
    ) -> None:
        for entry in self.report.entries:
            if entry.status is DeviceStatus.MISSING:
                continue

            with self.subTest(homey_id=entry.homey_id):
                self.assertIsNotNone(
                    entry.bridgeable_capability_count
                )
                self.assertGreaterEqual(
                    entry.bridgeable_capability_count, 0
                )

    def test_bridgeable_matches_count_positivity(self) -> None:
        for entry in self.report.entries:
            with self.subTest(homey_id=entry.homey_id):
                if entry.bridgeable_capability_count is None:
                    self.assertIsNone(entry.bridgeable)
                else:
                    self.assertEqual(
                        entry.bridgeable,
                        entry.bridgeable_capability_count > 0,
                    )

    def test_missing_entry_has_both_fields_none(self) -> None:
        by_id = {
            entry.homey_id: entry
            for entry in self.report.entries
        }

        missing_entry = by_id[self.fake_missing_id]

        self.assertEqual(
            missing_entry.status, DeviceStatus.MISSING
        )
        self.assertIsNone(missing_entry.bridgeable)
        self.assertIsNone(
            missing_entry.bridgeable_capability_count
        )

    def test_count_matches_direct_should_include_capability_usage(
        self,
    ) -> None:
        export_by_id = {
            device["id"]: device
            for device in self.export_data["devices"]
        }

        for entry in self.report.entries:
            if entry.status is DeviceStatus.MISSING:
                continue

            with self.subTest(homey_id=entry.homey_id):
                raw_capabilities = export_by_id[
                    entry.homey_id
                ].get("capabilities", [])

                expected = sum(
                    1
                    for capability in raw_capabilities
                    if should_include_capability(capability)
                )

                self.assertEqual(
                    entry.bridgeable_capability_count,
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
