"""Nejmenší použitelná HTTP vrstva nad DeviceConfigurationService.

Každý endpoint dělá přesně tři věci: parsuje vstup (JSON tělo/URL
parametr), zavolá jednu (nebo dvě, v případě preview+edity) metodu
`DeviceConfigurationService`, a převede výsledek/výjimku na JSON/HTTP
status. Žádná business logika, žádná validace dat nad rámec "je tam
povinné pole", žádná duplicitní transformace - tu už dělá service
vrstva a moduly pod ní.

Server needs no session/auth: je to jednouživatelský interní nástroj,
běžící defaultně jen na 127.0.0.1 (viz __main__.py).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Flask, Response, request, send_from_directory

from loxbridge.config_service import (
    DeviceConfigurationService,
    DeviceNotFoundError,
    InstanceNotFoundError,
    ReadOnlyModeError,
    TemplateNotFoundError,
)
from loxbridge.instance_builder import CapabilityEdit
from loxbridge.instance_save import SaveError
from loxbridge.instance_validation import ValidationResult
from loxbridge.json_view import to_jsonable


STATIC_DIR = Path(__file__).resolve().parent / "static"


def _parse_edits(
    raw_edits: Any,
) -> dict[str, CapabilityEdit]:
    if not isinstance(raw_edits, dict):
        return {}

    result: dict[str, CapabilityEdit] = {}

    for capability_id, fields in raw_edits.items():
        if not isinstance(fields, dict):
            continue

        result[capability_id] = CapabilityEdit(
            role=fields.get("role"),
            key=fields.get("key"),
            display_name=fields.get("display_name"),
        )

    return result


def create_app(
    service: DeviceConfigurationService | None = None,
) -> Flask:
    app = Flask(__name__, static_folder=None)
    svc = service or DeviceConfigurationService()

    def _json(payload: Any, status: int = 200) -> Response:
        return Response(
            response=json.dumps(
                to_jsonable(payload), ensure_ascii=False
            ),
            status=status,
            mimetype="application/json",
        )

    def _error(
        status: int,
        code: str,
        message: str,
        **extra: Any,
    ) -> Response:
        body: dict[str, Any] = {
            "error": code,
            "message": message,
        }
        body.update(extra)
        return _json(body, status=status)

    def _body() -> dict[str, Any]:
        data = request.get_json(force=True, silent=True)
        return data if isinstance(data, dict) else {}

    def _validation_result_dict(
        result: ValidationResult,
    ) -> dict[str, Any]:
        # ValidationResult.is_valid je @property, ne dataclass field,
        # takže generický to_jsonable() (jde jen po dataclasses.fields)
        # by ho vynechal - tady si HTTP vrstva vědomě vybírá, co z
        # doménového výsledku do JSON dát, přesně jak má (převod
        # DTO -> JSON), ne nová validační logika.
        return {
            "is_valid": result.is_valid,
            "problems": to_jsonable(result.problems),
        }

    # --- error handlers: doménová výjimka -> HTTP status ---

    @app.errorhandler(DeviceNotFoundError)
    def _handle_device_not_found(
        error: DeviceNotFoundError,
    ) -> Response:
        return _error(
            404,
            "device_not_found",
            "Homey zařízení "
            f"{error.args[0]!r} není v aktuálním "
            "exportu.",
        )

    @app.errorhandler(TemplateNotFoundError)
    def _handle_template_not_found(
        error: TemplateNotFoundError,
    ) -> Response:
        return _error(
            404,
            "template_not_found",
            f"Template {error.args[0]!r} neexistuje.",
        )

    @app.errorhandler(InstanceNotFoundError)
    def _handle_instance_not_found(
        error: InstanceNotFoundError,
    ) -> Response:
        return _error(
            404,
            "instance_not_found",
            f"Zařízení {error.args[0]!r} nemá Device "
            "Instance.",
        )

    @app.errorhandler(ReadOnlyModeError)
    def _handle_read_only(
        error: ReadOnlyModeError,
    ) -> Response:
        return _error(
            403,
            "read_only",
            str(error),
        )

    # --- statické GUI soubory ---

    @app.get("/")
    def index() -> Response:
        return send_from_directory(
            STATIC_DIR, "index.html"
        )

    @app.get("/app.js")
    def app_js() -> Response:
        return send_from_directory(STATIC_DIR, "app.js")

    @app.get("/style.css")
    def style_css() -> Response:
        return send_from_directory(
            STATIC_DIR, "style.css"
        )

    # --- API ---

    @app.get("/api/status")
    def status() -> Response:
        # Čistě informativní - GUI podle tohohle zobrazí READ ONLY
        # banner a zamkne Save tlačítka. Skutečné vynucení dělá
        # výhradně service (viz ReadOnlyModeError výše) - tenhle
        # endpoint není bezpečnostní hranice, jen UX hint.
        return _json({"read_only": svc.read_only})

    @app.get("/api/devices")
    def list_devices() -> Response:
        return _json(svc.list_devices())

    @app.get("/api/devices/<homey_id>")
    def get_device_detail(homey_id: str) -> Response:
        return _json(svc.get_device_detail(homey_id))

    @app.post("/api/devices/<homey_id>/preview")
    def preview_new_configuration(
        homey_id: str,
    ) -> Response:
        body = _body()

        template_id = body.get("template_id")
        instance_name = body.get("instance_name")
        loxone_name_base = body.get("loxone_name_base")
        key_base = body.get("key_base") or None

        if not (
            template_id
            and instance_name
            and loxone_name_base
        ):
            return _error(
                400,
                "bad_request",
                "template_id, instance_name a "
                "loxone_name_base jsou povinné.",
            )

        preview = (
            svc.preview_new_device_configuration(
                homey_id=homey_id,
                template_id=template_id,
                instance_name=instance_name,
                loxone_name_base=loxone_name_base,
                key_base=key_base,
            )
        )

        edits = _parse_edits(body.get("edits"))

        if edits:
            preview = (
                svc.edit_new_device_configuration(
                    preview, edits
                )
            )

        return _json(preview)

    @app.post("/api/devices/<homey_id>/validate")
    def validate_new_configuration(
        homey_id: str,
    ) -> Response:
        body = _body()

        instance = body.get("instance")
        template_id = body.get("template_id")

        if not isinstance(instance, dict) or not (
            template_id
        ):
            return _error(
                400,
                "bad_request",
                "instance a template_id jsou povinné.",
            )

        result = svc.validate_new_device_configuration(
            instance,
            homey_id=homey_id,
            template_id=template_id,
        )

        return _json(_validation_result_dict(result))

    @app.post("/api/devices/<homey_id>/save")
    def save_new_configuration(homey_id: str) -> Response:
        body = _body()

        instance = body.get("instance")
        template_id = body.get("template_id")

        if not isinstance(instance, dict) or not (
            template_id
        ):
            return _error(
                400,
                "bad_request",
                "instance a template_id jsou povinné.",
            )

        try:
            path = svc.save_new_device_configuration(
                instance,
                homey_id=homey_id,
                template_id=template_id,
            )

        except SaveError as error:
            return _error(
                422,
                "invalid_instance",
                str(error),
                **_validation_result_dict(error.result),
            )

        return _json({"saved_path": str(path)})

    @app.post(
        "/api/devices/<homey_id>/template-assignment/"
        "preview"
    )
    def preview_assignment(homey_id: str) -> Response:
        body = _body()

        template_id = body.get("template_id")

        if not template_id:
            return _error(
                400,
                "bad_request",
                "template_id je povinné.",
            )

        assignment = svc.preview_template_assignment(
            homey_id=homey_id, template_id=template_id
        )

        return _json(assignment)

    return app
