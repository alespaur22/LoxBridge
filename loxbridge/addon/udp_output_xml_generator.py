import argparse
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import yaml


DEFAULT_CONFIG_PATH = Path(
    "config/config.generated.yaml"
)

DEFAULT_OUTPUT_PATH = Path(
    "exports/LoxBridge_VirtualOutputs.xml"
)

DEFAULT_IP = "192.168.68.70"
DEFAULT_PORT = 7002

SUPPORTED_TYPES = {
    "boolean",
    "number",
    "enum",
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
            f"Konfigurace nebyla nalezena: {path}"
        ) from error

    except yaml.YAMLError as error:
        raise RuntimeError(
            f"Neplatný YAML v {path}: {error}"
        ) from error

    if not isinstance(config, dict):
        raise RuntimeError(
            f"{path} neobsahuje platný YAML objekt."
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
            "Address": (
                f"/dev/udp/{ip}/{port}"
            ),
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
    attributes = (
        base_command_attributes(
            title
        )
    )

    attributes["CmdOn"] = (
        f"{key}=1"
    )

    attributes["CmdOff"] = (
        f"{key}=0"
    )

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
    attributes = (
        base_command_attributes(
            title
        )
    )

    attributes["CmdOn"] = (
        f"{key}=<v.3>"
    )

    attributes["CmdOff"] = ""

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
    loxone_name = capability.get(
        "loxone_name"
    )

    if loxone_name:
        return str(loxone_name)

    title = capability.get(
        "title"
    )

    if title:
        return (
            f"{device_name} - {title}"
        )

    return (
        f"{device_name} - "
        f"{capability_id}"
    )


def get_setable_capability(
    capabilities: dict[str, Any],
    capability_id: str,
    expected_type: str,
) -> dict[str, Any] | None:
    capability = capabilities.get(
        capability_id
    )

    if not isinstance(
        capability,
        dict,
    ):
        return None

    if (
        capability.get("setable")
        is not True
    ):
        return None

    if (
        capability.get("type")
        != expected_type
    ):
        return None

    key = capability.get(
        "key"
    )

    if (
        not isinstance(key, str)
        or not key
    ):
        return None

    return capability


def get_base_key(
    capabilities: dict[str, Any],
) -> str | None:
    onoff = get_setable_capability(
        capabilities,
        "onoff",
        "boolean",
    )

    if onoff is None:
        return None

    onoff_key = onoff.get(
        "key"
    )

    if (
        not isinstance(onoff_key, str)
        or not onoff_key.endswith(
            "_onoff"
        )
    ):
        return None

    return onoff_key[
        :-len("_onoff")
    ]


def enum_has_value(
    capability: dict[str, Any],
    enum_id: str,
) -> bool:
    values = capability.get(
        "values"
    )

    if not isinstance(
        values,
        list,
    ):
        return False

    return any(
        isinstance(value, dict)
        and value.get("id") == enum_id
        for value in values
    )


def get_rgb_command_key(
    capabilities: dict[str, Any],
) -> str | None:
    dim = get_setable_capability(
        capabilities,
        "dim",
        "number",
    )

    hue = get_setable_capability(
        capabilities,
        "light_hue",
        "number",
    )

    saturation = get_setable_capability(
        capabilities,
        "light_saturation",
        "number",
    )

    mode = get_setable_capability(
        capabilities,
        "light_mode",
        "enum",
    )

    if (
        dim is None
        or hue is None
        or saturation is None
        or mode is None
    ):
        return None

    if not enum_has_value(
        mode,
        "color",
    ):
        return None

    base_key = get_base_key(
        capabilities
    )

    if base_key is None:
        return None

    return f"{base_key}_rgb"


def get_lumitech_command_key(
    capabilities: dict[str, Any],
) -> str | None:
    onoff = get_setable_capability(
        capabilities,
        "onoff",
        "boolean",
    )

    dim = get_setable_capability(
        capabilities,
        "dim",
        "number",
    )

    temperature = get_setable_capability(
        capabilities,
        "light_temperature",
        "number",
    )

    if (
        onoff is None
        or dim is None
        or temperature is None
    ):
        return None

    mode = get_setable_capability(
        capabilities,
        "light_mode",
        "enum",
    )

    if (
        mode is not None
        and not enum_has_value(
            mode,
            "temperature",
        )
    ):
        return None

    base_key = get_base_key(
        capabilities
    )

    if base_key is None:
        return None

    return f"{base_key}_lumitech"


def get_dimmer_command_key(
    capabilities: dict[str, Any],
) -> str | None:
    onoff = get_setable_capability(
        capabilities,
        "onoff",
        "boolean",
    )

    dim = get_setable_capability(
        capabilities,
        "dim",
        "number",
    )

    if (
        onoff is None
        or dim is None
    ):
        return None

    advanced_capabilities = {
        "light_hue": "number",
        "light_saturation": "number",
        "light_temperature": "number",
        "dim.white": "number",
    }

    for (
        capability_id,
        capability_type,
    ) in advanced_capabilities.items():
        capability = (
            get_setable_capability(
                capabilities,
                capability_id,
                capability_type,
            )
        )

        if capability is not None:
            return None

    base_key = get_base_key(
        capabilities
    )

    if base_key is None:
        return None

    return f"{base_key}_dimmer"


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
        "unsupported": 0,
        "missing_key": 0,
    }

    devices = config.get(
        "devices",
        [],
    )

    if not isinstance(
        devices,
        list,
    ):
        raise RuntimeError(
            "Konfigurace neobsahuje "
            "platný seznam devices."
        )

    used_keys: set[str] = set()

    for device in devices:
        if not isinstance(
            device,
            dict,
        ):
            continue

        device_name = str(
            device.get(
                "name",
                "Neznámé zařízení",
            )
        )

        capabilities = device.get(
            "capabilities",
            {},
        )

        if not isinstance(
            capabilities,
            dict,
        ):
            continue

        for (
            capability_id,
            capability,
        ) in capabilities.items():
            if not isinstance(
                capability,
                dict,
            ):
                continue

            if (
                capability.get("setable")
                is not True
            ):
                continue

            capability_type = (
                capability.get("type")
            )

            if (
                capability_type
                not in SUPPORTED_TYPES
            ):
                stats[
                    "unsupported"
                ] += 1

                continue

            key = capability.get(
                "key"
            )

            if (
                not isinstance(key, str)
                or not key
            ):
                stats[
                    "missing_key"
                ] += 1

                continue

            if key in used_keys:
                raise RuntimeError(
                    "Duplicitní Loxone key: "
                    f"{key}"
                )

            used_keys.add(key)

            title = get_command_title(
                device_name,
                str(capability_id),
                capability,
            )

            if (
                capability_type
                == "boolean"
            ):
                create_boolean_command(
                    root=root,
                    title=title,
                    key=key,
                )

                stats["boolean"] += 1

            elif capability_type in {
                "number",
                "enum",
            }:
                create_analog_command(
                    root=root,
                    title=title,
                    key=key,
                )

                stats[
                    capability_type
                ] += 1

            stats["generated"] += 1

        rgb_key = get_rgb_command_key(
            capabilities
        )

        if rgb_key is not None:
            if rgb_key in used_keys:
                raise RuntimeError(
                    "Duplicitní syntetický "
                    "RGB key: "
                    f"{rgb_key}"
                )

            used_keys.add(
                rgb_key
            )

            create_analog_command(
                root=root,
                title=(
                    f"{device_name} - RGB"
                ),
                key=rgb_key,
            )

            stats[
                "synthetic_rgb"
            ] += 1

            stats["generated"] += 1

        lumitech_key = (
            get_lumitech_command_key(
                capabilities
            )
        )

        if lumitech_key is not None:
            if lumitech_key in used_keys:
                raise RuntimeError(
                    "Duplicitní syntetický "
                    "Lumitech key: "
                    f"{lumitech_key}"
                )

            used_keys.add(
                lumitech_key
            )

            create_analog_command(
                root=root,
                title=(
                    f"{device_name} - Lumitech"
                ),
                key=lumitech_key,
            )

            stats[
                "synthetic_lumitech"
            ] += 1

            stats["generated"] += 1

        dimmer_key = (
            get_dimmer_command_key(
                capabilities
            )
        )

        if dimmer_key is not None:
            if dimmer_key in used_keys:
                raise RuntimeError(
                    "Duplicitní syntetický "
                    "Dimmer key: "
                    f"{dimmer_key}"
                )

            used_keys.add(
                dimmer_key
            )

            create_analog_command(
                root=root,
                title=(
                    f"{device_name} - Dimmer"
                ),
                key=dimmer_key,
            )

            stats[
                "synthetic_dimmer"
            ] += 1

            stats["generated"] += 1

    return stats


def write_xml(
    root: ET.Element,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tree = ET.ElementTree(root)

    ET.indent(
        tree,
        space="\t",
    )

    xml_body = ET.tostring(
        root,
        encoding="utf-8",
        short_empty_elements=True,
    )

    declaration = (
        b'<?xml version="1.0" '
        b'encoding="utf-8"?>\n'
    )

    output_path.write_bytes(
        declaration
        + xml_body
        + b"\n"
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generuje Loxone virtuální "
            "UDP výstupy pro ovládání Homey."
        )
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=(
            "Cesta ke config.generated.yaml"
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=(
            "Výstupní XML soubor."
        ),
    )

    parser.add_argument(
        "--ip",
        default=DEFAULT_IP,
        help=(
            "IPv4 adresa LoxBridge."
        ),
    )

    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=(
            "UDP port listeneru LoxBridge."
        ),
    )

    parser.add_argument(
        "--title",
        default="LoxBridge - Homey",
        help=(
            "Název virtuálního výstupu "
            "v Loxone Config."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    config = load_config(
        args.config
    )

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

    print(
        "LoxBridge Virtual Output "
        "XML Generator"
    )

    print(
        f"Výstup: {args.output}"
    )

    print(
        "UDP adresa: "
        f"/dev/udp/"
        f"{args.ip}/"
        f"{args.port}"
    )

    print()

    print(
        "Virtuální výstupy celkem: "
        f"{stats['generated']}"
    )

    print(
        "Boolean:                  "
        f"{stats['boolean']}"
    )

    print(
        "Number:                   "
        f"{stats['number']}"
    )

    print(
        "Enum:                     "
        f"{stats['enum']}"
    )

    print(
        "Syntetické RGB:           "
        f"{stats['synthetic_rgb']}"
    )

    print(
        "Syntetické Lumitech:      "
        f"{stats['synthetic_lumitech']}"
    )

    print(
        "Syntetické Dimmer:        "
        f"{stats['synthetic_dimmer']}"
    )

    print(
        "Nepodporované setable:    "
        f"{stats['unsupported']}"
    )

    print(
        "Chybějící key:            "
        f"{stats['missing_key']}"
    )


if __name__ == "__main__":
    main()