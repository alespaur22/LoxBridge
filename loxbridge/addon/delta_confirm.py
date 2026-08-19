from __future__ import annotations

import argparse
from pathlib import Path

from loxbridge.addon.delta import (
    CommandState,
    compare_states,
    input_state_from_xml,
    output_state_from_xml,
)
from loxbridge.addon.delta_state import (
    load_state,
    save_state,
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


def merge_added(
    *,
    baseline: CommandState,
    current: CommandState,
    added_keys: tuple[str, ...],
) -> dict[str, dict[str, str]]:
    result = {
        key: dict(attributes)
        for key, attributes in baseline.items()
    }

    for key in added_keys:
        attributes = current.get(key)

        if attributes is None:
            raise RuntimeError(
                "Potvrzovaný key není "
                f"v aktuálním stavu: {key}"
            )

        result[key] = dict(
            attributes
        )

    return result


def confirm_delta(
    *,
    config_path: Path,
    baseline_path: Path,
    ip: str,
    port: int,
    apply: bool,
) -> None:
    baseline_inputs, baseline_outputs = (
        load_state(
            baseline_path
        )
    )

    config = load_config(
        config_path
    )

    input_root, _ = generate_xml(
        config,
        mode="normal",
    )

    output_root = create_root(
        ip=ip,
        port=port,
        title="LoxBridge - Homey Outputs",
    )

    generate_commands(
        root=output_root,
        config=config,
    )

    current_inputs = input_state_from_xml(
        input_root
    )

    current_outputs = output_state_from_xml(
        output_root
    )

    input_delta = compare_states(
        baseline_inputs,
        current_inputs,
    )

    output_delta = compare_states(
        baseline_outputs,
        current_outputs,
    )

    merged_inputs = merge_added(
        baseline=baseline_inputs,
        current=current_inputs,
        added_keys=input_delta.added,
    )

    merged_outputs = merge_added(
        baseline=baseline_outputs,
        current=current_outputs,
        added_keys=output_delta.added,
    )

    print()
    print("LoxBridge DELTA Confirm")
    print("=======================")
    print()

    print("INPUTS")
    print("======")
    print(
        f"Baseline před : {len(baseline_inputs)}"
    )
    print(
        f"Potvrdit nové : {len(input_delta.added)}"
    )
    print(
        f"Zůstává navíc : {len(input_delta.removed)}"
    )
    print(
        f"Změněné       : {len(input_delta.changed)}"
    )
    print(
        f"Baseline po   : {len(merged_inputs)}"
    )
    print()

    for key in input_delta.added:
        print(
            f"  + {key}"
        )

    print()
    print("OUTPUTS")
    print("=======")
    print(
        f"Baseline před : {len(baseline_outputs)}"
    )
    print(
        f"Potvrdit nové : {len(output_delta.added)}"
    )
    print(
        f"Zůstává navíc : {len(output_delta.removed)}"
    )
    print(
        f"Změněné       : {len(output_delta.changed)}"
    )
    print(
        f"Baseline po   : {len(merged_outputs)}"
    )
    print()

    if not apply:
        print(
            "DRY RUN — baseline nebyla změněna."
        )
        print(
            "Po fyzickém potvrzení importu "
            "spusť znovu s --apply."
        )
        return

    save_state(
        baseline_path,
        inputs=merged_inputs,
        outputs=merged_outputs,
    )

    print(
        f"Baseline aktualizována: {baseline_path}"
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Potvrdí nově importované DELTA "
            "položky jako skutečně nasazené "
            "v Loxone."
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
        "--ip",
        default=DEFAULT_IP,
    )

    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Skutečně zapíše potvrzené "
            "ADDED položky do baseline."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    confirm_delta(
        config_path=args.config,
        baseline_path=args.baseline,
        ip=args.ip,
        port=args.port,
        apply=args.apply,
    )


if __name__ == "__main__":
    main()