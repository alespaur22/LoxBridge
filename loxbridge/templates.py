"""Device Template data model.

A Device Template describes one specific Homey product/model - not a
generic category - and a default role/key/display-name mapping for its
capabilities.

Templates are only ever a source of a *default proposal*. When a
Device Instance is created (or later, explicitly upgraded), a template
can pre-fill its mapping - but once written, the instance's own
``keys``/``display_names``/``role_bindings`` (see
``loxbridge/instances.py``) are the authoritative, standalone
configuration for that physical device. A hand-configured instance
that never used any template at all (``template: null``,
``template_version: null``) is just as valid and complete as one that
started from a template.

Nothing in the generate/runtime pipeline (``loxbridge.generate``,
``loxbridge.bridge``, ``realtime.mjs``, the XML generators) reads this
module, and this module never writes a Device Instance itself - the
tool that actually applies a template's default mapping onto an
instance (create or explicit upgrade) is separate, deliberately
not part of this step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from loxbridge.capability_filter import SUPPORTED_TYPES


TEMPLATE_SCHEMA_VERSION = 1

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TEMPLATES_DIR = PROJECT_ROOT / "config" / "templates"

VALID_DIRECTIONS = {
    "homey_to_loxone",
    "loxone_to_homey",
    "bidirectional",
}


def load_template(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError(
            f"Soubor {path} neobsahuje platný Device Template."
        )

    return data


def load_all_templates(
    directory: Path,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    if not directory.is_dir():
        return result

    for path in sorted(directory.glob("*.yaml")):
        template = load_template(path)

        template_id = template.get("template_id")

        if isinstance(template_id, str) and template_id:
            result[template_id] = template

    return result


def validate_template(
    template: dict[str, Any],
) -> list[str]:
    """Vrátí seznam problémů - prázdný seznam znamená validní template.

    Nevyhazuje výjimku - volající (CLI, budoucí GUI, testy) si sám
    rozhodne, jak přísně na chyby reagovat.
    """
    problems: list[str] = []

    template_id = template.get("template_id")

    if not isinstance(template_id, str) or not template_id:
        problems.append("Chybí nebo neplatné template_id.")

    version = template.get("version")

    if not isinstance(version, int) or isinstance(
        version, bool
    ) or version < 1:
        problems.append(
            "Chybí nebo neplatné version "
            "(musí být kladné celé číslo)."
        )

    match = template.get("match")

    if not isinstance(match, dict):
        problems.append("Chybí sekce match.")

    else:
        driver_id = match.get("driver_id")

        if not isinstance(driver_id, str) or not driver_id:
            problems.append(
                "match.driver_id chybí nebo je prázdné."
            )

        for field_name in (
            "requires_capabilities",
            "excludes_capabilities",
        ):
            value = match.get(field_name, [])

            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                problems.append(
                    f"match.{field_name} musí být "
                    "seznam řetězců."
                )

    capabilities = template.get("capabilities")

    if not isinstance(capabilities, dict) or not capabilities:
        problems.append(
            "Sekce capabilities chybí nebo je prázdná."
        )

    else:
        for (
            capability_id,
            mapping,
        ) in capabilities.items():
            if not isinstance(mapping, dict):
                problems.append(
                    f"capabilities.{capability_id} "
                    "musí být objekt."
                )

                continue

            role = mapping.get("role")

            if not isinstance(role, str) or not role:
                problems.append(
                    f"capabilities.{capability_id}.role "
                    "chybí nebo je prázdné."
                )

            direction = mapping.get("direction")

            if direction not in VALID_DIRECTIONS:
                problems.append(
                    f"capabilities.{capability_id}."
                    "direction neplatný: "
                    f"{direction!r}."
                )

            datatype = mapping.get("datatype")

            if datatype not in SUPPORTED_TYPES:
                problems.append(
                    f"capabilities.{capability_id}."
                    "datatype neplatný: "
                    f"{datatype!r}."
                )

    for list_field in ("commands", "events"):
        value = template.get(list_field, [])

        if not isinstance(value, list):
            problems.append(
                f"{list_field} musí být seznam."
            )

    return problems
