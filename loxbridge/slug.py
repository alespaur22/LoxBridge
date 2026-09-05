"""Sdílená slugifikace jmen do bezpečných identifikátorů.

Přesunuto beze změny chování z `loxbridge/generate.py` - tělo funkce
je identické. Používá `loxbridge.generate` (device/capability sluggy)
i `loxbridge.instance_builder` (výchozí key_base z instance_name).
"""

from __future__ import annotations

import re
import unicodedata


def slugify(
    value: str,
) -> str:
    normalized = unicodedata.normalize(
        "NFKD",
        value,
    )

    ascii_value = (
        normalized
        .encode(
            "ascii",
            "ignore",
        )
        .decode("ascii")
    )

    ascii_value = ascii_value.lower()

    slug = re.sub(
        r"[^a-z0-9]+",
        "_",
        ascii_value,
    )

    slug = re.sub(
        r"_+",
        "_",
        slug,
    )

    slug = slug.strip("_")

    return slug or "device"
