import sys
import time

from loxbridge.homey.client import HomeyClient
from loxbridge.loxone.udp import send_value


LOXONE_IP = "192.168.68.118"
LOXONE_PORT = 7001
POLL_INTERVAL = 1.0


def read_capability(
    client: HomeyClient,
    device_name: str,
    capability_id: str,
) -> bool | int | float | str | None:
    result = client.find_device_by_name(device_name)

    if result is None:
        raise RuntimeError(f'Zařízení "{device_name}" nebylo nalezeno.')

    _, device = result

    capability = device.get("capabilitiesObj", {}).get(capability_id)

    if capability is None:
        raise RuntimeError(
            f'Zařízení "{device_name}" nemá capability "{capability_id}".'
        )

    return capability.get("value")


def convert_for_loxone(value: object) -> bool | int | float | str:
    if isinstance(value, bool):
        return 1 if value else 0

    if value is None:
        raise RuntimeError("Capability nemá žádnou hodnotu.")

    if isinstance(value, (int, float, str)):
        return value

    raise RuntimeError(
        f"Nepodporovaný typ hodnoty: {type(value).__name__}"
    )


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "Použití:\n"
            'python3 -m loxbridge.homey.watch_capability '
            '"Název zařízení" capability_id'
        )
        print()
        print(
            "Příklad:\n"
            'python3 -m loxbridge.homey.watch_capability '
            '"Pohyb Chodba" alarm_motion'
        )
        sys.exit(1)

    device_name = sys.argv[1]
    capability_id = sys.argv[2]

    try:
        client = HomeyClient()
    except ValueError as error:
        print(error)
        sys.exit(1)

    print(f"Sleduji: {device_name}")
    print(f"Capability: {capability_id}")
    print("Ukončení: Ctrl + C")

    previous_value: object = object()

    try:
        while True:
            try:
                value = read_capability(
                    client=client,
                    device_name=device_name,
                    capability_id=capability_id,
                )

                if value != previous_value:
                    loxone_value = convert_for_loxone(value)

                    send_value(
                        ip=LOXONE_IP,
                        port=LOXONE_PORT,
                        value=loxone_value,
                    )

                    print(
                        f"{device_name}: {capability_id}={value!r} "
                        f"→ Loxone value={loxone_value}"
                    )

                    previous_value = value

            except RuntimeError as error:
                print(f"Chyba: {error}")

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nSledování ukončeno.")


if __name__ == "__main__":
    main()