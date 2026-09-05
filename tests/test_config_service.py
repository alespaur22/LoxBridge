from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from loxbridge.config_service import (
    DeviceConfigurationService,
    DeviceNotFoundError,
    InstanceNotFoundError,
    ReadOnlyModeError,
    TemplateNotFoundError,
)
from loxbridge.device_status import DeviceStatus
from loxbridge.instance_builder import (
    CapabilityEdit,
    build_instance_preview,
)
from loxbridge.instance_save import SaveError
from loxbridge.instances import load_all_instances, save_instance
from loxbridge.template_matching import MatchKind
from loxbridge.templates import load_template


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_TEMPLATE_PATH = (
    ROOT / "config" / "templates" / "xiaomi_mi.plug_maeu01.yaml"
)

BOJLER_ID = "aaaaaaaa-0000-0000-0000-000000000001"
NEW_BRIDGEABLE_ID = "bbbbbbbb-0000-0000-0000-000000000002"
NEW_NOT_BRIDGEABLE_ID = "cccccccc-0000-0000-0000-000000000003"
MISSING_ID = "dddddddd-0000-0000-0000-000000000004"


def _xiaomi_capabilities() -> list[dict]:
    return [
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
    ]


class DeviceConfigurationServiceTests(unittest.TestCase):
    """Vše výhradně v dočasném adresáři - žádný test se nikdy nedotkne
    reálného config/devices/."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp_path = Path(self._tmp.name)

        self.export_path = tmp_path / "homey_devices.json"
        self.instances_dir = tmp_path / "devices"
        self.templates_dir = tmp_path / "templates"
        self.instances_dir.mkdir()
        self.templates_dir.mkdir()

        self.template = load_template(SAMPLE_TEMPLATE_PATH)

        with (
            self.templates_dir / "xiaomi_mi.plug_maeu01.yaml"
        ).open("w", encoding="utf-8") as file:
            yaml.safe_dump(self.template, file)

        self.export_data = {
            "exported_at": "2026-09-05T00:00:00.000Z",
            "homey_ip": "192.0.2.10",
            "device_count": 3,
            "devices": [
                {
                    "id": BOJLER_ID,
                    "name": "Bojler",
                    "zone_name": "Sklep",
                    "class": "socket",
                    "driver_id": (
                        "homey:app:com.xiaomi-mi:"
                        "plug.maeu01"
                    ),
                    "available": True,
                    "capabilities": (
                        _xiaomi_capabilities()
                    ),
                },
                {
                    "id": NEW_BRIDGEABLE_ID,
                    "name": "Nová zásuvka",
                    "zone_name": "Kuchyně",
                    "class": "socket",
                    "driver_id": (
                        "homey:app:com.xiaomi-mi:"
                        "plug.maeu01"
                    ),
                    "available": True,
                    "capabilities": (
                        _xiaomi_capabilities()
                    ),
                },
                {
                    "id": NEW_NOT_BRIDGEABLE_ID,
                    "name": "Virtuální režim",
                    "zone_name": None,
                    "class": "other",
                    "driver_id": (
                        "homey:virtualdrivergroup:"
                        "driver"
                    ),
                    "available": True,
                    "capabilities": [],
                },
            ],
        }

        with self.export_path.open(
            "w", encoding="utf-8"
        ) as file:
            json.dump(self.export_data, file)

        self.service = DeviceConfigurationService(
            export_path=self.export_path,
            instances_dir=self.instances_dir,
            templates_dir=self.templates_dir,
        )

        bojler_device = self.export_data["devices"][0]

        self.bojler_preview = build_instance_preview(
            homey_device=bojler_device,
            template=self.template,
            instance_name="Bojler",
            loxone_name_base="Bojler",
        )

        save_instance(
            self.bojler_preview.instance,
            self.instances_dir,
        )

        missing_instance = copy.deepcopy(
            self.bojler_preview.instance
        )
        missing_instance["homey_id"] = MISSING_ID
        missing_instance["instance_id"] = MISSING_ID
        missing_instance["instance_name"] = "Duch"
        missing_instance["key_base"] = "duch"
        missing_instance["keys"]["capabilities"] = {
            "onoff": "duch_power",
            "measure_power": "duch_power_now",
            "meter_power": "duch_energy_total",
        }
        missing_instance["display_names"][
            "capabilities"
        ] = {
            "onoff": "Duch - Zapnutí",
            "measure_power": "Duch - Aktuální výkon",
            "meter_power": "Duch - Energie",
        }
        save_instance(missing_instance, self.instances_dir)

    def _instance_file_hashes(self) -> dict[str, bytes]:
        return {
            path.name: path.read_bytes()
            for path in self.instances_dir.glob("*.yaml")
        }

    # --- list_devices ---

    def test_list_devices_statuses_and_bridgeable(
        self,
    ) -> None:
        by_id = {
            item.homey_id: item
            for item in self.service.list_devices()
        }

        self.assertEqual(
            by_id[BOJLER_ID].status,
            DeviceStatus.CONFIGURED,
        )
        self.assertTrue(by_id[BOJLER_ID].bridgeable)
        self.assertEqual(
            by_id[BOJLER_ID].instance_name, "Bojler"
        )
        self.assertEqual(
            by_id[BOJLER_ID].template_id,
            "xiaomi_mi.plug_maeu01",
        )
        self.assertEqual(
            by_id[BOJLER_ID].template_version, 1
        )
        self.assertEqual(
            by_id[BOJLER_ID].zone_name, "Sklep"
        )

        self.assertEqual(
            by_id[NEW_BRIDGEABLE_ID].status,
            DeviceStatus.NEW,
        )
        self.assertTrue(
            by_id[NEW_BRIDGEABLE_ID].bridgeable
        )
        self.assertIsNone(
            by_id[NEW_BRIDGEABLE_ID].instance_name
        )

        self.assertEqual(
            by_id[NEW_NOT_BRIDGEABLE_ID].status,
            DeviceStatus.NEW,
        )
        self.assertFalse(
            by_id[NEW_NOT_BRIDGEABLE_ID].bridgeable
        )

        self.assertEqual(
            by_id[MISSING_ID].status,
            DeviceStatus.MISSING,
        )
        self.assertIsNone(by_id[MISSING_ID].bridgeable)
        self.assertEqual(
            by_id[MISSING_ID].instance_name, "Duch"
        )

    def test_matching_template_ids_only_for_new_bridgeable(
        self,
    ) -> None:
        by_id = {
            item.homey_id: item
            for item in self.service.list_devices()
        }

        self.assertEqual(
            by_id[
                NEW_BRIDGEABLE_ID
            ].matching_template_ids,
            ("xiaomi_mi.plug_maeu01",),
        )
        self.assertEqual(
            by_id[NEW_BRIDGEABLE_ID].template_match_kind,
            MatchKind.EXACT,
        )

        self.assertEqual(
            by_id[BOJLER_ID].matching_template_ids, ()
        )
        self.assertIsNone(
            by_id[BOJLER_ID].template_match_kind
        )
        self.assertEqual(
            by_id[
                NEW_NOT_BRIDGEABLE_ID
            ].matching_template_ids,
            (),
        )
        self.assertEqual(
            by_id[MISSING_ID].matching_template_ids, ()
        )

    # --- get_device_detail ---

    def test_get_device_detail_configured(self) -> None:
        detail = self.service.get_device_detail(
            BOJLER_ID
        )

        self.assertEqual(
            detail.status, DeviceStatus.CONFIGURED
        )
        self.assertIsNotNone(detail.raw_capabilities)
        self.assertEqual(
            len(detail.raw_capabilities), 3
        )
        self.assertTrue(
            all(
                capability.bridgeable
                for capability in (
                    detail.raw_capabilities
                )
            )
        )
        self.assertIsNotNone(detail.instance)
        self.assertEqual(
            detail.instance.template_id,
            "xiaomi_mi.plug_maeu01",
        )
        self.assertIn(
            "onoff",
            detail.instance.role_bindings[
                "capabilities"
            ],
        )
        self.assertIn(
            "onoff", detail.instance.keys["capabilities"]
        )

    def test_get_device_detail_missing_has_none_raw_capabilities(
        self,
    ) -> None:
        detail = self.service.get_device_detail(
            MISSING_ID
        )

        self.assertEqual(
            detail.status, DeviceStatus.MISSING
        )
        self.assertIsNone(detail.raw_capabilities)
        self.assertIsNotNone(detail.instance)

    def test_get_device_detail_live_device_with_empty_capabilities(
        self,
    ) -> None:
        detail = self.service.get_device_detail(
            NEW_NOT_BRIDGEABLE_ID
        )

        self.assertEqual(
            detail.status, DeviceStatus.NEW
        )
        self.assertEqual(detail.raw_capabilities, ())
        self.assertIsNone(detail.instance)

    def test_get_device_detail_unknown_raises(
        self,
    ) -> None:
        with self.assertRaises(DeviceNotFoundError):
            self.service.get_device_detail(
                "does-not-exist"
            )

    # --- NEW configuration ---

    def test_preview_new_device_configuration_unknown_device_raises(
        self,
    ) -> None:
        with self.assertRaises(DeviceNotFoundError):
            self.service.preview_new_device_configuration(
                homey_id="does-not-exist",
                template_id="xiaomi_mi.plug_maeu01",
                instance_name="X",
                loxone_name_base="X",
            )

    def test_preview_new_device_configuration_unknown_template_raises(
        self,
    ) -> None:
        with self.assertRaises(TemplateNotFoundError):
            self.service.preview_new_device_configuration(
                homey_id=NEW_BRIDGEABLE_ID,
                template_id="does.not_exist",
                instance_name="X",
                loxone_name_base="X",
            )

    def test_full_new_device_configuration_happy_path(
        self,
    ) -> None:
        preview = (
            self.service.preview_new_device_configuration(
                homey_id=NEW_BRIDGEABLE_ID,
                template_id="xiaomi_mi.plug_maeu01",
                instance_name="Nová zásuvka",
                loxone_name_base="Nová zásuvka",
            )
        )
        self.assertEqual(
            preview.preview.unmapped_template_capabilities,
            (),
        )

        edited = self.service.edit_new_device_configuration(
            preview,
            {
                "measure_power": CapabilityEdit(
                    display_name=(
                        "Nová zásuvka - Příkon"
                    )
                )
            },
        )
        self.assertEqual(
            edited.preview.instance["display_names"][
                "capabilities"
            ]["measure_power"],
            "Nová zásuvka - Příkon",
        )

        result = (
            self.service.validate_new_device_configuration(
                edited.preview.instance,
                homey_id=NEW_BRIDGEABLE_ID,
                template_id="xiaomi_mi.plug_maeu01",
            )
        )
        self.assertTrue(result.is_valid, result.problems)

        path = self.service.save_new_device_configuration(
            edited.preview.instance,
            homey_id=NEW_BRIDGEABLE_ID,
            template_id="xiaomi_mi.plug_maeu01",
        )
        self.assertTrue(path.is_file())

        by_id = {
            item.homey_id: item
            for item in self.service.list_devices()
        }
        self.assertEqual(
            by_id[NEW_BRIDGEABLE_ID].status,
            DeviceStatus.CONFIGURED,
        )

    def test_save_new_device_configuration_refuses_duplicate(
        self,
    ) -> None:
        preview = (
            self.service.preview_new_device_configuration(
                homey_id=NEW_BRIDGEABLE_ID,
                template_id="xiaomi_mi.plug_maeu01",
                instance_name="X",
                loxone_name_base="X",
            )
        )

        self.service.save_new_device_configuration(
            preview.preview.instance,
            homey_id=NEW_BRIDGEABLE_ID,
            template_id="xiaomi_mi.plug_maeu01",
        )

        with self.assertRaises(SaveError):
            self.service.save_new_device_configuration(
                preview.preview.instance,
                homey_id=NEW_BRIDGEABLE_ID,
                template_id="xiaomi_mi.plug_maeu01",
            )

    # --- existing instance / template assignment ---

    def test_preview_template_assignment_unknown_instance_raises(
        self,
    ) -> None:
        with self.assertRaises(InstanceNotFoundError):
            self.service.preview_template_assignment(
                homey_id=NEW_BRIDGEABLE_ID,
                template_id="xiaomi_mi.plug_maeu01",
            )

    def test_preview_and_validate_template_assignment_on_configured_device(
        self,
    ) -> None:
        preview = self.service.preview_template_assignment(
            homey_id=BOJLER_ID,
            template_id="xiaomi_mi.plug_maeu01",
        )
        self.assertTrue(
            preview.assignment.template_matches_device
        )

        result = self.service.validate_existing_instance(
            preview.assignment.instance,
            homey_id=BOJLER_ID,
            template_id="xiaomi_mi.plug_maeu01",
        )
        self.assertTrue(result.is_valid, result.problems)

    # --- MISSING + template_id required (refinement) ---

    def test_validate_existing_instance_with_template_on_missing_raises(
        self,
    ) -> None:
        instances = load_all_instances(
            self.instances_dir
        )
        missing_instance = instances[MISSING_ID]

        with self.assertRaises(DeviceNotFoundError):
            self.service.validate_existing_instance(
                missing_instance,
                homey_id=MISSING_ID,
                template_id="xiaomi_mi.plug_maeu01",
            )

    def test_save_existing_instance_with_template_on_missing_raises_and_writes_nothing(
        self,
    ) -> None:
        instances = load_all_instances(
            self.instances_dir
        )
        missing_instance = instances[MISSING_ID]

        hashes_before = self._instance_file_hashes()

        with self.assertRaises(DeviceNotFoundError):
            self.service.save_existing_instance(
                missing_instance,
                homey_id=MISSING_ID,
                template_id="xiaomi_mi.plug_maeu01",
            )

        self.assertEqual(
            self._instance_file_hashes(), hashes_before
        )

    def test_validate_existing_instance_without_template_on_missing_is_allowed(
        self,
    ) -> None:
        instances = load_all_instances(
            self.instances_dir
        )
        missing_instance = instances[MISSING_ID]

        result = self.service.validate_existing_instance(
            missing_instance,
            homey_id=MISSING_ID,
            template_id=None,
        )

        self.assertTrue(result.is_valid, result.problems)

    def test_save_existing_instance_without_template_on_missing_is_allowed(
        self,
    ) -> None:
        instances = load_all_instances(
            self.instances_dir
        )
        missing_instance = copy.deepcopy(
            instances[MISSING_ID]
        )
        missing_instance["instance_name"] = (
            "Duch - přejmenovaný"
        )

        path = self.service.save_existing_instance(
            missing_instance,
            homey_id=MISSING_ID,
            template_id=None,
        )

        reloaded = load_all_instances(
            self.instances_dir
        )[MISSING_ID]
        self.assertEqual(
            reloaded["instance_name"],
            "Duch - přejmenovaný",
        )
        self.assertTrue(path.is_file())

    # --- no caching ---

    def test_no_caching_reflects_externally_written_instance(
        self,
    ) -> None:
        by_id_before = {
            item.homey_id: item
            for item in self.service.list_devices()
        }
        self.assertEqual(
            by_id_before[NEW_BRIDGEABLE_ID].status,
            DeviceStatus.NEW,
        )

        preview = build_instance_preview(
            homey_device=self.export_data["devices"][
                1
            ],
            template=self.template,
            instance_name="Nová zásuvka",
            loxone_name_base="Nová zásuvka",
        )
        save_instance(
            preview.instance, self.instances_dir
        )

        by_id_after = {
            item.homey_id: item
            for item in self.service.list_devices()
        }
        self.assertEqual(
            by_id_after[NEW_BRIDGEABLE_ID].status,
            DeviceStatus.CONFIGURED,
        )

    # --- read/preview never write, template never auto-assigned ---

    def test_read_and_preview_use_cases_never_write_anything(
        self,
    ) -> None:
        hashes_before = self._instance_file_hashes()

        self.service.list_devices()
        self.service.get_device_detail(BOJLER_ID)
        self.service.preview_template_assignment(
            homey_id=BOJLER_ID,
            template_id="xiaomi_mi.plug_maeu01",
        )
        self.service.preview_new_device_configuration(
            homey_id=NEW_BRIDGEABLE_ID,
            template_id="xiaomi_mi.plug_maeu01",
            instance_name="X",
            loxone_name_base="X",
        )

        self.assertEqual(
            self._instance_file_hashes(), hashes_before
        )


class ReadOnlyModeTests(unittest.TestCase):
    """Read-only je operační přepínač service vrstvy - GET/preview/
    validate musí fungovat beze změny, jen save_* má být odmítnuto,
    dřív než se cokoliv zapíše."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp_path = Path(self._tmp.name)

        self.export_path = tmp_path / "homey_devices.json"
        self.instances_dir = tmp_path / "devices"
        self.templates_dir = tmp_path / "templates"
        self.instances_dir.mkdir()
        self.templates_dir.mkdir()

        self.template = load_template(SAMPLE_TEMPLATE_PATH)

        with (
            self.templates_dir / "xiaomi_mi.plug_maeu01.yaml"
        ).open("w", encoding="utf-8") as file:
            yaml.safe_dump(self.template, file)

        self.export_data = {
            "exported_at": "2026-09-05T00:00:00.000Z",
            "homey_ip": "192.0.2.10",
            "device_count": 1,
            "devices": [
                {
                    "id": NEW_BRIDGEABLE_ID,
                    "name": "Nová zásuvka",
                    "zone_name": "Kuchyně",
                    "class": "socket",
                    "driver_id": (
                        "homey:app:com.xiaomi-mi:"
                        "plug.maeu01"
                    ),
                    "available": True,
                    "capabilities": (
                        _xiaomi_capabilities()
                    ),
                }
            ],
        }

        with self.export_path.open(
            "w", encoding="utf-8"
        ) as file:
            json.dump(self.export_data, file)

        self.service = DeviceConfigurationService(
            export_path=self.export_path,
            instances_dir=self.instances_dir,
            templates_dir=self.templates_dir,
            read_only=True,
        )

    def test_read_only_flag_is_exposed(self) -> None:
        self.assertTrue(self.service.read_only)

    def test_list_and_detail_still_work(self) -> None:
        items = self.service.list_devices()
        self.assertEqual(len(items), 1)

        detail = self.service.get_device_detail(
            NEW_BRIDGEABLE_ID
        )
        self.assertEqual(detail.status, DeviceStatus.NEW)

    def test_preview_and_validate_still_work(self) -> None:
        preview = (
            self.service.preview_new_device_configuration(
                homey_id=NEW_BRIDGEABLE_ID,
                template_id="xiaomi_mi.plug_maeu01",
                instance_name="X",
                loxone_name_base="X",
            )
        )
        result = (
            self.service.validate_new_device_configuration(
                preview.preview.instance,
                homey_id=NEW_BRIDGEABLE_ID,
                template_id="xiaomi_mi.plug_maeu01",
            )
        )
        self.assertTrue(result.is_valid, result.problems)

    def test_save_new_device_configuration_raises_and_writes_nothing(
        self,
    ) -> None:
        preview = (
            self.service.preview_new_device_configuration(
                homey_id=NEW_BRIDGEABLE_ID,
                template_id="xiaomi_mi.plug_maeu01",
                instance_name="X",
                loxone_name_base="X",
            )
        )

        with self.assertRaises(ReadOnlyModeError):
            self.service.save_new_device_configuration(
                preview.preview.instance,
                homey_id=NEW_BRIDGEABLE_ID,
                template_id="xiaomi_mi.plug_maeu01",
            )

        self.assertEqual(
            list(self.instances_dir.glob("*.yaml")), []
        )

    def test_save_existing_instance_raises_and_writes_nothing(
        self,
    ) -> None:
        preview = (
            self.service.preview_new_device_configuration(
                homey_id=NEW_BRIDGEABLE_ID,
                template_id="xiaomi_mi.plug_maeu01",
                instance_name="X",
                loxone_name_base="X",
            )
        )

        with self.assertRaises(ReadOnlyModeError):
            self.service.save_existing_instance(
                preview.preview.instance,
                homey_id=NEW_BRIDGEABLE_ID,
                template_id="xiaomi_mi.plug_maeu01",
            )

        self.assertEqual(
            list(self.instances_dir.glob("*.yaml")), []
        )

    def test_read_only_check_happens_before_any_lookup(
        self,
    ) -> None:
        # I s neexistujícím homey_id/template_id musí prvně selhat
        # na ReadOnlyModeError, ne na DeviceNotFoundError/
        # TemplateNotFoundError - read-only je kontrola na vstupu do
        # metody, ne až po resolvování.
        with self.assertRaises(ReadOnlyModeError):
            self.service.save_new_device_configuration(
                {"homey_id": "does-not-exist"},
                homey_id="does-not-exist",
                template_id="does.not_exist",
            )


if __name__ == "__main__":
    unittest.main()
