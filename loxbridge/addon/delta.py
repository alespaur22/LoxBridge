from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
import xml.etree.ElementTree as ET


CommandAttributes = Mapping[str, str]
CommandState = Mapping[str, CommandAttributes]


@dataclass(frozen=True)
class ChangedCommand:
    key: str
    before: dict[str, str]
    after: dict[str, str]


@dataclass(frozen=True)
class DeltaResult:
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[ChangedCommand, ...]
    unchanged: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        return bool(
            self.added
            or self.removed
            or self.changed
        )


def compare_states(
    baseline: CommandState,
    current: CommandState,
) -> DeltaResult:
    baseline_keys = set(baseline)
    current_keys = set(current)

    added = tuple(
        sorted(
            current_keys - baseline_keys
        )
    )

    removed = tuple(
        sorted(
            baseline_keys - current_keys
        )
    )

    shared_keys = sorted(
        baseline_keys & current_keys
    )

    changed: list[ChangedCommand] = []
    unchanged: list[str] = []

    for key in shared_keys:
        before = dict(baseline[key])
        after = dict(current[key])

        if before == after:
            unchanged.append(key)
            continue

        changed.append(
            ChangedCommand(
                key=key,
                before=before,
                after=after,
            )
        )

    return DeltaResult(
        added=added,
        removed=removed,
        changed=tuple(changed),
        unchanged=tuple(unchanged),
    )


def _add_command(
    state: dict[str, dict[str, str]],
    key: str,
    command: ET.Element,
) -> None:
    if key in state:
        raise RuntimeError(
            f"Duplicitní LoxBridge key v XML: {key}"
        )

    state[key] = dict(
        command.attrib
    )


def _input_key(
    command: ET.Element,
) -> str:
    check = command.get("Check")

    if not check:
        raise RuntimeError(
            "VirtualInUdpCmd nemá atribut Check."
        )

    suffix = "=\\v"

    if not check.endswith(suffix):
        raise RuntimeError(
            "Neplatný rozpoznávací příkaz "
            f"VirtualInUdpCmd: {check}"
        )

    key = check[:-len(suffix)]

    if not key:
        raise RuntimeError(
            "VirtualInUdpCmd obsahuje prázdný key."
        )

    return key


def input_state_from_xml(
    root: ET.Element,
) -> dict[str, dict[str, str]]:
    if root.tag != "VirtualInUdp":
        raise RuntimeError(
            "Očekáván XML root VirtualInUdp, "
            f"nalezen {root.tag}."
        )

    state: dict[str, dict[str, str]] = {}

    for command in root.findall(
        "VirtualInUdpCmd"
    ):
        key = _input_key(command)

        _add_command(
            state,
            key,
            command,
        )

    return state


def _assignment_key(
    value: str,
) -> str:
    key, separator, _ = value.partition("=")

    if not separator or not key:
        raise RuntimeError(
            f"Neplatný LoxBridge příkaz: {value}"
        )

    return key


def _output_key(
    command: ET.Element,
) -> str:
    cmd_on = command.get("CmdOn") or ""
    cmd_off = command.get("CmdOff") or ""

    keys: set[str] = set()

    if cmd_on:
        keys.add(
            _assignment_key(cmd_on)
        )

    if cmd_off:
        keys.add(
            _assignment_key(cmd_off)
        )

    if not keys:
        raise RuntimeError(
            "VirtualOutCmd neobsahuje CmdOn ani CmdOff."
        )

    if len(keys) != 1:
        raise RuntimeError(
            "VirtualOutCmd používá rozdílný key "
            "v CmdOn a CmdOff."
        )

    return next(iter(keys))


def output_state_from_xml(
    root: ET.Element,
) -> dict[str, dict[str, str]]:
    if root.tag != "VirtualOut":
        raise RuntimeError(
            "Očekáván XML root VirtualOut, "
            f"nalezen {root.tag}."
        )

    state: dict[str, dict[str, str]] = {}

    for command in root.findall(
        "VirtualOutCmd"
    ):
        key = _output_key(command)

        _add_command(
            state,
            key,
            command,
        )

    return state