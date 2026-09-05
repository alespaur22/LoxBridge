"""One-off migration: build Device Instance files from an existing
``config.generated.yaml``.

This tool is read-only with respect to ``config.generated.yaml`` (and
every other runtime file) - it only produces new files under a target
instances directory. It is not called from ``loxbridge.generate`` or
from the bridge; it must be run explicitly, once, by a person who
understands they are creating the initial Device Instance store from
whatever LoxBridge already generated in the past.

Because the values are copied verbatim from the already-generated
config (see ``loxbridge.instances.build_instance_from_generated_device``),
running this against a config.generated.yaml that is currently wired
into a live Loxone project preserves every existing technical key and
every existing Loxone display name exactly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from loxbridge.instances import (
    DEFAULT_INSTANCES_DIR,
    build_instance_from_generated_device,
    save_instance,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SOURCE_PATH = (
    PROJECT_ROOT / "config" / "config.generated.yaml"
)


def load_generated_config(path: Path) -> dict[str, Any]:
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


def migrate(
    source_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    config = load_generated_config(source_path)

    devices = config.get("devices")

    if not isinstance(devices, list):
        raise RuntimeError(
            f"{source_path} neobsahuje seznam devices."
        )

    written: list[Path] = []
    skipped: list[str] = []

    for device in devices:
        if not isinstance(device, dict):
            continue

        try:
            instance = build_instance_from_generated_device(
                device
            )

        except ValueError as error:
            skipped.append(str(error))
            continue

        written.append(save_instance(instance, output_dir))

    return {
        "source": source_path,
        "output_dir": output_dir,
        "device_count": len(devices),
        "written": written,
        "skipped": skipped,
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Jednorázová migrace: z config.generated.yaml "
            "vytvoří Device Instance soubory. "
            "config.generated.yaml se při tom nikdy nezapisuje."
        )
    )

    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_PATH,
        help=(
            "Cesta ke config.generated.yaml "
            "(výchozí: config/config.generated.yaml)."
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_INSTANCES_DIR,
        help=(
            "Kam zapsat Device Instance soubory "
            "(výchozí: config/devices/)."
        ),
    )

    return parser.parse_args()


def main() -> None:
    print("LoxBridge Device Instance Migration")
    print("====================================")

    args = parse_arguments()

    print(f"Zdroj:  {args.source}")
    print(f"Výstup: {args.output_dir}")
    print()

    result = migrate(args.source, args.output_dir)

    print("Migrace dokončena.")
    print(f"Zařízení ve zdroji:      {result['device_count']}")
    print(f"Vytvořeno instancí:      {len(result['written'])}")

    if result["skipped"]:
        print(
            "Přeskočeno (chybí "
            f"homey_id): {len(result['skipped'])}"
        )

        for reason in result["skipped"]:
            print(f"  - {reason}")

    print()
    print(
        "config.generated.yaml nebyl změněn - "
        "tento nástroj ho pouze čte."
    )


if __name__ == "__main__":
    try:
        main()

    except RuntimeError as error:
        print(f"Chyba: {error}", file=sys.stderr)

        raise SystemExit(1) from error
