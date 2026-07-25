from __future__ import annotations

from loxbridge.addon.addon_generator import TemplateGenerator
from loxbridge.addon.xml_generator import XmlGenerator
from loxbridge.config.loader import ConfigLoader
from loxbridge.homey.client import HomeyClient
from loxbridge.homey.parser import HomeyParser


def main() -> None:

    config = ConfigLoader().load()

    homey_config = config.get("homey")

    if not isinstance(homey_config, dict):
        raise ValueError(
            "V config.yaml chybí sekce 'homey'."
        )

    homey_ip = homey_config.get("ip")
    homey_token = homey_config.get("token")

    if not homey_ip:
        raise ValueError(
            "V config.yaml chybí homey.ip."
        )

    if not homey_token:
        raise ValueError(
            "V config.yaml chybí homey.token."
        )

    print("Načítám zařízení z Homey...")

    client = HomeyClient(
        ip=str(homey_ip),
        token=str(homey_token),
    )

    raw_devices = client.get_devices()

    devices = HomeyParser.parse(
        raw_devices
    )

    print(
        f"Nalezeno zařízení: {len(devices)}"
    )

    capability_count = sum(
        len(device.capabilities)
        for device in devices
    )

    print(
        f"Nalezeno capabilities: {capability_count}"
    )

    print("Generuji XML šablonu...")

    xml = XmlGenerator(
        devices=devices,
    ).generate()

    print("Vytvářím Loxone Template...")

    output_path = TemplateGenerator().build(
        xml=xml,
    )

    print()
    print("----------------------------------------")
    print("Hotovo")
    print("----------------------------------------")
    print(f"Zařízení    : {len(devices)}")
    print(f"Capabilities: {capability_count}")
    print(f"Výstup      : {output_path.resolve()}")
    print("----------------------------------------")


if __name__ == "__main__":
    main()