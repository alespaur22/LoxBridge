"""Read-only Device Status report: Configured / New / Missing.

This compares two already-existing, already-loadable sources of truth:

- the current Homey export (``exports/homey_devices.json``) - what
  Homey reports *right now*,
- the Device Instance store (``config/devices/*.yaml``, see
  ``loxbridge.instances``) - what LoxBridge already has configured.

The status of a device is always a *derived* value, computed fresh from
these two sources every time it's asked for. Nothing here is persisted
anywhere, and nothing here mutates its inputs - ``compute_device_status_
report()`` is a pure function. This module is not imported by
``loxbridge.generate``, ``loxbridge.bridge`` or any XML generator, and
does not affect them.

Field names deliberately reuse the vocabulary that already exists
instead of inventing parallel terms:

- ``exported_at`` / ``homey_ip`` / ``device_count`` come verbatim from
  the Homey export's own top-level fields.
- ``instance_name`` / ``enabled`` come verbatim from the Device
  Instance schema (see ``loxbridge/instances.py``).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from loxbridge.capability_filter import (
    should_include_capability,
)
from loxbridge.instances import (
    DEFAULT_INSTANCES_DIR,
    load_all_instances,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPORT_PATH = PROJECT_ROOT / "exports" / "homey_devices.json"


class DeviceStatus(str, Enum):
    CONFIGURED = "configured"
    NEW = "new"
    MISSING = "missing"


@dataclass(frozen=True)
class DeviceStatusEntry:
    homey_id: str
    status: DeviceStatus

    # Z Homey exportu - vyplněno jen pro CONFIGURED/NEW
    # (zařízení je v aktuálním exportu přítomné).
    homey_name: str | None = None
    homey_class: str | None = None
    driver_id: str | None = None
    homey_available: bool | None = None

    # Z Device Instance - vyplněno jen pro CONFIGURED/MISSING
    # (instance existuje).
    instance_name: str | None = None
    instance_enabled: bool | None = None

    # Odvozeno stejným pravidlem jako generate.py
    # (loxbridge.capability_filter.should_include_capability) nad
    # syrovými Homey capabilities - nezávislé na status i na
    # ostatních polích. None pro MISSING: bez aktuálních Homey dat
    # nelze bridgeability posoudit.
    bridgeable: bool | None = None
    bridgeable_capability_count: int | None = None


@dataclass(frozen=True)
class DeviceStatusReport:
    # Metadata převzatá 1:1 z exports/homey_devices.json.
    exported_at: str | None
    homey_ip: str | None
    device_count: int | None  # deklarovaná hodnota z exportu

    # Odvozené počty.
    actual_device_count: int  # len(export["devices"])
    instance_count: int

    entries: tuple[DeviceStatusEntry, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def by_status(
        self,
        status: DeviceStatus,
    ) -> tuple[DeviceStatusEntry, ...]:
        return tuple(
            entry
            for entry in self.entries
            if entry.status == status
        )


def _bridgeable_capability_count(
    device: dict[str, Any] | None,
) -> int | None:
    if device is None:
        # MISSING - zařízení není v aktuálním exportu, bez
        # aktuálních Homey dat nelze bridgeability posoudit.
        return None

    raw_capabilities = device.get("capabilities")

    if not isinstance(raw_capabilities, list):
        raw_capabilities = []

    return sum(
        1
        for capability in raw_capabilities
        if isinstance(capability, dict)
        and should_include_capability(capability)
    )


def compute_device_status_report(
    export_data: dict[str, Any],
    instances: dict[str, dict[str, Any]],
) -> DeviceStatusReport:
    """Čistá funkce: žádné I/O, žádná mutace `export_data`/`instances`.

    `export_data` je přesně to, co vrátí json.load() nad
    exports/homey_devices.json. `instances` je přesně to, co vrátí
    loxbridge.instances.load_all_instances().
    """
    raw_devices = export_data.get("devices")

    if not isinstance(raw_devices, list):
        raw_devices = []

    export_by_id: dict[str, dict[str, Any]] = {}

    for device in raw_devices:
        if not isinstance(device, dict):
            continue

        homey_id = device.get("id")

        if isinstance(homey_id, str) and homey_id:
            export_by_id[homey_id] = device

    # Deterministické pořadí - podle homey_id, ne podle pořadí v
    # souboru (to se může mezi exporty/OS lišit).
    all_ids = sorted(
        set(export_by_id) | set(instances)
    )

    entries: list[DeviceStatusEntry] = []

    for homey_id in all_ids:
        device = export_by_id.get(homey_id)
        instance = instances.get(homey_id)

        if device is not None and instance is not None:
            status = DeviceStatus.CONFIGURED

        elif device is not None:
            status = DeviceStatus.NEW

        else:
            status = DeviceStatus.MISSING

        bridgeable_count = _bridgeable_capability_count(device)

        entries.append(
            DeviceStatusEntry(
                homey_id=homey_id,
                status=status,
                homey_name=(
                    device.get("name") if device else None
                ),
                homey_class=(
                    device.get("class") if device else None
                ),
                driver_id=(
                    device.get("driver_id")
                    if device
                    else None
                ),
                homey_available=(
                    device.get("available")
                    if device
                    else None
                ),
                instance_name=(
                    instance.get("instance_name")
                    if instance
                    else None
                ),
                instance_enabled=(
                    instance.get("enabled")
                    if instance
                    else None
                ),
                bridgeable=(
                    None
                    if bridgeable_count is None
                    else bridgeable_count > 0
                ),
                bridgeable_capability_count=bridgeable_count,
            )
        )

    declared_device_count = export_data.get("device_count")

    if not isinstance(declared_device_count, int):
        declared_device_count = None

    actual_device_count = len(raw_devices)

    warnings: list[str] = []

    if (
        declared_device_count is not None
        and declared_device_count != actual_device_count
    ):
        warnings.append(
            "Export deklaruje device_count="
            f"{declared_device_count}, ale pole devices "
            f"obsahuje {actual_device_count} položek."
        )

    exported_at = export_data.get("exported_at")

    if not isinstance(exported_at, str):
        exported_at = None

    homey_ip = export_data.get("homey_ip")

    if not isinstance(homey_ip, str):
        homey_ip = None

    return DeviceStatusReport(
        exported_at=exported_at,
        homey_ip=homey_ip,
        device_count=declared_device_count,
        actual_device_count=actual_device_count,
        instance_count=len(instances),
        entries=tuple(entries),
        warnings=tuple(warnings),
    )


def _entry_label(entry: DeviceStatusEntry) -> str:
    return (
        entry.homey_name
        or entry.instance_name
        or entry.homey_id
    )


def _entry_flags(entry: DeviceStatusEntry) -> str:
    flags: list[str] = []

    if entry.homey_available is False:
        flags.append("Homey: offline")

    if entry.instance_enabled is False:
        flags.append("instance: disabled")

    if entry.bridgeable is False:
        flags.append("not bridgeable")

    if not flags:
        return ""

    return " [" + ", ".join(flags) + "]"


def _print_group(
    report: DeviceStatusReport,
    status: DeviceStatus,
) -> None:
    entries = report.by_status(status)

    print(f"{status.value.upper()} ({len(entries)})")

    for entry in entries:
        print(
            f"  - {_entry_label(entry)}"
            f"{_entry_flags(entry)}  "
            f"({entry.homey_id})"
        )

    print()


def _print_new_group(report: DeviceStatusReport) -> None:
    entries = report.by_status(DeviceStatus.NEW)

    bridgeable = tuple(
        entry for entry in entries if entry.bridgeable
    )
    not_bridgeable = tuple(
        entry for entry in entries if not entry.bridgeable
    )

    print(f"NEW ({len(entries)})")

    print(
        f"  bridgeable=True ({len(bridgeable)}) "
        "- nabídnout k nové konfiguraci"
    )

    for entry in bridgeable:
        print(
            f"    - {_entry_label(entry)}  "
            f"({entry.homey_id})  "
            "capabilities="
            f"{entry.bridgeable_capability_count}"
        )

    print(
        f"  bridgeable=False ({len(not_bridgeable)}) "
        "- skrýt z hlavního seznamu, jen diagnostika"
    )

    for entry in not_bridgeable:
        print(
            f"    - {_entry_label(entry)}  "
            f"({entry.homey_id})"
        )

    print()


def main() -> None:
    print("LoxBridge Device Status")
    print("========================")
    print()

    try:
        export_data = json.loads(
            EXPORT_PATH.read_text(encoding="utf-8")
        )

    except FileNotFoundError as error:
        print(
            f"Chyba: export nebyl nalezen: {EXPORT_PATH}",
            file=sys.stderr,
        )

        raise SystemExit(1) from error

    instances = load_all_instances(DEFAULT_INSTANCES_DIR)

    report = compute_device_status_report(
        export_data,
        instances,
    )

    print(f"Export:         {EXPORT_PATH}")
    print(f"Instance store: {DEFAULT_INSTANCES_DIR}")
    print()

    if report.exported_at:
        print(f"exported_at:  {report.exported_at}")

    if report.homey_ip:
        print(f"homey_ip:     {report.homey_ip}")

    print(f"device_count (deklarovaný): {report.device_count}")
    print(
        "device_count (skutečný):    "
        f"{report.actual_device_count}"
    )
    print(f"Instance store:             {report.instance_count}")
    print()

    bridgeable_true = sum(
        1 for entry in report.entries if entry.bridgeable is True
    )
    bridgeable_false = sum(
        1
        for entry in report.entries
        if entry.bridgeable is False
    )
    bridgeable_unknown = sum(
        1
        for entry in report.entries
        if entry.bridgeable is None
    )

    print(f"Bridgeable=True:           {bridgeable_true}")
    print(f"Bridgeable=False:          {bridgeable_false}")
    print(
        "Bridgeable=None (MISSING): "
        f"{bridgeable_unknown}"
    )
    print()

    _print_group(report, DeviceStatus.CONFIGURED)
    _print_new_group(report)
    _print_group(report, DeviceStatus.MISSING)

    if report.warnings:
        print("Varování:")

        for warning in report.warnings:
            print(f"  - {warning}")

    else:
        print("Žádná varování.")


if __name__ == "__main__":
    main()
