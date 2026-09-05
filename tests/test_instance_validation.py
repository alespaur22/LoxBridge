from __future__ import annotations

import copy
import unittest
from pathlib import Path

from loxbridge.instance_builder import build_instance_preview
from loxbridge.instance_validation import (
    SaveMode,
    validate_device_instance,
)
from loxbridge.templates import load_template


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_TEMPLATE_PATH = (
    ROOT / "config" / "templates" / "xiaomi_mi.plug_maeu01.yaml"
)


def _second_xiaomi_plug_device() -> dict:
    return {
        "id": "c2b1a000-1111-2222-3333-444455556666",
        "name": "Xiaomi Zásuvka Mraznička",
        "zone_name": "Sklep",
        "class": "socket",
        "driver_id": "homey:app:com.xiaomi-mi:plug.maeu01",
        "available": True,
        "capabilities": [
            {
                "id": "onoff",
                "type": "boolean",
                "getable": True,
                "setable": True,
            },
            {
                "id": "measure_power",
                "type": "number",
                "getable": True,
                "setable": False,
            },
            {
                "id": "meter_power",
                "type": "number",
                "getable": True,
                "setable": False,
            },
        ],
    }


def _unrelated_device() -> dict:
    return {
        "id": "unrelated-device-id",
        "name": "Unrelated",
        "driver_id": "homey:app:com.fibaro:FGS-223",
        "capabilities": [
            {
                "id": "onoff",
                "type": "boolean",
                "getable": True,
                "setable": True,
            }
        ],
    }


class ValidateDeviceInstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = load_template(SAMPLE_TEMPLATE_PATH)

    def _valid_preview(self):
        return build_instance_preview(
            homey_device=_second_xiaomi_plug_device(),
            template=self.template,
            instance_name="Mraznička",
            loxone_name_base="Mraznička",
        )

    def test_freshly_built_preview_is_valid_for_create(
        self,
    ) -> None:
        preview = self._valid_preview()

        result = validate_device_instance(
            preview.instance,
            homey_device=_second_xiaomi_plug_device(),
            template=self.template,
            existing_instances={},
            mode=SaveMode.CREATE,
        )

        self.assertTrue(result.is_valid, result.problems)
        self.assertEqual(result.problems, ())

    def test_missing_homey_id(self) -> None:
        instance = self._valid_preview().instance
        instance["homey_id"] = ""

        result = validate_device_instance(
            instance,
            homey_device=None,
            template=None,
            existing_instances={},
            mode=SaveMode.CREATE,
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(
            result.errors()[0].code, "missing_homey_id"
        )

    def test_malformed_shape_missing_category(self) -> None:
        instance = self._valid_preview().instance
        del instance["keys"]["events"]

        result = validate_device_instance(
            instance,
            homey_device=None,
            template=None,
            existing_instances={},
            mode=SaveMode.CREATE,
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(
                p.code == "malformed_shape"
                for p in result.errors()
            )
        )

    def test_keys_and_display_names_must_cover_same_capabilities(
        self,
    ) -> None:
        instance = self._valid_preview().instance
        del instance["display_names"]["capabilities"][
            "onoff"
        ]

        result = validate_device_instance(
            instance,
            homey_device=None,
            template=None,
            existing_instances={},
            mode=SaveMode.CREATE,
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(
                p.code == "malformed_shape"
                for p in result.errors()
            )
        )

    def test_dangling_role_binding_is_malformed(self) -> None:
        instance = self._valid_preview().instance
        instance["role_bindings"]["capabilities"][
            "nonexistent_capability"
        ] = "some_role"

        result = validate_device_instance(
            instance,
            homey_device=None,
            template=None,
            existing_instances={},
            mode=SaveMode.CREATE,
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(
                p.code == "malformed_shape"
                for p in result.errors()
            )
        )

    def test_invalid_key_format(self) -> None:
        instance = self._valid_preview().instance
        instance["keys"]["capabilities"]["onoff"] = (
            "Not Valid Key!"
        )

        result = validate_device_instance(
            instance,
            homey_device=None,
            template=None,
            existing_instances={},
            mode=SaveMode.CREATE,
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(
                p.code == "invalid_key_format"
                for p in result.errors()
            )
        )

    def test_key_collision_within_instance(self) -> None:
        instance = self._valid_preview().instance
        instance["keys"]["capabilities"]["measure_power"] = (
            instance["keys"]["capabilities"]["onoff"]
        )

        result = validate_device_instance(
            instance,
            homey_device=None,
            template=None,
            existing_instances={},
            mode=SaveMode.CREATE,
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(
                p.code == "key_collision_within_instance"
                for p in result.errors()
            )
        )

    def test_identity_leak(self) -> None:
        instance = self._valid_preview().instance
        instance["keys"]["capabilities"]["onoff"] = (
            f"leak_{instance['homey_id']}"
        )

        result = validate_device_instance(
            instance,
            homey_device=None,
            template=None,
            existing_instances={},
            mode=SaveMode.CREATE,
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(
                p.code == "identity_leak"
                for p in result.errors()
            )
        )

    def test_homey_device_mismatch(self) -> None:
        instance = self._valid_preview().instance

        result = validate_device_instance(
            instance,
            homey_device=_unrelated_device(),
            template=None,
            existing_instances={},
            mode=SaveMode.CREATE,
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(
                p.code == "homey_device_mismatch"
                for p in result.errors()
            )
        )

    def test_unknown_capability_not_on_device(self) -> None:
        instance = self._valid_preview().instance
        device = _second_xiaomi_plug_device()
        device["capabilities"] = [
            c
            for c in device["capabilities"]
            if c["id"] != "meter_power"
        ]

        result = validate_device_instance(
            instance,
            homey_device=device,
            template=None,
            existing_instances={},
            mode=SaveMode.CREATE,
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(
                p.code == "unknown_capability"
                for p in result.errors()
            )
        )

    def test_template_reference_mismatch(self) -> None:
        instance = self._valid_preview().instance
        wrong_template = copy.deepcopy(self.template)
        wrong_template["template_id"] = "some.other_template"

        result = validate_device_instance(
            instance,
            homey_device=_second_xiaomi_plug_device(),
            template=wrong_template,
            existing_instances={},
            mode=SaveMode.CREATE,
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(
                p.code == "template_reference_mismatch"
                for p in result.errors()
            )
        )

    def test_template_mismatch_when_device_does_not_match(
        self,
    ) -> None:
        instance = self._valid_preview().instance
        # Instance says it's this template, but the homey_device we
        # pass in doesn't actually match it (wrong driver_id).
        device = _unrelated_device()
        device["id"] = instance["homey_id"]

        result = validate_device_instance(
            instance,
            homey_device=device,
            template=self.template,
            existing_instances={},
            mode=SaveMode.CREATE,
        )

        self.assertFalse(result.is_valid)
        codes = {p.code for p in result.errors()}
        self.assertIn("template_mismatch", codes)

    def test_unmapped_template_capability_is_warning_not_error(
        self,
    ) -> None:
        device = _second_xiaomi_plug_device()
        # Build preview from a device missing meter_power, so the
        # resulting instance legitimately doesn't map it.
        device_without_meter = copy.deepcopy(device)
        device_without_meter["capabilities"] = [
            c
            for c in device_without_meter["capabilities"]
            if c["id"] != "meter_power"
        ]

        preview = build_instance_preview(
            homey_device=device_without_meter,
            template=self.template,
            instance_name="Mraznička",
            loxone_name_base="Mraznička",
        )

        # Now validate against a device that DOES have meter_power -
        # e.g. a firmware update added it after the instance was
        # created.
        result = validate_device_instance(
            preview.instance,
            homey_device=device,
            template=self.template,
            existing_instances={},
            mode=SaveMode.CREATE,
        )

        self.assertTrue(result.is_valid, result.errors())
        warning_codes = {
            p.code for p in result.warnings()
        }
        self.assertIn(
            "unmapped_template_capability", warning_codes
        )

    def test_duplicate_homey_id_blocks_create(self) -> None:
        preview = self._valid_preview()

        result = validate_device_instance(
            preview.instance,
            homey_device=_second_xiaomi_plug_device(),
            template=self.template,
            existing_instances={
                preview.instance["homey_id"]: (
                    preview.instance
                )
            },
            mode=SaveMode.CREATE,
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(
                p.code == "duplicate_homey_id"
                for p in result.errors()
            )
        )

    def test_instance_not_found_blocks_replace(self) -> None:
        preview = self._valid_preview()

        result = validate_device_instance(
            preview.instance,
            homey_device=_second_xiaomi_plug_device(),
            template=self.template,
            existing_instances={},
            mode=SaveMode.REPLACE,
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(
                p.code == "instance_not_found"
                for p in result.errors()
            )
        )

    def test_replace_of_self_is_not_a_collision(self) -> None:
        preview = self._valid_preview()

        result = validate_device_instance(
            preview.instance,
            homey_device=_second_xiaomi_plug_device(),
            template=self.template,
            existing_instances={
                preview.instance["homey_id"]: (
                    preview.instance
                )
            },
            mode=SaveMode.REPLACE,
        )

        self.assertTrue(result.is_valid, result.problems)

    def test_key_collision_with_other_instance(self) -> None:
        preview = self._valid_preview()

        other_instance = copy.deepcopy(preview.instance)
        other_instance["homey_id"] = "some-other-homey-id"
        other_instance["instance_id"] = "some-other-homey-id"

        result = validate_device_instance(
            preview.instance,
            homey_device=_second_xiaomi_plug_device(),
            template=self.template,
            existing_instances={
                "some-other-homey-id": other_instance
            },
            mode=SaveMode.CREATE,
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(
                p.code
                == "key_collision_with_other_instance"
                for p in result.errors()
            )
        )

    def test_validate_does_not_mutate_inputs(self) -> None:
        preview = self._valid_preview()
        device = _second_xiaomi_plug_device()
        template = copy.deepcopy(self.template)
        existing = {}

        instance_before = copy.deepcopy(preview.instance)
        device_before = copy.deepcopy(device)
        template_before = copy.deepcopy(template)

        validate_device_instance(
            preview.instance,
            homey_device=device,
            template=template,
            existing_instances=existing,
            mode=SaveMode.CREATE,
        )

        self.assertEqual(preview.instance, instance_before)
        self.assertEqual(device, device_before)
        self.assertEqual(template, template_before)
        self.assertEqual(existing, {})


if __name__ == "__main__":
    unittest.main()
