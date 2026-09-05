from __future__ import annotations

import copy
import unittest
from pathlib import Path

from loxbridge.instance_builder import (
    CapabilityEdit,
    InstancePreview,
    apply_preview_edits,
    build_instance_preview,
)
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


class ApplyPreviewEditsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = load_template(SAMPLE_TEMPLATE_PATH)

    def _base_preview(self) -> InstancePreview:
        return build_instance_preview(
            homey_device=_second_xiaomi_plug_device(),
            template=self.template,
            instance_name="Mraznička",
            loxone_name_base="Mraznička",
        )

    # --- immutability ---

    def test_does_not_mutate_original_preview_instance(
        self,
    ) -> None:
        preview = self._base_preview()
        instance_before = copy.deepcopy(preview.instance)
        defaults_before = dict(preview.capability_defaults)

        apply_preview_edits(
            preview,
            {
                "measure_power": CapabilityEdit(
                    role="consumption"
                )
            },
        )

        self.assertEqual(preview.instance, instance_before)
        self.assertEqual(
            preview.capability_defaults, defaults_before
        )

    def test_returns_a_new_preview_object(self) -> None:
        preview = self._base_preview()

        edited = apply_preview_edits(
            preview,
            {
                "measure_power": CapabilityEdit(
                    role="consumption"
                )
            },
        )

        self.assertIsNot(edited, preview)
        self.assertIsNot(edited.instance, preview.instance)

    def test_does_not_mutate_edits_argument(self) -> None:
        preview = self._base_preview()
        edits = {
            "measure_power": CapabilityEdit(
                role="consumption"
            )
        }
        edits_before = dict(edits)

        apply_preview_edits(preview, edits)

        self.assertEqual(edits, edits_before)

    # --- independent field changes ---

    def test_role_key_display_name_change_independently(
        self,
    ) -> None:
        preview = self._base_preview()

        edited = apply_preview_edits(
            preview,
            {
                "measure_power": CapabilityEdit(
                    role="consumption",
                    display_name="Mraznička - Příkon",
                )
            },
        )

        capabilities = edited.instance

        self.assertEqual(
            capabilities["role_bindings"]["capabilities"][
                "measure_power"
            ],
            "consumption",
        )
        self.assertEqual(
            capabilities["display_names"]["capabilities"][
                "measure_power"
            ],
            "Mraznička - Příkon",
        )
        # key nebylo editováno - zůstává template default beze změny.
        self.assertEqual(
            capabilities["keys"]["capabilities"][
                "measure_power"
            ],
            "mraznicka_power_now",
        )

    def test_key_only_edit_leaves_role_and_display_name_untouched(
        self,
    ) -> None:
        preview = self._base_preview()

        edited = apply_preview_edits(
            preview,
            {
                "measure_power": CapabilityEdit(
                    key="mraznicka_spotreba"
                )
            },
        )

        self.assertEqual(
            edited.instance["keys"]["capabilities"][
                "measure_power"
            ],
            "mraznicka_spotreba",
        )
        self.assertEqual(
            edited.instance["role_bindings"][
                "capabilities"
            ]["measure_power"],
            "power_now",
        )
        self.assertEqual(
            edited.instance["display_names"][
                "capabilities"
            ]["measure_power"],
            "Mraznička - Aktuální výkon",
        )

    def test_editing_one_capability_does_not_affect_another(
        self,
    ) -> None:
        preview = self._base_preview()

        edited = apply_preview_edits(
            preview,
            {
                "measure_power": CapabilityEdit(
                    role="consumption"
                )
            },
        )

        self.assertEqual(
            edited.instance["role_bindings"][
                "capabilities"
            ]["onoff"],
            "power",
        )
        self.assertEqual(
            edited.instance["keys"]["capabilities"][
                "onoff"
            ],
            "mraznicka_power",
        )

    # --- role change never regenerates key/display_name ---

    def test_changing_role_does_not_regenerate_key_or_display_name(
        self,
    ) -> None:
        preview = self._base_preview()

        original_key = preview.instance["keys"][
            "capabilities"
        ]["measure_power"]
        original_name = preview.instance[
            "display_names"
        ]["capabilities"]["measure_power"]

        edited = apply_preview_edits(
            preview,
            {
                "measure_power": CapabilityEdit(
                    role="completely_unrelated_role"
                )
            },
        )

        self.assertEqual(
            edited.instance["keys"]["capabilities"][
                "measure_power"
            ],
            original_key,
        )
        self.assertEqual(
            edited.instance["display_names"][
                "capabilities"
            ]["measure_power"],
            original_name,
        )

    # --- overrides bookkeeping ---

    def test_overrides_recorded_only_for_diverged_fields(
        self,
    ) -> None:
        preview = self._base_preview()

        edited = apply_preview_edits(
            preview,
            {
                "measure_power": CapabilityEdit(
                    role="consumption",
                    display_name="Mraznička - Příkon",
                )
            },
        )

        overrides = edited.instance["overrides"][
            "capabilities"
        ]

        self.assertEqual(
            overrides["measure_power"],
            ["role", "display_name"],
        )
        self.assertNotIn("onoff", overrides)
        self.assertNotIn("meter_power", overrides)

    def test_reset_field_to_template_default_removes_it_from_overrides(
        self,
    ) -> None:
        preview = self._base_preview()

        edited_once = apply_preview_edits(
            preview,
            {
                "measure_power": CapabilityEdit(
                    role="consumption",
                    display_name="Mraznička - Příkon",
                )
            },
        )

        self.assertEqual(
            edited_once.instance["overrides"][
                "capabilities"
            ]["measure_power"],
            ["role", "display_name"],
        )

        # Vrátit roli přesně na template default (power_now).
        edited_back = apply_preview_edits(
            edited_once,
            {
                "measure_power": CapabilityEdit(
                    role="power_now"
                )
            },
        )

        self.assertEqual(
            edited_back.instance["role_bindings"][
                "capabilities"
            ]["measure_power"],
            "power_now",
        )
        # role zmizela z overrides, display_name tam zůstává.
        self.assertEqual(
            edited_back.instance["overrides"][
                "capabilities"
            ]["measure_power"],
            ["display_name"],
        )

    def test_full_reset_removes_capability_entry_from_overrides(
        self,
    ) -> None:
        preview = self._base_preview()

        edited_once = apply_preview_edits(
            preview,
            {
                "measure_power": CapabilityEdit(
                    role="consumption"
                )
            },
        )

        self.assertIn(
            "measure_power",
            edited_once.instance["overrides"][
                "capabilities"
            ],
        )

        reset = apply_preview_edits(
            edited_once,
            {
                "measure_power": CapabilityEdit(
                    role="power_now"
                )
            },
        )

        self.assertNotIn(
            "measure_power",
            reset.instance["overrides"]["capabilities"],
        )

    def test_diff_is_against_original_defaults_not_previous_edit_state(
        self,
    ) -> None:
        """Přesný scénář ze zadání: role+display_name se změní,
        role se pak vrátí na template default - display_name
        divergence musí přežít, protože diff je vždy proti PŮVODNÍM
        template defaultům, ne proti předchozímu (už upravenému)
        stavu preview."""
        preview = self._base_preview()

        step1 = apply_preview_edits(
            preview,
            {
                "measure_power": CapabilityEdit(
                    role="consumption",
                    display_name="Mraznička - Příkon",
                )
            },
        )
        step2 = apply_preview_edits(
            step1,
            {
                "measure_power": CapabilityEdit(
                    role="power_now"
                )
            },
        )

        self.assertEqual(
            step2.instance["overrides"]["capabilities"][
                "measure_power"
            ],
            ["display_name"],
        )

        # capability_defaults je stejné napříč celým řetězcem editací.
        self.assertEqual(
            preview.capability_defaults,
            step1.capability_defaults,
        )
        self.assertEqual(
            step1.capability_defaults,
            step2.capability_defaults,
        )

    def test_capability_defaults_not_written_into_instance(
        self,
    ) -> None:
        preview = self._base_preview()

        edited = apply_preview_edits(
            preview,
            {
                "measure_power": CapabilityEdit(
                    role="consumption"
                )
            },
        )

        self.assertNotIn(
            "capability_defaults", edited.instance
        )

    # --- editing a capability that doesn't exist ---

    def test_editing_nonexistent_capability_raises(
        self,
    ) -> None:
        preview = self._base_preview()

        with self.assertRaises(ValueError):
            apply_preview_edits(
                preview,
                {
                    "does_not_exist": CapabilityEdit(
                        role="x"
                    )
                },
            )

    def test_editing_nonexistent_capability_writes_nothing(
        self,
    ) -> None:
        preview = self._base_preview()

        try:
            apply_preview_edits(
                preview,
                {
                    "does_not_exist": CapabilityEdit(
                        role="x"
                    ),
                    "measure_power": CapabilityEdit(
                        role="consumption"
                    ),
                },
            )
        except ValueError:
            pass

        # Původní preview zůstává nedotčené i když jeden z editů
        # v dávce byl neplatný.
        self.assertEqual(
            preview.instance["role_bindings"][
                "capabilities"
            ]["measure_power"],
            "power_now",
        )

    # --- validate_device_instance nad editovaným Preview ---

    def test_edited_preview_passes_validate_device_instance(
        self,
    ) -> None:
        device = _second_xiaomi_plug_device()
        preview = build_instance_preview(
            homey_device=device,
            template=self.template,
            instance_name="Mraznička",
            loxone_name_base="Mraznička",
        )

        edited = apply_preview_edits(
            preview,
            {
                "measure_power": CapabilityEdit(
                    role="consumption",
                    display_name="Mraznička - Příkon",
                )
            },
        )

        result = validate_device_instance(
            edited.instance,
            homey_device=device,
            template=self.template,
            existing_instances={},
            mode=SaveMode.CREATE,
        )

        self.assertTrue(result.is_valid, result.problems)

    def test_editing_key_to_invalid_format_is_caught_by_validate(
        self,
    ) -> None:
        device = _second_xiaomi_plug_device()
        preview = build_instance_preview(
            homey_device=device,
            template=self.template,
            instance_name="Mraznička",
            loxone_name_base="Mraznička",
        )

        edited = apply_preview_edits(
            preview,
            {
                "measure_power": CapabilityEdit(
                    key="Not Valid Key!"
                )
            },
        )

        result = validate_device_instance(
            edited.instance,
            homey_device=device,
            template=self.template,
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


if __name__ == "__main__":
    unittest.main()
