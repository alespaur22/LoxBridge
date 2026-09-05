"""Save: the single write path for a Device Instance.

Save is itself a security boundary - it never trusts that a caller
(Preview/GUI) already validated. It always reloads the current
instance store fresh from disk and re-runs the exact same
``validate_device_instance()`` a Preview/GUI would call for display
purposes, refusing to write anything at all on any error-severity
problem. There is no bypass parameter.

    result = validate_device_instance(...)
    if not result.is_valid:
        raise SaveError(result)
    atomic_write(...)

The actual write is atomic (see ``loxbridge.instances.save_instance``:
temp file + ``os.replace``), so a crash mid-write never leaves a
corrupted or partially-overwritten instance file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loxbridge.instance_validation import (
    SaveMode,
    ValidationResult,
    validate_device_instance,
)
from loxbridge.instances import (
    load_all_instances,
    save_instance,
)


class SaveError(RuntimeError):
    def __init__(self, result: ValidationResult) -> None:
        self.result = result

        messages = "\n".join(
            f"- {problem.code}: {problem.message}"
            for problem in result.errors()
        )

        super().__init__(
            "Device Instance je nevalidní, zápis "
            f"odmítnut:\n{messages}"
        )


def save_device_instance(
    instance: dict[str, Any],
    *,
    directory: Path,
    mode: SaveMode,
    homey_device: dict[str, Any] | None = None,
    template: dict[str, Any] | None = None,
) -> Path:
    """Jediná cesta k zápisu Device Instance.

    Vždy si sám znovu načte aktuální stav `directory` a znovu spustí
    `validate_device_instance()` - bez ohledu na to, jestli volající
    validaci už dřív zavolal (např. kvůli zobrazení v GUI). Při
    jakémkoliv error-severity problému nezapíše vůbec nic, ani
    nevytvoří, ani nepřepíše žádný soubor.
    """
    existing_instances = load_all_instances(directory)

    result = validate_device_instance(
        instance,
        homey_device=homey_device,
        template=template,
        existing_instances=existing_instances,
        mode=mode,
    )

    if not result.is_valid:
        raise SaveError(result)

    return save_instance(instance, directory)
