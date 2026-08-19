from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


STATE_SCHEMA_VERSION = 1


CommandAttributes = Mapping[str, str]
CommandState = Mapping[str, CommandAttributes]


def create_state_document(
    *,
    inputs: CommandState,
    outputs: CommandState,
) -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "inputs": {
            key: dict(attributes)
            for key, attributes
            in sorted(inputs.items())
        },
        "outputs": {
            key: dict(attributes)
            for key, attributes
            in sorted(outputs.items())
        },
    }


def save_state(
    path: Path,
    *,
    inputs: CommandState,
    outputs: CommandState,
) -> None:
    document = create_state_document(
        inputs=inputs,
        outputs=outputs,
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    text = json.dumps(
        document,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )

    path.write_text(
        text + "\n",
        encoding="utf-8",
    )


def _load_command_state(
    value: Any,
    *,
    section: str,
) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        raise RuntimeError(
            f"Baseline sekce '{section}' není objekt."
        )

    result: dict[str, dict[str, str]] = {}

    for key, attributes in value.items():
        if not isinstance(key, str) or not key:
            raise RuntimeError(
                f"Baseline sekce '{section}' obsahuje "
                "neplatný key."
            )

        if not isinstance(attributes, dict):
            raise RuntimeError(
                f"Baseline položka '{key}' "
                "neobsahuje atributy."
            )

        normalized: dict[str, str] = {}

        for attribute, attribute_value in (
            attributes.items()
        ):
            if (
                not isinstance(attribute, str)
                or not isinstance(
                    attribute_value,
                    str,
                )
            ):
                raise RuntimeError(
                    f"Baseline položka '{key}' "
                    "obsahuje neplatný atribut."
                )

            normalized[attribute] = (
                attribute_value
            )

        result[key] = normalized

    return result


def load_state(
    path: Path,
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, dict[str, str]],
]:
    try:
        text = path.read_text(
            encoding="utf-8",
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            f"Baseline nebyla nalezena: {path}"
        ) from error

    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Baseline není platný JSON: {path}"
        ) from error

    if not isinstance(document, dict):
        raise RuntimeError(
            "Baseline neobsahuje JSON objekt."
        )

    schema_version = document.get(
        "schema_version"
    )

    if schema_version != STATE_SCHEMA_VERSION:
        raise RuntimeError(
            "Nepodporovaná baseline schema version: "
            f"{schema_version}"
        )

    inputs = _load_command_state(
        document.get("inputs"),
        section="inputs",
    )

    outputs = _load_command_state(
        document.get("outputs"),
        section="outputs",
    )

    return inputs, outputs