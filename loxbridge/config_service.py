"""Thin orchestration layer for a future GUI/CLI.

This module introduces NO new business logic. Every use-case method is
just composition of already-existing, already-tested pure functions
from ``loxbridge.device_status``, ``loxbridge.templates``,
``loxbridge.template_matching``, ``loxbridge.capability_filter``,
``loxbridge.instance_builder``, ``loxbridge.template_assignment``,
``loxbridge.instance_validation`` and ``loxbridge.instance_save``. None
of those modules import this one - this is the outermost, topmost
layer, with a strictly one-directional dependency graph.

No caching: every method re-reads the Homey export, the Device
Instance store and the Device Template store fresh from disk on every
call. State can change between calls (a Save, a re-export), and this
layer never risks acting on a stale snapshot.

``validate_*``/``save_*`` deliberately take a plain instance ``dict``,
not one of the Preview DTOs below - they are workflow-agnostic
primitives that just delegate to ``validate_device_instance()``/
``save_device_instance()``. Only the *preview* step differs by
workflow (Configure NEW vs. Assign Template); validate/save are the
exact same operation regardless of which preview produced the
candidate, and stay reusable for future workflows (generic edit,
template upgrade) that don't exist yet.

A note on the DTOs below and any future HTTP layer: they are plain
frozen dataclasses, and ``dataclasses.asdict()`` will happily unnest
them (including the nested domain objects like ``InstancePreview``).
That does NOT mean they are ready for ``json.dumps()`` as-is: the
``Enum`` values used here (``DeviceStatus``, ``MatchKind``) are not
natively JSON-serializable by the stdlib encoder. Converting those to
plain strings (or writing a small custom encoder) is left for whenever
an HTTP layer is actually built - deliberately not solved here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from loxbridge.capability_filter import should_include_capability
from loxbridge.device_status import (
    EXPORT_PATH,
    DeviceStatus,
    compute_device_status_report,
)
from loxbridge.instance_builder import (
    CapabilityEdit,
    InstancePreview,
    apply_preview_edits,
    build_instance_preview,
)
from loxbridge.instance_save import save_device_instance
from loxbridge.instance_validation import (
    SaveMode,
    ValidationResult,
    validate_device_instance,
)
from loxbridge.instances import (
    DEFAULT_INSTANCES_DIR,
    load_all_instances,
)
from loxbridge.template_assignment import (
    TemplateAssignmentPreview,
    build_template_assignment_preview,
)
from loxbridge.template_matching import (
    MatchKind,
    match_templates,
)
from loxbridge.templates import (
    DEFAULT_TEMPLATES_DIR,
    load_all_templates,
)


class DeviceNotFoundError(LookupError):
    """homey_id není v aktuálním Homey exportu."""


class TemplateNotFoundError(LookupError):
    """template_id není v template store."""


class InstanceNotFoundError(LookupError):
    """homey_id nemá Device Instance."""


class ReadOnlyModeError(PermissionError):
    """Save byl odmítnut, protože service běží v read-only režimu.

    Tohle je operační/deployment přepínač (smí tahle instance vůbec
    zapisovat?), ne doménové validační pravidlo - kontrola proběhne
    dřív, než se cokoliv začne resolvovat (homey_device, template), a
    dřív, než se vůbec zavolá `save_device_instance()`. Samotný zápis
    ani validace se kvůli němu nijak nemění.
    """


# --- DTO / read-modely -----------------------------------------------


@dataclass(frozen=True)
class DeviceListItem:
    homey_id: str
    homey_name: str | None
    homey_class: str | None
    zone_name: str | None
    driver_id: str | None
    status: DeviceStatus
    bridgeable: bool | None
    bridgeable_capability_count: int | None
    homey_available: bool | None
    instance_enabled: bool | None
    instance_name: str | None
    template_id: str | None
    template_version: int | None
    # Jen pro status=NEW a bridgeable=True - jinak matching nemá smysl.
    matching_template_ids: tuple[str, ...] = ()
    template_match_kind: MatchKind | None = None


@dataclass(frozen=True)
class RawCapabilityInfo:
    id: str
    type: str | None
    getable: bool | None
    setable: bool | None
    title: str | None
    units: str | None
    min: Any | None
    max: Any | None
    step: Any | None
    values: list[dict[str, Any]] | None
    bridgeable: bool


@dataclass(frozen=True)
class InstanceSummary:
    instance_name: str | None
    loxone_name_base: str | None
    key_base: str | None
    enabled: bool | None
    template_id: str | None
    template_version: int | None
    role_bindings: dict[str, Any]
    keys: dict[str, Any]
    display_names: dict[str, Any]
    overrides: dict[str, Any]


@dataclass(frozen=True)
class DeviceDetail:
    homey_id: str
    homey_name: str | None
    homey_class: str | None
    zone_name: str | None
    driver_id: str | None
    homey_available: bool | None
    status: DeviceStatus
    bridgeable: bool | None
    bridgeable_capability_count: int | None
    # None = zařízení není v aktuálním Homey exportu (status=MISSING).
    # ()   = zařízení v exportu je, ale capability list je opravdu
    #        prázdný. Tenhle rozdíl je záměrný - "nevíme" vs. "víme,
    #        že nic nemá" jsou dvě různé věci.
    raw_capabilities: tuple[RawCapabilityInfo, ...] | None
    instance: InstanceSummary | None
    # Stejné pravidlo jako v list_devices() - jen navíc i pro
    # CONFIGURED bez template, ne jen NEW. Počítá se pouze tehdy, když
    # zařízení dosud nemá přiřazený template (instance neexistuje,
    # nebo existuje ale template je None) a je vidět v aktuálním
    # exportu - to je přesně situace, kdy dává smysl nabídnout
    # "přiřadit template" (nový i legacy případ).
    matching_template_ids: tuple[str, ...] = ()
    template_match_kind: MatchKind | None = None


@dataclass(frozen=True)
class NewConfigurationPreview:
    homey_id: str
    template_id: str
    template_label: str | None
    preview: InstancePreview


@dataclass(frozen=True)
class ExistingAssignmentPreview:
    homey_id: str
    template_id: str
    template_label: str | None
    assignment: TemplateAssignmentPreview


# --- service -----------------------------------------------------------


class DeviceConfigurationService:
    def __init__(
        self,
        *,
        export_path: Path = EXPORT_PATH,
        instances_dir: Path = DEFAULT_INSTANCES_DIR,
        templates_dir: Path = DEFAULT_TEMPLATES_DIR,
        read_only: bool = False,
    ) -> None:
        self._export_path = export_path
        self._instances_dir = instances_dir
        self._templates_dir = templates_dir
        self.read_only = read_only

    def _require_writable(self) -> None:
        if self.read_only:
            raise ReadOnlyModeError(
                "Service běží v read-only režimu - zápis "
                "je zakázán."
            )

    # --- interní: čtení, vždy čerstvé, nikdy cachované ---

    def _load_export(self) -> dict[str, Any]:
        return json.loads(
            self._export_path.read_text(encoding="utf-8")
        )

    @staticmethod
    def _raw_devices_by_id(
        export_data: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        devices = export_data.get("devices")

        if not isinstance(devices, list):
            return {}

        result: dict[str, dict[str, Any]] = {}

        for device in devices:
            if not isinstance(device, dict):
                continue

            device_id = device.get("id")

            if isinstance(device_id, str) and device_id:
                result[device_id] = device

        return result

    def _require_raw_device(
        self, homey_id: str
    ) -> dict[str, Any]:
        device = self._raw_devices_by_id(
            self._load_export()
        ).get(homey_id)

        if device is None:
            raise DeviceNotFoundError(homey_id)

        return device

    def _find_raw_device_or_none(
        self, homey_id: str
    ) -> dict[str, Any] | None:
        return self._raw_devices_by_id(
            self._load_export()
        ).get(homey_id)

    def _load_instances(self) -> dict[str, dict[str, Any]]:
        return load_all_instances(self._instances_dir)

    def _load_templates(self) -> dict[str, dict[str, Any]]:
        return load_all_templates(self._templates_dir)

    def _find_template(
        self, template_id: str
    ) -> dict[str, Any]:
        template = self._load_templates().get(template_id)

        if template is None:
            raise TemplateNotFoundError(template_id)

        return template

    # --- read use-cases ---

    def list_devices(self) -> tuple[DeviceListItem, ...]:
        export_data = self._load_export()
        instances = self._load_instances()
        templates = self._load_templates()
        raw_by_id = self._raw_devices_by_id(export_data)

        report = compute_device_status_report(
            export_data, instances
        )

        items: list[DeviceListItem] = []

        for entry in report.entries:
            matching_template_ids: tuple[str, ...] = ()
            template_match_kind: MatchKind | None = None

            if (
                entry.status == DeviceStatus.NEW
                and entry.bridgeable
            ):
                raw_device = raw_by_id.get(entry.homey_id)

                if raw_device is not None:
                    match_result = match_templates(
                        raw_device, templates
                    )
                    matching_template_ids = (
                        match_result.candidate_template_ids
                    )
                    template_match_kind = (
                        match_result.kind
                    )

            instance = instances.get(entry.homey_id)
            raw_device = raw_by_id.get(entry.homey_id)

            items.append(
                DeviceListItem(
                    homey_id=entry.homey_id,
                    homey_name=entry.homey_name,
                    homey_class=entry.homey_class,
                    zone_name=(
                        raw_device.get("zone_name")
                        if raw_device
                        else None
                    ),
                    driver_id=entry.driver_id,
                    status=entry.status,
                    bridgeable=entry.bridgeable,
                    bridgeable_capability_count=(
                        entry.bridgeable_capability_count
                    ),
                    homey_available=(
                        entry.homey_available
                    ),
                    instance_enabled=(
                        entry.instance_enabled
                    ),
                    instance_name=entry.instance_name,
                    template_id=(
                        instance.get("template")
                        if instance
                        else None
                    ),
                    template_version=(
                        instance.get("template_version")
                        if instance
                        else None
                    ),
                    matching_template_ids=(
                        matching_template_ids
                    ),
                    template_match_kind=(
                        template_match_kind
                    ),
                )
            )

        return tuple(items)

    def get_device_detail(
        self, homey_id: str
    ) -> DeviceDetail:
        export_data = self._load_export()
        instances = self._load_instances()
        raw_by_id = self._raw_devices_by_id(export_data)

        report = compute_device_status_report(
            export_data, instances
        )

        entry = next(
            (
                candidate
                for candidate in report.entries
                if candidate.homey_id == homey_id
            ),
            None,
        )

        if entry is None:
            raise DeviceNotFoundError(homey_id)

        raw_device = raw_by_id.get(homey_id)
        instance = instances.get(homey_id)

        if raw_device is None:
            raw_capabilities = None

        else:
            raw_capability_list = raw_device.get(
                "capabilities"
            )

            if not isinstance(raw_capability_list, list):
                raw_capability_list = []

            raw_capabilities = tuple(
                RawCapabilityInfo(
                    id=capability.get("id"),
                    type=capability.get("type"),
                    getable=capability.get("getable"),
                    setable=capability.get("setable"),
                    title=capability.get("title"),
                    units=capability.get("units"),
                    min=capability.get("min"),
                    max=capability.get("max"),
                    step=capability.get("step"),
                    values=capability.get("values"),
                    bridgeable=should_include_capability(
                        capability
                    ),
                )
                for capability in raw_capability_list
                if isinstance(capability, dict)
            )

        instance_summary = None

        if instance is not None:
            instance_summary = InstanceSummary(
                instance_name=instance.get(
                    "instance_name"
                ),
                loxone_name_base=instance.get(
                    "loxone_name_base"
                ),
                key_base=instance.get("key_base"),
                enabled=instance.get("enabled"),
                template_id=instance.get("template"),
                template_version=instance.get(
                    "template_version"
                ),
                role_bindings=(
                    instance.get("role_bindings") or {}
                ),
                keys=instance.get("keys") or {},
                display_names=(
                    instance.get("display_names") or {}
                ),
                overrides=instance.get("overrides") or {},
            )

        matching_template_ids: tuple[str, ...] = ()
        template_match_kind: MatchKind | None = None

        has_template = bool(
            instance and instance.get("template")
        )

        if raw_device is not None and not has_template:
            match_result = match_templates(
                raw_device, self._load_templates()
            )
            matching_template_ids = (
                match_result.candidate_template_ids
            )
            template_match_kind = match_result.kind

        return DeviceDetail(
            homey_id=homey_id,
            homey_name=entry.homey_name,
            homey_class=entry.homey_class,
            zone_name=(
                raw_device.get("zone_name")
                if raw_device
                else None
            ),
            driver_id=entry.driver_id,
            homey_available=entry.homey_available,
            status=entry.status,
            bridgeable=entry.bridgeable,
            bridgeable_capability_count=(
                entry.bridgeable_capability_count
            ),
            raw_capabilities=raw_capabilities,
            instance=instance_summary,
            matching_template_ids=matching_template_ids,
            template_match_kind=template_match_kind,
        )

    # --- NEW device configuration ---

    def preview_new_device_configuration(
        self,
        *,
        homey_id: str,
        template_id: str,
        instance_name: str,
        loxone_name_base: str,
        key_base: str | None = None,
    ) -> NewConfigurationPreview:
        # NEW workflow vždy potřebuje živé Homey capability data -
        # bez nich není z čeho stavět.
        homey_device = self._require_raw_device(homey_id)
        template = self._find_template(template_id)

        preview = build_instance_preview(
            homey_device=homey_device,
            template=template,
            instance_name=instance_name,
            loxone_name_base=loxone_name_base,
            key_base=key_base,
        )

        return NewConfigurationPreview(
            homey_id=homey_id,
            template_id=template_id,
            template_label=template.get("label"),
            preview=preview,
        )

    def edit_new_device_configuration(
        self,
        preview: NewConfigurationPreview,
        edits: dict[str, CapabilityEdit],
    ) -> NewConfigurationPreview:
        updated = apply_preview_edits(
            preview.preview, edits
        )

        return replace(preview, preview=updated)

    def validate_new_device_configuration(
        self,
        instance: dict[str, Any],
        *,
        homey_id: str,
        template_id: str,
    ) -> ValidationResult:
        homey_device = self._require_raw_device(homey_id)
        template = self._find_template(template_id)
        existing_instances = self._load_instances()

        return validate_device_instance(
            instance,
            homey_device=homey_device,
            template=template,
            existing_instances=existing_instances,
            mode=SaveMode.CREATE,
        )

    def save_new_device_configuration(
        self,
        instance: dict[str, Any],
        *,
        homey_id: str,
        template_id: str,
    ) -> Path:
        self._require_writable()

        homey_device = self._require_raw_device(homey_id)
        template = self._find_template(template_id)

        return save_device_instance(
            instance,
            directory=self._instances_dir,
            mode=SaveMode.CREATE,
            homey_device=homey_device,
            template=template,
        )

    # --- existing instance / template assignment ---

    def preview_template_assignment(
        self,
        *,
        homey_id: str,
        template_id: str,
    ) -> ExistingAssignmentPreview:
        existing_instance = self._load_instances().get(
            homey_id
        )

        if existing_instance is None:
            raise InstanceNotFoundError(homey_id)

        # Assignment potřebuje živá Homey data stejně jako Configure
        # NEW - jinak nejde ověřit, že template vůbec sedí.
        homey_device = self._require_raw_device(homey_id)
        template = self._find_template(template_id)

        assignment = build_template_assignment_preview(
            existing_instance=existing_instance,
            homey_device=homey_device,
            template=template,
        )

        return ExistingAssignmentPreview(
            homey_id=homey_id,
            template_id=template_id,
            template_label=template.get("label"),
            assignment=assignment,
        )

    def validate_existing_instance(
        self,
        instance: dict[str, Any],
        *,
        homey_id: str,
        template_id: str | None = None,
    ) -> ValidationResult:
        if template_id is not None:
            # Template operace nesmí obejít Homey/template matching
            # jen proto, že zařízení je MISSING.
            homey_device = self._require_raw_device(
                homey_id
            )
            template = self._find_template(template_id)

        else:
            # Bez template - typicky obecná editace MISSING instance
            # v budoucnu - živé Homey zařízení není povinné.
            homey_device = self._find_raw_device_or_none(
                homey_id
            )
            template = None

        existing_instances = self._load_instances()

        return validate_device_instance(
            instance,
            homey_device=homey_device,
            template=template,
            existing_instances=existing_instances,
            mode=SaveMode.REPLACE,
        )

    def save_existing_instance(
        self,
        instance: dict[str, Any],
        *,
        homey_id: str,
        template_id: str | None = None,
    ) -> Path:
        self._require_writable()

        if template_id is not None:
            homey_device = self._require_raw_device(
                homey_id
            )
            template = self._find_template(template_id)

        else:
            homey_device = self._find_raw_device_or_none(
                homey_id
            )
            template = None

        return save_device_instance(
            instance,
            directory=self._instances_dir,
            mode=SaveMode.REPLACE,
            homey_device=homey_device,
            template=template,
        )
