import socket
from collections.abc import Callable
from threading import Event

from loxbridge.logger.logger import logger


LISTEN_IP = "0.0.0.0"
LISTEN_PORT = 7002


def listen_for_commands(
    callback: Callable[[str, str], None],
    stop_event: Event,
) -> None:
    with socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    ) as sock:
        sock.bind(
            (LISTEN_IP, LISTEN_PORT)
        )

        sock.settimeout(1.0)

        logger.info(
            "Loxone → Homey UDP listener: "
            f"{LISTEN_IP}:{LISTEN_PORT}"
        )

        while not stop_event.is_set():
            try:
                data, address = sock.recvfrom(
                    4096
                )

            except socket.timeout:
                continue

            try:
                message = data.decode(
                    "utf-8"
                ).strip()

            except UnicodeDecodeError:
                logger.warning(
                    "Neplatná UDP data od "
                    f"{address[0]}:"
                    f"{address[1]}"
                )
                continue

            if "=" not in message:
                logger.warning(
                    f"Neplatný UDP příkaz: "
                    f"{message}"
                )
                continue

            key, value = message.split(
                "=",
                1,
            )

            key = key.strip()
            value = value.strip()

            if not key:
                logger.warning(
                    "UDP příkaz nemá key."
                )
                continue

            logger.info(
                f"Loxone → LoxBridge: "
                f"{key}={value}"
            )

            callback(
                key,
                value,
            )