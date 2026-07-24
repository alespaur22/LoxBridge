import sys
import time

from loxbridge.homey.client import HomeyClient
from loxbridge.loxone.udp import send_value


DEVICE_NAME = "Pohyb Chodba"
CAPABILITY_ID = "alarm_motion"

LOXONE_IP = "192.168.68.118"
LOXONE_PORT = 7001

POLL_INTERVAL = 1.0


def read_motion(client: HomeyClient) -> bool:
    result = client.find_device_by_name(DEVICE_NAME)

    if result is None:
        raise RuntimeError(f'Zařízení "{DEVICE_NAME}" nebylo nalezeno.')

    _, device = result

    capability = device.get("capabilitiesObj", {}).get(CAPABILITY_ID)

    if capability is None:
        raise RuntimeError(
            f'Zařízení "{DEVICE_NAME}" nemá capability "{CAPABILITY_ID}".'
        )

    return bool(capability.get("value"))


def main() -> None:
    try:
        client = HomeyClient()
    except ValueError as error:
        print(error)
        sys.exit(1)

    print(f"Sleduji {DEVICE_NAME} / {CAPABILITY_ID}")
    print("Ukončení: Ctrl + C")

    previous_motion: bool | None = None

    try:
        while True:
            try:
                motion = read_motion(client)

                if motion != previous_motion:
                    loxone_value = 1 if motion else 0

                    send_value(
                        ip=LOXONE_IP,
                        port=LOXONE_PORT,
                        value=loxone_value,
                    )

                    print(
                        f"{DEVICE_NAME}: {CAPABILITY_ID}={motion} "
                        f"→ Loxone value={loxone_value}"
                    )

                    previous_motion = motion

            except RuntimeError as error:
                print(f"Chyba: {error}")

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nSledování ukončeno.")


if __name__ == "__main__":
    main()