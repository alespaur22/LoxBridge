import json
import os
import urllib.error
import urllib.request


class HomeyClient:
    def __init__(self, ip: str | None = None, token: str | None = None) -> None:
        self.ip = ip or os.environ.get("HOMEY_IP")
        self.token = token or os.environ.get("HOMEY_TOKEN")

        if not self.ip:
            raise ValueError("Chybí HOMEY_IP.")

        if not self.token:
            raise ValueError("Chybí HOMEY_TOKEN.")

    def get_devices(self) -> dict:
        url = f"http://{self.ip}/api/manager/devices/device"

        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.load(response)

        except urllib.error.HTTPError as error:
            raise RuntimeError(
                f"Homey vrátilo HTTP chybu {error.code}: {error.reason}"
            ) from error

        except urllib.error.URLError as error:
            raise RuntimeError(
                f"Homey není dostupné: {error.reason}"
            ) from error

    def find_device_by_name(self, name: str) -> tuple[str, dict] | None:
        devices = self.get_devices()

        for device_id, device in devices.items():
            device_name = device.get("name", "")

            if device_name.casefold() == name.casefold():
                return device_id, device

        return None