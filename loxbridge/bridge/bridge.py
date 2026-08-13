import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, TextIO

import yaml

from loxbridge.logger.logger import logger
from loxbridge.loxone.udp import send_value


RESTART_DELAY = 3.0
SUPPORTED_TYPES = {"boolean", "number", "enum"}


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

    @classmethod
    def runtime_config_path(cls) -> Path:
        root = cls.project_root()

        generated_path = root / "config" / "config.generated.yaml"
        base_path = root / "config" / "config.yaml"

        if generated_path.is_file():
            return generated_path

        return base_path

    @staticmethod
    def load_yaml(path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as file:
                config = yaml.safe_load(file)

        except FileNotFoundError as error:
            raise RuntimeError(
                f"Konfigurace nebyla nalezena: {path}"
            ) from error

        except yaml.YAMLError as error:
            raise RuntimeError(
                f"Neplatný YAML v {path}: {error}"
            ) from error

        if not isinstance(config, dict):
            raise RuntimeError(
                f"{path} neobsahuje platný YAML objekt."
            )

        return config

    def validate_config(self) -> tuple[str, int]:
        try:
            homey_config = self.config["homey"]
            loxone_config = self.config["loxone"]

            homey_config["ip"]
            homey_config["token"]

            loxone_ip = str(loxone_config["ip"])
            loxone_port = int(loxone_config["port"])

            return loxone_ip, loxone_port

        except (ValueError, KeyError, TypeError) as error:
            raise RuntimeError(
                f"Chyba konfigurace: {error}"
            ) from error

    @staticmethod
    def capability_is_supported(capability_config: object) -> bool:
        # Původní formát:
        # alarm_motion: chodba_pohyb
        if isinstance(capability_config, str):
            return True

        # Nový generovaný formát:
        # alarm_motion:
        #   key: pohyb_chodba_alarm_motion
        #   type: boolean
        if isinstance(capability_config, dict):
            capability_type = capability_config.get("type")
            return capability_type in SUPPORTED_TYPES

        return False

    def log_configuration(
        self,
        loxone_ip: str,
        loxone_port: int,
    ) -> None:
        config_path = self.runtime_config_path()
        runtime_config = self.load_yaml(config_path)

        devices = runtime_config.get("devices", [])

        device_count = 0
        capability_count = 0
        skipped_count = 0

        if isinstance(devices, list):
            for device in devices:
                if not isinstance(device, dict):
                    continue

                device_count += 1

                capabilities = device.get("capabilities", {})

                if not isinstance(capabilities, dict):
                    continue

                for capability_config in capabilities.values():
                    if self.capability_is_supported(capability_config):
                        capability_count += 1
                    else:
                        skipped_count += 1

        logger.info("LoxBridge realtime spuštěn")
        logger.info(f"Homey: {self.config['homey']['ip']}")
        logger.info(f"Loxone: {loxone_ip}:{loxone_port}")
        logger.info(f"Realtime config: {config_path.name}")
        logger.info(f"Zařízení: {device_count}")
        logger.info(f"Realtime capabilities: {capability_count}")

        if skipped_count:
            logger.info(
                f"Zatím přeskočeno nepodporovaných capability: {skipped_count}"
            )

        logger.info("Ukončení: Ctrl + C")

    @staticmethod
    def log_helper_stderr(stream: TextIO) -> None:
        for line in stream:
            message = line.rstrip()

            if message:
                logger.info(message)

    def start_helper(self) -> subprocess.Popen[str]:
        root = self.project_root()

        helper_path = (
            root
            / "loxbridge"
            / "homey"
            / "realtime.mjs"
        )

        config_path = self.runtime_config_path()

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
                "Příkaz node nebyl nalezen."
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
            skipped = event.get("skipped", 0)
            missing = event.get("missing", 0)

            logger.info(
                f"Realtime spojení aktivní. Odběry: {subscriptions}"
            )

            if skipped:
                logger.info(
                    f"Realtime nepodporované capability: {skipped}"
                )

            if missing:
                logger.warning(
                    f"Chybějící zařízení/capability: {missing}"
                )

            return

        if event_type == "warning":
            logger.warning(
                str(
                    event.get(
                        "message",
                        "Neznámé varování.",
                    )
                )
            )
            return

        if event_type == "fatal":
            raise RuntimeError(
                str(
                    event.get(
                        "message",
                        "Realtime helper selhal.",
                    )
                )
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

        event_label = (
            "počáteční stav"
            if initial
            else "realtime"
        )

        logger.info(
            f"{device_name}: "
            f"{capability_id}={value!r} "
            f"→ {loxone_key}={loxone_value} "
            f"[{event_label}]"
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

            except (
                KeyError,
                TypeError,
                ValueError,
                RuntimeError,
            ) as error:
                logger.error(
                    f"Chyba realtime události: {error}"
                )

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

        try:
            self.log_configuration(
                loxone_ip=loxone_ip,
                loxone_port=loxone_port,
            )

        except RuntimeError as error:
            logger.error(str(error))
            sys.exit(1)

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
                    logger.error(
                        f"Chyba realtime komunikace: {error}"
                    )

                if self.stop_requested:
                    break

                logger.info(
                    "Nový pokus o připojení za "
                    f"{RESTART_DELAY:g} s."
                )

                time.sleep(RESTART_DELAY)

        except KeyboardInterrupt:
            logger.info(
                "Požadováno ukončení LoxBridge."
            )

        finally:
            self.stop_helper()
            logger.info("LoxBridge ukončen.")