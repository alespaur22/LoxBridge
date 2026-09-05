"""Shared, reusable Device Instance validation.

One validator, used identically by every write path that will ever
exist for a Device Instance: Configure NEW (this step), and later -
unchanged - generic instance editing, assigning a template to a
legacy instance, and template upgrades. It operates on a plain
instance dict, never on a builder-specific object like
``loxbridge.instance_builder.InstancePreview``, so every future caller
shares exactly the same integrity rules instead of re-implementing
them.

Never modifies anything - it only reports problems. ``save_instance``-
style write helpers must call this and refuse to write on any error-
severity problem; they must never carry their own, separate copy of
these checks.

Two severities:
- ``error`` - blocks a write (``ValidationResult.is_valid`` is False).
- ``warning`` - surfaced for a human/GUI to see, never blocks a write.
  Used for things that are informative but not inherently wrong (e.g.
  a template capability the device doesn't currently use).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loxbridge.capability_filter import should_include_capability
from loxbridge.instances import contains_identity_leak
from loxbridge.template_matching import MatchKind, match_templates


_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

_SECTIONS = ("capabilities", "commands", "events")


class SaveMode(str, Enum):
    CREATE = "create"
    REPLACE = "replace"


@dataclass(frozen=True)
class ValidationProblem:
    code: str
    message: str
    severity: str = "error"
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationResult:
    problems: tuple[ValidationProblem, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not any(
            problem.severity == "error"
            for problem in self.problems
        )

    def errors(self) -> tuple[ValidationProblem, ...]:
        return tuple(
            problem
            for problem in self.problems
            if problem.severity == "error"
        )

    def warnings(self) -> tuple[ValidationProblem, ...]:
        return tuple(
            problem
            for problem in self.problems
            if problem.severity == "warning"
        )


def _device_capability_ids(
    homey_device: dict[str, Any],
) -> set[str]:
    capabilities = homey_device.get("capabilities")

    if not isinstance(capabilities, list):
        return set()

    ids: set[str] = set()

    for capability in capabilities:
        if not isinstance(capability, dict):
            continue

        if not should_include_capability(capability):
            continue

        capability_id = capability.get("id")

        if isinstance(capability_id, str) and capability_id:
            ids.add(capability_id)

    return ids


def _section_dict(
    parent: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    value = parent.get(key)

    return value if isinstance(value, dict) else {}


def validate_device_instance(
    instance: dict[str, Any],
    *,
    homey_device: dict[str, Any] | None,
    template: dict[str, Any] | None,
    existing_instances: dict[str, dict[str, Any]],
    mode: SaveMode,
) -> ValidationResult:
    """Čistá funkce - žádné I/O, žádná mutace žádného parametru.

    `homey_device`/`template` jsou volitelné: kontroly, které je
    potřebují (shoda se zařízením, pokrytí template capabilities),
    se provedou jen tehdy, když jsou předané - jinak se prostě
    vynechají (např. obecná úprava instance beze změny template
    nemusí mít po ruce živá Homey data).
    """
    problems: list[ValidationProblem] = []

    homey_id = instance.get("homey_id")

    if not isinstance(homey_id, str) or not homey_id:
        problems.append(
            ValidationProblem(
                "missing_homey_id",
                "Instance nemá platné homey_id.",
            )
        )

        return ValidationResult(tuple(problems))

    # --- tvar keys/display_names/role_bindings ---
    keys = instance.get("keys")
    display_names = instance.get("display_names")
    role_bindings = instance.get("role_bindings")

    for section_name, section in (
        ("keys", keys),
        ("display_names", display_names),
        ("role_bindings", role_bindings),
    ):
        if not isinstance(section, dict) or not all(
            isinstance(section.get(name), dict)
            for name in _SECTIONS
        ):
            problems.append(
                ValidationProblem(
                    "malformed_shape",
                    f"{section_name} musí mít tvar "
                    "{capabilities, commands, events}, "
                    "každé jako dict.",
                    detail={"section": section_name},
                )
            )

    keys = keys if isinstance(keys, dict) else {}
    display_names = (
        display_names
        if isinstance(display_names, dict)
        else {}
    )
    role_bindings = (
        role_bindings
        if isinstance(role_bindings, dict)
        else {}
    )

    capability_keys = _section_dict(keys, "capabilities")
    capability_names = _section_dict(
        display_names, "capabilities"
    )
    capability_roles = _section_dict(
        role_bindings, "capabilities"
    )

    if set(capability_keys) != set(capability_names):
        problems.append(
            ValidationProblem(
                "malformed_shape",
                "keys.capabilities a display_names.capabilities "
                "nemají stejnou množinu capability id.",
            )
        )

    if not set(capability_roles).issubset(
        set(capability_keys)
    ):
        problems.append(
            ValidationProblem(
                "malformed_shape",
                "role_bindings.capabilities obsahuje capability "
                "id, které není v keys.capabilities "
                "(role bez klíče).",
            )
        )

    # --- formát a kolize klíčů v rámci téže instance ---
    all_keys: list[tuple[str, str, str]] = []

    for category in _SECTIONS:
        section = _section_dict(keys, category)

        for identifier, key in section.items():
            if not isinstance(key, str) or not (
                _KEY_PATTERN.match(key)
            ):
                problems.append(
                    ValidationProblem(
                        "invalid_key_format",
                        "Neplatný formát klíče pro "
                        f"{category}.{identifier}: "
                        f"{key!r}.",
                        detail={
                            "category": category,
                            "identifier": identifier,
                            "key": key,
                        },
                    )
                )

            else:
                all_keys.append(
                    (key, category, identifier)
                )

    seen_keys: dict[str, tuple[str, str]] = {}

    for key, category, identifier in all_keys:
        if key in seen_keys:
            other_category, other_identifier = seen_keys[
                key
            ]

            problems.append(
                ValidationProblem(
                    "key_collision_within_instance",
                    f"Klíč {key!r} je použitý víckrát "
                    f"v téže instanci "
                    f"({other_category}.{other_identifier} "
                    f"a {category}.{identifier}).",
                    detail={"key": key},
                )
            )

        else:
            seen_keys[key] = (category, identifier)

    # --- únik identity ---
    if contains_identity_leak(instance):
        problems.append(
            ValidationProblem(
                "identity_leak",
                "homey_id uniká do viditelných "
                "keys/display_names.",
            )
        )

    # --- konzistence s Homey zařízením ---
    if homey_device is not None:
        device_id = homey_device.get("id")

        if device_id != homey_id:
            problems.append(
                ValidationProblem(
                    "homey_device_mismatch",
                    "Předaný homey_device "
                    f"(id={device_id!r}) neodpovídá "
                    f"instance.homey_id ({homey_id!r}).",
                )
            )

        else:
            device_capability_ids = (
                _device_capability_ids(homey_device)
            )

            for capability_id in capability_keys:
                if (
                    capability_id
                    not in device_capability_ids
                ):
                    problems.append(
                        ValidationProblem(
                            "unknown_capability",
                            "Instance mapuje capability "
                            f"{capability_id!r}, kterou "
                            "zařízení nemá (nebo neprojde "
                            "should_include_capability).",
                            detail={
                                "capability_id": (
                                    capability_id
                                )
                            },
                        )
                    )

    # --- konzistence s template ---
    if template is not None:
        template_id = template.get("template_id")

        if instance.get("template") != template_id:
            problems.append(
                ValidationProblem(
                    "template_reference_mismatch",
                    f"Předaný template {template_id!r} "
                    "neodpovídá instance.template "
                    f"({instance.get('template')!r}).",
                )
            )

        elif homey_device is not None:
            match_result = match_templates(
                homey_device,
                {template_id: template},
            )

            if not (
                match_result.kind == MatchKind.EXACT
                and match_result.candidate_template_ids
                == (template_id,)
            ):
                problems.append(
                    ValidationProblem(
                        "template_mismatch",
                        f"Template {template_id!r} podle "
                        "match_templates() na tohle "
                        "zařízení jednoznačně nesedí "
                        f"(výsledek: "
                        f"{match_result.kind.value}).",
                    )
                )

            template_capabilities = template.get(
                "capabilities"
            )

            if isinstance(template_capabilities, dict):
                device_capability_ids = (
                    _device_capability_ids(homey_device)
                )

                for (
                    capability_id
                ) in template_capabilities:
                    if (
                        capability_id
                        in device_capability_ids
                        and capability_id
                        not in capability_keys
                    ):
                        problems.append(
                            ValidationProblem(
                                "unmapped_template_"
                                "capability",
                                "Template nabízí mapping "
                                f"pro {capability_id!r}, "
                                "které je na zařízení "
                                "dostupné, ale instance "
                                "ho nevyužívá.",
                                severity="warning",
                                detail={
                                    "capability_id": (
                                        capability_id
                                    )
                                },
                            )
                        )

    # --- CREATE/REPLACE a kolize s ostatními instancemi ---
    if (
        mode == SaveMode.CREATE
        and homey_id in existing_instances
    ):
        problems.append(
            ValidationProblem(
                "duplicate_homey_id",
                f"homey_id {homey_id!r} už má existující "
                "instanci (mode=CREATE).",
            )
        )

    if (
        mode == SaveMode.REPLACE
        and homey_id not in existing_instances
    ):
        problems.append(
            ValidationProblem(
                "instance_not_found",
                f"homey_id {homey_id!r} nemá existující "
                "instanci k nahrazení (mode=REPLACE).",
            )
        )

    others = {
        other_id: other_instance
        for other_id, other_instance in (
            existing_instances.items()
        )
        if other_id != homey_id
    }

    candidate_keys = {
        key for key, _category, _identifier in all_keys
    }

    for other_id, other_instance in others.items():
        other_keys_section = (
            other_instance.get("keys")
            if isinstance(
                other_instance.get("keys"), dict
            )
            else {}
        )

        other_keys: set[str] = set()

        for category in _SECTIONS:
            section = _section_dict(
                other_keys_section, category
            )

            other_keys.update(
                value
                for value in section.values()
                if isinstance(value, str)
            )

        for key in candidate_keys & other_keys:
            problems.append(
                ValidationProblem(
                    "key_collision_with_other_instance",
                    f"Klíč {key!r} koliduje s existující "
                    f"instancí {other_id}.",
                    detail={
                        "key": key,
                        "other_homey_id": other_id,
                    },
                )
            )

    return ValidationResult(tuple(problems))
