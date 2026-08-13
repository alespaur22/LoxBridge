from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = (
    PROJECT_ROOT
    / "config"
    / "config.generated.yaml"
)

OUTPUT_DIRECTORY = (
    PROJECT_ROOT
    / "exports"
)

OUTPUT_PATH = (
    OUTPUT_DIRECTORY
    / "LoxBridge_VirtualInputs.xml"
)

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
            "Generovaná konfigurace "
            f"nebyla nalezena: {path}\n"
            "Nejdřív spusť:\n"
            "python -m loxbridge.generate"
        ) from error

    except yaml.YAMLError as error:
        raise RuntimeError(
            "Neplatný YAML v souboru "
            f"{path}: {error}"
        ) from error

    if not isinstance(config, dict):
        raise RuntimeError(
            f"Soubor {path} "
            "neobsahuje YAML objekt."
        )

    if not isinstance(
        config.get("loxone"),
        dict,
    ):
        raise RuntimeError(
            "V generované konfiguraci "
            "chybí sekce loxone."
        )

    if not isinstance(
        config.get("devices"),
        list,
    ):
        raise RuntimeError(
            "V generované konfiguraci "
            "chybí seznam devices."
        )

    return config


def get_enum_max(
    capability: dict[str, Any],
) -> int:
    values = capability.get("values")

    if not isinstance(values, list):
        return 0

    numeric_values: list[int] = []

    for value in values:
        if not isinstance(value, dict):
            continue

        numeric_value = value.get("value")

        if isinstance(numeric_value, int):
            numeric_values.append(
                numeric_value
            )

    if not numeric_values:
        return 0

    return max(numeric_values)


def create_udp_command(
    title: str,
    key: str,
    capability_type: str,
    capability: dict[str, Any],
    unit: str | None = None,
) -> Element:
    command = Element(
        "VirtualInUdpCmd"
    )

    command.set(
        "Title",
        title,
    )

    command.set(
        "Comment",
        "",
    )

    command.set(
        "Address",
        "",
    )

    command.set(
        "Check",
        f"{key}=\\v",
    )

    # Všechny podporované hodnoty používáme
    # jako analogové stavové vstupy.
    #
    # boolean:
    # false = 0
    # true  = 1
    #
    # enum:
    # jednotlivé stavy = 0, 1, 2, 3...
    #
    # number:
    # skutečná číselná hodnota
    command.set(
        "Analog",
        "true",
    )

    command.set(
        "Signed",
        "true",
    )

    if capability_type == "boolean":
        minimum = 0
        maximum = 1

    elif capability_type == "enum":
        minimum = 0
        maximum = get_enum_max(
            capability
        )

    else:
        minimum = -10000
        maximum = 10000

    command.set(
        "SourceValLow",
        str(minimum),
    )

    command.set(
        "DestValLow",
        str(minimum),
    )

    command.set(
        "SourceValHigh",
        str(maximum),
    )

    command.set(
        "DestValHigh",
        str(maximum),
    )

    command.set(
        "DefVal",
        "0",
    )

    command.set(
        "MinVal",
        str(minimum),
    )

    command.set(
        "MaxVal",
        str(maximum),
    )

    if (
        capability_type == "number"
        and unit
    ):
        command.set(
            "Unit",
            unit,
        )

    elif capability_type == "number":
        command.set(
            "Unit",
            "<v.1>",
        )

    else:
        command.set(
            "Unit",
            "",
        )

    command.set(
        "HintText",
        "",
    )

    return command


def generate_xml(
    config: dict[str, Any],
) -> tuple[
    bytes,
    int,
    int,
    int,
    int,
    int,
]:
    loxone_config = config["loxone"]

    try:
        port = int(
            loxone_config["port"]
        )

    except (
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise RuntimeError(
            "V konfiguraci chybí "
            "platný loxone.port."
        ) from error

    root = Element(
        "VirtualInUdp"
    )

    root.set(
        "HintText",
        "",
    )

    root.set(
        "Title",
        "LoxBridge - Homey",
    )

    root.set(
        "Comment",
        "",
    )

    root.set(
        "Address",
        "",
    )

    root.set(
        "Port",
        str(port),
    )

    info = SubElement(
        root,
        "Info",
    )

    info.set(
        "templateType",
        "1",
    )

    info.set(
        "minVersion",
        "17010630",
    )

    generated_count = 0
    boolean_count = 0
    number_count = 0
    enum_count = 0
    skipped_count = 0

    devices = config["devices"]

    for device in devices:
        if not isinstance(
            device,
            dict,
        ):
            continue

        capabilities = device.get(
            "capabilities"
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

            capability_type = (
                capability.get("type")
            )

            if (
                capability_type
                not in SUPPORTED_TYPES
            ):
                skipped_count += 1
                continue

            key = capability.get(
                "key"
            )

            loxone_name = capability.get(
                "loxone_name"
            )

            unit = capability.get(
                "unit"
            )

            if (
                not isinstance(key, str)
                or not key
            ):
                raise RuntimeError(
                    f'Capability "{capability_id}" '
                    "nemá platný key."
                )

            if (
                not isinstance(
                    loxone_name,
                    str,
                )
                or not loxone_name
            ):
                raise RuntimeError(
                    f'Capability "{capability_id}" '
                    "nemá platný loxone_name."
                )

            if not isinstance(
                unit,
                str,
            ):
                unit = None

            root.append(
                create_udp_command(
                    title=loxone_name,
                    key=key,
                    capability_type=(
                        capability_type
                    ),
                    capability=capability,
                    unit=unit,
                )
            )

            generated_count += 1

            if (
                capability_type
                == "boolean"
            ):
                boolean_count += 1

            elif (
                capability_type
                == "number"
            ):
                number_count += 1

            elif (
                capability_type
                == "enum"
            ):
                enum_count += 1

    raw_xml = tostring(
        root,
        encoding="utf-8",
    )

    document = minidom.parseString(
        raw_xml
    )

    xml = document.toprettyxml(
        indent="\t",
        encoding="utf-8",
    )

    return (
        xml,
        generated_count,
        boolean_count,
        number_count,
        enum_count,
        skipped_count,
    )


def save_xml(
    xml: bytes,
    path: Path,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "wb"
    ) as file:
        file.write(xml)


def main() -> None:
    print(
        "LoxBridge UDP XML Generator"
    )

    print(
        "==========================="
    )

    print(
        f"Konfigurace: {CONFIG_PATH}"
    )

    print(
        f"Výstup:      {OUTPUT_PATH}"
    )

    print()

    config = load_config(
        CONFIG_PATH
    )

    (
        xml,
        generated_count,
        boolean_count,
        number_count,
        enum_count,
        skipped_count,
    ) = generate_xml(
        config
    )

    save_xml(
        xml=xml,
        path=OUTPUT_PATH,
    )

    print(
        "Generování dokončeno."
    )

    print(
        "UDP vstupy celkem:       "
        f"{generated_count}"
    )

    print(
        "Boolean stavové 0/1:     "
        f"{boolean_count}"
    )

    print(
        "Číselné hodnoty:         "
        f"{number_count}"
    )

    print(
        "Enum hodnoty:            "
        f"{enum_count}"
    )

    print(
        "String přeskočeno:       "
        f"{skipped_count}"
    )

    print()

    print(
        "XML uloženo do: "
        f"{OUTPUT_PATH}"
    )


if __name__ == "__main__":
    try:
        main()

    except RuntimeError as error:
        print(
            f"CHYBA: {error}",
            file=sys.stderr,
        )

        raise SystemExit(1) from error