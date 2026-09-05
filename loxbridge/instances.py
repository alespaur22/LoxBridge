"""Device Instance data model.

A Device Instance is the persistent, user-owned record for one physical
Homey device that LoxBridge exposes to Loxone. It is the future source
of truth for that device's Loxone-facing identity:

- ``homey_id`` is the stable *internal* identity (a Homey device UUID).
  It is used only to look up the instance record and is never written
  into a Loxone-visible key or display name.
- ``key_base`` is a frozen, human-readable slug used to build technical
  Loxone keys (``bojler_power``). It is set once, from the device name
  at the time the instance is created, and is never recomputed from a
  later Homey rename.
- ``loxone_name_base`` is a frozen, human-readable base used to build
  the display names Loxone shows for each virtual input/output
  (``"Bojler - Zapnutí"``). Also frozen at creation, independent of
  ``key_base`` so the two can diverge later (e.g. a nicer display name
  without touching already-wired technical keys).
- ``instance_name`` is a separate, purely cosmetic label meant for a
  future GUI device list; it is not used to derive keys or names.
- ``keys`` / ``display_names`` hold the actual per-capability,
  per-command and per-event values. Once written, nothing in this
  module recomputes them automatically.
- ``role_bindings`` records, per capability/command/event, which
  stable semantic *role* (e.g. ``power``, ``power_now``) it plays.
  This is authoritative instance data, not an audit trail: a
  hand-configured instance that never used any Device Template is
  just as complete and valid with a hand-typed ``role_bindings`` as
  one that was pre-filled from a template. A template (see
  ``loxbridge/templates.py``) is only ever a source of a *default
  proposal* for ``keys``/``display_names``/``role_bindings`` at
  instance creation or explicit upgrade time - once written, the
  instance owns this data outright. ``template``/``template_version``
  record only the origin/pin used for that proposal, never a runtime
  dependency.

This module only defines the data shape and file I/O. Nothing in the
existing generate/runtime pipeline (``loxbridge.generate``,
``loxbridge.bridge``, ``realtime.mjs``, the XML generators) reads from
or writes to it yet, and this module never touches
``config/config.generated.yaml``. Wiring a future ``generate`` run to
consume Device Instances - including the rule that it must never
silently create/update a persisted instance record for a new template
role - is a separate, later step.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import yaml


INSTANCE_SCHEMA_VERSION = 1

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INSTANCES_DIR = PROJECT_ROOT / "config" / "devices"


def _capability_key_value_maps(
    capabilities: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    keys: dict[str, Any] = {}
    names: dict[str, Any] = {}

    for capability_id, capability in capabilities.items():
        if not isinstance(capability, dict):
            continue

        keys[capability_id] = capability.get("key")
        names[capability_id] = capability.get("loxone_name")

    return keys, names


def _command_key_value_maps(
    commands: list[Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    keys: dict[str, Any] = {}
    names: dict[str, Any] = {}

    for command in commands:
        if not isinstance(command, dict):
            continue

        role = command.get("kind")

        if not role:
            continue

        keys[role] = command.get("key")
        names[role] = command.get("title")

    return keys, names


def _event_role(
    event_key: str,
    key_base: str,
) -> str:
    prefix = f"{key_base}_" if key_base else ""

    if prefix and event_key.startswith(prefix):
        return event_key[len(prefix):]

    return event_key


def _event_key_value_maps(
    events: list[Any],
    key_base: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    keys: dict[str, Any] = {}
    names: dict[str, Any] = {}

    for event in events:
        if not isinstance(event, dict):
            continue

        full_key = str(event.get("key") or "")

        if not full_key:
            continue

        role = _event_role(full_key, key_base)

        keys[role] = event.get("key")
        names[role] = event.get("title")

    return keys, names


def build_instance_from_generated_device(
    device: dict[str, Any],
) -> dict[str, Any]:
    """Build a Device Instance record from one entry of
    ``config.generated.yaml``'s ``devices`` list.

    Pure function: takes an already-generated device dict, returns the
    instance dict. Reads and writes no files, and captures today's
    already-computed keys/names verbatim instead of recomputing
    anything - that is what makes the migration lossless.
    """
    homey_id = device.get("homey_id")

    if not homey_id:
        raise ValueError(
            "Zařízení "
            f"{device.get('name')!r} "
            "nemá homey_id - nelze "
            "vytvořit Device Instance."
        )

    device_name = str(device.get("name") or "")
    key_base = str(device.get("slug") or "")

    capabilities = device.get("capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}

    loxbridge = device.get("loxbridge")
    if not isinstance(loxbridge, dict):
        loxbridge = {}

    commands = loxbridge.get("commands")
    if not isinstance(commands, list):
        commands = []

    events = loxbridge.get("events")
    if not isinstance(events, list):
        events = []

    capability_keys, capability_names = (
        _capability_key_value_maps(capabilities)
    )

    command_keys, command_names = (
        _command_key_value_maps(commands)
    )

    event_keys, event_names = _event_key_value_maps(
        events,
        key_base,
    )

    return {
        "schema_version": INSTANCE_SCHEMA_VERSION,
        "instance_id": homey_id,
        "homey_id": homey_id,
        "homey_name_last_seen": device_name,
        "instance_name": device_name,
        "loxone_name_base": device_name,
        "key_base": key_base,
        "enabled": True,
        # Zatím nepřiřazeno - model-specific templates jsou
        # samostatný, pozdější krok. legacy_profile jen dokumentuje,
        # jaký profil dnešní Profile Engine pro zařízení určil.
        "template": None,
        "template_version": None,
        "legacy_profile": loxbridge.get("profile"),
        "homey_meta": {
            "class": device.get("homey_class"),
            "driver_id": device.get("driver_id"),
            "zone_name": device.get("zone_name"),
        },
        # Migrace nepoužívá žádný template, takže role zatím nejsou
        # známé - prázdné, ale přítomné ve stejném symetrickém tvaru
        # jako keys/display_names, aby byl formát instancí od začátku
        # konzistentní bez ohledu na to, jestli/kdy se k nim template
        # přiřadí.
        "role_bindings": {
            "capabilities": {},
            "commands": {},
            "events": {},
        },
        "keys": {
            "capabilities": capability_keys,
            "commands": command_keys,
            "events": event_keys,
        },
        "display_names": {
            "capabilities": capability_names,
            "commands": command_names,
            "events": event_names,
        },
        "overrides": {},
    }


def instance_filename(instance: dict[str, Any]) -> str:
    homey_id = str(instance["homey_id"])

    return f"{homey_id}.yaml"


def save_instance(
    instance: dict[str, Any],
    directory: Path,
) -> Path:
    """Atomický zápis: obsah se napíše do dočasného souboru ve stejném
    adresáři a teprve po úspěšném zápisu se `os.replace()`-ne přes
    cílovou cestu. Pád procesu uprostřed zápisu tak nikdy nenechá
    poškozený ani částečně přepsaný instance soubor - buď se objeví
    celý nový obsah, nebo zůstane beze změny ten starý.
    """
    directory.mkdir(parents=True, exist_ok=True)

    path = directory / instance_filename(instance)

    tmp_path = (
        directory
        / f".{path.name}.{uuid.uuid4().hex}.tmp"
    )

    try:
        with tmp_path.open(
            "w", encoding="utf-8"
        ) as file:
            yaml.safe_dump(
                instance,
                file,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
                width=120,
            )

        os.replace(tmp_path, path)

    except BaseException:
        tmp_path.unlink(missing_ok=True)

        raise

    return path


def load_instance(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError(
            f"Soubor {path} neobsahuje "
            "platnou Device Instance."
        )

    return data


def load_all_instances(
    directory: Path,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    if not directory.is_dir():
        return result

    for path in sorted(directory.glob("*.yaml")):
        instance = load_instance(path)

        homey_id = instance.get("homey_id")

        if isinstance(homey_id, str) and homey_id:
            result[homey_id] = instance

    return result


def contains_identity_leak(
    instance: dict[str, Any],
) -> bool:
    """True if the internal ``homey_id`` shows up inside any
    Loxone-visible key or display name of this instance.

    This is the concrete guard for the rule that homey_id must stay an
    internal lookup index only, never a user-visible string.
    """
    homey_id = str(instance.get("homey_id") or "")

    if not homey_id:
        return False

    def _walk(value: Any) -> bool:
        if isinstance(value, str):
            return homey_id in value

        if isinstance(value, dict):
            return any(_walk(item) for item in value.values())

        if isinstance(value, list):
            return any(_walk(item) for item in value)

        return False

    return _walk(instance.get("keys")) or _walk(
        instance.get("display_names")
    )
