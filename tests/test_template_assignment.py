from __future__ import annotations

import copy
import unittest
from pathlib import Path

from loxbridge.instance_validation import (
    SaveMode,
    validate_device_instance,
)
from loxbridge.template_assignment import (
    RoleConflict,
    build_template_assignment_preview,
)
from loxbridge.templates import load_template


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_TEMPLATE_PATH = (
    ROOT / "config" / "templates" / "xiaomi_mi.plug_maeu01.yaml"
)

HOMEY_ID = "c2b1a000-1111-2222-3333-444455556666"


def _second_xiaomi_plug_device(**overrides) -> dict:
    device = {
        "id": HOMEY_ID,
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
    device.update(overrides)
    return device


def _legacy_instance(
    *,
    capability_keys: dict[str, str] | None = None,
    capability_names: dict[str, str] | None = None,
    role_bindings: dict[str, str] | None = None,
    include_role_bindings_section: bool = False,
) -> dict:
    """Tvar odpovídající REÁLNÉ migrované instanci - žádný
    `role_bindings` klíč vůbec (57 dnešních souborů ho nemá), plochý
    `overrides: {}`."""
    keys = (
        capability_keys
        if capability_keys is not None
        else {
            "onoff": "mraznicka_onoff",
            "measure_power": "mraznicka_measure_power",
            "meter_power": "mraznicka_meter_power",
        }
    )
    names = (
        capability_names
        if capability_names is not None
        else {
            "onoff": "Mraznička - Zapnuto",
            "measure_power": "Mraznička - Příkon",
            "meter_power": "Mraznička - Spotřeba",
        }
    )

    instance: dict = {
        "schema_version": 1,
        "instance_id": HOMEY_ID,
        "homey_id": HOMEY_ID,
        "homey_name_last_seen": (
            "Xiaomi Zásuvka Mraznička"
        ),
        "instance_name": "Mraznička",
        "loxone_name_base": "Mraznička",
        "key_base": "mraznicka",
        "enabled": True,
        "template": None,
        "template_version": None,
        "legacy_profile": "switch.socket",
        "homey_meta": {
            "class": "socket",
            "driver_id": (
                "homey:app:com.xiaomi-mi:plug.maeu01"
            ),
            "zone_name": "Sklep",
        },
        "keys": {
            "capabilities": keys,
            "commands": {},
            "events": {},
        },
        "display_names": {
            "capabilities": names,
            "commands": {},
            "events": {},
        },
        "overrides": {},
    }

    if include_role_bindings_section or role_bindings:
        instance["role_bindings"] = {
            "capabilities": role_bindings or {},
            "commands": {},
            "events": {},
        }

    return instance


class TemplateAssignmentPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = load_template(SAMPLE_TEMPLATE_PATH)

    # --- role_bindings prefill on a pure legacy instance ---

    def test_legacy_instance_gets_role_bindings_filled(
        self,
    ) -> None:
        existing = _legacy_instance()  # no role_bindings key at all
        device = _second_xiaomi_plug_device()

        preview = build_template_assignment_preview(
            existing_instance=existing,
            homey_device=device,
            template=self.template,
        )

        self.assertEqual(
            preview.instance["role_bindings"][
                "capabilities"
            ],
            {
                "onoff": "power",
                "measure_power": "power_now",
                "meter_power": "energy_total",
            },
        )
        self.assertEqual(preview.conflicts, ())
        self.assertEqual(
            preview.missing_instance_capabilities, ()
        )
        self.assertEqual(
            preview.unmatched_instance_capabilities, ()
        )
        self.assertTrue(preview.template_matches_device)
        self.assertEqual(
            preview.instance["template"],
            "xiaomi_mi.plug_maeu01",
        )
        self.assertEqual(
            preview.instance["template_version"], 1
        )

    # --- the central invariant: keys/display_names/identity untouched ---

    def test_keys_and_display_names_remain_identical(
        self,
    ) -> None:
        existing = _legacy_instance()
        existing_before = copy.deepcopy(existing)
        device = _second_xiaomi_plug_device()

        preview = build_template_assignment_preview(
            existing_instance=existing,
            homey_device=device,
            template=self.template,
        )

        self.assertEqual(
            preview.instance["keys"],
            existing_before["keys"],
        )
        self.assertEqual(
            preview.instance["display_names"],
            existing_before["display_names"],
        )
        self.assertEqual(
            preview.instance["key_base"],
            existing_before["key_base"],
        )
        self.assertEqual(
            preview.instance["instance_name"],
            existing_before["instance_name"],
        )
        self.assertEqual(
            preview.instance["loxone_name_base"],
            existing_before["loxone_name_base"],
        )
        self.assertEqual(
            preview.instance["homey_id"],
            existing_before["homey_id"],
        )

    # --- missing / unmatched capabilities ---

    def test_template_capability_missing_on_instance_is_not_added(
        self,
    ) -> None:
        existing = _legacy_instance(
            capability_keys={
                "onoff": "mraznicka_onoff",
                "measure_power": (
                    "mraznicka_measure_power"
                ),
                # meter_power chybí - instance ho dosud nemapuje.
            },
            capability_names={
                "onoff": "Mraznička - Zapnuto",
                "measure_power": "Mraznička - Příkon",
            },
        )
        device = _second_xiaomi_plug_device()

        preview = build_template_assignment_preview(
            existing_instance=existing,
            homey_device=device,
            template=self.template,
        )

        self.assertEqual(
            preview.missing_instance_capabilities,
            ("meter_power",),
        )
        self.assertNotIn(
            "meter_power",
            preview.instance["keys"]["capabilities"],
        )
        self.assertNotIn(
            "meter_power",
            preview.instance["role_bindings"][
                "capabilities"
            ],
        )

    def test_instance_capability_unknown_to_template_is_left_alone(
        self,
    ) -> None:
        existing = _legacy_instance(
            capability_keys={
                "onoff": "mraznicka_onoff",
                "measure_power": (
                    "mraznicka_measure_power"
                ),
                "meter_power": "mraznicka_meter_power",
                "rssi": "mraznicka_rssi",
            },
            capability_names={
                "onoff": "Mraznička - Zapnuto",
                "measure_power": "Mraznička - Příkon",
                "meter_power": "Mraznička - Spotřeba",
                "rssi": "Mraznička - Signál",
            },
        )
        existing_before = copy.deepcopy(existing)
        device = _second_xiaomi_plug_device()

        preview = build_template_assignment_preview(
            existing_instance=existing,
            homey_device=device,
            template=self.template,
        )

        self.assertEqual(
            preview.unmatched_instance_capabilities,
            ("rssi",),
        )
        self.assertEqual(
            preview.instance["keys"]["capabilities"][
                "rssi"
            ],
            existing_before["keys"]["capabilities"][
                "rssi"
            ],
        )
        self.assertNotIn(
            "rssi",
            preview.instance["role_bindings"][
                "capabilities"
            ],
        )

    # --- conflicting role binding: never silently overwritten ---

    def test_conflicting_role_binding_is_preserved_and_reported(
        self,
    ) -> None:
        existing = _legacy_instance(
            role_bindings={
                "measure_power": "custom_existing_role"
            }
        )
        device = _second_xiaomi_plug_device()

        preview = build_template_assignment_preview(
            existing_instance=existing,
            homey_device=device,
            template=self.template,
        )

        self.assertEqual(
            preview.conflicts,
            (
                RoleConflict(
                    capability_id="measure_power",
                    existing_role="custom_existing_role",
                    template_role="power_now",
                ),
            ),
        )
        # Role zůstává existující, nikdy tiše nepřepsaná.
        self.assertEqual(
            preview.instance["role_bindings"][
                "capabilities"
            ]["measure_power"],
            "custom_existing_role",
        )
        # Ostatní role, které konflikt neměly, se přesto předvyplní.
        self.assertEqual(
            preview.instance["role_bindings"][
                "capabilities"
            ]["onoff"],
            "power",
        )

    def test_matching_existing_role_is_not_a_conflict(
        self,
    ) -> None:
        existing = _legacy_instance(
            role_bindings={"measure_power": "power_now"}
        )
        device = _second_xiaomi_plug_device()

        preview = build_template_assignment_preview(
            existing_instance=existing,
            homey_device=device,
            template=self.template,
        )

        self.assertEqual(preview.conflicts, ())
        self.assertEqual(
            preview.instance["role_bindings"][
                "capabilities"
            ]["measure_power"],
            "power_now",
        )

    # --- template mismatch ---

    def test_template_mismatch_is_reported_as_not_matching(
        self,
    ) -> None:
        existing = _legacy_instance()
        # Homey ID musí sedět s instancí, ale driver_id patří jinému
        # zařízení - simuluje "přiřazen špatný template".
        mismatched_device = _second_xiaomi_plug_device(
            driver_id="homey:app:com.fibaro:FGS-223"
        )

        preview = build_template_assignment_preview(
            existing_instance=existing,
            homey_device=mismatched_device,
            template=self.template,
        )

        self.assertFalse(preview.template_matches_device)

    def test_template_mismatch_makes_validate_reject_replace(
        self,
    ) -> None:
        existing = _legacy_instance()
        mismatched_device = _second_xiaomi_plug_device(
            driver_id="homey:app:com.fibaro:FGS-223"
        )

        preview = build_template_assignment_preview(
            existing_instance=existing,
            homey_device=mismatched_device,
            template=self.template,
        )

        result = validate_device_instance(
            preview.instance,
            homey_device=mismatched_device,
            template=self.template,
            existing_instances={HOMEY_ID: existing},
            mode=SaveMode.REPLACE,
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(
                p.code == "template_mismatch"
                for p in result.errors()
            )
        )

    # --- overrides computed against template defaults ---

    def test_overrides_reflect_legacy_keys_diverging_from_template(
        self,
    ) -> None:
        # Legacy klíče/názvy jsou záměrně jiné, než by dnes navrhl
        # template (mraznicka_onoff vs. template default
        # mraznicka_power) - ale nesmí se přejmenovat, jen nahlásit.
        existing = _legacy_instance()
        device = _second_xiaomi_plug_device()

        preview = build_template_assignment_preview(
            existing_instance=existing,
            homey_device=device,
            template=self.template,
        )

        overrides = preview.instance["overrides"][
            "capabilities"
        ]

        # onoff: role byla nově předvyplněna na template default
        # ("power"), takže role NENÍ override - ale uložený key/name
        # se od template defaultu liší, takže tam jsou.
        self.assertIn("onoff", overrides)
        self.assertNotIn("role", overrides["onoff"])
        self.assertIn("key", overrides["onoff"])
        self.assertIn("display_name", overrides["onoff"])

        # Skutečný key/display_name zůstal beze změny.
        self.assertEqual(
            preview.instance["keys"]["capabilities"][
                "onoff"
            ],
            "mraznicka_onoff",
        )
        self.assertEqual(
            preview.instance["display_names"][
                "capabilities"
            ]["onoff"],
            "Mraznička - Zapnuto",
        )

    def test_no_override_when_legacy_values_already_match_template_default(
        self,
    ) -> None:
        # Klíče/názvy přesně odpovídají tomu, co by template navrhl -
        # žádný override.
        existing = _legacy_instance(
            capability_keys={
                "onoff": "mraznicka_power",
                "measure_power": "mraznicka_power_now",
                "meter_power": "mraznicka_energy_total",
            },
            capability_names={
                "onoff": "Mraznička - Zapnutí",
                "measure_power": (
                    "Mraznička - Aktuální výkon"
                ),
                "meter_power": "Mraznička - Energie",
            },
        )
        device = _second_xiaomi_plug_device()

        preview = build_template_assignment_preview(
            existing_instance=existing,
            homey_device=device,
            template=self.template,
        )

        self.assertEqual(
            preview.instance["overrides"]["capabilities"],
            {},
        )

    def test_conflicting_role_also_counts_as_role_override(
        self,
    ) -> None:
        existing = _legacy_instance(
            role_bindings={
                "measure_power": "custom_existing_role"
            }
        )
        device = _second_xiaomi_plug_device()

        preview = build_template_assignment_preview(
            existing_instance=existing,
            homey_device=device,
            template=self.template,
        )

        overrides = preview.instance["overrides"][
            "capabilities"
        ]

        self.assertIn("role", overrides["measure_power"])

    # --- purity ---

    def test_inputs_are_not_mutated(self) -> None:
        existing = _legacy_instance(
            role_bindings={
                "measure_power": "custom_existing_role"
            }
        )
        device = _second_xiaomi_plug_device()
        template = copy.deepcopy(self.template)

        existing_before = copy.deepcopy(existing)
        device_before = copy.deepcopy(device)
        template_before = copy.deepcopy(template)

        build_template_assignment_preview(
            existing_instance=existing,
            homey_device=device,
            template=template,
        )

        self.assertEqual(existing, existing_before)
        self.assertEqual(device, device_before)
        self.assertEqual(template, template_before)

    # --- downstream validate_device_instance(..., REPLACE) ---

    def test_valid_assignment_passes_validate_replace(
        self,
    ) -> None:
        existing = _legacy_instance()
        device = _second_xiaomi_plug_device()

        preview = build_template_assignment_preview(
            existing_instance=existing,
            homey_device=device,
            template=self.template,
        )

        result = validate_device_instance(
            preview.instance,
            homey_device=device,
            template=self.template,
            existing_instances={HOMEY_ID: existing},
            mode=SaveMode.REPLACE,
        )

        self.assertTrue(result.is_valid, result.problems)

    def test_valid_assignment_fails_create_because_instance_exists(
        self,
    ) -> None:
        # CREATE musí odmítnout, protože homey_id už existuje - to je
        # přesně proč assignment vždy jde přes REPLACE, ne CREATE.
        existing = _legacy_instance()
        device = _second_xiaomi_plug_device()

        preview = build_template_assignment_preview(
            existing_instance=existing,
            homey_device=device,
            template=self.template,
        )

        result = validate_device_instance(
            preview.instance,
            homey_device=device,
            template=self.template,
            existing_instances={HOMEY_ID: existing},
            mode=SaveMode.CREATE,
        )

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(
                p.code == "duplicate_homey_id"
                for p in result.errors()
            )
        )


if __name__ == "__main__":
    unittest.main()
