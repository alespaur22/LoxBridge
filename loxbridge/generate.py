import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from loxbridge.addon.translations import get_capability_title


PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPORT_PATH = PROJECT_ROOT / "exports" / "homey_devices.json"
CURRENT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
GENERATED_CONFIG_PATH = PROJECT_ROOT / "config" / "config.generated.yaml"

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


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = ascii_value.lower()

    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value)
    slug = re.sub(r"_+", "_", slug)
    slug = slug.strip("_")

    return slug or "device"


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

    except FileNotFoundError as error:
        raise RuntimeError(
            f"Soubor nebyl nalezen: {path}"
        ) from error

    except yaml.YAMLError as error:
        raise RuntimeError(
            f"Neplatný YAML v souboru {path}: {error}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Soubor {path} neobsahuje YAML objekt."
        )

    return data


def load_export(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

    except FileNotFoundError as error:
        raise RuntimeError(
            f"Export zařízení nebyl nalezen: {path}\n"
            "Nejdřív spusť:\n"
            "node loxbridge/homey/export_devices.mjs"
        ) from error

    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Neplatný JSON v souboru {path}: {error}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError(
            "Export zařízení neobsahuje JSON objekt."
        )

    devices = data.get("devices")

    if not isinstance(devices, list):
        raise RuntimeError(
            "V exportu chybí seznam devices."
        )

    return data


def should_include_capability(
    capability: dict[str, Any],
) -> bool:
    capability_id = str(
        capability.get("id", "")
    )

    capability_type = capability.get("type")
    getable = capability.get("getable")

    if not capability_id:
        return False

    if getable is not True:
        return False

    if capability_type not in SUPPORTED_TYPES:
        return False

    if capability_id in IGNORED_CAPABILITIES:
        return False

    if capability_id.startswith(
        IGNORED_CAPABILITY_PREFIXES
    ):
        return False

    return True


def build_enum_values(
    capability: dict[str, Any],
) -> list[dict[str, Any]]:
    values = capability.get("values")

    if not isinstance(values, list):
        return []

    result: list[dict[str, Any]] = []

    for index, value in enumerate(values):
        if not isinstance(value, dict):
            continue

        value_id = value.get("id")

        if value_id is None:
            continue

        value_title = value.get("title")

        result.append(
            {
                "id": str(value_id),
                "title": (
                    str(value_title)
                    if value_title is not None
                    else str(value_id)
                ),
                "value": index,
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

    title = get_capability_title(
        capability_id,
        capability.get("title"),
    )

    capability_type = capability.get("type")
    unit = capability.get("units")

    data: dict[str, Any] = {
        "key": loxone_key,
        "type": capability_type,
        "title": title,
        "loxone_name": f"{device_name} - {title}",
        "setable": bool(
            capability.get("setable", False)
    ),
}

    if unit:
        data["unit"] = unit

    if capability_type == "enum":
        enum_values = build_enum_values(
            capability
        )

        if enum_values:
            data["values"] = enum_values

    return data


def make_unique_key(
    base_key: str,
    used_keys: set[str],
) -> str:
    if base_key not in used_keys:
        used_keys.add(base_key)
        return base_key

    counter = 2

    while True:
        candidate = f"{base_key}_{counter}"

        if candidate not in used_keys:
            used_keys.add(candidate)
            return candidate

        counter += 1


def generate_devices(
    exported_devices: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    generated_devices: list[dict[str, Any]] = []
    used_keys: set[str] = set()
    capability_count = 0

    name_counts = Counter(
        str(device.get("name", "")).strip()
        for device in exported_devices
    )

    for device in exported_devices:
        device_name = str(
            device.get("name", "")
        ).strip()

        device_id = str(
            device.get("id", "")
        ).strip()

        if not device_name:
            continue

        device_slug = slugify(
            device_name
        )

        if name_counts[device_name] > 1 and device_id:
            device_slug = (
                f"{device_slug}_{device_id[:8]}"
            )

        generated_capabilities: dict[
            str,
            dict[str, Any],
        ] = {}

        capabilities = device.get(
            "capabilities",
            [],
        )

        if not isinstance(capabilities, list):
            continue

        for capability in capabilities:
            if not isinstance(capability, dict):
                continue

            if not should_include_capability(
                capability
            ):
                continue

            capability_id = str(
                capability["id"]
            )

            capability_slug = slugify(
                capability_id
            )

            base_key = (
                f"{device_slug}_{capability_slug}"
            )

            loxone_key = make_unique_key(
                base_key,
                used_keys,
            )

            generated_capabilities[
                capability_id
            ] = build_capability(
                device_name=device_name,
                capability=capability,
                loxone_key=loxone_key,
            )

            capability_count += 1

        if not generated_capabilities:
            continue

        generated_device: dict[str, Any] = {
            "name": device_name,
            "slug": device_slug,
            "capabilities": generated_capabilities,
        }

        if device_id:
            generated_device["homey_id"] = device_id

        generated_devices.append(
            generated_device
        )

    return generated_devices, capability_count


def build_generated_config(
    current_config: dict[str, Any],
    export_data: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    homey_config = current_config.get("homey")
    loxone_config = current_config.get("loxone")

    if not isinstance(homey_config, dict):
        raise RuntimeError(
            "V config.yaml chybí sekce homey."
        )

    if not isinstance(loxone_config, dict):
        raise RuntimeError(
            "V config.yaml chybí sekce loxone."
        )

    exported_devices = export_data["devices"]

    generated_devices, capability_count = generate_devices(
        exported_devices
    )

    generated_config = {
        "homey": homey_config,
        "loxone": loxone_config,
        "devices": generated_devices,
    }

    return generated_config, capability_count


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
    print("LoxBridge Config Generator")
    print("==========================")
    print(f"Export:        {EXPORT_PATH}")
    print(f"Zdroj configu: {CURRENT_CONFIG_PATH}")
    print(f"Výstup:        {GENERATED_CONFIG_PATH}")
    print()

    current_config = load_yaml(
        CURRENT_CONFIG_PATH
    )

    export_data = load_export(
        EXPORT_PATH
    )

    generated_config, capability_count = build_generated_config(
        current_config=current_config,
        export_data=export_data,
    )

    save_generated_config(
        config=generated_config,
        path=GENERATED_CONFIG_PATH,
    )

    device_count = len(
        generated_config["devices"]
    )

    print("Generování dokončeno.")
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
    print()
    print(
        "Funkční config.yaml nebyl změněn."
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

        raise SystemExit(1) from error