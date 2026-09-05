"""Read-only Device Template matching against a raw Homey export
device.

Matching classifies a device against the loaded templates into exactly
one of three tiers (``MatchKind``) and never assigns anything by
itself - it only answers "which template(s), if any, would apply".
Writing a chosen template's mapping into a Device Instance is a
separate, explicit, not-yet-built tool; this module has no side
effects and touches no files.

``driver_id`` is always the required, primary identifier - a template
never matches across a different ``driver_id``. Some Homey apps use a
single ``driver_id`` for several distinct physical products (verified
in this project's own export data: every Shelly device shares
``homey:app:cloud.shelly:shelly`` regardless of model), so
``match.requires_capabilities``/``match.excludes_capabilities`` exist
to disambiguate *within* an already driver_id-matched candidate set -
never as a substitute for driver_id, and never across different
driver_ids.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class MatchKind(str, Enum):
    NO_MATCH = "no_match"
    EXACT = "exact"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class MatchResult:
    kind: MatchKind
    candidate_template_ids: tuple[str, ...] = ()


def _raw_capability_ids(
    device: dict[str, Any],
) -> set[str]:
    capabilities = device.get("capabilities")

    if not isinstance(capabilities, list):
        return set()

    ids: set[str] = set()

    for capability in capabilities:
        if not isinstance(capability, dict):
            continue

        capability_id = capability.get("id")

        if isinstance(capability_id, str) and capability_id:
            ids.add(capability_id)

    return ids


def _template_matches(
    template: dict[str, Any],
    *,
    device_driver_id: str,
    device_capability_ids: set[str],
) -> bool:
    match = template.get("match")

    if not isinstance(match, dict):
        return False

    driver_id = match.get("driver_id")

    if driver_id != device_driver_id:
        return False

    requires = match.get("requires_capabilities") or []

    if not set(requires).issubset(device_capability_ids):
        return False

    excludes = match.get("excludes_capabilities") or []

    if set(excludes) & device_capability_ids:
        return False

    return True


def match_templates(
    device: dict[str, Any],
    templates: dict[str, dict[str, Any]],
) -> MatchResult:
    """Čistá funkce - žádné I/O, žádná mutace `device`/`templates`.

    `device` je jeden syrový záznam z exports/homey_devices.json
    (jedna položka pole `devices`). `templates` je výstup
    `loxbridge.templates.load_all_templates()`.

    Nikdy nic nepřiřazuje - jen klasifikuje do NO_MATCH / EXACT /
    AMBIGUOUS. Kandidáti v AMBIGUOUS jsou seřazení deterministicky
    (podle template_id), ne podle pořadí souborů na disku.
    """
    device_driver_id = device.get("driver_id")

    if (
        not isinstance(device_driver_id, str)
        or not device_driver_id
    ):
        return MatchResult(kind=MatchKind.NO_MATCH)

    device_capability_ids = _raw_capability_ids(device)

    candidates = tuple(
        sorted(
            template_id
            for template_id, template in templates.items()
            if _template_matches(
                template,
                device_driver_id=device_driver_id,
                device_capability_ids=device_capability_ids,
            )
        )
    )

    if not candidates:
        return MatchResult(kind=MatchKind.NO_MATCH)

    if len(candidates) == 1:
        return MatchResult(
            kind=MatchKind.EXACT,
            candidate_template_ids=candidates,
        )

    return MatchResult(
        kind=MatchKind.AMBIGUOUS,
        candidate_template_ids=candidates,
    )
