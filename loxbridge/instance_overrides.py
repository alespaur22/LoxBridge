"""Sdílený override-diff primitiv.

Používá jak stavba zcela nové, template-based instance
(`loxbridge.instance_builder`), tak přiřazení template existující
instanci (`loxbridge.template_assignment`): pro danou capability
porovná její AKTUÁLNÍ (role, key, display_name) s tím, co by template
navrhl jako výchozí hodnotu, a vrátí seznam polí, která se rozešla.

Je to čistě bookkeeping - nikdy nerozhoduje ani neurčuje výslednou
hodnotu, jen reportuje, která pole už neodpovídají svému template
defaultu. Skutečná hodnota vždy žije jen v `role_bindings`/`keys`/
`display_names` instance.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityDefault:
    """Pristine, template-derived hodnoty pro jednu capability -
    nikdy se nemutují, nikdy se nepersistují do Device Instance
    samotné."""

    role: str | None
    key: str | None
    display_name: str | None


# Fixní pořadí, ve kterém se pole kontrolují proti výchozím hodnotám -
# deterministické bez ohledu na pořadí iterace dictu.
OVERRIDE_FIELD_ORDER = ("role", "key", "display_name")


def diverged_fields(
    *,
    role: str | None,
    key: str | None,
    display_name: str | None,
    default: CapabilityDefault,
) -> list[str]:
    current = {
        "role": role,
        "key": key,
        "display_name": display_name,
    }

    defaults = {
        "role": default.role,
        "key": default.key,
        "display_name": default.display_name,
    }

    return [
        field_name
        for field_name in OVERRIDE_FIELD_ORDER
        if current[field_name] != defaults[field_name]
    ]
