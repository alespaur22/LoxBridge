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
    / "LoxBridge_VirtualOutputs.xml"
)

DEFAULT_IP = "192.168.68.70"
DEFAULT_PORT = 7002
DEFAULT_TITLE = "LoxBridge - Homey Outputs"

SUPPORTED_TYPES = {
    "boolean",
    "number",
    "enum",
}

SYNTHETIC_KIND_STATS = {
    "rgb": "synthetic_rgb",
    "rgb_white_rgb": "synthetic_rgb",
    "lumitech": "synthetic_lumitech",
    "dimmer": "synthetic_dimmer",
    "rgb_white_white": "synthetic_white",
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
            f"Neplatný YAML v {path}: {error}"
        ) from error

    if not isinstance(config, dict):
        raise RuntimeError(
            f"{path} neobsahuje platný YAML objekt."
        )

    if not isinstance(config.get("devices"), list):
        raise RuntimeError(
            "Konfigurace neobsahuje platný seznam devices."
        )

    return config


def create_root(
    ip: str,
    port: int,
    title: str,
) -> ET.Element:
    root = ET.Element(
        "VirtualOut",
        {
            "HintText": "",
            "Title": title,
            "Comment": "",
            "Address": f"/dev/udp/{ip}/{port}",
            "CmdInit": "",
            "CloseAfterSend": "true",
            "CmdSep": ";",
        },
    )

    ET.SubElement(
        root,
        "Info",
        {
            "templateType": "3",
            "minVersion": "17010630",
        },
    )

    return root


def base_command_attributes(
    title: str,
) -> dict[str, str]:
    return {
        "Title": title,
        "Comment": "",
        "CmdOnMethod": "GET",
        "CmdOffMethod": "GET",
        "CmdOn": "",
        "CmdOnHTTP": "",
        "CmdOnPost": "",
        "CmdOff": "",
        "CmdOffHTTP": "",
        "CmdOffPost": "",
        "CmdAnswer": "",
        "Analog": "false",
        "Repeat": "0",
        "RepeatRate": "0",
        "HintText": "",
    }


def create_boolean_command(
    root: ET.Element,
    title: str,
    key: str,
) -> None:
    attributes = base_command_attributes(title)
    attributes["CmdOn"] = f"{key}=1"
    attributes["CmdOff"] = f"{key}=0"
    attributes["Analog"] = "false"

    ET.SubElement(
        root,
        "VirtualOutCmd",
        attributes,
    )


def create_analog_command(
    root: ET.Element,
    title: str,
    key: str,
) -> None:
    attributes = base_command_attributes(title)
    attributes["CmdOn"] = f"{key}=<v.3>"
    attributes["Analog"] = "true"

    ET.SubElement(
        root,
        "VirtualOutCmd",
        attributes,
    )


def get_command_title(
    device_name: str,
    capability_id: str,
    capability: dict[str, Any],
) -> str:
    loxone_name = capability.get("loxone_name")

    if loxone_name:
        return str(loxone_name)

    title = capability.get("title")

    if title:
        return f"{device_name} - {title}"

    return f"{device_name} - {capability_id}"


def get_profile_commands(
    device: dict[str, Any],
) -> list[dict[str, Any]]:
    loxbridge = device.get("loxbridge")

    if not isinstance(loxbridge, dict):
        return []

    commands = loxbridge.get("commands")

    if not isinstance(commands, list):
        return []

    return [
        command
        for command in commands
        if isinstance(command, dict)
    ]


def add_synthetic_command(
    root: ET.Element,
    command: dict[str, Any],
    used_keys: set[str],
    stats: dict[str, int],
) -> None:
    key = command.get("key")
    title = command.get("title")
    kind = command.get("kind")

    if not isinstance(key, str) or not key:
        raise RuntimeError(
            "Profil obsahuje syntetický příkaz bez platného key."
        )

    if not isinstance(title, str) or not title:
        title = key

    if key in used_keys:
        raise RuntimeError(
            f"Duplicitní syntetický Loxone key: {key}"
        )

    used_keys.add(key)

    create_analog_command(
        root=root,
        title=title,
        key=key,
    )

    stats["generated"] += 1

    stat_name = SYNTHETIC_KIND_STATS.get(str(kind))

    if stat_name:
        stats[stat_name] += 1
    else:
        stats["synthetic_other"] += 1


def generate_commands(
    root: ET.Element,
    config: dict[str, Any],
) -> dict[str, int]:
    stats = {
        "generated": 0,
        "boolean": 0,
        "number": 0,
        "enum": 0,
        "synthetic_rgb": 0,
        "synthetic_lumitech": 0,
        "synthetic_dimmer": 0,
        "synthetic_white": 0,
        "synthetic_other": 0,
        "unsupported": 0,
        "missing_key": 0,
    }

    devices = config["devices"]
    used_keys: set[str] = set()

    for device in devices:
        if not isinstance(device, dict):
            continue

        device_name = str(
            device.get("name", "Neznámé zařízení")
        )

        capabilities = device.get("capabilities", {})

        if not isinstance(capabilities, dict):
            continue

        # Raw Homey výstupy zachováváme kvůli zpětné kompatibilitě.
        for capability_id, capability in capabilities.items():
            if not isinstance(capability, dict):
                continue

            if capability.get("setable") is not True:
                continue

            capability_type = capability.get("type")

            if capability_type not in SUPPORTED_TYPES:
                stats["unsupported"] += 1
                continue

            key = capability.get("key")

            if not isinstance(key, str) or not key:
                stats["missing_key"] += 1
                continue

            if key in used_keys:
                raise RuntimeError(
                    f"Duplicitní Loxone key: {key}"
                )

            used_keys.add(key)

            title = get_command_title(
                device_name,
                str(capability_id),
                capability,
            )

            if capability_type == "boolean":
                create_boolean_command(
                    root=root,
                    title=title,
                    key=key,
                )
                stats["boolean"] += 1

            else:
                create_analog_command(
                    root=root,
                    title=title,
                    key=key,
                )
                stats[str(capability_type)] += 1

            stats["generated"] += 1

        # Syntetické výstupy už neurčuje XML generátor.
        # Jsou připravené centrálním Profile Enginem v config.generated.yaml.
        for command in get_profile_commands(device):
            add_synthetic_command(
                root=root,
                command=command,
                used_keys=used_keys,
                stats=stats,
            )

    return stats


def write_xml(
    root: ET.Element,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ET.indent(root, space="\t")

    xml_body = ET.tostring(
        root,
        encoding="utf-8",
        short_empty_elements=True,
    )

    declaration = (
        b'<?xml version="1.0" encoding="utf-8"?>\n'
    )

    output_path.write_bytes(
        declaration + xml_body + b"\n"
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generuje Loxone virtuální UDP výstupy pro ovládání Homey."
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
        "--ip",
        default=DEFAULT_IP,
        help="IPv4 adresa LoxBridge.",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="UDP port listeneru LoxBridge.",
    )

    parser.add_argument(
        "--title",
        default=DEFAULT_TITLE,
        help="Název virtuálního výstupu v Loxone Config.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    config = load_config(args.config)

    root = create_root(
        ip=args.ip,
        port=args.port,
        title=args.title,
    )

    stats = generate_commands(
        root=root,
        config=config,
    )

    write_xml(
        root=root,
        output_path=args.output,
    )

    print("LoxBridge Virtual Output XML Generator")
    print(f"Výstup: {args.output}")
    print(f"UDP adresa: /dev/udp/{args.ip}/{args.port}")
    print()
    print(f"Virtuální výstupy celkem: {stats['generated']}")
    print(f"Boolean:                  {stats['boolean']}")
    print(f"Number:                   {stats['number']}")
    print(f"Enum:                     {stats['enum']}")
    print(f"Syntetické RGB:           {stats['synthetic_rgb']}")
    print(f"Syntetické Lumitech:      {stats['synthetic_lumitech']}")
    print(f"Syntetické Dimmer:        {stats['synthetic_dimmer']}")
    print(f"Syntetické White:         {stats['synthetic_white']}")

    if stats["synthetic_other"]:
        print(
            "Syntetické ostatní:       "
            f"{stats['synthetic_other']}"
        )

    print(f"Nepodporované setable:    {stats['unsupported']}")
    print(f"Chybějící key:            {stats['missing_key']}")


if __name__ == "__main__":
    main()
