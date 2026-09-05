from __future__ import annotations

import copy
import unittest
from pathlib import Path

from loxbridge.instance_builder import build_instance_preview
from loxbridge.templates import load_template


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_TEMPLATE_PATH = (
    ROOT / "config" / "templates" / "xiaomi_mi.plug_maeu01.yaml"
)


def _second_xiaomi_plug_device() -> dict:
    """Syntetické druhé zařízení stejného modelu - reálný export má
    jen jedno (Bazénová filtrace), takže tohle je jasně vymyšlené,
    ale se stejným driver_id a stejnou reálnou capability signaturou."""
    return {
        "id": "c2b1a000-1111-2222-3333-444455556666",
        "name": "Xiaomi Zásuvka Mraznička",
        "zone_id": "zone-1",
        "zone_name": "Sklep",
        "class": "socket",
        "driver_id": "homey:app:com.xiaomi-mi:plug.maeu01",
        "available": True,
        "capabilities": [
            {
                "id": "onoff",
                "title": "Turned on",
                "type": "boolean",
                "getable": True,
                "setable": True,
            },
            {
                "id": "measure_power",
                "title": "Power",
                "type": "number",
                "getable": True,
                "setable": False,
                "units": "W",
            },
            {
                "id": "meter_power",
                "title": "Energy",
                "type": "number",
                "getable": True,
                "setable": False,
                "units": "kWh",
            },
        ],
    }


class BuildInstancePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = load_template(SAMPLE_TEMPLATE_PATH)

    def test_build_is_pure_and_does_not_mutate_inputs(
        self,
    ) -> None:
        device = _second_xiaomi_plug_device()
        template = copy.deepcopy(self.template)

        device_before = copy.deepcopy(device)
        template_before = copy.deepcopy(template)

        build_instance_preview(
            homey_device=device,
            template=template,
            instance_name="Mraznička",
            loxone_name_base="Mraznička",
        )

        self.assertEqual(device, device_before)
        self.assertEqual(template, template_before)

    def test_identity_fields(self) -> None:
        device = _second_xiaomi_plug_device()

        preview = build_instance_preview(
            homey_device=device,
            template=self.template,
            instance_name="Mraznička",
            loxone_name_base="Mraznička",
        )

        instance = preview.instance

        self.assertEqual(
            instance["homey_id"],
            "c2b1a000-1111-2222-3333-444455556666",
        )
        self.assertEqual(
            instance["instance_id"], instance["homey_id"]
        )
        self.assertEqual(
            instance["homey_name_last_seen"],
            "Xiaomi Zásuvka Mraznička",
        )
        self.assertEqual(
            instance["instance_name"], "Mraznička"
        )
        self.assertEqual(
            instance["loxone_name_base"], "Mraznička"
        )
        self.assertEqual(instance["key_base"], "mraznicka")
        self.assertTrue(instance["enabled"])
        self.assertEqual(
            instance["template"], "xiaomi_mi.plug_maeu01"
        )
        self.assertEqual(instance["template_version"], 1)
        self.assertIsNone(instance["legacy_profile"])
        self.assertEqual(
            instance["homey_meta"]["driver_id"],
            "homey:app:com.xiaomi-mi:plug.maeu01",
        )

    def test_role_bindings_keys_and_display_names(
        self,
    ) -> None:
        device = _second_xiaomi_plug_device()

        preview = build_instance_preview(
            homey_device=device,
            template=self.template,
            instance_name="Mraznička",
            loxone_name_base="Mraznička",
        )

        instance = preview.instance

        self.assertEqual(
            instance["role_bindings"]["capabilities"],
            {
                "onoff": "power",
                "measure_power": "power_now",
                "meter_power": "energy_total",
            },
        )
        self.assertEqual(
            instance["keys"]["capabilities"],
            {
                "onoff": "mraznicka_power",
                "measure_power": "mraznicka_power_now",
                "meter_power": "mraznicka_energy_total",
            },
        )
        self.assertEqual(
            instance["display_names"]["capabilities"],
            {
                "onoff": "Mraznička - Zapnutí",
                "measure_power": (
                    "Mraznička - Aktuální výkon"
                ),
                "meter_power": "Mraznička - Energie",
            },
        )
        self.assertEqual(
            instance["keys"]["commands"], {}
        )
        self.assertEqual(instance["keys"]["events"], {})
        self.assertEqual(preview.unmapped_template_capabilities, ())

    def test_explicit_key_base_overrides_slugified_name(
        self,
    ) -> None:
        device = _second_xiaomi_plug_device()

        preview = build_instance_preview(
            homey_device=device,
            template=self.template,
            instance_name="Mraznička",
            loxone_name_base="Mraznička",
            key_base="freezer",
        )

        self.assertEqual(
            preview.instance["key_base"], "freezer"
        )
        self.assertEqual(
            preview.instance["keys"]["capabilities"][
                "onoff"
            ],
            "freezer_power",
        )

    def test_missing_device_capability_is_reported_as_unmapped(
        self,
    ) -> None:
        device = _second_xiaomi_plug_device()
        device["capabilities"] = [
            capability
            for capability in device["capabilities"]
            if capability["id"] != "meter_power"
        ]

        preview = build_instance_preview(
            homey_device=device,
            template=self.template,
            instance_name="Mraznička",
            loxone_name_base="Mraznička",
        )

        self.assertEqual(
            preview.unmapped_template_capabilities,
            ("meter_power",),
        )
        self.assertNotIn(
            "meter_power",
            preview.instance["keys"]["capabilities"],
        )

    def test_ungetable_capability_is_treated_as_unmapped(
        self,
    ) -> None:
        device = _second_xiaomi_plug_device()

        for capability in device["capabilities"]:
            if capability["id"] == "measure_power":
                capability["getable"] = False

        preview = build_instance_preview(
            homey_device=device,
            template=self.template,
            instance_name="Mraznička",
            loxone_name_base="Mraznička",
        )

        self.assertIn(
            "measure_power",
            preview.unmapped_template_capabilities,
        )

    def test_missing_homey_device_id_raises(self) -> None:
        device = _second_xiaomi_plug_device()
        device["id"] = ""

        with self.assertRaises(ValueError):
            build_instance_preview(
                homey_device=device,
                template=self.template,
                instance_name="Mraznička",
                loxone_name_base="Mraznička",
            )


if __name__ == "__main__":
    unittest.main()
