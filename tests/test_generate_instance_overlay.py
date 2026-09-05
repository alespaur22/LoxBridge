from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from loxbridge.generate import (
    apply_instance_overrides,
    build_generated_config,
    generate_and_save,
    generate_devices,
    validate_unique_keys,
)
from loxbridge.instances import (
    DEFAULT_INSTANCES_DIR,
    build_instance_from_generated_device,
    load_all_instances,
)


ROOT = Path(__file__).resolve().parents[1]
EXPORT_PATH = ROOT / "exports" / "homey_devices.json"


def _sample_generated_device() -> dict:
    return {
        "name": "LED Obývák",
        "slug": "led_obyvak",
        "homey_id": "4a54b6a3-4074-44f6-a109-7e41210e2ae2",
        "homey_class": "light",
        "driver_id": "homey:app:com.fibaro:FGRGBWM-442",
        "zone_name": None,
        "capabilities": {
            "onoff": {
                "key": "led_obyvak_onoff",
                "loxone_name": "LED Obývák - Zapnuto",
                "type": "boolean",
            },
            "dim": {
                "key": "led_obyvak_dim",
                "loxone_name": "LED Obývák - Jas",
                "type": "number",
            },
        },
        "loxbridge": {
            "profile": "light.rgb_tunable_white",
            "commands": [
                {
                    "key": "led_obyvak_rgb",
                    "title": "LED Obývák - RGB",
                    "kind": "rgb",
                },
            ],
            "events": [
                {
                    "key": "led_obyvak_input_1_press_1x",
                    "title": "LED Obývák - Input 1 - Press 1x",
                    "kind": "pulse",
                },
            ],
        },
    }


class ApplyInstanceOverridesTests(unittest.TestCase):
    def test_no_instance_is_a_noop(self) -> None:
        device = _sample_generated_device()
        before = copy.deepcopy(device)

        apply_instance_overrides(device, None)

        self.assertEqual(device, before)

    def test_overrides_capability_key_and_name(self) -> None:
        device = _sample_generated_device()

        instance = {
            "key_base": "bojler",
            "keys": {
                "capabilities": {"onoff": "bojler_power"},
                "commands": {},
                "events": {},
            },
            "display_names": {
                "capabilities": {
                    "onoff": "Bojler - Zapnutí",
                },
                "commands": {},
                "events": {},
            },
        }

        apply_instance_overrides(device, instance)

        self.assertEqual(
            device["capabilities"]["onoff"]["key"],
            "bojler_power",
        )
        self.assertEqual(
            device["capabilities"]["onoff"]["loxone_name"],
            "Bojler - Zapnutí",
        )
        # dim nebyla v instanci - zůstává dnešní hodnota.
        self.assertEqual(
            device["capabilities"]["dim"]["key"],
            "led_obyvak_dim",
        )

    def test_overrides_command_key_and_title_by_kind(self) -> None:
        device = _sample_generated_device()

        instance = {
            "key_base": "obyvak",
            "keys": {
                "capabilities": {},
                "commands": {"rgb": "obyvak_barva"},
                "events": {},
            },
            "display_names": {
                "capabilities": {},
                "commands": {"rgb": "Obývák - Barva"},
                "events": {},
            },
        }

        apply_instance_overrides(device, instance)

        command = device["loxbridge"]["commands"][0]

        self.assertEqual(command["key"], "obyvak_barva")
        self.assertEqual(command["title"], "Obývák - Barva")

    def test_overrides_event_key_using_frozen_key_base(self) -> None:
        device = _sample_generated_device()

        # Zařízení bylo v Homey přejmenováno - dnešní slug se liší
        # od zamrzlého key_base v instanci. Přiřazení musí přesto
        # najít roli podle zamrzlého key_base z instance.
        device["slug"] = "obyvak_led_novy"

        instance = {
            "key_base": "led_obyvak",
            "keys": {
                "capabilities": {},
                "commands": {},
                "events": {
                    "input_1_press_1x": "obyvak_tlacitko_1_press_1x",
                },
            },
            "display_names": {
                "capabilities": {},
                "commands": {},
                "events": {
                    "input_1_press_1x": "Obývák - Tlačítko 1 - 1x",
                },
            },
        }

        apply_instance_overrides(device, instance)

        event = device["loxbridge"]["events"][0]

        self.assertEqual(
            event["key"], "obyvak_tlacitko_1_press_1x"
        )
        self.assertEqual(
            event["title"], "Obývák - Tlačítko 1 - 1x"
        )

    def test_missing_role_falls_back_and_does_not_mutate_instance(
        self,
    ) -> None:
        device = _sample_generated_device()

        instance = {
            "key_base": "led_obyvak",
            "keys": {
                "capabilities": {},
                "commands": {},
                "events": {},
            },
            "display_names": {
                "capabilities": {},
                "commands": {},
                "events": {},
            },
        }

        instance_before = copy.deepcopy(instance)

        apply_instance_overrides(device, instance)

        # Nic v instanci se nezapisuje/nemění.
        self.assertEqual(instance, instance_before)

        # A dnešní dopočítané hodnoty zůstávají beze změny.
        self.assertEqual(
            device["capabilities"]["onoff"]["key"],
            "led_obyvak_onoff",
        )
        self.assertEqual(
            device["loxbridge"]["commands"][0]["key"],
            "led_obyvak_rgb",
        )
        self.assertEqual(
            device["loxbridge"]["events"][0]["key"],
            "led_obyvak_input_1_press_1x",
        )


class ValidateUniqueKeysTests(unittest.TestCase):
    def test_passes_for_clean_config(self) -> None:
        export_data = json.loads(
            EXPORT_PATH.read_text(encoding="utf-8")
        )

        config, _ = build_generated_config(
            current_config={
                "homey": {"ip": "192.0.2.10", "token": "t"},
                "loxone": {"ip": "192.0.2.20", "port": 7001},
            },
            export_data=export_data,
        )

        # Nesmí vyhodit.
        validate_unique_keys(config)

    def test_raises_on_capability_key_collision(self) -> None:
        config = {
            "devices": [
                {
                    "name": "Zařízení A",
                    "capabilities": {
                        "onoff": {"key": "shared_key"},
                    },
                    "loxbridge": {"commands": [], "events": []},
                },
                {
                    "name": "Zařízení B",
                    "capabilities": {
                        "onoff": {"key": "shared_key"},
                    },
                    "loxbridge": {"commands": [], "events": []},
                },
            ]
        }

        with self.assertRaises(RuntimeError) as ctx:
            validate_unique_keys(config)

        self.assertIn("shared_key", str(ctx.exception))
        self.assertIn("Zařízení A", str(ctx.exception))
        self.assertIn("Zařízení B", str(ctx.exception))


class GenerateAndSaveSafetyTests(unittest.TestCase):
    def _write_export(self, path: Path, devices: list[dict]) -> None:
        with path.open("w", encoding="utf-8") as file:
            json.dump({"devices": devices}, file)

    def test_writes_output_when_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            current_config_path = tmp_path / "config.yaml"
            export_path = tmp_path / "homey_devices.json"
            output_path = tmp_path / "config.generated.yaml"
            instances_dir = tmp_path / "devices"

            with current_config_path.open(
                "w", encoding="utf-8"
            ) as file:
                yaml.safe_dump(
                    {
                        "homey": {
                            "ip": "192.0.2.10",
                            "token": "t",
                        },
                        "loxone": {
                            "ip": "192.0.2.20",
                            "port": 7001,
                        },
                    },
                    file,
                )

            self._write_export(
                export_path,
                [
                    {
                        "id": "dev-1",
                        "name": "Sensor A",
                        "class": "sensor",
                        "capabilities": [
                            {
                                "id": "measure_temperature",
                                "title": "Temperature",
                                "type": "number",
                                "getable": True,
                                "setable": False,
                            }
                        ],
                    }
                ],
            )

            config, count = generate_and_save(
                current_config_path=current_config_path,
                export_path=export_path,
                output_path=output_path,
                instances_dir=instances_dir,
            )

            self.assertTrue(output_path.is_file())
            self.assertEqual(count, 1)
            self.assertEqual(len(config["devices"]), 1)

    def test_existing_output_untouched_when_validation_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            current_config_path = tmp_path / "config.yaml"
            export_path = tmp_path / "homey_devices.json"
            output_path = tmp_path / "config.generated.yaml"
            instances_dir = tmp_path / "devices"

            with current_config_path.open(
                "w", encoding="utf-8"
            ) as file:
                yaml.safe_dump(
                    {
                        "homey": {
                            "ip": "192.0.2.10",
                            "token": "t",
                        },
                        "loxone": {
                            "ip": "192.0.2.20",
                            "port": 7001,
                        },
                    },
                    file,
                )

            # Dvě různá zařízení, jejichž jediná capability se
            # namapuje na stejný Loxone klíč přes dvě přiřazené
            # instance - vyrobená kolize.
            self._write_export(
                export_path,
                [
                    {
                        "id": "dev-1",
                        "name": "Zařízení A",
                        "class": "sensor",
                        "capabilities": [
                            {
                                "id": "measure_temperature",
                                "title": "Temperature",
                                "type": "number",
                                "getable": True,
                                "setable": False,
                            }
                        ],
                    },
                    {
                        "id": "dev-2",
                        "name": "Zařízení B",
                        "class": "sensor",
                        "capabilities": [
                            {
                                "id": "measure_temperature",
                                "title": "Temperature",
                                "type": "number",
                                "getable": True,
                                "setable": False,
                            }
                        ],
                    },
                ],
            )

            instances_dir.mkdir(parents=True)

            for device_id in ("dev-1", "dev-2"):
                instance = {
                    "homey_id": device_id,
                    "key_base": "kolize",
                    "keys": {
                        "capabilities": {
                            "measure_temperature": (
                                "kolize_teplota"
                            )
                        },
                        "commands": {},
                        "events": {},
                    },
                    "display_names": {
                        "capabilities": {},
                        "commands": {},
                        "events": {},
                    },
                }

                with (instances_dir / f"{device_id}.yaml").open(
                    "w", encoding="utf-8"
                ) as file:
                    yaml.safe_dump(instance, file)

            # Předchozí "produkční" obsah - musí zůstat nedotčený.
            previous_content = (
                "loxbridge:\n"
                "  schema_version: 5\n"
                "devices: []\n"
            )

            output_path.write_text(
                previous_content, encoding="utf-8"
            )

            with self.assertRaises(RuntimeError) as ctx:
                generate_and_save(
                    current_config_path=current_config_path,
                    export_path=export_path,
                    output_path=output_path,
                    instances_dir=instances_dir,
                )

            self.assertIn("kolize_teplota", str(ctx.exception))

            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                previous_content,
            )


class FullMigratedFleetRegressionTests(unittest.TestCase):
    """Nejsilnější regresní pojistka: pokud je na tomhle stroji
    reálně namigrovaný config/devices/, ověří se, že zapojení
    instance store do generate_devices() nezmění výstup oproti
    dnešnímu chování (instances=None) pro stejná data. config/devices/
    je gitignored - na čistém checkoutu bez migrace se test přeskočí.
    """

    def test_real_instances_produce_identical_config(self) -> None:
        real_instances = load_all_instances(DEFAULT_INSTANCES_DIR)

        if not real_instances:
            self.skipTest(
                "config/devices/ je prázdný nebo neexistuje - "
                "migrace zatím neproběhla na tomhle stroji."
            )

        export_data = json.loads(
            EXPORT_PATH.read_text(encoding="utf-8")
        )

        current_config = {
            "homey": {"ip": "192.0.2.10", "token": "t"},
            "loxone": {"ip": "192.0.2.20", "port": 7001},
        }

        without_instances, count_without = build_generated_config(
            current_config=current_config,
            export_data=export_data,
            instances=None,
        )

        with_instances, count_with = build_generated_config(
            current_config=current_config,
            export_data=export_data,
            instances=real_instances,
        )

        self.assertEqual(count_without, count_with)
        self.assertEqual(without_instances, with_instances)


if __name__ == "__main__":
    unittest.main()
