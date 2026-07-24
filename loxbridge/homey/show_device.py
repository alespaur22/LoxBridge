import json
import os
import sys
import urllib.error
import urllib.request


DEVICE_NAME = "LED Obývák"


def main() -> None:
    homey_ip = os.environ.get("HOMEY_IP")
    homey_token = os.environ.get("HOMEY_TOKEN")

    if not homey_ip or not homey_token:
        print("Chybí HOMEY_IP nebo HOMEY_TOKEN.")
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

    for device_id, device in devices.items():
        if device.get("name") == DEVICE_NAME:
            print(f"ID zařízení: {device_id}")
            print()
            print(json.dumps(device, indent=2, ensure_ascii=False))
            return

    print(f'Zařízení "{DEVICE_NAME}" nebylo nalezeno.')
    sys.exit(1)


if __name__ == "__main__":
    main()