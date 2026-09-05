"""Jediný zdroj pravdy pro to, které syrové Homey capabilities
LoxBridge vůbec bere v potaz.

Používá jak generate pipeline (`loxbridge.generate`, aby rozhodla, co
skutečně skončí v `config.generated.yaml`), tak read-only device status
report (`loxbridge.device_status`, aby odvodila, jestli má zařízení
vůbec něco "bridgeable", nezávisle na tom, jestli už má Device
Instance).

Přesunuto beze změny chování z `loxbridge/generate.py` - tělo funkce
a konstanty jsou identické, jen mají teď jediné místo, odkud se
importují, místo dvou nezávislých kopií.
"""

from __future__ import annotations

from typing import Any


SUPPORTED_TYPES = {
    "boolean",
    "number",
    "enum",
    "string",
}


IGNORED_CAPABILITY_PREFIXES = (
    "devicecapabilities_",
)


IGNORED_CAPABILITIES = {
    "button",
}


def should_include_capability(
    capability: dict[str, Any],
) -> bool:
    capability_id = str(
        capability.get(
            "id",
            "",
        )
    )

    capability_type = (
        capability.get(
            "type"
        )
    )

    getable = capability.get(
        "getable"
    )

    if not capability_id:
        return False

    if getable is not True:
        return False

    if (
        capability_type
        not in SUPPORTED_TYPES
    ):
        return False

    if (
        capability_id
        in IGNORED_CAPABILITIES
    ):
        return False

    if capability_id.startswith(
        IGNORED_CAPABILITY_PREFIXES
    ):
        return False

    return True
