from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from loxbridge.templates import (
    DEFAULT_TEMPLATES_DIR,
    load_all_templates,
    load_template,
    validate_template,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_TEMPLATE_PATH = (
    ROOT / "config" / "templates" / "xiaomi_mi.plug_maeu01.yaml"
)


def _valid_template(**overrides) -> dict:
    base = {
        "template_id": "vendor.model",
        "version": 1,
        "label": "Vendor Model",
        "match": {
            "driver_id": "homey:app:vendor:model",
            "requires_capabilities": ["onoff"],
            "excludes_capabilities": [],
        },
        "capabilities": {
            "onoff": {
                "role": "power",
                "direction": "bidirectional",
                "datatype": "boolean",
                "key_suffix": "power",
                "display_suffix": "Zapnutí",
                "transform": [],
            }
        },
        "commands": [],
        "events": [],
    }
    base.update(overrides)
    return base


class ValidateTemplateTests(unittest.TestCase):
    def test_valid_template_has_no_problems(self) -> None:
        self.assertEqual(
            validate_template(_valid_template()), []
        )

    def test_missing_template_id(self) -> None:
        template = _valid_template()
        del template["template_id"]

        problems = validate_template(template)

        self.assertTrue(
            any("template_id" in p for p in problems)
        )

    def test_invalid_version(self) -> None:
        for bad_version in (0, -1, "1", None, True):
            with self.subTest(bad_version=bad_version):
                template = _valid_template(
                    version=bad_version
                )
                problems = validate_template(template)
                self.assertTrue(
                    any("version" in p for p in problems)
                )

    def test_missing_match_section(self) -> None:
        template = _valid_template()
        del template["match"]

        problems = validate_template(template)

        self.assertTrue(
            any("match" in p for p in problems)
        )

    def test_missing_driver_id(self) -> None:
        template = _valid_template()
        template["match"] = {
            "requires_capabilities": [],
            "excludes_capabilities": [],
        }

        problems = validate_template(template)

        self.assertTrue(
            any("driver_id" in p for p in problems)
        )

    def test_requires_capabilities_must_be_string_list(
        self,
    ) -> None:
        template = _valid_template()
        template["match"]["requires_capabilities"] = "onoff"

        problems = validate_template(template)

        self.assertTrue(
            any(
                "requires_capabilities" in p
                for p in problems
            )
        )

    def test_empty_capabilities_section(self) -> None:
        template = _valid_template(capabilities={})

        problems = validate_template(template)

        self.assertTrue(
            any("capabilities" in p for p in problems)
        )

    def test_missing_role(self) -> None:
        template = _valid_template()
        del template["capabilities"]["onoff"]["role"]

        problems = validate_template(template)

        self.assertTrue(
            any("role" in p for p in problems)
        )

    def test_invalid_direction(self) -> None:
        template = _valid_template()
        template["capabilities"]["onoff"]["direction"] = (
            "sideways"
        )

        problems = validate_template(template)

        self.assertTrue(
            any("direction" in p for p in problems)
        )

    def test_invalid_datatype(self) -> None:
        template = _valid_template()
        template["capabilities"]["onoff"]["datatype"] = (
            "banana"
        )

        problems = validate_template(template)

        self.assertTrue(
            any("datatype" in p for p in problems)
        )

    def test_commands_and_events_must_be_lists(self) -> None:
        template = _valid_template(
            commands={"not": "a list"}
        )

        problems = validate_template(template)

        self.assertTrue(
            any("commands" in p for p in problems)
        )


class LoadTemplateTests(unittest.TestCase):
    def test_load_and_save_roundtrip(self) -> None:
        template = _valid_template()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vendor.model.yaml"

            with path.open("w", encoding="utf-8") as file:
                yaml.safe_dump(template, file)

            loaded = load_template(path)

        self.assertEqual(loaded, template)

    def test_load_all_templates_keyed_by_template_id(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)

            for template_id in ("a.one", "b.two"):
                template = _valid_template(
                    template_id=template_id
                )

                path = directory / f"{template_id}.yaml"

                with path.open(
                    "w", encoding="utf-8"
                ) as file:
                    yaml.safe_dump(template, file)

            loaded = load_all_templates(directory)

        self.assertEqual(set(loaded), {"a.one", "b.two"})

    def test_load_all_templates_missing_directory_returns_empty(
        self,
    ) -> None:
        missing = Path(tempfile.mkdtemp()) / "does-not-exist"

        self.assertEqual(load_all_templates(missing), {})


class SampleTemplateFileTests(unittest.TestCase):
    """Ukázkový template v config/templates/ musí být sám o sobě
    validní a musí odpovídat reálným datům, ze kterých vychází."""

    def test_sample_template_file_is_valid(self) -> None:
        template = load_template(SAMPLE_TEMPLATE_PATH)

        self.assertEqual(validate_template(template), [])

    def test_sample_template_matches_documented_real_device(
        self,
    ) -> None:
        template = load_template(SAMPLE_TEMPLATE_PATH)

        self.assertEqual(
            template["match"]["driver_id"],
            "homey:app:com.xiaomi-mi:plug.maeu01",
        )
        self.assertEqual(
            set(
                template["match"]["requires_capabilities"]
            ),
            {"onoff", "measure_power", "meter_power"},
        )


if __name__ == "__main__":
    unittest.main()
