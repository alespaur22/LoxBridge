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
            config = yaml.safe_load(
                file
            )

    except FileNotFoundError as error:
        raise RuntimeError(
            f"Konfigurace nebyla nalezena: {path}"
        ) from error

    except yaml.YAMLError as error:
        raise RuntimeError(
            f"Neplatný YAML v {path}: {error}"
        ) from error

    if not isinstance(
        config,
        dict,
    ):
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
            "Address":
                f"/dev/udp/{ip}/{port}",
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

    attributes["Analog"] = (
        "false"
    )

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

    attributes["Analog"] = (
        "true"
    )

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
    loxone_name = (
        capability.get(
            "loxone_name"
        )
    )

    if loxone_name:
        return str(
            loxone_name
        )

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
    capability = (
        capabilities.get(
            capability_id
        )
    )

    if not isinstance(
        capability,
        dict,
    ):
        return None

    if (
        capability.get(
            "setable"
        )
        is not True
    ):
        return None

    if (
        capability.get(
            "type"
        )
        != expected_type
    ):
        return None

    key = capability.get(
        "key"
    )

    if (
        not isinstance(
            key,
            str,
        )
        or not key
    ):
        return None

    return capability


def get_base_key(
    capabilities: dict[str, Any],
) -> str | None:
    onoff = (
        get_setable_capability(
            capabilities,
            "onoff",
            "boolean",
        )
    )

    if onoff is None:
        return None

    onoff_key = (
        onoff.get(
            "key"
        )
    )

    if (
        not isinstance(
            onoff_key,
            str,
        )
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
        isinstance(
            value,
            dict,
        )
        and value.get(
            "id"
        ) == enum_id
        for value in values
    )


def get_rgb_command_key(
    capabilities: dict[str, Any],
) -> str | None:
    dim = (
        get_setable_capability(
            capabilities,
            "dim",
            "number",
        )
    )

    hue = (
        get_setable_capability(
            capabilities,
            "light_hue",
            "number",
        )
    )

    saturation = (
        get_setable_capability(
            capabilities,
            "light_saturation",
            "number",
        )
    )

    mode = (
        get_setable_capability(
            capabilities,
            "light_mode",
            "enum",
        )
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

    base_key = (
        get_base_key(
            capabilities
        )
    )

    if base_key is None:
        return None

    return (
        f"{base_key}_rgb"
    )


def get_lumitech_command_key(
    capabilities: dict[str, Any],
) -> str | None:
    onoff = (
        get_setable_capability(
            capabilities,
            "onoff",
            "boolean",
        )
    )

    dim = (
        get_setable_capability(
            capabilities,
            "dim",
            "number",
        )
    )

    temperature = (
        get_setable_capability(
            capabilities,
            "light_temperature",
            "number",
        )
    )

    if (
        onoff is None
        or dim is None
        or temperature is None
    ):
        return None

    mode = (
        get_setable_capability(
            capabilities,
            "light_mode",
            "enum",
        )
    )

    if (
        mode is not None
        and not enum_has_value(
            mode,
            "temperature",
        )
    ):
        return None

    base_key = (
        get_base_key(
            capabilities
        )
    )

    if base_key is None:
        return None

    return (
        f"{base_key}_lumitech"
    )


def get_dimmer_command_key(
    capabilities: dict[str, Any],
) -> str | None:
    onoff = (
        get_setable_capability(
            capabilities,
            "onoff",
            "boolean",
        )
    )

    dim = (
        get_setable_capability(
            capabilities,
            "dim",
            "number",
        )
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

    base_key = (
        get_base_key(
            capabilities
        )
    )

    if base_key is None:
        return None

    return (
        f"{base_key}_dimmer"
    )


def get_rgbw_white_channel_keys(
    capabilities: dict[str, Any],
) -> tuple[str, str] | None:
    # RGB + samostatný white kanál.
    #
    # light_mode zde nechceme.
    #
    # onoff.whitemode záměrně není
    # podmínkou ani součástí profilu.
    #
    # U testovaného driveru jeho
    # zapnutí fyzicky vynutí
    # 100 % bílé.

    light_mode = (
        get_setable_capability(
            capabilities,
            "light_mode",
            "enum",
        )
    )

    if light_mode is not None:
        return None

    required = [
        get_setable_capability(
            capabilities,
            "onoff",
            "boolean",
        ),
        get_setable_capability(
            capabilities,
            "dim",
            "number",
        ),
        get_setable_capability(
            capabilities,
            "light_hue",
            "number",
        ),
        get_setable_capability(
            capabilities,
            "light_saturation",
            "number",
        ),
        get_setable_capability(
            capabilities,
            "dim.white",
            "number",
        ),
    ]

    if any(
        capability is None
        for capability in required
    ):
        return None

    base_key = (
        get_base_key(
            capabilities
        )
    )

    if base_key is None:
        return None

    return (
        f"{base_key}_rgb",
        f"{base_key}_white",
    )


def add_synthetic_analog(
    root: ET.Element,
    used_keys: set[str],
    stats: dict[str, int],
    *,
    key: str,
    title: str,
    stat_name: str,
    duplicate_label: str,
) -> None:
    if key in used_keys:
        raise RuntimeError(
            f"Duplicitní "
            f"{duplicate_label} "
            f"key: {key}"
        )

    used_keys.add(
        key
    )

    create_analog_command(
        root=root,
        title=title,
        key=key,
    )

    stats[
        stat_name
    ] += 1

    stats[
        "generated"
    ] += 1


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

        capabilities = (
            device.get(
                "capabilities",
                {},
            )
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
                capability.get(
                    "setable"
                )
                is not True
            ):
                continue

            capability_type = (
                capability.get(
                    "type"
                )
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
                not isinstance(
                    key,
                    str,
                )
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

            used_keys.add(
                key
            )

            title = (
                get_command_title(
                    device_name,
                    str(
                        capability_id
                    ),
                    capability,
                )
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

                stats[
                    "boolean"
                ] += 1

            else:
                create_analog_command(
                    root=root,
                    title=title,
                    key=key,
                )

                stats[
                    capability_type
                ] += 1

            stats[
                "generated"
            ] += 1

        rgb_key = (
            get_rgb_command_key(
                capabilities
            )
        )

        if rgb_key is not None:
            add_synthetic_analog(
                root,
                used_keys,
                stats,
                key=rgb_key,
                title=(
                    f"{device_name} - RGB"
                ),
                stat_name=(
                    "synthetic_rgb"
                ),
                duplicate_label=(
                    "syntetický RGB"
                ),
            )

        lumitech_key = (
            get_lumitech_command_key(
                capabilities
            )
        )

        if lumitech_key is not None:
            add_synthetic_analog(
                root,
                used_keys,
                stats,
                key=lumitech_key,
                title=(
                    f"{device_name} - Lumitech"
                ),
                stat_name=(
                    "synthetic_lumitech"
                ),
                duplicate_label=(
                    "syntetický Lumitech"
                ),
            )

        dimmer_key = (
            get_dimmer_command_key(
                capabilities
            )
        )

        if dimmer_key is not None:
            add_synthetic_analog(
                root,
                used_keys,
                stats,
                key=dimmer_key,
                title=(
                    f"{device_name} - Dimmer"
                ),
                stat_name=(
                    "synthetic_dimmer"
                ),
                duplicate_label=(
                    "syntetický Dimmer"
                ),
            )

        rgbw_keys = (
            get_rgbw_white_channel_keys(
                capabilities
            )
        )

        if rgbw_keys is not None:
            (
                rgbw_rgb_key,
                rgbw_white_key,
            ) = rgbw_keys

            add_synthetic_analog(
                root,
                used_keys,
                stats,
                key=rgbw_rgb_key,
                title=(
                    f"{device_name} - RGB"
                ),
                stat_name=(
                    "synthetic_rgb"
                ),
                duplicate_label=(
                    "RGBW RGB"
                ),
            )

            add_synthetic_analog(
                root,
                used_keys,
                stats,
                key=rgbw_white_key,
                title=(
                    f"{device_name} - White"
                ),
                stat_name=(
                    "synthetic_white"
                ),
                duplicate_label=(
                    "RGBW White"
                ),
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

    ET.indent(
        root,
        space="\t",
    )

    xml_body = (
        ET.tostring(
            root,
            encoding="utf-8",
            short_empty_elements=True,
        )
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
            "Cesta ke "
            "config.generated.yaml"
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
            "Název virtuálního "
            "výstupu v Loxone Config."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = (
        parse_arguments()
    )

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
        f"UDP adresa: "
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
        "Syntetické White:         "
        f"{stats['synthetic_white']}"
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