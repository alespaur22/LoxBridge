"""Assign Template to Existing Instance: pure Build/Preview for
attaching a Device Template to an already-configured (legacy) Device
Instance, without ever touching its already-authoritative identity,
``keys`` or ``display_names``.

Unlike ``loxbridge.instance_builder.build_instance_preview()`` (which
builds a brand-new instance FROM a template), this module only ever
*adds* to an EXISTING instance:

- ``template`` / ``template_version`` (provenance/pin - never a
  runtime dependency, see ``loxbridge/instances.py``),
- ``role_bindings.capabilities`` entries for capabilities the instance
  already maps but doesn't yet have a role for,
- ``overrides.capabilities`` bookkeeping, recomputed the same way
  ``loxbridge.instance_builder.apply_preview_edits`` does.

It never invents a new key, never renames a display name, and never
silently overwrites a role_binding that already disagrees with the
template - such disagreements are reported as conflicts for a human to
resolve, never auto-resolved. A template capability the instance
doesn't currently map is reported, never added automatically. An
instance capability the template doesn't know about is left
completely alone and reported too.

Like every other Build/Preview step, this has no I/O and writes
nothing. The resulting draft goes through the exact same
``validate_device_instance(..., mode=SaveMode.REPLACE)`` and
``save_device_instance()`` as any other instance update - there is no
separate write path for template assignment.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from loxbridge.instance_overrides import (
    CapabilityDefault,
    diverged_fields,
)
from loxbridge.template_matching import (
    MatchKind,
    match_templates,
)


@dataclass(frozen=True)
class RoleConflict:
    capability_id: str
    existing_role: str
    template_role: str


@dataclass(frozen=True)
class TemplateAssignmentPreview:
    instance: dict[str, Any]
    # V template i v instanci, ale instance na ně dosud nemá key -
    # nikdy se nepřidává automaticky, jen se reportuje.
    missing_instance_capabilities: tuple[str, ...]
    # V instanci, ale template o nich nic neví - ponechány beze
    # změny, jen reportovány.
    unmatched_instance_capabilities: tuple[str, ...]
    # Capability, kde instance už měla jinou roli než navrhuje
    # template - existující hodnota se NIKDY tiše nepřepíše.
    conflicts: tuple[RoleConflict, ...]
    # Čistě diagnostické - jestli tenhle template podle
    # match_templates() na tohle zařízení vůbec jednoznačně sedí.
    # Assignment se stává neplatným až přes validate_device_instance()
    # (stejný "template_mismatch" check jako u Configure NEW) - tohle
    # pole existuje jen proto, aby to GUI mohlo zobrazit v Preview bez
    # nutnosti volat validátor zvlášť.
    template_matches_device: bool


def _section_dict(
    parent: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    value = parent.get(key)

    return dict(value) if isinstance(value, dict) else {}


def build_template_assignment_preview(
    *,
    existing_instance: dict[str, Any],
    homey_device: dict[str, Any],
    template: dict[str, Any],
) -> TemplateAssignmentPreview:
    """Pure function - nikdy nemutuje `existing_instance`,
    `homey_device` ani `template`.

    Po návratu je `instance["keys"]` a `instance["display_names"]`
    value-for-value identické s `existing_instance["keys"]`/
    `existing_instance["display_names"]` - tahle funkce do nich nikdy
    nezapisuje, jen z nich čte pro diagnostiku a pro přepočet
    `overrides`. Stejně tak `key_base`, `instance_name`,
    `loxone_name_base` a `homey_id` zůstávají beze změny.
    """
    instance = copy.deepcopy(existing_instance)

    template_id = template.get("template_id")
    template_version = template.get("version")

    template_capabilities = template.get("capabilities")

    if not isinstance(template_capabilities, dict):
        template_capabilities = {}

    keys_capabilities = _section_dict(
        _section_dict(instance, "keys"), "capabilities"
    )
    display_names_capabilities = _section_dict(
        _section_dict(instance, "display_names"),
        "capabilities",
    )

    # role_bindings může u starších (legacy) instancí chybět úplně -
    # normalizuje se na symetrický tvar, ale existující role se nikdy
    # neztratí ani nepřepíší.
    existing_role_bindings = instance.get("role_bindings")

    if not isinstance(existing_role_bindings, dict):
        existing_role_bindings = {}

    role_bindings_capabilities = _section_dict(
        existing_role_bindings, "capabilities"
    )
    role_bindings_commands = _section_dict(
        existing_role_bindings, "commands"
    )
    role_bindings_events = _section_dict(
        existing_role_bindings, "events"
    )

    instance_capability_ids = set(keys_capabilities)
    template_capability_ids = {
        capability_id
        for capability_id, mapping in (
            template_capabilities.items()
        )
        if isinstance(mapping, dict)
    }

    missing = sorted(
        template_capability_ids - instance_capability_ids
    )
    unmatched = sorted(
        instance_capability_ids - template_capability_ids
    )

    key_base = instance.get("key_base") or ""
    loxone_name_base = instance.get("loxone_name_base") or ""

    conflicts: list[RoleConflict] = []
    overrides_capabilities: dict[str, list[str]] = {}

    for capability_id in sorted(
        instance_capability_ids & template_capability_ids
    ):
        mapping = template_capabilities[capability_id]

        template_role = mapping.get("role")
        key_suffix = mapping.get("key_suffix")
        display_suffix = mapping.get("display_suffix")

        default = CapabilityDefault(
            role=template_role,
            key=(
                f"{key_base}_{key_suffix}"
                if key_suffix
                else None
            ),
            display_name=(
                f"{loxone_name_base} - {display_suffix}"
                if display_suffix
                else None
            ),
        )

        existing_role = role_bindings_capabilities.get(
            capability_id
        )

        if existing_role is None:
            # Role zatím není nastavená - template ji smí předvyplnit.
            role_bindings_capabilities[capability_id] = (
                template_role
            )
            final_role = template_role

        elif existing_role == template_role:
            final_role = existing_role

        else:
            # Role už existuje a liší se - NIKDY tiše nepřepsat.
            conflicts.append(
                RoleConflict(
                    capability_id=capability_id,
                    existing_role=existing_role,
                    template_role=template_role,
                )
            )
            final_role = existing_role

        diverged = diverged_fields(
            role=final_role,
            key=keys_capabilities.get(capability_id),
            display_name=(
                display_names_capabilities.get(
                    capability_id
                )
            ),
            default=default,
        )

        if diverged:
            overrides_capabilities[capability_id] = (
                diverged
            )

    # Jediné klíče instance, které tahle operace smí zapsat:
    # template/template_version/role_bindings/overrides. keys,
    # display_names, key_base, instance_name, loxone_name_base,
    # homey_id a vše ostatní zůstává tím, co bylo deep-copy'nuto z
    # existující instance beze změny.
    instance["template"] = template_id
    instance["template_version"] = template_version
    instance["role_bindings"] = {
        "capabilities": role_bindings_capabilities,
        "commands": role_bindings_commands,
        "events": role_bindings_events,
    }
    instance["overrides"] = {
        "capabilities": overrides_capabilities,
        "commands": {},
        "events": {},
    }

    match_result = match_templates(
        homey_device,
        {template_id: template},
    )

    template_matches_device = (
        match_result.kind == MatchKind.EXACT
        and match_result.candidate_template_ids
        == (template_id,)
    )

    return TemplateAssignmentPreview(
        instance=instance,
        missing_instance_capabilities=tuple(missing),
        unmatched_instance_capabilities=tuple(unmatched),
        conflicts=tuple(conflicts),
        template_matches_device=template_matches_device,
    )
