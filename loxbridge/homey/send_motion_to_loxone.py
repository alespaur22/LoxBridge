import sys

from loxbridge.homey.client import HomeyClient
from loxbridge.loxone.udp import send_value


DEVICE_NAME = "Pohyb Chodba"
CAPABILITY_ID = "alarm_motion"

LOXONE_IP = "192.168.68.118"
LOXONE_PORT = 7001


def main() -> None:
    try:
        client = HomeyClient()
        result = client.find_device_by_name(DEVICE_NAME)

    except (ValueError, RuntimeError) as error:
        print(error)
        sys.exit(1)

    if result is None:
        print(f'Zařízení "{DEVICE_NAME}" nebylo nalezeno.')
        sys.exit(1)

    _, device = result

    capability = device.get("capabilitiesObj", {}).get(CAPABILITY_ID)

    if capability is None:
        print(
            f'Zařízení "{DEVICE_NAME}" '
            f"nemá capability {CAPABILITY_ID}."
        )
        sys.exit(1)

    motion = bool(capability.get("value"))
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


if __name__ == "__main__":
    main()