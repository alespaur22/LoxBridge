import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TextIO

from loxbridge.logger.logger import logger
from loxbridge.loxone.udp import send_value


RESTART_DELAY = 3.0


class Bridge:
    def __init__(self, config):
        self.config = config
        self.process: subprocess.Popen[str] | None = None
        self.stop_requested = False

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

    @staticmethod
    def project_root() -> Path:
        return Path(__file__).resolve().parents[2]

    def validate_config(self) -> tuple[str, int]:
        try:
            homey_config = self.config["homey"]
            loxone_config = self.config["loxone"]
            devices_config = self.config["devices"]

            homey_config["ip"]
            homey_config["token"]

            if not isinstance(devices_config, list) or not devices_config:
                raise ValueError("Seznam devices je prázdný.")

            loxone_ip = str(loxone_config["ip"])
            loxone_port = int(loxone_config["port"])

            return loxone_ip, loxone_port

        except (ValueError, KeyError, TypeError) as error:
            raise RuntimeError(f"Chyba konfigurace: {error}") from error

    def log_configuration(self, loxone_ip: str, loxone_port: int) -> None:
        homey_config = self.config["homey"]
        devices_config = self.config["devices"]

        logger.info("LoxBridge realtime spuštěn")
        logger.info(f"Homey: {homey_config['ip']}")
        logger.info(f"Loxone: {loxone_ip}:{loxone_port}")

        for device_config in devices_config:
            device_name = device_config["name"]
            logger.info(f"Zařízení: {device_name}")

            for capability_id, loxone_key in (
                device_config["capabilities"].items()
            ):
                logger.info(f"  {capability_id} → {loxone_key}")

        logger.info("Ukončení: Ctrl + C")

    @staticmethod
    def log_helper_stderr(stream: TextIO) -> None:
        for line in stream:
            message = line.rstrip()

            if message:
                logger.info(message)

    def start_helper(self) -> subprocess.Popen[str]:
        root = self.project_root()
        helper_path = root / "loxbridge" / "homey" / "realtime.mjs"
        config_path = root / "config" / "config.yaml"

        if not helper_path.is_file():
            raise RuntimeError(
                f"Realtime helper nebyl nalezen: {helper_path}"
            )

        if not config_path.is_file():
            raise RuntimeError(
                f"Konfigurace nebyla nalezena: {config_path}"
            )

        try:
            process = subprocess.Popen(
                [
                    "node",
                    str(helper_path),
                    str(config_path),
                ],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )

        except FileNotFoundError as error:
            raise RuntimeError(
                "Příkaz node nebyl nalezen. "
                "Zkontroluj instalaci Node.js."
            ) from error

        if process.stdout is None or process.stderr is None:
            process.terminate()
            raise RuntimeError(
                "Nepodařilo se otevřít výstup realtime helperu."
            )

        stderr_thread = threading.Thread(
            target=self.log_helper_stderr,
            args=(process.stderr,),
            daemon=True,
        )
        stderr_thread.start()

        return process

    @staticmethod
    def process_event(
        event: dict,
        loxone_ip: str,
        loxone_port: int,
    ) -> None:
        event_type = event.get("type")

        if event_type == "ready":
            subscriptions = event.get("subscriptions", 0)
            logger.info(
                f"Realtime spojení aktivní. Odběry: {subscriptions}"
            )
            return

        if event_type == "warning":
            logger.warning(str(event.get("message", "Neznámé varování.")))
            return

        if event_type == "fatal":
            raise RuntimeError(
                str(event.get("message", "Realtime helper selhal."))
            )

        if event_type != "value":
            logger.warning(
                f"Neznámá zpráva realtime helperu: {event!r}"
            )
            return

        device_name = str(event["device_name"])
        capability_id = str(event["capability_id"])
        loxone_key = str(event["loxone_key"])
        value = event.get("value")
        initial = bool(event.get("initial", False))

        loxone_value = Bridge.convert_for_loxone(value)

        send_value(
            ip=loxone_ip,
            port=loxone_port,
            key=loxone_key,
            value=loxone_value,
        )

        event_label = "počáteční stav" if initial else "realtime"

        logger.info(
            f"{device_name}: {capability_id}={value!r} "
            f"→ {loxone_key}={loxone_value} [{event_label}]"
        )

    def run_helper(
        self,
        loxone_ip: str,
        loxone_port: int,
    ) -> int:
        self.process = self.start_helper()

        assert self.process.stdout is not None

        for line in self.process.stdout:
            if self.stop_requested:
                break

            message = line.strip()

            if not message:
                continue

            try:
                event = json.loads(message)

            except json.JSONDecodeError:
                logger.warning(
                    f"Neplatná zpráva realtime helperu: {message}"
                )
                continue

            try:
                self.process_event(
                    event=event,
                    loxone_ip=loxone_ip,
                    loxone_port=loxone_port,
                )

            except (KeyError, TypeError, ValueError, RuntimeError) as error:
                logger.error(f"Chyba realtime události: {error}")

        return self.process.wait()

    def stop_helper(self) -> None:
        self.stop_requested = True

        if self.process is None:
            return

        if self.process.poll() is not None:
            return

        self.process.terminate()

        try:
            self.process.wait(timeout=5)

        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)

    def run(self) -> None:
        try:
            loxone_ip, loxone_port = self.validate_config()

        except RuntimeError as error:
            logger.error(str(error))
            sys.exit(1)

        self.log_configuration(
            loxone_ip=loxone_ip,
            loxone_port=loxone_port,
        )

        try:
            while not self.stop_requested:
                try:
                    return_code = self.run_helper(
                        loxone_ip=loxone_ip,
                        loxone_port=loxone_port,
                    )

                    if self.stop_requested:
                        break

                    logger.error(
                        "Realtime spojení bylo ukončeno "
                        f"s kódem {return_code}."
                    )

                except RuntimeError as error:
                    logger.error(f"Chyba realtime komunikace: {error}")

                if self.stop_requested:
                    break

                logger.info(
                    f"Nový pokus o připojení za {RESTART_DELAY:g} s."
                )
                time.sleep(RESTART_DELAY)

        except KeyboardInterrupt:
            logger.info("Požadováno ukončení LoxBridge.")

        finally:
            self.stop_helper()
            logger.info("LoxBridge ukončen.")
