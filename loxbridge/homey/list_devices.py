import json
import os
import sys
import urllib.error
import urllib.request


def main() -> None:
    homey_ip = os.environ.get("HOMEY_IP")
    homey_token = os.environ.get("HOMEY_TOKEN")

    if not homey_ip or not homey_token:
        print("Chybí HOMEY_IP nebo HOMEY_TOKEN.")
        print("Nejdřív je nastav v terminálu pomocí příkazu export.")
        sys.exit(1)

    url = f"http://{homey_ip}/api/manager/devices/device"

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {homey_token}",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            devices = json.load(response)

    except urllib.error.HTTPError as error:
        print(f"Homey vrátilo HTTP chybu {error.code}: {error.reason}")
        sys.exit(1)

    except urllib.error.URLError as error:
        print(f"Homey není dostupné: {error.reason}")
        sys.exit(1)

    print(f"Nalezeno zařízení: {len(devices)}")
    print()

    for device in devices.values():
        name = device.get("name", "Bez názvu")
        device_class = device.get("class", "unknown")
        print(f"- {name} [{device_class}]")


if __name__ == "__main__":
    main()