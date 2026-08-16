import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, TextIO

import yaml

from loxbridge.homey.event_listener import (
    DEFAULT_LISTEN_PORT as EVENT_LISTEN_PORT,
    listen_for_homey_events,
)
from loxbridge.logger.logger import logger
from loxbridge.loxone.udp import send_value
from loxbridge.loxone.udp_listener import (
    listen_for_commands,
)


RESTART_DELAY = 3.0

SUPPORTED_TYPES = {
    "boolean",
    "number",
    "enum",
}


class Bridge:
    def __init__(self, config):
        self.config = config

        self.process: subprocess.Popen[str] | None = None

        self.stop_requested = False

        self.command_stop_event = threading.Event()

        self.command_thread: (
            threading.Thread | None
        ) = None

        self.event_stop_event = threading.Event()

        self.event_thread: (
            threading.Thread | None
        ) = None

        self.stdin_lock = threading.Lock()

    @staticmethod
    def convert_for_loxone(
        value: object,
    ) -> bool | int | float | str:
        if isinstance(value, bool):
            return 1 if value else 0

        if value is None:
            raise RuntimeError(
                "Capability nemá žádnou hodnotu."
            )

        if isinstance(
            value,
            (int, float, str),
        ):
            return value

        raise RuntimeError(
            "Nepodporovaný typ hodnoty: "
            f"{type(value).__name__}"
        )

    @staticmethod
    def project_root() -> Path:
        return Path(
            __file__
        ).resolve().parents[2]

    @classmethod
    def runtime_config_path(
        cls,
    ) -> Path:
        root = cls.project_root()

        generated_path = (
            root
            / "config"
            / "config.generated.yaml"
        )

        base_path = (
            root
            / "config"
            / "config.yaml"
        )

        if generated_path.is_file():
            return generated_path

        return base_path

    @staticmethod
    def load_yaml(
        path: Path,
    ) -> dict[str, Any]:
        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as file:
                config = yaml.safe_load(
                    file
                )

        except FileNotFoundError as error:
            raise RuntimeError(
                "Konfigurace nebyla nalezena: "
                f"{path}"
            ) from error

        except yaml.YAMLError as error:
            raise RuntimeError(
                f"Neplatný YAML v {path}: "
                f"{error}"
            ) from error

        if not isinstance(
            config,
            dict,
        ):
            raise RuntimeError(
                f"{path} neobsahuje "
                "platný YAML objekt."
            )

        return config

    def validate_config(
        self,
    ) -> tuple[str, int]:
        try:
            homey_config = (
                self.config["homey"]
            )

            loxone_config = (
                self.config["loxone"]
            )

            homey_config["ip"]
            homey_config["token"]

            loxone_ip = str(
                loxone_config["ip"]
            )

            loxone_port = int(
                loxone_config["port"]
            )

            return (
                loxone_ip,
                loxone_port,
            )

        except (
            ValueError,
            KeyError,
            TypeError,
        ) as error:
            raise RuntimeError(
                f"Chyba konfigurace: "
                f"{error}"
            ) from error

    @staticmethod
    def capability_is_supported(
        capability_config: object,
    ) -> bool:
        # Původní formát:
        # alarm_motion: chodba_pohyb
        if isinstance(
            capability_config,
            str,
        ):
            return True

        # Nový generovaný formát:
        # alarm_motion:
        #   key: pohyb_chodba_alarm_motion
        #   type: boolean
        if isinstance(
            capability_config,
            dict,
        ):
            capability_type = (
                capability_config.get(
                    "type"
                )
            )

            return (
                capability_type
                in SUPPORTED_TYPES
            )

        return False

    def log_configuration(
        self,
        loxone_ip: str,
        loxone_port: int,
    ) -> None:
        config_path = (
            self.runtime_config_path()
        )

        runtime_config = (
            self.load_yaml(
                config_path
            )
        )

        devices = runtime_config.get(
            "devices",
            [],
        )

        device_count = 0
        capability_count = 0
        skipped_count = 0

        if isinstance(
            devices,
            list,
        ):
            for device in devices:
                if not isinstance(
                    device,
                    dict,
                ):
                    continue

                device_count += 1

                capabilities = (
                    device.get(
                        "capabilities",
                        {},
                    )
                )

                if not isinstance(
                    capabilities,
                    dict,
                ):
                    continue

                for (
                    capability_config
                ) in capabilities.values():
                    if (
                        self
                        .capability_is_supported(
                            capability_config
                        )
                    ):
                        capability_count += 1
                    else:
                        skipped_count += 1

        logger.info(
            "LoxBridge realtime spuštěn"
        )

        logger.info(
            "Homey: "
            f"{self.config['homey']['ip']}"
        )

        logger.info(
            f"Loxone: "
            f"{loxone_ip}:"
            f"{loxone_port}"
        )

        logger.info(
            "Realtime config: "
            f"{config_path.name}"
        )

        logger.info(
            f"Zařízení: "
            f"{device_count}"
        )

        logger.info(
            "Realtime capabilities: "
            f"{capability_count}"
        )

        if skipped_count:
            logger.info(
                "Zatím přeskočeno "
                "nepodporovaných capability: "
                f"{skipped_count}"
            )

        logger.info(
            "Ukončení: Ctrl + C"
        )

    @staticmethod
    def log_helper_stderr(
        stream: TextIO,
    ) -> None:
        for line in stream:
            message = line.rstrip()

            if message:
                logger.info(
                    message
                )

    def start_helper(
        self,
    ) -> subprocess.Popen[str]:
        root = self.project_root()

        helper_path = (
            root
            / "loxbridge"
            / "homey"
            / "realtime.mjs"
        )

        config_path = (
            self.runtime_config_path()
        )

        if not helper_path.is_file():
            raise RuntimeError(
                "Realtime helper "
                "nebyl nalezen: "
                f"{helper_path}"
            )

        if not config_path.is_file():
            raise RuntimeError(
                "Konfigurace nebyla "
                "nalezena: "
                f"{config_path}"
            )

        try:
            process = subprocess.Popen(
                [
                    "node",
                    str(helper_path),
                    str(config_path),
                ],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )

        except FileNotFoundError as error:
            raise RuntimeError(
                "Příkaz node "
                "nebyl nalezen."
            ) from error

        if (
            process.stdin is None
            or process.stdout is None
            or process.stderr is None
        ):
            process.terminate()

            raise RuntimeError(
                "Nepodařilo se otevřít "
                "komunikaci s realtime "
                "helperem."
            )

        stderr_thread = (
            threading.Thread(
                target=(
                    self.log_helper_stderr
                ),
                args=(
                    process.stderr,
                ),
                daemon=True,
            )
        )

        stderr_thread.start()

        return process

    def send_homey_command(
        self,
        key: str,
        value: str,
    ) -> None:
        process = self.process

        if (
            process is None
            or process.poll()
            is not None
            or process.stdin is None
        ):
            logger.warning(
                "Homey realtime spojení "
                "není připravené "
                "pro příkaz."
            )

            return

        request_id = (
            f"udp-{time.time_ns()}"
        )

        command = {
            "type": "command",
            "key": key,
            "value": value,
            "request_id": (
                request_id
            ),
        }

        message = json.dumps(
            command,
            ensure_ascii=False,
        )

        try:
            with self.stdin_lock:
                process.stdin.write(
                    message + "\n"
                )

                process.stdin.flush()

        except (
            BrokenPipeError,
            OSError,
        ) as error:
            logger.error(
                "Nepodařilo se "
                "odeslat příkaz "
                "do Homey: "
                f"{error}"
            )

    def start_command_listener(
        self,
    ) -> None:
        if (
            self.command_thread
            is not None
            and self.command_thread
            .is_alive()
        ):
            return

        self.command_stop_event.clear()

        self.command_thread = (
            threading.Thread(
                target=(
                    listen_for_commands
                ),
                args=(
                    self.send_homey_command,
                    self.command_stop_event,
                ),
                daemon=True,
            )
        )

        self.command_thread.start()

    @staticmethod
    def collect_event_keys(
        runtime_config: dict[str, Any],
    ) -> set[str]:
        result: set[str] = set()

        devices = runtime_config.get(
            "devices",
            [],
        )

        if not isinstance(devices, list):
            return result

        for device in devices:
            if not isinstance(device, dict):
                continue

            loxbridge = device.get("loxbridge")

            if not isinstance(loxbridge, dict):
                continue

            events = loxbridge.get("events")

            if not isinstance(events, list):
                continue

            for event in events:
                if not isinstance(event, dict):
                    continue

                key = event.get("key")

                if isinstance(key, str) and key:
                    result.add(key)

        return result

    @staticmethod
    def send_homey_event_to_loxone(
        key: str,
        loxone_ip: str,
        loxone_port: int,
    ) -> None:
        send_value(
            ip=loxone_ip,
            port=loxone_port,
            key=key,
            value=1,
        )

        logger.info(
            "Homey event → Loxone: "
            f"{key}"
        )

    def run_event_listener(
        self,
        *,
        trusted_source_ip: str,
        allowed_keys: set[str],
        loxone_ip: str,
        loxone_port: int,
    ) -> None:
        try:
            listen_for_homey_events(
                trusted_source_ip=trusted_source_ip,
                allowed_keys=allowed_keys,
                callback=lambda key: (
                    self.send_homey_event_to_loxone(
                        key,
                        loxone_ip,
                        loxone_port,
                    )
                ),
                stop_event=self.event_stop_event,
                listen_port=EVENT_LISTEN_PORT,
            )
        except OSError as error:
            logger.error(
                "Homey event HTTP listener selhal: "
                f"{error}"
            )

    def start_event_listener(
        self,
        *,
        loxone_ip: str,
        loxone_port: int,
    ) -> None:
        if (
            self.event_thread is not None
            and self.event_thread.is_alive()
        ):
            return

        runtime_config = self.load_yaml(
            self.runtime_config_path()
        )

        allowed_keys = self.collect_event_keys(
            runtime_config
        )

        if not allowed_keys:
            logger.info(
                "Homey event HTTP listener: "
                "žádné event vstupy v profilu."
            )
            return

        trusted_source_ip = str(
            self.config.get("homey", {}).get("ip", "")
        )

        if not trusted_source_ip:
            raise RuntimeError(
                "V konfiguraci chybí homey.ip pro event listener."
            )

        self.event_stop_event.clear()

        self.event_thread = threading.Thread(
            target=self.run_event_listener,
            kwargs={
                "trusted_source_ip": trusted_source_ip,
                "allowed_keys": allowed_keys,
                "loxone_ip": loxone_ip,
                "loxone_port": loxone_port,
            },
            daemon=True,
        )

        self.event_thread.start()

    def stop_event_listener(
        self,
    ) -> None:
        self.event_stop_event.set()

        if self.event_thread is None:
            return

        self.event_thread.join(timeout=2)

    @staticmethod
    def process_event(
        event: dict,
        loxone_ip: str,
        loxone_port: int,
    ) -> None:
        event_type = event.get(
            "type"
        )

        if event_type == "ready":
            subscriptions = (
                event.get(
                    "subscriptions",
                    0,
                )
            )

            commands = event.get(
                "commands",
                0,
            )

            skipped = event.get(
                "skipped",
                0,
            )

            missing = event.get(
                "missing",
                0,
            )

            logger.info(
                "Realtime spojení "
                "aktivní. Odběry: "
                f"{subscriptions}"
            )

            logger.info(
                "Homey ovladatelných "
                "capability: "
                f"{commands}"
            )

            if skipped:
                logger.info(
                    "Realtime "
                    "nepodporované "
                    "capability: "
                    f"{skipped}"
                )

            if missing:
                logger.warning(
                    "Chybějící "
                    "zařízení/capability: "
                    f"{missing}"
                )

            return

        if (
            event_type
            == "command_result"
        ):
            success = bool(
                event.get(
                    "success",
                    False,
                )
            )

            key = str(
                event.get(
                    "key",
                    "",
                )
            )

            if success:
                logger.info(
                    "Homey příkaz "
                    "potvrzen: "
                    f"{key} → "
                    f"{event.get('device_name')} "
                    "/ "
                    f"{event.get('capability_id')}"
                    "="
                    f"{event.get('homey_value')!r}"
                )

            else:
                logger.error(
                    "Homey příkaz "
                    "selhal: "
                    f"{key} - "
                    f"{event.get('message')}"
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
                        "Realtime helper "
                        "selhal.",
                    )
                )
            )

        if event_type != "value":
            logger.warning(
                "Neznámá zpráva "
                "realtime helperu: "
                f"{event!r}"
            )

            return

        device_name = str(
            event["device_name"]
        )

        capability_id = str(
            event["capability_id"]
        )

        loxone_key = str(
            event["loxone_key"]
        )

        value = event.get(
            "value"
        )

        initial = bool(
            event.get(
                "initial",
                False,
            )
        )

        loxone_value = (
            Bridge.convert_for_loxone(
                value
            )
        )

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
            f"{capability_id}="
            f"{value!r} "
            f"→ "
            f"{loxone_key}="
            f"{loxone_value} "
            f"[{event_label}]"
        )

    def run_helper(
        self,
        loxone_ip: str,
        loxone_port: int,
    ) -> int:
        self.process = (
            self.start_helper()
        )

        self.start_command_listener()

        self.start_event_listener(
            loxone_ip=loxone_ip,
            loxone_port=loxone_port,
        )

        assert (
            self.process.stdout
            is not None
        )

        for line in (
            self.process.stdout
        ):
            if self.stop_requested:
                break

            message = line.strip()

            if not message:
                continue

            try:
                event = json.loads(
                    message
                )

            except (
                json.JSONDecodeError
            ):
                logger.warning(
                    "Neplatná zpráva "
                    "realtime helperu: "
                    f"{message}"
                )

                continue

            try:
                self.process_event(
                    event=event,
                    loxone_ip=loxone_ip,
                    loxone_port=(
                        loxone_port
                    ),
                )

            except (
                KeyError,
                TypeError,
                ValueError,
                RuntimeError,
            ) as error:
                logger.error(
                    "Chyba realtime "
                    "události: "
                    f"{error}"
                )

        return (
            self.process.wait()
        )

    def stop_helper(
        self,
    ) -> None:
        self.stop_requested = True

        if self.process is None:
            return

        if (
            self.process.poll()
            is not None
        ):
            return

        self.process.terminate()

        try:
            self.process.wait(
                timeout=5
            )

        except (
            subprocess.TimeoutExpired
        ):
            self.process.kill()

            self.process.wait(
                timeout=5
            )

    def stop_command_listener(
        self,
    ) -> None:
        self.command_stop_event.set()

        if (
            self.command_thread
            is None
        ):
            return

        self.command_thread.join(
            timeout=2
        )

    def run(
        self,
    ) -> None:
        try:
            (
                loxone_ip,
                loxone_port,
            ) = self.validate_config()

        except RuntimeError as error:
            logger.error(
                str(error)
            )

            sys.exit(1)

        try:
            self.log_configuration(
                loxone_ip=loxone_ip,
                loxone_port=(
                    loxone_port
                ),
            )

        except RuntimeError as error:
            logger.error(
                str(error)
            )

            sys.exit(1)

        try:
            while not (
                self.stop_requested
            ):
                try:
                    return_code = (
                        self.run_helper(
                            loxone_ip=(
                                loxone_ip
                            ),
                            loxone_port=(
                                loxone_port
                            ),
                        )
                    )

                    if (
                        self.stop_requested
                    ):
                        break

                    logger.error(
                        "Realtime spojení "
                        "bylo ukončeno "
                        "s kódem "
                        f"{return_code}."
                    )

                except (
                    RuntimeError
                ) as error:
                    logger.error(
                        "Chyba realtime "
                        "komunikace: "
                        f"{error}"
                    )

                if self.stop_requested:
                    break

                logger.info(
                    "Nový pokus "
                    "o připojení za "
                    f"{RESTART_DELAY:g} s."
                )

                time.sleep(
                    RESTART_DELAY
                )

        except KeyboardInterrupt:
            logger.info(
                "Požadováno ukončení "
                "LoxBridge."
            )

        finally:
            self.stop_event_listener()

            self.stop_command_listener()

            self.stop_helper()

            logger.info(
                "LoxBridge ukončen."
            )