from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from loxbridge.instance_builder import build_instance_preview
from loxbridge.instance_save import SaveError, save_device_instance
from loxbridge.instance_validation import SaveMode
from loxbridge.instances import load_all_instances, load_instance
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


class SaveDeviceInstanceTests(unittest.TestCase):
    """Save se testuje výhradně proti dočasnému adresáři - nikdy proti
    reálnému config/devices/."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        self.template = load_template(SAMPLE_TEMPLATE_PATH)
        self.device = _second_xiaomi_plug_device()

    def _valid_preview(self):
        return build_instance_preview(
            homey_device=self.device,
            template=self.template,
            instance_name="Mraznička",
            loxone_name_base="Mraznička",
        )

    def test_create_writes_valid_instance(self) -> None:
        preview = self._valid_preview()

        path = save_device_instance(
            preview.instance,
            directory=self.directory,
            mode=SaveMode.CREATE,
            homey_device=self.device,
            template=self.template,
        )

        self.assertTrue(path.is_file())
        loaded = load_instance(path)
        self.assertEqual(loaded, preview.instance)

    def test_create_refuses_when_homey_id_already_exists(
        self,
    ) -> None:
        preview = self._valid_preview()

        save_device_instance(
            preview.instance,
            directory=self.directory,
            mode=SaveMode.CREATE,
            homey_device=self.device,
            template=self.template,
        )

        with self.assertRaises(SaveError):
            save_device_instance(
                preview.instance,
                directory=self.directory,
                mode=SaveMode.CREATE,
                homey_device=self.device,
                template=self.template,
            )

    def test_replace_refuses_when_instance_does_not_exist(
        self,
    ) -> None:
        preview = self._valid_preview()

        with self.assertRaises(SaveError):
            save_device_instance(
                preview.instance,
                directory=self.directory,
                mode=SaveMode.REPLACE,
                homey_device=self.device,
                template=self.template,
            )

        self.assertEqual(
            list(self.directory.glob("*.yaml")), []
        )

    def test_replace_overwrites_existing_instance(self) -> None:
        preview = self._valid_preview()

        save_device_instance(
            preview.instance,
            directory=self.directory,
            mode=SaveMode.CREATE,
            homey_device=self.device,
            template=self.template,
        )

        updated = copy.deepcopy(preview.instance)
        updated["display_names"]["capabilities"][
            "onoff"
        ] = "Mraznička - Zapnuto ručně"

        path = save_device_instance(
            updated,
            directory=self.directory,
            mode=SaveMode.REPLACE,
            homey_device=self.device,
            template=self.template,
        )

        loaded = load_instance(path)
        self.assertEqual(
            loaded["display_names"]["capabilities"][
                "onoff"
            ],
            "Mraznička - Zapnuto ručně",
        )

    def test_key_collision_with_other_instance_blocks_save(
        self,
    ) -> None:
        first = self._valid_preview()

        save_device_instance(
            first.instance,
            directory=self.directory,
            mode=SaveMode.CREATE,
            homey_device=self.device,
            template=self.template,
        )

        colliding = copy.deepcopy(first.instance)
        colliding["homey_id"] = "another-homey-id"
        colliding["instance_id"] = "another-homey-id"
        # klíč zůstává stejný jako u first -> kolize

        with self.assertRaises(SaveError):
            save_device_instance(
                colliding,
                directory=self.directory,
                mode=SaveMode.CREATE,
                homey_device=None,
                template=None,
            )

        self.assertEqual(
            len(list(self.directory.glob("*.yaml"))), 1
        )

    # --- Klíčový invariant: Save je bezpečnostní hranice sama o sobě ---

    def test_direct_call_with_invalid_instance_writes_nothing(
        self,
    ) -> None:
        """Přímé volání save_device_instance() s nevalidní instancí -
        BEZ jakéhokoliv předchozího volání validate_device_instance()
        volajícím - musí zápis odmítnout a nesmí nic zapsat."""
        preview = self._valid_preview()

        invalid_instance = copy.deepcopy(preview.instance)
        # Únik homey_id do viditelného klíče.
        invalid_instance["keys"]["capabilities"]["onoff"] = (
            f"leak_{invalid_instance['homey_id']}"
        )

        with self.assertRaises(SaveError):
            save_device_instance(
                invalid_instance,
                directory=self.directory,
                mode=SaveMode.CREATE,
            )

        self.assertEqual(
            list(self.directory.glob("*.yaml")), []
        )
        self.assertEqual(load_all_instances(self.directory), {})

    def test_direct_call_missing_homey_id_writes_nothing(
        self,
    ) -> None:
        broken_instance = {"homey_id": ""}

        with self.assertRaises(SaveError):
            save_device_instance(
                broken_instance,
                directory=self.directory,
                mode=SaveMode.CREATE,
            )

        self.assertEqual(
            list(self.directory.glob("*.yaml")), []
        )

    def test_failed_replace_leaves_existing_file_byte_identical(
        self,
    ) -> None:
        preview = self._valid_preview()

        path = save_device_instance(
            preview.instance,
            directory=self.directory,
            mode=SaveMode.CREATE,
            homey_device=self.device,
            template=self.template,
        )

        original_bytes = path.read_bytes()

        invalid_replacement = copy.deepcopy(
            preview.instance
        )
        invalid_replacement["keys"]["capabilities"][
            "onoff"
        ] = "Not Valid Key!"

        with self.assertRaises(SaveError):
            save_device_instance(
                invalid_replacement,
                directory=self.directory,
                mode=SaveMode.REPLACE,
                homey_device=self.device,
                template=self.template,
            )

        self.assertEqual(path.read_bytes(), original_bytes)

    def test_failed_create_with_duplicate_leaves_file_byte_identical(
        self,
    ) -> None:
        preview = self._valid_preview()

        path = save_device_instance(
            preview.instance,
            directory=self.directory,
            mode=SaveMode.CREATE,
            homey_device=self.device,
            template=self.template,
        )

        original_bytes = path.read_bytes()

        second_attempt = copy.deepcopy(preview.instance)
        second_attempt["display_names"]["capabilities"][
            "onoff"
        ] = "Tohle by se nemělo nikdy zapsat"

        with self.assertRaises(SaveError):
            save_device_instance(
                second_attempt,
                directory=self.directory,
                mode=SaveMode.CREATE,
                homey_device=self.device,
                template=self.template,
            )

        self.assertEqual(path.read_bytes(), original_bytes)

    def test_no_stray_tmp_files_left_after_successful_save(
        self,
    ) -> None:
        preview = self._valid_preview()

        save_device_instance(
            preview.instance,
            directory=self.directory,
            mode=SaveMode.CREATE,
            homey_device=self.device,
            template=self.template,
        )

        all_files = list(self.directory.iterdir())
        self.assertEqual(len(all_files), 1)
        self.assertTrue(all_files[0].name.endswith(".yaml"))


if __name__ == "__main__":
    unittest.main()
