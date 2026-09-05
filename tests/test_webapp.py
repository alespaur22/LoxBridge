from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from loxbridge.config_service import DeviceConfigurationService
from loxbridge.instance_builder import build_instance_preview
from loxbridge.instances import load_all_instances, save_instance
from loxbridge.templates import load_template
from loxbridge.webapp.app import create_app


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_TEMPLATE_PATH = (
    ROOT / "config" / "templates" / "xiaomi_mi.plug_maeu01.yaml"
)

BOJLER_ID = "aaaaaaaa-0000-0000-0000-000000000001"
NEW_BRIDGEABLE_ID = "bbbbbbbb-0000-0000-0000-000000000002"
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


class WebAppTests(unittest.TestCase):
    """Vše výhradně v dočasném adresáři, přes Flask test_client()
    (žádný skutečně naslouchající socket, žádné reálné 127.0.0.1
    spojení potřeba) - nikdy proti reálnému config/devices/."""

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
            "device_count": 2,
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
            ],
        }

        with self.export_path.open(
            "w", encoding="utf-8"
        ) as file:
            json.dump(self.export_data, file)

        service = DeviceConfigurationService(
            export_path=self.export_path,
            instances_dir=self.instances_dir,
            templates_dir=self.templates_dir,
        )

        self.app = create_app(service=service)
        self.client = self.app.test_client()

        bojler_preview = build_instance_preview(
            homey_device=self.export_data["devices"][0],
            template=self.template,
            instance_name="Bojler",
            loxone_name_base="Bojler",
        )
        save_instance(
            bojler_preview.instance, self.instances_dir
        )

        import copy

        missing_instance = copy.deepcopy(
            bojler_preview.instance
        )
        missing_instance["homey_id"] = MISSING_ID
        missing_instance["instance_id"] = MISSING_ID
        missing_instance["instance_name"] = "Duch"
        save_instance(missing_instance, self.instances_dir)

    def _instance_hashes(self) -> dict[str, bytes]:
        return {
            path.name: path.read_bytes()
            for path in self.instances_dir.glob("*.yaml")
        }

    # --- GET /api/devices ---

    def test_get_devices_lists_all_statuses(self) -> None:
        response = self.client.get("/api/devices")
        self.assertEqual(response.status_code, 200)

        by_id = {
            item["homey_id"]: item
            for item in response.get_json()
        }

        self.assertEqual(
            by_id[BOJLER_ID]["status"], "configured"
        )
        self.assertEqual(
            by_id[NEW_BRIDGEABLE_ID]["status"], "new"
        )
        self.assertEqual(
            by_id[MISSING_ID]["status"], "missing"
        )

    # --- GET /api/devices/<id> ---

    def test_get_detail_new(self) -> None:
        response = self.client.get(
            f"/api/devices/{NEW_BRIDGEABLE_ID}"
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()

        self.assertEqual(body["status"], "new")
        self.assertEqual(len(body["raw_capabilities"]), 3)
        self.assertEqual(
            body["matching_template_ids"],
            ["xiaomi_mi.plug_maeu01"],
        )
        self.assertEqual(
            body["template_match_kind"], "exact"
        )

    def test_get_detail_configured(self) -> None:
        response = self.client.get(
            f"/api/devices/{BOJLER_ID}"
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()

        self.assertEqual(body["status"], "configured")
        self.assertEqual(
            body["instance"]["template_id"],
            "xiaomi_mi.plug_maeu01",
        )

    def test_get_detail_missing(self) -> None:
        response = self.client.get(
            f"/api/devices/{MISSING_ID}"
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()

        self.assertEqual(body["status"], "missing")
        self.assertIsNone(body["raw_capabilities"])
        self.assertIsNotNone(body["instance"])

    def test_get_detail_unknown_returns_404(self) -> None:
        response = self.client.get(
            "/api/devices/does-not-exist"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.get_json()["error"],
            "device_not_found",
        )

    # --- preview NEW ---

    def test_preview_new_device(self) -> None:
        response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/preview",
            json={
                "template_id": "xiaomi_mi.plug_maeu01",
                "instance_name": "Nová zásuvka",
                "loxone_name_base": "Nová zásuvka",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()

        self.assertEqual(
            body["preview"]["instance"]["role_bindings"][
                "capabilities"
            ]["onoff"],
            "power",
        )
        self.assertEqual(
            body["preview"]["instance"]["keys"][
                "capabilities"
            ]["onoff"],
            "nova_zasuvka_power",
        )

    def test_preview_unknown_template_returns_404(
        self,
    ) -> None:
        response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/preview",
            json={
                "template_id": "does.not_exist",
                "instance_name": "X",
                "loxone_name_base": "X",
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.get_json()["error"],
            "template_not_found",
        )

    def test_preview_unknown_device_returns_404(
        self,
    ) -> None:
        response = self.client.post(
            "/api/devices/does-not-exist/preview",
            json={
                "template_id": "xiaomi_mi.plug_maeu01",
                "instance_name": "X",
                "loxone_name_base": "X",
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.get_json()["error"],
            "device_not_found",
        )

    def test_preview_missing_required_field_returns_400(
        self,
    ) -> None:
        response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/preview",
            json={"template_id": "xiaomi_mi.plug_maeu01"},
        )
        self.assertEqual(response.status_code, 400)

    # --- full edit/validate/save happy path přes HTTP ---

    def test_full_happy_path_new_to_configured(
        self,
    ) -> None:
        preview_response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/preview",
            json={
                "template_id": "xiaomi_mi.plug_maeu01",
                "instance_name": "Nová zásuvka",
                "loxone_name_base": "Nová zásuvka",
                "edits": {
                    "measure_power": {
                        "display_name": (
                            "Nová zásuvka - Příkon"
                        )
                    }
                },
            },
        )
        self.assertEqual(
            preview_response.status_code, 200
        )
        instance = preview_response.get_json()[
            "preview"
        ]["instance"]
        self.assertEqual(
            instance["display_names"]["capabilities"][
                "measure_power"
            ],
            "Nová zásuvka - Příkon",
        )

        validate_response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/validate",
            json={
                "instance": instance,
                "template_id": "xiaomi_mi.plug_maeu01",
            },
        )
        self.assertEqual(
            validate_response.status_code, 200
        )
        validate_body = validate_response.get_json()
        self.assertTrue(
            validate_body["is_valid"],
            validate_body["problems"],
        )

        save_response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/save",
            json={
                "instance": instance,
                "template_id": "xiaomi_mi.plug_maeu01",
            },
        )
        self.assertEqual(save_response.status_code, 200)
        self.assertTrue(
            Path(
                save_response.get_json()["saved_path"]
            ).is_file()
        )

        # GET /api/devices znovu - BEZ restartu appky - musí
        # ukázat CONFIGURED.
        devices_response = self.client.get(
            "/api/devices"
        )
        by_id = {
            item["homey_id"]: item
            for item in devices_response.get_json()
        }
        self.assertEqual(
            by_id[NEW_BRIDGEABLE_ID]["status"],
            "configured",
        )
        self.assertEqual(
            by_id[NEW_BRIDGEABLE_ID]["instance_name"],
            "Nová zásuvka",
        )

    # --- nevalidní save -> 4xx, nic nezapíše ---

    def test_invalid_save_returns_4xx_and_writes_nothing(
        self,
    ) -> None:
        preview_response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/preview",
            json={
                "template_id": "xiaomi_mi.plug_maeu01",
                "instance_name": "Nová zásuvka",
                "loxone_name_base": "Nová zásuvka",
            },
        )
        instance = preview_response.get_json()[
            "preview"
        ]["instance"]
        # Neplatný formát klíče - GUI stav není bezpečnostní hranice,
        # backend to musí samo odmítnout i bez předchozího Validate.
        instance["keys"]["capabilities"][
            "onoff"
        ] = "Not Valid Key!"

        hashes_before = self._instance_hashes()

        save_response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/save",
            json={
                "instance": instance,
                "template_id": "xiaomi_mi.plug_maeu01",
            },
        )

        self.assertEqual(save_response.status_code, 422)
        body = save_response.get_json()
        self.assertEqual(body["error"], "invalid_instance")
        self.assertFalse(body["is_valid"])
        self.assertTrue(body["problems"])

        self.assertEqual(
            self._instance_hashes(), hashes_before
        )

    def test_save_unknown_template_returns_404(
        self,
    ) -> None:
        response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/save",
            json={
                "instance": {"homey_id": NEW_BRIDGEABLE_ID},
                "template_id": "does.not_exist",
            },
        )
        self.assertEqual(response.status_code, 404)

    # --- template operace nad MISSING -> 404 ---

    def test_template_assignment_preview_on_missing_returns_404(
        self,
    ) -> None:
        response = self.client.post(
            f"/api/devices/{MISSING_ID}/"
            "template-assignment/preview",
            json={"template_id": "xiaomi_mi.plug_maeu01"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.get_json()["error"],
            "device_not_found",
        )

    def test_template_assignment_preview_unknown_instance_returns_404(
        self,
    ) -> None:
        response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/"
            "template-assignment/preview",
            json={"template_id": "xiaomi_mi.plug_maeu01"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.get_json()["error"],
            "instance_not_found",
        )

    def test_template_assignment_preview_on_configured(
        self,
    ) -> None:
        response = self.client.post(
            f"/api/devices/{BOJLER_ID}/"
            "template-assignment/preview",
            json={"template_id": "xiaomi_mi.plug_maeu01"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(
            body["assignment"]["template_matches_device"]
        )

    # --- static GUI files served ---

    def test_index_html_served(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"LoxBridge", response.data)

    def test_app_js_served(self) -> None:
        response = self.client.get("/app.js")
        self.assertEqual(response.status_code, 200)

    def test_status_reports_not_read_only_by_default(
        self,
    ) -> None:
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["read_only"])


class ReadOnlyWebAppTests(unittest.TestCase):
    """Stejná fixture jako WebAppTests, ale service je sestavená s
    read_only=True - GET/preview/validate musí fungovat beze změny,
    save musí vrátit 403 a nic nezapsat."""

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

        service = DeviceConfigurationService(
            export_path=self.export_path,
            instances_dir=self.instances_dir,
            templates_dir=self.templates_dir,
            read_only=True,
        )

        self.app = create_app(service=service)
        self.client = self.app.test_client()

    def test_status_reports_read_only(self) -> None:
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["read_only"])

    def test_get_devices_still_works(self) -> None:
        response = self.client.get("/api/devices")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()), 1)

    def test_preview_still_works(self) -> None:
        response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/preview",
            json={
                "template_id": "xiaomi_mi.plug_maeu01",
                "instance_name": "X",
                "loxone_name_base": "X",
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_validate_still_works(self) -> None:
        preview_response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/preview",
            json={
                "template_id": "xiaomi_mi.plug_maeu01",
                "instance_name": "X",
                "loxone_name_base": "X",
            },
        )
        instance = preview_response.get_json()[
            "preview"
        ]["instance"]

        response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/validate",
            json={
                "instance": instance,
                "template_id": "xiaomi_mi.plug_maeu01",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["is_valid"])

    def test_save_returns_403_and_writes_nothing(
        self,
    ) -> None:
        preview_response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/preview",
            json={
                "template_id": "xiaomi_mi.plug_maeu01",
                "instance_name": "X",
                "loxone_name_base": "X",
            },
        )
        instance = preview_response.get_json()[
            "preview"
        ]["instance"]

        response = self.client.post(
            f"/api/devices/{NEW_BRIDGEABLE_ID}/save",
            json={
                "instance": instance,
                "template_id": "xiaomi_mi.plug_maeu01",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.get_json()["error"], "read_only"
        )
        self.assertEqual(
            list(self.instances_dir.glob("*.yaml")), []
        )


if __name__ == "__main__":
    unittest.main()
