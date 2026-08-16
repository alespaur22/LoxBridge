import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from loxbridge.addon.translations import (
    get_capability_title,
)
from loxbridge.profiles import (
    PROFILE_SCHEMA_VERSION,
    build_device_manifest,
)


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


def slugify(
    value: str,
) -> str:
    normalized = unicodedata.normalize(
        "NFKD",
        value,
    )

    ascii_value = (
        normalized
        .encode(
            "ascii",
            "ignore",
        )
        .decode("ascii")
    )

    ascii_value = ascii_value.lower()

    slug = re.sub(
        r"[^a-z0-9]+",
        "_",
        ascii_value,
    )

    slug = re.sub(
        r"_+",
        "_",
        slug,
    )

    slug = slug.strip("_")

    return slug or "device"


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


def generate_devices(
    exported_devices: list[
        dict[str, Any]
    ],
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
        exported_devices
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

    current_config = (
        load_yaml(
            CURRENT_CONFIG_PATH
        )
    )

    export_data = (
        load_export(
            EXPORT_PATH
        )
    )

    (
        generated_config,
        capability_count,
    ) = build_generated_config(
        current_config=(
            current_config
        ),
        export_data=(
            export_data
        ),
    )

    save_generated_config(
        config=generated_config,
        path=(
            GENERATED_CONFIG_PATH
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
        "Zařízení v exportu:     "
        f"{export_data.get('device_count', '?')}"
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