import sys

from loxbridge.homey.client import HomeyClient


def print_device(device_id: str, device: dict) -> None:
    print()
    print(f"Název: {device.get('name', 'Bez názvu')}")
    print(f"Třída: {device.get('class', 'unknown')}")
    print(f"Driver: {device.get('driverId', 'unknown')}")
    print(f"ID: {device_id}")
    print()
    print("Capabilities:")
    print("-" * 72)

    capabilities = device.get("capabilitiesObj", {})

    for capability_id, capability in capabilities.items():
        value = capability.get("value")
        capability_type = capability.get("type", "unknown")
        getable = capability.get("getable", False)
        setable = capability.get("setable", False)
        units = capability.get("units") or ""

        access = []

        if getable:
            access.append("čtení")

        if setable:
            access.append("ovládání")

        access_text = ", ".join(access) if access else "bez přístupu"

        print(
            f"{capability_id:30} "
            f"value={str(value):12} "
            f"type={capability_type:8} "
            f"{units:5} "
            f"[{access_text}]"
        )


def main() -> None:
    if len(sys.argv) < 2:
        print(
            'Použití: python3 -m loxbridge.homey.inspect_device '
            '"Název zařízení"'
        )
        sys.exit(1)

    device_name = " ".join(sys.argv[1:])

    try:
        client = HomeyClient()
        result = client.find_device_by_name(device_name)

    except (ValueError, RuntimeError) as error:
        print(error)
        sys.exit(1)

    if result is None:
        print(f'Zařízení "{device_name}" nebylo nalezeno.')
        sys.exit(1)

    device_id, device = result
    print_device(device_id, device)


if __name__ == "__main__":
    main()