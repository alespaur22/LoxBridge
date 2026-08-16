from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT
    / "config"
    / "config.generated.yaml"
)

DEFAULT_OUTPUT_PATH = (
    PROJECT_ROOT
    / "exports"
    / "LoxBridge_VirtualInputs.xml"
)

DEFAULT_TITLE = "LoxBridge - Homey Inputs"

SUPPORTED_TYPES = {
    "boolean",
    "number",
    "enum",
}

INPUT_MODES = {
    "normal",
    "raw",
}


def load_config(
    path: Path,
) -> dict[str, Any]:
    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            config = yaml.safe_load(file)

    except FileNotFoundError as error:
        raise RuntimeError(
            "Generovaná konfigurace nebyla "
            f"nalezena: {path}\n"
            "Nejdřív spusť:\n"
            "python -m loxbridge.generate"
        ) from error

    except yaml.YAMLError as error:
        raise RuntimeError(
            f"Neplatný YAML v souboru {path}: {error}"
        ) from error

    if not isinstance(config, dict):
        raise RuntimeError(
            f"Soubor {path} neobsahuje YAML objekt."
        )

    if not isinstance(config.get("loxone"), dict):
        raise RuntimeError(
            "V generované konfiguraci chybí sekce loxone."
        )

    if not isinstance(config.get("devices"), list):
        raise RuntimeError(
            "V generované konfiguraci chybí seznam devices."
        )

    return config


def get_enum_max(
    capability: dict[str, Any],
) -> int:
    values = capability.get("values")

    if not isinstance(values, list):
        return 0

    numeric_values = [
        value.get("value")
        for value in values
        if isinstance(value, dict)
        and isinstance(value.get("value"), int)
    ]

    if not numeric_values:
        return 0

    return max(numeric_values)


def create_udp_command(
    *,
    title: str,
    key: str,
    capability_type: str,
    capability: dict[str, Any] | None = None,
    unit: str | None = None,
) -> ET.Element:
    command = ET.Element("VirtualInUdpCmd")

    command.set("Title", title)
    command.set("Comment", "")
    command.set("Address", "")
    command.set("Check", f"{key}=\\v")

    # Stavové boolean hodnoty používáme jako analog 0/1.
    # Loxone Virtual UDP digitální vstupy se chovají jako impulsy,
    # zatímco pro stav potřebujeme zachovat 0 i 1.
    command.set("Analog", "true")
    command.set("Signed", "true")

    if capability_type == "boolean":
        minimum = 0
        maximum = 1

    elif capability_type == "enum":
        minimum = 0
        maximum = get_enum_max(
            capability or {}
        )

    else:
        minimum = -10000
        maximum = 10000

    for attribute, value in (
        ("SourceValLow", minimum),
        ("DestValLow", minimum),
        ("SourceValHigh", maximum),
        ("DestValHigh", maximum),
        ("DefVal", 0),
        ("MinVal", minimum),
        ("MaxVal", maximum),
    ):
        command.set(attribute, str(value))

    if capability_type == "number" and unit:
        command.set("Unit", unit)
    elif capability_type == "number":
        command.set("Unit", "<v.1>")
    else:
        command.set("Unit", "")

    command.set("HintText", "")

    return command


def create_event_udp_command(
    *,
    title: str,
    key: str,
) -> ET.Element:
    command = ET.Element("VirtualInUdpCmd")

    command.set("Title", title)
    command.set("Comment", "")
    command.set("Address", "")
    command.set("Check", f"{key}=\\v")
    command.set("Signed", "true")

    # Event vstup je záměrně digitální. Každý přijatý UDP paket
    # vytvoří v Loxone jeden impuls; žádný trvalý stav 0/1 se
    # neudržuje.
    command.set("Analog", "false")

    for attribute, value in (
        ("SourceValLow", 0),
        ("DestValLow", 0),
        ("SourceValHigh", 1),
        ("DestValHigh", 1),
        ("DefVal", 0),
        ("MinVal", 0),
        ("MaxVal", 1),
    ):
        command.set(attribute, str(value))

    command.set("Unit", "")
    command.set("HintText", "")

    return command


def get_normalized_inputs(
    device: dict[str, Any],
) -> list[dict[str, Any]]:
    loxbridge = device.get("loxbridge")

    if not isinstance(loxbridge, dict):
        return []

    inputs = loxbridge.get("inputs")

    if not isinstance(inputs, list):
        return []

    return [
        item
        for item in inputs
        if isinstance(item, dict)
    ]


def get_events(
    device: dict[str, Any],
) -> list[dict[str, Any]]:
    loxbridge = device.get("loxbridge")

    if not isinstance(loxbridge, dict):
        return []

    events = loxbridge.get("events")

    if not isinstance(events, list):
        return []

    return [
        item
        for item in events
        if isinstance(item, dict)
    ]


def raw_capabilities_suppressed_in_normal(
    device: dict[str, Any],
) -> set[str]:
    result: set[str] = set()

    for item in get_normalized_inputs(device):
        if item.get("replace_raw_in_normal") is not True:
            continue

        source = item.get("source_capability")

        if isinstance(source, str) and source:
            result.add(source)

    loxbridge = device.get("loxbridge")

    if isinstance(loxbridge, dict):
        suppressed = loxbridge.get("suppress_raw_inputs")

        if isinstance(suppressed, list):
            for source in suppressed:
                if isinstance(source, str) and source:
                    result.add(source)

    return result


def generate_xml(
    config: dict[str, Any],
    *,
    mode: str = "normal",
    title: str = DEFAULT_TITLE,
) -> tuple[ET.Element, dict[str, int]]:
    if mode not in INPUT_MODES:
        raise RuntimeError(
            f"Neplatný režim vstupů: {mode}"
        )

    loxone_config = config["loxone"]

    try:
        port = int(loxone_config["port"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "V konfiguraci chybí platný loxone.port."
        ) from error

    root = ET.Element(
        "VirtualInUdp",
        {
            "HintText": "",
            "Title": title,
            "Comment": "",
            "Address": "",
            "Port": str(port),
        },
    )

    ET.SubElement(
        root,
        "Info",
        {
            "templateType": "1",
            "minVersion": "17010630",
        },
    )

    stats = {
        "generated": 0,
        "raw": 0,
        "normalized": 0,
        "events": 0,
        "boolean": 0,
        "number": 0,
        "enum": 0,
        "skipped": 0,
        "replaced_raw": 0,
    }

    used_keys: set[str] = set()

    for device in config["devices"]:
        if not isinstance(device, dict):
            continue

        capabilities = device.get("capabilities")

        if not isinstance(capabilities, dict):
            continue

        replaced_sources = (
            raw_capabilities_suppressed_in_normal(device)
            if mode == "normal"
            else set()
        )

        for capability_id, capability in capabilities.items():
            if not isinstance(capability, dict):
                continue

            capability_type = capability.get("type")

            if capability_type not in SUPPORTED_TYPES:
                stats["skipped"] += 1
                continue

            if (
                mode == "normal"
                and capability_id in replaced_sources
            ):
                stats["replaced_raw"] += 1
                continue

            key = capability.get("key")
            title_value = capability.get("loxone_name")

            if not isinstance(key, str) or not key:
                stats["skipped"] += 1
                continue

            if not isinstance(title_value, str) or not title_value:
                title_value = str(capability_id)

            if key in used_keys:
                raise RuntimeError(
                    f"Duplicitní Loxone input key: {key}"
                )

            used_keys.add(key)

            command = create_udp_command(
                title=title_value,
                key=key,
                capability_type=str(capability_type),
                capability=capability,
                unit=(
                    str(capability.get("unit"))
                    if capability.get("unit")
                    else None
                ),
            )

            root.append(command)

            stats["generated"] += 1
            stats["raw"] += 1
            stats[str(capability_type)] += 1

        if mode != "normal":
            continue

        for normalized in get_normalized_inputs(device):
            key = normalized.get("key")
            normalized_title = normalized.get("title")
            normalized_type = normalized.get("type")

            if (
                not isinstance(key, str)
                or not key
                or not isinstance(normalized_title, str)
                or not normalized_title
                or normalized_type not in SUPPORTED_TYPES
            ):
                stats["skipped"] += 1
                continue

            if key in used_keys:
                raise RuntimeError(
                    f"Duplicitní normalizovaný input key: {key}"
                )

            used_keys.add(key)

            root.append(
                create_udp_command(
                    title=normalized_title,
                    key=key,
                    capability_type=str(normalized_type),
                    capability=normalized,
                    unit=(
                        str(normalized.get("unit"))
                        if normalized.get("unit")
                        else None
                    ),
                )
            )

            stats["generated"] += 1
            stats["normalized"] += 1
            stats[str(normalized_type)] += 1

        for event in get_events(device):
            key = event.get("key")
            event_title = event.get("title")
            event_kind = event.get("kind")

            if (
                not isinstance(key, str)
                or not key
                or not isinstance(event_title, str)
                or not event_title
                or event_kind != "pulse"
            ):
                stats["skipped"] += 1
                continue

            if key in used_keys:
                raise RuntimeError(
                    f"Duplicitní event input key: {key}"
                )

            used_keys.add(key)
            root.append(
                create_event_udp_command(
                    title=event_title,
                    key=key,
                )
            )

            stats["generated"] += 1
            stats["events"] += 1

    return root, stats


def save_xml(
    root: ET.Element,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ET.indent(root, space="\t")

    body = ET.tostring(
        root,
        encoding="utf-8",
        short_empty_elements=True,
    )

    declaration = (
        b'<?xml version="1.0" encoding="utf-8"?>\n'
    )

    output_path.write_bytes(
        declaration + body + b"\n"
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generuje Loxone virtuální UDP vstupy pro stavy a eventy z Homey."
        )
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Cesta ke config.generated.yaml",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Výstupní XML soubor.",
    )

    parser.add_argument(
        "--mode",
        choices=sorted(INPUT_MODES),
        default="normal",
        help=(
            "normal = normalizované vstupy profilů; "
            "raw = původní Homey capabilities bez úprav."
        ),
    )

    parser.add_argument(
        "--title",
        default=DEFAULT_TITLE,
        help="Název šablony v Loxone Config.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    config = load_config(args.config)

    root, stats = generate_xml(
        config,
        mode=args.mode,
        title=args.title,
    )

    save_xml(
        root,
        args.output,
    )

    print("LoxBridge UDP XML Generator")
    print("===========================")
    print(f"Konfigurace: {args.config}")
    print(f"Výstup:      {args.output}")
    print(f"Režim:       {args.mode}")
    print()
    print("Generování dokončeno.")
    print(f"UDP vstupy celkem:       {stats['generated']}")
    print(f"Raw Homey vstupy:        {stats['raw']}")
    print(f"Normalizované vstupy:    {stats['normalized']}")
    print(f"Event vstupy:            {stats['events']}")
    print(f"Skryté raw vstupy:       {stats['replaced_raw']}")
    print(f"Boolean stavové 0/1:     {stats['boolean']}")
    print(f"Číselné hodnoty:         {stats['number']}")
    print(f"Enum hodnoty:            {stats['enum']}")
    print(f"Přeskočeno:              {stats['skipped']}")
    print()
    print(f"XML uloženo do: {args.output}")


if __name__ == "__main__":
    main()
