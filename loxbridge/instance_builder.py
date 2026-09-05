"""Build/Preview: pure construction of a NEW, template-based Device
Instance draft.

No I/O, no mutation of inputs, and no Profile Engine involvement - a
Device Template already answers "what is this device", more
specifically than Profile Engine's generic category detection, so
building a template-based instance never calls
``loxbridge.profiles.build_device_manifest()``.

This module only builds the *default* draft straight from a template.
It is deliberately not the place that would build a hand-edited
instance, an "assign template to a legacy instance" draft, or a
template-upgrade draft - those are separate, later operations. All of
them (this one included) end up validated by the exact same
``loxbridge.instance_validation.validate_device_instance()``, which
never depends on anything from this module.

``apply_preview_edits()`` lets a caller (a future GUI) change the
pre-filled role/key/display_name for a capability before Save. It is
just as pure/no-I/O as ``build_instance_preview()``: it returns a new
``InstancePreview`` and never mutates the one it was given.

To decide which fields currently diverge from the template (recorded
in ``instance["overrides"]`` purely as bookkeeping for a future GUI -
never a second source of truth; the *value* always lives only in
``role_bindings``/``keys``/``display_names``), the preview carries the
original, pristine template defaults alongside the instance draft in
``capability_defaults``. This is deliberately a *sibling* dataclass
field, not part of ``instance`` itself - it exists only to make the
override diff correct and is never written into the Device Instance
that ``save_device_instance()`` persists. Every ``apply_preview_edits``
call carries the same ``capability_defaults`` forward unchanged, so
overrides are always recomputed against the true original defaults,
never against whatever the previous edit happened to produce - that is
what lets reverting a field back to its template default make its
override entry disappear again, instead of accumulating an
append-only edit history.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from loxbridge.capability_filter import should_include_capability
from loxbridge.instance_overrides import (
    CapabilityDefault,
    diverged_fields,
)
from loxbridge.instances import INSTANCE_SCHEMA_VERSION
from loxbridge.slug import slugify


@dataclass(frozen=True)
class InstancePreview:
    instance: dict[str, Any]
    # Template capabilities that exist in the template but were not
    # found on this particular device (or didn't pass
    # should_include_capability). Purely diagnostic - a device
    # legitimately not having every optional capability a template
    # knows about is not a defect; see
    # loxbridge.instance_validation's "unmapped_template_capability"
    # warning for the same fact recomputed independently at validate
    # time.
    unmapped_template_capabilities: tuple[str, ...]
    # Original template defaults per mapped capability_id - the
    # baseline that apply_preview_edits() diffs overrides against.
    # Not part of `instance`; never saved.
    capability_defaults: dict[str, CapabilityDefault] = field(
        default_factory=dict
    )


def _raw_capabilities_by_id(
    homey_device: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    capabilities = homey_device.get("capabilities")

    if not isinstance(capabilities, list):
        return {}

    result: dict[str, dict[str, Any]] = {}

    for capability in capabilities:
        if not isinstance(capability, dict):
            continue

        capability_id = capability.get("id")

        if isinstance(capability_id, str) and capability_id:
            result[capability_id] = capability

    return result


def build_instance_preview(
    *,
    homey_device: dict[str, Any],
    template: dict[str, Any],
    instance_name: str,
    loxone_name_base: str,
    key_base: str | None = None,
) -> InstancePreview:
    homey_id = homey_device.get("id")

    if not isinstance(homey_id, str) or not homey_id:
        raise ValueError(
            "homey_device nemá platné id - nelze "
            "sestavit Device Instance."
        )

    resolved_key_base = (
        key_base if key_base else slugify(instance_name)
    )

    raw_capabilities = _raw_capabilities_by_id(
        homey_device
    )

    template_capabilities = template.get("capabilities")

    if not isinstance(template_capabilities, dict):
        template_capabilities = {}

    role_bindings_capabilities: dict[str, str] = {}
    keys_capabilities: dict[str, str] = {}
    display_names_capabilities: dict[str, str] = {}
    capability_defaults: dict[str, CapabilityDefault] = {}
    unmapped: list[str] = []

    for (
        capability_id,
        mapping,
    ) in template_capabilities.items():
        if not isinstance(mapping, dict):
            continue

        raw_capability = raw_capabilities.get(
            capability_id
        )

        if raw_capability is None or not (
            should_include_capability(raw_capability)
        ):
            unmapped.append(capability_id)

            continue

        role = mapping.get("role")
        key_suffix = mapping.get("key_suffix")
        display_suffix = mapping.get("display_suffix")

        key = f"{resolved_key_base}_{key_suffix}"
        display_name = (
            f"{loxone_name_base} - {display_suffix}"
        )

        role_bindings_capabilities[capability_id] = role
        keys_capabilities[capability_id] = key
        display_names_capabilities[capability_id] = (
            display_name
        )
        capability_defaults[capability_id] = (
            CapabilityDefault(
                role=role,
                key=key,
                display_name=display_name,
            )
        )

    instance = {
        "schema_version": INSTANCE_SCHEMA_VERSION,
        "instance_id": homey_id,
        "homey_id": homey_id,
        "homey_name_last_seen": homey_device.get(
            "name"
        ),
        "instance_name": instance_name,
        "loxone_name_base": loxone_name_base,
        "key_base": resolved_key_base,
        "enabled": True,
        "template": template.get("template_id"),
        "template_version": template.get("version"),
        "legacy_profile": None,
        "homey_meta": {
            "class": homey_device.get("class"),
            "driver_id": homey_device.get(
                "driver_id"
            ),
            "zone_name": homey_device.get(
                "zone_name"
            ),
        },
        "role_bindings": {
            "capabilities": role_bindings_capabilities,
            "commands": {},
            "events": {},
        },
        "keys": {
            "capabilities": keys_capabilities,
            "commands": {},
            "events": {},
        },
        "display_names": {
            "capabilities": display_names_capabilities,
            "commands": {},
            "events": {},
        },
        "overrides": {
            "capabilities": {},
            "commands": {},
            "events": {},
        },
    }

    return InstancePreview(
        instance=instance,
        unmapped_template_capabilities=tuple(
            sorted(unmapped)
        ),
        capability_defaults=capability_defaults,
    )


@dataclass(frozen=True)
class CapabilityEdit:
    role: str | None = None
    key: str | None = None
    display_name: str | None = None


def apply_preview_edits(
    preview: InstancePreview,
    edits: dict[str, CapabilityEdit],
) -> InstancePreview:
    """Pure function - nikdy nemutuje `preview` ani `preview.instance`.

    Editovat lze jen capability, které v kandidátní instanci už
    existují (byly namapované `build_instance_preview()`) - odkaz na
    cokoliv jiného vyhodí `ValueError`. role/key/display_name se mění
    nezávisle: úprava role nikdy sama nezmění key ani display_name
    (a naopak) a hodnoty se zapisují přesně tak, jak byly předané -
    žádné slugování, žádné automatické opravy.

    `overrides.capabilities` se při každém volání přepočítá od nuly
    jako diff proti `preview.capability_defaults` (originální,
    nezměněné template defaulty zachycené jednou při stavbě) - nikdy
    proti aktuálnímu, případně už dřív upravenému stavu instance. Díky
    tomu vrácení pole zpátky na výchozí hodnotu z template příslušný
    override zase odstraní, místo aby se hromadila append-only historie
    změn.
    """
    instance = copy.deepcopy(preview.instance)

    capability_keys = instance["keys"]["capabilities"]
    capability_names = instance["display_names"][
        "capabilities"
    ]
    capability_roles = instance["role_bindings"][
        "capabilities"
    ]

    for capability_id, edit in edits.items():
        if capability_id not in capability_keys:
            raise ValueError(
                "Nelze editovat capability "
                f"{capability_id!r} - v kandidátní "
                "instanci vůbec neexistuje."
            )

        if edit.role is not None:
            capability_roles[capability_id] = edit.role

        if edit.key is not None:
            capability_keys[capability_id] = edit.key

        if edit.display_name is not None:
            capability_names[capability_id] = (
                edit.display_name
            )

    overrides_capabilities: dict[str, list[str]] = {}

    for (
        capability_id,
        default,
    ) in preview.capability_defaults.items():
        if capability_id not in capability_keys:
            continue

        diverged = diverged_fields(
            role=capability_roles.get(capability_id),
            key=capability_keys.get(capability_id),
            display_name=capability_names.get(
                capability_id
            ),
            default=default,
        )

        if diverged:
            overrides_capabilities[capability_id] = (
                diverged
            )

    instance["overrides"] = {
        "capabilities": overrides_capabilities,
        "commands": {},
        "events": {},
    }

    return InstancePreview(
        instance=instance,
        unmapped_template_capabilities=(
            preview.unmapped_template_capabilities
        ),
        capability_defaults=preview.capability_defaults,
    )
