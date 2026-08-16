from __future__ import annotations

import json
import re
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event
from typing import Any
from urllib.parse import urlsplit

from loxbridge.logger.logger import logger


DEFAULT_LISTEN_IP = "0.0.0.0"
DEFAULT_LISTEN_PORT = 7010
EVENT_PATH = "/event"
MAX_BODY_BYTES = 4096

EVENT_KEY_RE = re.compile(r"^[a-z0-9_]+$")


class EventPayloadError(ValueError):
    pass


def parse_event_payload(
    raw_body: bytes,
    allowed_keys: set[str],
) -> str:
    if len(raw_body) > MAX_BODY_BYTES:
        raise EventPayloadError(
            "HTTP event payload je příliš velký."
        )

    try:
        payload: Any = json.loads(
            raw_body.decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EventPayloadError(
            "HTTP event payload není platný JSON."
        ) from error

    if not isinstance(payload, dict):
        raise EventPayloadError(
            "HTTP event payload musí být JSON objekt."
        )

    key = payload.get("key")

    if not isinstance(key, str) or not EVENT_KEY_RE.fullmatch(key):
        raise EventPayloadError(
            "HTTP event payload nemá platný key."
        )

    if key not in allowed_keys:
        raise EventPayloadError(
            f"Neznámý Homey event key: {key}"
        )

    return key


def make_event_handler(
    *,
    trusted_source_ip: str,
    allowed_keys: set[str],
    callback: Callable[[str], None],
) -> type[BaseHTTPRequestHandler]:
    class EventHandler(BaseHTTPRequestHandler):
        server_version = "LoxBridgeEvent/1"

        def log_message(
            self,
            format: str,
            *args: object,
        ) -> None:
            # Vlastní stručné logování děláme níže.
            return

        def send_empty(
            self,
            status_code: int,
        ) -> None:
            self.send_response(status_code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self) -> None:
            path = urlsplit(self.path).path

            if path != EVENT_PATH:
                self.send_empty(404)
                return

            source_ip = self.client_address[0]

            if (
                trusted_source_ip
                and source_ip != trusted_source_ip
            ):
                logger.warning(
                    "Homey event HTTP odmítnut z IP "
                    f"{source_ip}."
                )
                self.send_empty(403)
                return

            try:
                content_length = int(
                    self.headers.get(
                        "Content-Length",
                        "0",
                    )
                )
            except ValueError:
                self.send_empty(400)
                return

            if (
                content_length <= 0
                or content_length > MAX_BODY_BYTES
            ):
                self.send_empty(413)
                return

            raw_body = self.rfile.read(
                content_length
            )

            try:
                key = parse_event_payload(
                    raw_body,
                    allowed_keys,
                )
            except EventPayloadError as error:
                logger.warning(str(error))
                self.send_empty(400)
                return

            try:
                callback(key)
            except Exception as error:  # noqa: BLE001
                logger.error(
                    "Homey event HTTP callback selhal: "
                    f"{error}"
                )
                self.send_empty(500)
                return

            logger.info(
                "Homey event → LoxBridge: "
                f"{key}"
            )
            self.send_empty(204)

    return EventHandler


def listen_for_homey_events(
    *,
    trusted_source_ip: str,
    allowed_keys: set[str],
    callback: Callable[[str], None],
    stop_event: Event,
    listen_ip: str = DEFAULT_LISTEN_IP,
    listen_port: int = DEFAULT_LISTEN_PORT,
) -> None:
    handler = make_event_handler(
        trusted_source_ip=trusted_source_ip,
        allowed_keys=allowed_keys,
        callback=callback,
    )

    with ThreadingHTTPServer(
        (listen_ip, listen_port),
        handler,
    ) as server:
        server.daemon_threads = True
        server.timeout = 0.5

        logger.info(
            "Homey → LoxBridge event HTTP listener: "
            f"{listen_ip}:{listen_port}{EVENT_PATH}"
        )
        logger.info(
            "Povolené eventy: "
            f"{len(allowed_keys)}"
        )

        while not stop_event.is_set():
            server.handle_request()
