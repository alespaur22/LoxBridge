from __future__ import annotations

import re
from typing import Any


PROFILE_SCHEMA_VERSION = 4

RGBW_WHITE_MASTER_DIM = 0.01


INPUT_BANK_CAPABILITY_RE = re.compile(
    r"^measure_voltage\.input(?P<index>\d+)$"
)


# Fibaro RGBW Controller 2 neposílá tlačítkové vstupy jako změny
# measure_voltage.*. V režimu Scene je Homey publikuje jako Flow
# trigger "Switch is pressed". Adaptér je soustředěný do Profile
# Engine, takže runtime ani XML generátory nemusí znát konkrétní
# Homey driver.
FIBARO_RGBW_SCENE_DRIVER = (
    "homey:app:com.fibaro:FGRGBWM-442"
)

FIBARO_SCENE_EVENTS = (
    ("press_1x", "Press 1x", "Key Pressed 1 time"),
    ("press_2x", "Press 2x", "Key Pressed 2 times"),
    ("press_3x", "Press 3x", "Key Pressed 3 times"),
    ("hold", "Hold", "Key Held Down"),
    ("release", "Release", "Key Released"),
)


def _capability(
    capabilities: dict[str, dict[str, Any]],
    capability_id: str,
) -> dict[str, Any] | None:
    capability = capabilities.get(capability_id)

    if not isinstance(capability, dict):
        return None

    return capability


def _is_setable(
    capabilities: dict[str, dict[str, Any]],
    capability_id: str,
    expected_type: str | None = None,
) -> bool:
    capability = _capability(
        capabilities,
        capability_id,
    )

    if capability is None:
        return False

    if capability.get("setable") is not True:
        return False

    if (
        expected_type is not None
        and capability.get("type") != expected_type
    ):
        return False

    return True


def _enum_has_value(
    capabilities: dict[str, dict[str, Any]],
    capability_id: str,
    value_id: str,
) -> bool:
    capability = _capability(
        capabilities,
        capability_id,
    )

    if capability is None:
        return False

    values = capability.get("values")

    if not isinstance(values, list):
        return False

    return any(
        isinstance(value, dict)
        and value.get("id") == value_id
        for value in values
    )


def _command(
    *,
    key: str,
    title: str,
    kind: str,
    targets: dict[str, str],
    group: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "key": key,
        "title": title,
        "kind": kind,
        "targets": targets,
    }

    if group:
        result["group"] = group

    if options:
        result["options"] = options

    return result


def detect_primary_profile(
    exported_device: dict[str, Any],
    capabilities: dict[str, dict[str, Any]],
) -> str:
    device_class = str(
        exported_device.get("class") or ""
    )

    has_onoff = _is_setable(
        capabilities,
        "onoff",
        "boolean",
    )

    has_dim = _is_setable(
        capabilities,
        "dim",
        "number",
    )

    has_hue = _is_setable(
        capabilities,
        "light_hue",
        "number",
    )

    has_saturation = _is_setable(
        capabilities,
        "light_saturation",
        "number",
    )

    has_temperature = _is_setable(
        capabilities,
        "light_temperature",
        "number",
    )

    has_white_dim = _is_setable(
        capabilities,
        "dim.white",
        "number",
    )

    if device_class == "light":
        if (
            has_onoff
            and has_dim
            and has_hue
            and has_saturation
            and has_white_dim
        ):
            return "light.rgb_white_channel"

        if (
            has_onoff
            and has_dim
            and has_hue
            and has_saturation
            and has_temperature
        ):
            return "light.rgb_tunable_white"

        if (
            has_onoff
            and has_dim
            and has_temperature
        ):
            return "light.tunable_white"

        if (
            has_onoff
            and has_dim
            and has_hue
            and has_saturation
        ):
            return "light.rgb"

        if has_onoff and has_dim:
            return "light.dimmer"

        if has_onoff:
            return "light.switch"

    if device_class == "thermostat":
        if (
            _is_setable(
                capabilities,
                "operation_mode",
                "enum",
            )
            and _is_setable(
                capabilities,
                "fan_speed",
                "enum",
            )
            and _is_setable(
                capabilities,
                "target_temperature",
                "number",
            )
        ):
            return "climate.ac"

        if _is_setable(
            capabilities,
            "target_temperature",
            "number",
        ):
            return "climate.thermostat"

    if device_class == "sensor":
        if "alarm_motion" in capabilities:
            return "sensor.motion"

        if (
            "measure_temperature" in capabilities
            or "measure_humidity" in capabilities
        ):
            return "sensor.environment"

        return "sensor.generic"

    if device_class == "watervalve":
        return "water.valve"

    if device_class == "socket" and has_onoff:
        return "switch.socket"

    if device_class in {"button", "remote"}:
        return "input.remote"

    if has_onoff:
        return "switch.generic"

    return "generic"


def build_commands(
    *,
    device_name: str,
    device_slug: str,
    profile_id: str,
    capabilities: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []

    if profile_id == "light.rgb_tunable_white":
        rgb_targets = {
            "onoff": "onoff",
            "dim": "dim",
            "hue": "light_hue",
            "saturation": "light_saturation",
        }

        if _is_setable(
            capabilities,
            "light_mode",
            "enum",
        ) and _enum_has_value(
            capabilities,
            "light_mode",
            "color",
        ):
            rgb_targets["mode"] = "light_mode"

        lumitech_targets = {
            "onoff": "onoff",
            "dim": "dim",
            "temperature": "light_temperature",
        }

        if _is_setable(
            capabilities,
            "light_mode",
            "enum",
        ) and _enum_has_value(
            capabilities,
            "light_mode",
            "temperature",
        ):
            lumitech_targets["mode"] = "light_mode"

        commands.extend(
            [
                _command(
                    key=f"{device_slug}_rgb",
                    title=f"{device_name} - RGB",
                    kind="rgb",
                    group="main_light",
                    targets=rgb_targets,
                ),
                _command(
                    key=f"{device_slug}_lumitech",
                    title=f"{device_name} - Lumitech",
                    kind="lumitech",
                    group="main_light",
                    targets=lumitech_targets,
                ),
            ]
        )

    elif profile_id == "light.tunable_white":
        targets = {
            "onoff": "onoff",
            "dim": "dim",
            "temperature": "light_temperature",
        }

        if _is_setable(
            capabilities,
            "light_mode",
            "enum",
        ) and _enum_has_value(
            capabilities,
            "light_mode",
            "temperature",
        ):
            targets["mode"] = "light_mode"

        commands.append(
            _command(
                key=f"{device_slug}_lumitech",
                title=f"{device_name} - Lumitech",
                kind="lumitech",
                group="main_light",
                targets=targets,
            )
        )

    elif profile_id == "light.rgb":
        targets = {
            "onoff": "onoff",
            "dim": "dim",
            "hue": "light_hue",
            "saturation": "light_saturation",
        }

        if _is_setable(
            capabilities,
            "light_mode",
            "enum",
        ) and _enum_has_value(
            capabilities,
            "light_mode",
            "color",
        ):
            targets["mode"] = "light_mode"

        commands.append(
            _command(
                key=f"{device_slug}_rgb",
                title=f"{device_name} - RGB",
                kind="rgb",
                group="main_light",
                targets=targets,
            )
        )

    elif profile_id == "light.dimmer":
        commands.append(
            _command(
                key=f"{device_slug}_dimmer",
                title=f"{device_name} - Dimmer",
                kind="dimmer",
                targets={
                    "onoff": "onoff",
                    "dim": "dim",
                },
            )
        )

    elif profile_id == "light.rgb_white_channel":
        shared_targets = {
            "onoff": "onoff",
            "dim": "dim",
            "hue": "light_hue",
            "saturation": "light_saturation",
            "whiteDim": "dim.white",
        }

        commands.extend(
            [
                _command(
                    key=f"{device_slug}_rgb",
                    title=f"{device_name} - RGB",
                    kind="rgb_white_rgb",
                    group="main_light",
                    targets=shared_targets,
                ),
                _command(
                    key=f"{device_slug}_white",
                    title=f"{device_name} - White",
                    kind="rgb_white_white",
                    group="main_light",
                    targets=shared_targets,
                    options={
                        "white_master_dim": (
                            RGBW_WHITE_MASTER_DIM
                        ),
                        "use_whitemode": False,
                    },
                ),
            ]
        )

    return commands


def build_normalized_inputs(
    *,
    exported_device: dict[str, Any],
    device_name: str,
    device_slug: str,
    capabilities: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    # Phase 2: stavové capability zůstávají v raw/normal vrstvě.
    # Event-only tlačítka se generují přes build_event_inputs().
    return []


def build_event_inputs(
    *,
    exported_device: dict[str, Any],
    device_name: str,
    device_slug: str,
    capabilities: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    suppress_raw_inputs: list[str] = []

    driver_id = str(
        exported_device.get("driver_id") or ""
    )

    if driver_id != FIBARO_RGBW_SCENE_DRIVER:
        return events, suppress_raw_inputs

    homey_id = str(
        exported_device.get("id") or ""
    )

    if not homey_id:
        return events, suppress_raw_inputs

    matches: list[tuple[int, str]] = []

    for capability_id, capability in capabilities.items():
        if capability.get("type") != "number":
            continue

        match = INPUT_BANK_CAPABILITY_RE.match(
            capability_id
        )

        if not match:
            continue

        matches.append(
            (
                int(match.group("index")),
                capability_id,
            )
        )

    trigger_card_id = (
        f"homey:device:{homey_id}:"
        "FGRGBWM-442:scene"
    )

    for index, source_capability in sorted(matches):
        suppress_raw_inputs.append(source_capability)

        for event_id, event_title, scene_id in FIBARO_SCENE_EVENTS:
            events.append(
                {
                    "key": (
                        f"{device_slug}_input_{index}_{event_id}"
                    ),
                    "title": (
                        f"{device_name} - Input {index} - "
                        f"{event_title}"
                    ),
                    "kind": "pulse",
                    "type": "event",
                    "trigger": {
                        "card_id": trigger_card_id,
                        "args": {
                            "input": str(index),
                            "scene": scene_id,
                        },
                    },
                }
            )

    return events, suppress_raw_inputs


def build_device_manifest(
    *,
    exported_device: dict[str, Any],
    device_name: str,
    device_slug: str,
    capabilities: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    profile_id = detect_primary_profile(
        exported_device,
        capabilities,
    )

    events, suppress_raw_inputs = build_event_inputs(
        exported_device=exported_device,
        device_name=device_name,
        device_slug=device_slug,
        capabilities=capabilities,
    )

    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "profile": profile_id,
        "commands": build_commands(
            device_name=device_name,
            device_slug=device_slug,
            profile_id=profile_id,
            capabilities=capabilities,
        ),
        "inputs": build_normalized_inputs(
            exported_device=exported_device,
            device_name=device_name,
            device_slug=device_slug,
            capabilities=capabilities,
        ),
        "events": events,
        "suppress_raw_inputs": suppress_raw_inputs,
    }
