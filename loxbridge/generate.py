import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from loxbridge.addon.translations import (
    get_capability_title,
)
from loxbridge.capability_filter import (
    should_include_capability,
)
from loxbridge.instances import (
    DEFAULT_INSTANCES_DIR,
    load_all_instances,
)
from loxbridge.profiles import (
    PROFILE_SCHEMA_VERSION,
    build_device_manifest,
)
from loxbridge.slug import slugify


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)

EXPORT_PATH = (
    PROJECT_ROOT
    / "exports"
    / "homey_devices.json"
)

CURRENT_CONFIG_PATH = (
    PROJECT_ROOT
    / "config"
    / "config.yaml"
)

GENERATED_CONFIG_PATH = (
    PROJECT_ROOT
    / "config"
    / "config.generated.yaml"
)


# Speciální mapování Homey enumů
# na hodnoty používané blokem
# Klimatizace v Loxone.
#
# operation_mode:
#   1 = Auto
#   2 = Heat
#   3 = Cool
#   4 = Dry
#   5 = Fan
#
# fan_speed:
#   0 = Off       - řeší samostatné onoff
#   1 = Auto
#   2 = Silent    - rezervováno
#   3 = Low
#   4 = LowMid
#   5 = Mid
#   6 = HighMid
#   7 = High
LOXONE_ENUM_MAPPINGS: dict[
    str,
    dict[str, int],
] = {
    "operation_mode": {
        "Auto": 1,
        "Heat": 2,
        "Cool": 3,
        "Dry": 4,
        "Fan": 5,
    },
    "fan_speed": {
        "Auto": 1,
        "Low": 3,
        "LowMid": 4,
        "Mid": 5,
        "HighMid": 6,
        "High": 7,
    },
}


def load_yaml(
    path: Path,
) -> dict[str, Any]:
    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = yaml.safe_load(
                file
            )

    except FileNotFoundError as error:
        raise RuntimeError(
            "Soubor nebyl nalezen: "
            f"{path}"
        ) from error

    except yaml.YAMLError as error:
        raise RuntimeError(
            "Neplatný YAML v souboru "
            f"{path}: {error}"
        ) from error

    if not isinstance(
        data,
        dict,
    ):
        raise RuntimeError(
            f"Soubor {path} "
            "neobsahuje YAML objekt."
        )

    return data


def load_export(
    path: Path,
) -> dict[str, Any]:
    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(
                file
            )

    except FileNotFoundError as error:
        raise RuntimeError(
            "Export zařízení nebyl "
            f"nalezen: {path}\n"
            "Nejdřív spusť:\n"
            "node "
            "loxbridge/homey/"
            "export_devices.mjs"
        ) from error

    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Neplatný JSON v souboru "
            f"{path}: {error}"
        ) from error

    if not isinstance(
        data,
        dict,
    ):
        raise RuntimeError(
            "Export zařízení "
            "neobsahuje JSON objekt."
        )

    devices = data.get(
        "devices"
    )

    if not isinstance(
        devices,
        list,
    ):
        raise RuntimeError(
            "V exportu chybí "
            "seznam devices."
        )

    return data


def build_enum_values(
    capability_id: str,
    capability: dict[str, Any],
) -> list[dict[str, Any]]:
    values = capability.get(
        "values"
    )

    if not isinstance(
        values,
        list,
    ):
        return []

    valid_values: list[
        dict[str, Any]
    ] = []

    for value in values:
        if not isinstance(
            value,
            dict,
        ):
            continue

        if (
            value.get("id")
            is None
        ):
            continue

        valid_values.append(
            value
        )

    mapping = (
        LOXONE_ENUM_MAPPINGS.get(
            capability_id
        )
    )

    # Speciální Loxone mapování
    # použijeme pouze tehdy,
    # pokud známe všechny enum
    # hodnoty dané capability.
    #
    # Pokud např. jiná integrace
    # používá capability fan_speed
    # s jinými enum hodnotami,
    # automaticky se vrátíme
    # k běžnému číslování 0..n.
    use_loxone_mapping = (
        mapping is not None
        and bool(valid_values)
        and all(
            str(value["id"])
            in mapping
            for value
            in valid_values
        )
    )

    result: list[
        dict[str, Any]
    ] = []

    for index, value in enumerate(
        valid_values
    ):
        value_id = str(
            value["id"]
        )

        value_title = (
            value.get(
                "title"
            )
        )

        if (
            use_loxone_mapping
            and mapping is not None
        ):
            numeric_value = (
                mapping[value_id]
            )

        else:
            numeric_value = index

        result.append(
            {
                "id": value_id,
                "title": (
                    str(
                        value_title
                    )
                    if (
                        value_title
                        is not None
                    )
                    else value_id
                ),
                "value": (
                    numeric_value
                ),
            }
        )

    return result


def build_capability(
    device_name: str,
    capability: dict[str, Any],
    loxone_key: str,
) -> dict[str, Any]:
    capability_id = str(
        capability["id"]
    )

    title = (
        get_capability_title(
            capability_id,
            capability.get(
                "title"
            ),
        )
    )

    capability_type = (
        capability.get(
            "type"
        )
    )

    unit = capability.get(
        "units"
    )

    data: dict[
        str,
        Any,
    ] = {
        "key": loxone_key,
        "type": capability_type,
        "title": title,
        "loxone_name": (
            f"{device_name} - "
            f"{title}"
        ),
        "setable": bool(
            capability.get(
                "setable",
                False,
            )
        ),
    }

    if unit:
        data["unit"] = unit

    if (
        capability_type
        == "enum"
    ):
        enum_values = (
            build_enum_values(
                capability_id,
                capability,
            )
        )

        if enum_values:
            data["values"] = (
                enum_values
            )

    return data


def make_unique_key(
    base_key: str,
    used_keys: set[str],
) -> str:
    if (
        base_key
        not in used_keys
    ):
        used_keys.add(
            base_key
        )

        return base_key

    counter = 2

    while True:
        candidate = (
            f"{base_key}_"
            f"{counter}"
        )

        if (
            candidate
            not in used_keys
        ):
            used_keys.add(
                candidate
            )

            return candidate

        counter += 1


def _event_role(
    event_key: str,
    key_base: str,
) -> str:
    prefix = f"{key_base}_" if key_base else ""

    if prefix and event_key.startswith(prefix):
        return event_key[len(prefix):]

    return event_key


def apply_instance_overrides(
    generated_device: dict[str, Any],
    instance: dict[str, Any] | None,
) -> None:
    """Přepíše key/title/loxone_name generovaného zařízení hodnotami
    z jeho Device Instance, in place.

    Profile Engine (loxbridge.profiles) už rozhodl, jaké capabilities/
    commands/events zařízení má, a build_capability()/build_commands()/
    build_event_inputs() pro ně dopočítaly výchozí (slug-based) key a
    název. Tahle funkce nic nepřidává ani neodebírá - jen pro role, pro
    které má instance uloženou hodnotu, tu výchozí hodnotu nahradí
    zamrzlou hodnotou z instance. Role, které instance nezná (chybí
    v config/devices/, nebo instance danou roli ještě nemá uloženou),
    zůstávají na dnešním dopočítaném chování - to je fallback popsaný
    v návrhu. Instance samotná se tu nikdy nezapisuje ani neupravuje.
    """
    if not instance:
        return

    keys = instance.get("keys") or {}
    display_names = instance.get("display_names") or {}

    capability_keys = keys.get("capabilities") or {}
    capability_names = (
        display_names.get("capabilities") or {}
    )

    capabilities = (
        generated_device.get("capabilities") or {}
    )

    for capability_id, capability in capabilities.items():
        if not isinstance(capability, dict):
            continue

        if capability_id in capability_keys:
            capability["key"] = capability_keys[
                capability_id
            ]

        if capability_id in capability_names:
            capability["loxone_name"] = capability_names[
                capability_id
            ]

    loxbridge = generated_device.get("loxbridge") or {}

    command_keys = keys.get("commands") or {}
    command_names = display_names.get("commands") or {}

    for command in loxbridge.get("commands") or []:
        if not isinstance(command, dict):
            continue

        role = command.get("kind")

        if role in command_keys:
            command["key"] = command_keys[role]

        if role in command_names:
            command["title"] = command_names[role]

    event_keys = keys.get("events") or {}
    event_names = display_names.get("events") or {}

    # Role eventu se odvozuje odseknutím key_base prefixu z klíče -
    # stejně jako to dělala migrace. Použije se zamrzlý key_base
    # z instance (ne aktuální slug zařízení), aby přiřazení fungovalo
    # i po přejmenování zařízení v Homey.
    event_key_base = str(
        instance.get("key_base")
        or generated_device.get("slug")
        or ""
    )

    for event in loxbridge.get("events") or []:
        if not isinstance(event, dict):
            continue

        full_key = str(event.get("key") or "")

        role = _event_role(full_key, event_key_base)

        if role in event_keys:
            event["key"] = event_keys[role]

        if role in event_names:
            event["title"] = event_names[role]


def generate_devices(
    exported_devices: list[
        dict[str, Any]
    ],
    instances: dict[str, dict[str, Any]] | None = None,
) -> tuple[
    list[dict[str, Any]],
    int,
]:
    generated_devices: list[
        dict[str, Any]
    ] = []

    used_keys: set[str] = set()

    capability_count = 0

    name_counts = Counter(
        str(
            device.get(
                "name",
                "",
            )
        ).strip()
        for device
        in exported_devices
    )

    for device in exported_devices:
        device_name = str(
            device.get(
                "name",
                "",
            )
        ).strip()

        device_id = str(
            device.get(
                "id",
                "",
            )
        ).strip()

        if not device_name:
            continue

        device_slug = slugify(
            device_name
        )

        if (
            name_counts[
                device_name
            ] > 1
            and device_id
        ):
            device_slug = (
                f"{device_slug}_"
                f"{device_id[:8]}"
            )

        generated_capabilities: dict[
            str,
            dict[str, Any],
        ] = {}

        capabilities = (
            device.get(
                "capabilities",
                [],
            )
        )

        if not isinstance(
            capabilities,
            list,
        ):
            continue

        for capability in capabilities:
            if not isinstance(
                capability,
                dict,
            ):
                continue

            if not (
                should_include_capability(
                    capability
                )
            ):
                continue

            capability_id = str(
                capability["id"]
            )

            capability_slug = (
                slugify(
                    capability_id
                )
            )

            base_key = (
                f"{device_slug}_"
                f"{capability_slug}"
            )

            loxone_key = (
                make_unique_key(
                    base_key,
                    used_keys,
                )
            )

            generated_capabilities[
                capability_id
            ] = build_capability(
                device_name=(
                    device_name
                ),
                capability=(
                    capability
                ),
                loxone_key=(
                    loxone_key
                ),
            )

            capability_count += 1

        if not (
            generated_capabilities
        ):
            continue

        generated_device: dict[
            str,
            Any,
        ] = {
            "name": device_name,
            "slug": device_slug,
            "homey_class": device.get("class"),
            "driver_id": device.get("driver_id"),
            "zone_name": device.get("zone_name"),
            "capabilities": (
                generated_capabilities
            ),
            "loxbridge": build_device_manifest(
                exported_device=device,
                device_name=device_name,
                device_slug=device_slug,
                capabilities=generated_capabilities,
            ),
        }

        if device_id:
            generated_device[
                "homey_id"
            ] = device_id

        instance = (
            instances.get(device_id)
            if instances and device_id
            else None
        )

        apply_instance_overrides(
            generated_device,
            instance,
        )

        generated_devices.append(
            generated_device
        )

    return (
        generated_devices,
        capability_count,
    )


def build_generated_config(
    current_config: dict[
        str,
        Any,
    ],
    export_data: dict[
        str,
        Any,
    ],
    instances: dict[str, dict[str, Any]] | None = None,
) -> tuple[
    dict[str, Any],
    int,
]:
    homey_config = (
        current_config.get(
            "homey"
        )
    )

    loxone_config = (
        current_config.get(
            "loxone"
        )
    )

    if not isinstance(
        homey_config,
        dict,
    ):
        raise RuntimeError(
            "V config.yaml "
            "chybí sekce homey."
        )

    if not isinstance(
        loxone_config,
        dict,
    ):
        raise RuntimeError(
            "V config.yaml "
            "chybí sekce loxone."
        )

    exported_devices = (
        export_data[
            "devices"
        ]
    )

    (
        generated_devices,
        capability_count,
    ) = generate_devices(
        exported_devices,
        instances=instances,
    )

    generated_config = {
        "loxbridge": {
            "schema_version": PROFILE_SCHEMA_VERSION,
        },
        "homey": (
            homey_config
        ),
        "loxone": (
            loxone_config
        ),
        "devices": (
            generated_devices
        ),
    }

    return (
        generated_config,
        capability_count,
    )


def save_generated_config(
    config: dict[str, Any],
    path: Path,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        yaml.safe_dump(
            config,
            file,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=120,
        )


def _register_key(
    seen: dict[str, tuple[str, str, str]],
    collisions: list[str],
    key: Any,
    device_name: str,
    category: str,
    role: Any,
) -> None:
    if not key:
        return

    key = str(key)

    if key in seen:
        previous_device, previous_category, previous_role = (
            seen[key]
        )

        collisions.append(
            f"  {key!r}: "
            f"{previous_device} / {previous_category} / "
            f"{previous_role}  ×  "
            f"{device_name} / {category} / {role}"
        )

        return

    seen[key] = (device_name, category, role)


def validate_unique_keys(
    generated_config: dict[str, Any],
) -> None:
    """Ověří, že žádné dva Loxone klíče v celém config.generated.yaml
    nekolidují - napříč capabilities, commands i events, přes všechna
    zařízení.

    Kolize je chyba konfigurace, ne něco, co se má tiše přejmenovat -
    volající (generate_and_save) tuhle funkci musí zavolat před
    zápisem výstupu a při chybě soubor vůbec nezapisovat.
    """
    seen: dict[str, tuple[str, str, str]] = {}
    collisions: list[str] = []

    devices = generated_config.get("devices") or []

    for device in devices:
        if not isinstance(device, dict):
            continue

        device_name = str(device.get("name", ""))

        capabilities = device.get("capabilities") or {}

        for capability_id, capability in capabilities.items():
            if not isinstance(capability, dict):
                continue

            _register_key(
                seen,
                collisions,
                capability.get("key"),
                device_name,
                "capability",
                capability_id,
            )

        loxbridge = device.get("loxbridge") or {}

        for command in loxbridge.get("commands") or []:
            if not isinstance(command, dict):
                continue

            _register_key(
                seen,
                collisions,
                command.get("key"),
                device_name,
                "command",
                command.get("kind"),
            )

        for event in loxbridge.get("events") or []:
            if not isinstance(event, dict):
                continue

            _register_key(
                seen,
                collisions,
                event.get("key"),
                device_name,
                "event",
                event.get("key"),
            )

    if collisions:
        raise RuntimeError(
            "Kolize Loxone klíčů - generate zastaven, "
            "výstupní soubor nebyl zapsán:\n"
            + "\n".join(collisions)
        )


def generate_and_save(
    *,
    current_config_path: Path,
    export_path: Path,
    output_path: Path,
    instances_dir: Path,
) -> tuple[dict[str, Any], int]:
    """Kompletní pipeline generate → validace → zápis.

    Validace unikátnosti klíčů proběhne vždy před zápisem výstupu.
    Pokud selže (nebo selže cokoliv dřívějšího), output_path se vůbec
    neotevře pro zápis, takže existující soubor na téhle cestě zůstane
    nedotčený.
    """
    current_config = load_yaml(current_config_path)
    export_data = load_export(export_path)
    instances = load_all_instances(instances_dir)

    generated_config, capability_count = build_generated_config(
        current_config=current_config,
        export_data=export_data,
        instances=instances,
    )

    validate_unique_keys(generated_config)

    save_generated_config(
        config=generated_config,
        path=output_path,
    )

    return generated_config, capability_count


def main() -> None:
    print(
        "LoxBridge Config Generator"
    )

    print(
        "=========================="
    )

    print(
        f"Export:        "
        f"{EXPORT_PATH}"
    )

    print(
        f"Zdroj configu: "
        f"{CURRENT_CONFIG_PATH}"
    )

    print(
        f"Výstup:        "
        f"{GENERATED_CONFIG_PATH}"
    )

    print()

    instances = load_all_instances(
        DEFAULT_INSTANCES_DIR
    )

    print(
        "Device Instance store: "
        f"{len(instances)} "
        "instancí "
        f"({DEFAULT_INSTANCES_DIR})"
    )

    print()

    (
        generated_config,
        capability_count,
    ) = generate_and_save(
        current_config_path=(
            CURRENT_CONFIG_PATH
        ),
        export_path=EXPORT_PATH,
        output_path=(
            GENERATED_CONFIG_PATH
        ),
        instances_dir=(
            DEFAULT_INSTANCES_DIR
        ),
    )

    device_count = len(
        generated_config[
            "devices"
        ]
    )

    print(
        "Generování dokončeno."
    )

    print(
        "Zařízení v konfiguraci: "
        f"{device_count}"
    )

    print(
        "Capabilities:           "
        f"{capability_count}"
    )

    profile_counts = Counter(
        str(
            device.get(
                "loxbridge", {}
            ).get(
                "profile",
                "generic",
            )
        )
        for device in generated_config["devices"]
        if isinstance(device, dict)
    )

    print()
    print("Profily:")

    for profile_id, count in sorted(
        profile_counts.items()
    ):
        print(
            f"  {profile_id:<28} "
            f"{count}"
        )

    print()

    print(
        "Funkční config.yaml "
        "nebyl změněn."
    )

    print(
        "Nový návrh je uložen v: "
        f"{GENERATED_CONFIG_PATH}"
    )


if __name__ == "__main__":
    try:
        main()

    except RuntimeError as error:
        print(
            f"Chyba: {error}",
            file=sys.stderr,
        )

        raise SystemExit(
            1
        ) from error