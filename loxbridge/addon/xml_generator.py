from __future__ import annotations

from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

from loxbridge.models.device import Device


class XmlGenerator:

    def __init__(self, devices: list[Device]):
        self.devices = devices

    def generate(self) -> bytes:

        root = Element("VirtualInUdp")

        root.set("Title", "Homey")
        root.set("Comment", "")
        root.set("Address", "")
        root.set("Port", "7000")

        info = SubElement(root, "Info")
        info.set("templateType", "1")
        info.set("minVersion", "12020923")

        for device in sorted(
            self.devices,
            key=lambda item: item.name.casefold(),
        ):
            for capability in sorted(
                device.capabilities,
                key=lambda item: item.normalized_name.casefold(),
            ):
                title = self._create_title(
                    device_name=device.name,
                    capability_name=capability.normalized_name,
                )

                check = self._create_check(
                    device_id=device.id,
                    capability_name=capability.normalized_name,
                )

                analog = capability.value_type == "number"

                root.append(
                    self._create_udp_input(
                        title=title,
                        check=check,
                        analog=analog,
                    )
                )

        raw_xml = tostring(
            root,
            encoding="utf-8",
        )

        document = minidom.parseString(raw_xml)

        return document.toprettyxml(
            indent="\t",
            encoding="utf-8",
        )

    @staticmethod
    def _create_title(
        device_name: str,
        capability_name: str,
    ) -> str:

        readable_capability = capability_name.replace(
            "_",
            " ",
        ).title()

        return f"{device_name} - {readable_capability}"

    @staticmethod
    def _create_check(
        device_id: str,
        capability_name: str,
    ) -> str:

        return (
            f"homey."
            f"{device_id}."
            f"{capability_name}"
            f"@\\v"
        )

    @staticmethod
    def _create_udp_input(
        title: str,
        check: str,
        analog: bool,
    ) -> Element:

        command = Element("VirtualInUdpCmd")

        command.set("Title", title)
        command.set("Comment", "")
        command.set("Address", "")
        command.set("Check", check)

        command.set("Signed", "true")
        command.set(
            "Analog",
            "true" if analog else "false",
        )

        command.set("SourceValLow", "0")
        command.set("DestValLow", "0")
        command.set("SourceValHigh", "100")
        command.set("DestValHigh", "100")

        command.set("DefVal", "0")
        command.set("MinVal", "-10000")
        command.set("MaxVal", "10000")

        return command