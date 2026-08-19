from __future__ import annotations

import argparse
from pathlib import Path
from typing import Mapping
import xml.etree.ElementTree as ET

from loxbridge.addon.delta import (
    CommandState,
    compare_states,
    input_state_from_xml,
    output_state_from_xml,
)
from loxbridge.addon.delta_state import (
    load_state,
)
from loxbridge.addon.udp_output_xml_generator import (
    DEFAULT_IP,
    DEFAULT_PORT,
    create_root,
    generate_commands,
)
from loxbridge.addon.udp_xml_generator import (
    DEFAULT_CONFIG_PATH,
    generate_xml,
    load_config,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_BASELINE_PATH = (
    PROJECT_ROOT
    / "config"
    / "loxone_imported_state.json"
)

DEFAULT_INPUT_OUTPUT_PATH = (
    PROJECT_ROOT
    / "exports"
    / "LoxBridge_DELTA_Inputs.xml"
)

DEFAULT_OUTPUT_OUTPUT_PATH = (
    PROJECT_ROOT
    / "exports"
    / "LoxBridge_DELTA_Outputs.xml"
)

DELTA_INPUT_TITLE = (
    "LoxBridge - NEW Inputs"
)

DELTA_OUTPUT_TITLE = (
    "LoxBridge - NEW Outputs"
)


def build_delta_root(
    *,
    source_root: ET.Element,
    command_tag: str,
    current_state: CommandState,
    added_keys: tuple[str, ...],
    title: str,
) -> ET.Element:
    root_attributes = dict(
        source_root.attrib
    )

    root_attributes["Title"] = title

    root = ET.Element(
        source_root.tag,
        root_attributes,
    )

    info = source_root.find("Info")

    if info is not None:
        ET.SubElement(
            root,
            "Info",
            dict(info.attrib),
        )

    for key in added_keys:
        attributes = current_state.get(key)

        if attributes is None:
            raise RuntimeError(
                "DELTA obsahuje key, který není "
                f"v aktuálním stavu: {key}"
            )

        ET.SubElement(
            root,
            command_tag,
            dict(attributes),
        )

    return root


def save_xml(
    root: ET.Element,
    path: Path,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ET.indent(
        root,
        space="\t",
    )

    body = ET.tostring(
        root,
        encoding="utf-8",
        short_empty_elements=True,
    )

    declaration = (
        b'<?xml version="1.0" '
        b'encoding="utf-8"?>\n'
    )

    path.write_bytes(
        declaration
        + body
        + b"\n"
    )


def save_delta_or_remove(
    *,
    root: ET.Element,
    added_count: int,
    path: Path,
) -> bool:
    if added_count == 0:
        if path.exists():
            path.unlink()

        return False

    save_xml(
        root,
        path,
    )

    return True


def print_delta(
    *,
    name: str,
    baseline_count: int,
    current_count: int,
    delta: object,
) -> None:
    added = delta.added
    removed = delta.removed
    changed = delta.changed

    print(name)
    print("=" * len(name))
    print(
        f"Baseline : {baseline_count}"
    )
    print(
        f"Current  : {current_count}"
    )
    print(
        f"Added    : {len(added)}"
    )
    print(
        f"Removed  : {len(removed)}"
    )
    print(
        f"Changed  : {len(changed)}"
    )

    if added:
        print()
        print("PŘIDAT DO LOXONE:")

        for key in added:
            print(
                f"  + {key}"
            )

    if removed:
        print()
        print(
            "V LOXONE ZŮSTÁVÁ NAVÍC:"
        )

        for key in removed:
            print(
                f"  - {key}"
            )

    if changed:
        print()
        print(
            "POZOR - ZMĚNĚNÉ DEFINICE:"
        )

        for change in changed:
            print(
                f"  ~ {change.key}"
            )

    print()


def generate_delta(
    *,
    config_path: Path,
    baseline_path: Path,
    input_output_path: Path,
    output_output_path: Path,
    ip: str,
    port: int,
) -> None:
    baseline_inputs, baseline_outputs = (
        load_state(
            baseline_path
        )
    )

    config = load_config(
        config_path
    )

    current_input_root, _ = (
        generate_xml(
            config,
            mode="normal",
        )
    )

    current_output_root = create_root(
        ip=ip,
        port=port,
        title="LoxBridge - Homey Outputs",
    )

    generate_commands(
        root=current_output_root,
        config=config,
    )

    current_inputs = (
        input_state_from_xml(
            current_input_root
        )
    )

    current_outputs = (
        output_state_from_xml(
            current_output_root
        )
    )

    input_delta = compare_states(
        baseline_inputs,
        current_inputs,
    )

    output_delta = compare_states(
        baseline_outputs,
        current_outputs,
    )

    delta_input_root = build_delta_root(
        source_root=current_input_root,
        command_tag="VirtualInUdpCmd",
        current_state=current_inputs,
        added_keys=input_delta.added,
        title=DELTA_INPUT_TITLE,
    )

    delta_output_root = build_delta_root(
        source_root=current_output_root,
        command_tag="VirtualOutCmd",
        current_state=current_outputs,
        added_keys=output_delta.added,
        title=DELTA_OUTPUT_TITLE,
    )

    input_written = save_delta_or_remove(
        root=delta_input_root,
        added_count=len(
            input_delta.added
        ),
        path=input_output_path,
    )

    output_written = save_delta_or_remove(
        root=delta_output_root,
        added_count=len(
            output_delta.added
        ),
        path=output_output_path,
    )

    print()
    print(
        "LoxBridge DELTA Generator"
    )
    print(
        "========================="
    )
    print()

    print_delta(
        name="INPUTS",
        baseline_count=len(
            baseline_inputs
        ),
        current_count=len(
            current_inputs
        ),
        delta=input_delta,
    )

    print_delta(
        name="OUTPUTS",
        baseline_count=len(
            baseline_outputs
        ),
        current_count=len(
            current_outputs
        ),
        delta=output_delta,
    )

    print(
        "DELTA XML"
    )
    print(
        "========="
    )

    if input_written:
        print(
            "Inputs : "
            f"{input_output_path}"
        )
    else:
        print(
            "Inputs : žádné nové položky"
        )

    if output_written:
        print(
            "Outputs: "
            f"{output_output_path}"
        )
    else:
        print(
            "Outputs: žádné nové položky"
        )

    print()
    print(
        "Baseline NEBYLA změněna."
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Vygeneruje pouze nové Loxone "
            "virtuální vstupy a výstupy oproti "
            "poslední potvrzené baseline."
        )
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
    )

    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE_PATH,
    )

    parser.add_argument(
        "--inputs-output",
        type=Path,
        default=DEFAULT_INPUT_OUTPUT_PATH,
    )

    parser.add_argument(
        "--outputs-output",
        type=Path,
        default=DEFAULT_OUTPUT_OUTPUT_PATH,
    )

    parser.add_argument(
        "--ip",
        default=DEFAULT_IP,
    )

    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    generate_delta(
        config_path=args.config,
        baseline_path=args.baseline,
        input_output_path=(
            args.inputs_output
        ),
        output_output_path=(
            args.outputs_output
        ),
        ip=args.ip,
        port=args.port,
    )


if __name__ == "__main__":
    main()