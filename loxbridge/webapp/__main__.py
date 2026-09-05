"""Spuštění dev serveru: python -m loxbridge.webapp

Bind defaultně jen na 127.0.0.1 - žádný jiný stroj v síti se sem
nedostane. Žádná systemd integrace, žádný auto-restart produkčního
Loxbridge - tohle je oddělený, samostatně spouštěný proces nad stejným
config/devices/ + config/templates/ + exports/homey_devices.json, jaké
už používá zbytek projektu.

Read-only režim (žádný zápis, GET/preview/validate dál fungují):

    LOXBRIDGE_CONFIG_READ_ONLY=1 python -m loxbridge.webapp
    python -m loxbridge.webapp --read-only
"""

from __future__ import annotations

import argparse
import os

from loxbridge.config_service import DeviceConfigurationService
from loxbridge.webapp.app import create_app


def _read_only_from_environment() -> bool:
    value = os.environ.get(
        "LOXBRIDGE_CONFIG_READ_ONLY", ""
    )
    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "LoxBridge Configurator - vývojový server."
        )
    )

    parser.add_argument(
        "--read-only",
        action="store_true",
        help=(
            "Zakázat všechny save operace - GET/preview/"
            "validate dál fungují beze změny. Rovnocenné "
            "nastavení proměnné prostředí "
            "LOXBRIDGE_CONFIG_READ_ONLY=1."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    read_only = (
        args.read_only or _read_only_from_environment()
    )

    if read_only:
        print(
            "LoxBridge Configurator: READ-ONLY režim - "
            "žádný zápis nebude proveden."
        )

    service = DeviceConfigurationService(
        read_only=read_only
    )

    app = create_app(service=service)
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
