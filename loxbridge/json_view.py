"""Framework-agnostic JSON view konverze pro doménová DTO.

Doménové moduly (loxbridge.config_service a vše, co skládá) o JSON ani
o HTTP nic nevědí a mít nemají - zůstávají čistý Python/dataclasses.
Tohle je jediné místo, které umí převést doménovou hodnotu (dataclass,
Enum, tuple, Path, vnořený dict/list) na strukturu, kterou už
`json.dumps()` bez potíží serializuje.

Žádná framework-specific magie (žádný Flask/pydantic import) - tenhle
modul je použitelný i bez nainstalovaného Flasku a testovatelný zcela
nezávisle na HTTP vrstvě.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from pathlib import Path
from typing import Any


def to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(
        value, type
    ):
        return {
            field.name: to_jsonable(
                getattr(value, field.name)
            )
            for field in dataclasses.fields(value)
        }

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]

    if isinstance(value, dict):
        return {
            str(key): to_jsonable(item)
            for key, item in value.items()
        }

    # str/int/float/bool/None procházejí beze změny.
    return value
