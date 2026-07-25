import sys
import time

from loxbridge.homey.client import HomeyClient
from loxbridge.logger.logger import logger
from loxbridge.loxone.udp import send_value

POLL_INTERVAL = 1.0


class Bridge:
    def __init__(self, config):
        self.config = config

    @staticmethod
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

    def run(self) -> None:
        try:
            homey_config = self.config["homey"]
            loxone_config = self.config["loxone"]
            devices_config = self.config["devices"]

            client = HomeyClient(
                ip=homey_config["ip"],
                token=homey_config["token"],
            )

            loxone_ip = loxone_config["ip"]
            loxone_port = int(loxone_config["port"])

        except (ValueError, KeyError, TypeError) as error:
            logger.error(f"Chyba konfigurace: {error}")
            sys.exit(1)

        previous_values: dict[tuple[str, str], object] = {}

        logger.info("LoxBridge spuštěn")
        logger.info(f"Homey: {homey_config['ip']}")
        logger.info(f"Loxone: {loxone_ip}:{loxone_port}")

        for device_config in devices_config:
            device_name = device_config["name"]

            logger.info(f"Zařízení: {device_name}")

            for capability_id, loxone_key in device_config["capabilities"].items():
                logger.info(f"  {capability_id} → {loxone_key}")

        logger.info("Ukončení: Ctrl + C")

        try:
            while True:
                try:
                    devices = client.get_devices()

                    devices_by_name = {
                        device.get("name", "").casefold(): device
                        for device in devices.values()
                    }

                    for device_config in devices_config:
                        device_name = device_config["name"]
                        configured_capabilities = device_config["capabilities"]

                        device = devices_by_name.get(device_name.casefold())

                        if device is None:
                            logger.warning(
                                f'Zařízení "{device_name}" nebylo nalezeno.'
                            )
                            continue

                        capabilities = device.get("capabilitiesObj", {})

                        for capability_id, loxone_key in configured_capabilities.items():
                            capability = capabilities.get(capability_id)

                            if capability is None:
                                logger.warning(
                                    f'Zařízení "{device_name}" nemá capability "{capability_id}".'
                                )
                                continue

                            value = capability.get("value")
                            value_id = (device_name, capability_id)

                            previous_value = previous_values.get(
                                value_id,
                                object(),
                            )

                            if value == previous_value:
                                continue

                            loxone_value = self.convert_for_loxone(value)

                            send_value(
                                ip=loxone_ip,
                                port=loxone_port,
                                key=loxone_key,
                                value=loxone_value,
                            )

                            logger.info(
                                f"{device_name}: {capability_id}={value!r} "
                                f"→ {loxone_key}={loxone_value}"
                            )

                            previous_values[value_id] = value

                except RuntimeError as error:
                    logger.error(f"Chyba komunikace: {error}")

                time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("LoxBridge ukončen.")