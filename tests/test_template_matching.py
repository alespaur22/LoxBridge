from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from loxbridge.template_matching import (
    MatchKind,
    match_templates,
)
from loxbridge.templates import load_template


ROOT = Path(__file__).resolve().parents[1]
EXPORT_PATH = ROOT / "exports" / "homey_devices.json"
SAMPLE_TEMPLATE_PATH = (
    ROOT / "config" / "templates" / "xiaomi_mi.plug_maeu01.yaml"
)


def _template(
    template_id: str,
    driver_id: str,
    requires: list[str] | None = None,
    excludes: list[str] | None = None,
) -> dict:
    return {
        "template_id": template_id,
        "version": 1,
        "label": template_id,
        "match": {
            "driver_id": driver_id,
            "requires_capabilities": requires or [],
            "excludes_capabilities": excludes or [],
        },
        "capabilities": {},
        "commands": [],
        "events": [],
    }


def _synthetic_device(
    driver_id: str, capability_ids: list[str]
) -> dict:
    return {
        "id": "dev-1",
        "name": "Test Device",
        "driver_id": driver_id,
        "capabilities": [
            {"id": cid} for cid in capability_ids
        ],
    }


class SyntheticMatchingTests(unittest.TestCase):
    def test_no_candidates_is_no_match(self) -> None:
        device = _synthetic_device(
            "homey:app:vendor:x", ["onoff"]
        )
        templates = {
            "other": _template(
                "other", "homey:app:vendor:y"
            )
        }

        result = match_templates(device, templates)

        self.assertEqual(result.kind, MatchKind.NO_MATCH)
        self.assertEqual(result.candidate_template_ids, ())

    def test_driver_id_mismatch_never_matches_on_capabilities_alone(
        self,
    ) -> None:
        device = _synthetic_device(
            "homey:app:vendor:x",
            ["onoff", "measure_power"],
        )
        templates = {
            "wrong_driver": _template(
                "wrong_driver",
                "homey:app:vendor:y",
                requires=["onoff", "measure_power"],
            )
        }

        result = match_templates(device, templates)

        self.assertEqual(result.kind, MatchKind.NO_MATCH)

    def test_single_matching_template_is_exact(self) -> None:
        device = _synthetic_device(
            "homey:app:vendor:x",
            ["onoff", "measure_power"],
        )
        templates = {
            "vendor.x": _template(
                "vendor.x",
                "homey:app:vendor:x",
                requires=["onoff"],
            )
        }

        result = match_templates(device, templates)

        self.assertEqual(result.kind, MatchKind.EXACT)
        self.assertEqual(
            result.candidate_template_ids, ("vendor.x",)
        )

    def test_missing_required_capability_is_no_match(
        self,
    ) -> None:
        device = _synthetic_device(
            "homey:app:vendor:x", ["onoff"]
        )
        templates = {
            "vendor.x": _template(
                "vendor.x",
                "homey:app:vendor:x",
                requires=["onoff", "measure_power"],
            )
        }

        result = match_templates(device, templates)

        self.assertEqual(result.kind, MatchKind.NO_MATCH)

    def test_present_excluded_capability_is_no_match(
        self,
    ) -> None:
        device = _synthetic_device(
            "homey:app:vendor:x",
            ["onoff", "light_hue"],
        )
        templates = {
            "vendor.x": _template(
                "vendor.x",
                "homey:app:vendor:x",
                requires=["onoff"],
                excludes=["light_hue"],
            )
        }

        result = match_templates(device, templates)

        self.assertEqual(result.kind, MatchKind.NO_MATCH)

    def test_two_matching_templates_same_driver_is_ambiguous(
        self,
    ) -> None:
        device = _synthetic_device(
            "homey:app:vendor:x",
            ["onoff", "measure_power"],
        )
        templates = {
            "vendor.x.broad": _template(
                "vendor.x.broad",
                "homey:app:vendor:x",
                requires=["onoff"],
            ),
            "vendor.x.narrow": _template(
                "vendor.x.narrow",
                "homey:app:vendor:x",
                requires=["onoff", "measure_power"],
            ),
        }

        result = match_templates(device, templates)

        self.assertEqual(result.kind, MatchKind.AMBIGUOUS)
        self.assertEqual(
            result.candidate_template_ids,
            ("vendor.x.broad", "vendor.x.narrow"),
        )

    def test_candidate_order_is_deterministic(self) -> None:
        device = _synthetic_device(
            "homey:app:vendor:x", ["onoff"]
        )
        templates_forward = {
            "z.template": _template(
                "z.template", "homey:app:vendor:x"
            ),
            "a.template": _template(
                "a.template", "homey:app:vendor:x"
            ),
        }
        templates_reversed = {
            "a.template": templates_forward["a.template"],
            "z.template": templates_forward["z.template"],
        }

        result_a = match_templates(
            device, templates_forward
        )
        result_b = match_templates(
            device, templates_reversed
        )

        self.assertEqual(
            result_a.candidate_template_ids,
            ("a.template", "z.template"),
        )
        self.assertEqual(
            result_a.candidate_template_ids,
            result_b.candidate_template_ids,
        )

    def test_no_driver_id_on_device_is_no_match(self) -> None:
        device = {
            "id": "dev-1",
            "name": "No driver",
            "capabilities": [{"id": "onoff"}],
        }
        templates = {
            "vendor.x": _template(
                "vendor.x", "homey:app:vendor:x"
            )
        }

        result = match_templates(device, templates)

        self.assertEqual(result.kind, MatchKind.NO_MATCH)

    def test_pure_function_does_not_mutate_inputs(self) -> None:
        device = _synthetic_device(
            "homey:app:vendor:x", ["onoff"]
        )
        templates = {
            "vendor.x": _template(
                "vendor.x", "homey:app:vendor:x"
            )
        }

        device_before = copy.deepcopy(device)
        templates_before = copy.deepcopy(templates)

        match_templates(device, templates)

        self.assertEqual(device, device_before)
        self.assertEqual(templates, templates_before)


class RealExportMatchingTests(unittest.TestCase):
    """Matching ověřený proti reálnému, git-trackovanému
    exports/homey_devices.json - včetně reálného scénáře, kde více
    zařízení sdílí stejné driver_id (Shelly), a proto je
    excludes_capabilities nutné pro spolehlivé rozlišení modelů."""

    @classmethod
    def setUpClass(cls) -> None:
        export_data = json.loads(
            EXPORT_PATH.read_text(encoding="utf-8")
        )
        cls.devices_by_name = {
            device["name"]: device
            for device in export_data["devices"]
        }

    def test_xiaomi_plug_template_exactly_matches_real_device(
        self,
    ) -> None:
        template = load_template(SAMPLE_TEMPLATE_PATH)
        device = self.devices_by_name["Bazénová filtrace"]

        result = match_templates(
            device,
            {template["template_id"]: template},
        )

        self.assertEqual(result.kind, MatchKind.EXACT)
        self.assertEqual(
            result.candidate_template_ids,
            (template["template_id"],),
        )

    def test_xiaomi_plug_template_does_not_match_other_real_devices(
        self,
    ) -> None:
        template = load_template(SAMPLE_TEMPLATE_PATH)
        other_device = self.devices_by_name["LED Obývák"]

        result = match_templates(
            other_device,
            {template["template_id"]: template},
        )

        self.assertEqual(result.kind, MatchKind.NO_MATCH)

    def test_shared_shelly_driver_id_without_excludes_is_ambiguous(
        self,
    ) -> None:
        # Real LED Koupelna je Shelly RGBW, ale MÁ i onoff/
        # measure_power/meter_power vedle RGBW capabilities - proto
        # bez excludes_capabilities by "obecný relé" template
        # kolidoval s "RGBW" templatem na stejném zařízení.
        device = self.devices_by_name["LED Koupelna"]

        rgbw_template = _template(
            "shelly.rgbw",
            "homey:app:cloud.shelly:shelly",
            requires=["dim", "light_hue", "light_saturation"],
        )
        relay_template_without_excludes = _template(
            "shelly.relay_naive",
            "homey:app:cloud.shelly:shelly",
            requires=["onoff", "measure_power", "meter_power"],
        )

        result = match_templates(
            device,
            {
                "shelly.rgbw": rgbw_template,
                "shelly.relay_naive": (
                    relay_template_without_excludes
                ),
            },
        )

        self.assertEqual(result.kind, MatchKind.AMBIGUOUS)

    def test_excludes_capabilities_disambiguates_real_shelly_device(
        self,
    ) -> None:
        device = self.devices_by_name["LED Koupelna"]

        rgbw_template = _template(
            "shelly.rgbw",
            "homey:app:cloud.shelly:shelly",
            requires=["dim", "light_hue", "light_saturation"],
        )
        relay_template_with_excludes = _template(
            "shelly.relay_strict",
            "homey:app:cloud.shelly:shelly",
            requires=["onoff", "measure_power", "meter_power"],
            excludes=["light_hue"],
        )

        result = match_templates(
            device,
            {
                "shelly.rgbw": rgbw_template,
                "shelly.relay_strict": (
                    relay_template_with_excludes
                ),
            },
        )

        self.assertEqual(result.kind, MatchKind.EXACT)
        self.assertEqual(
            result.candidate_template_ids,
            ("shelly.rgbw",),
        )


if __name__ == "__main__":
    unittest.main()
