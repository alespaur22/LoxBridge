from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from loxbridge.addon.delta import (
    input_state_from_xml,
)
from loxbridge.addon.delta_generator import (
    build_delta_root,
    save_delta_or_remove,
)


class DeltaGeneratorTests(
    unittest.TestCase
):

    def test_builds_only_added_inputs(
        self,
    ) -> None:
        source_root = ET.fromstring(
            """
            <VirtualInUdp
                Title="LoxBridge - Homey Inputs"
                Port="7001"
            >
                <Info
                    templateType="1"
                    minVersion="17010630"
                />
                <VirtualInUdpCmd
                    Title="Existing"
                    Check="existing=\\v"
                    Analog="true"
                />
                <VirtualInUdpCmd
                    Title="New Event"
                    Check="new_event=\\v"
                    Analog="false"
                />
            </VirtualInUdp>
            """
        )

        current_state = (
            input_state_from_xml(
                source_root
            )
        )

        delta_root = build_delta_root(
            source_root=source_root,
            command_tag=(
                "VirtualInUdpCmd"
            ),
            current_state=current_state,
            added_keys=(
                "new_event",
            ),
            title=(
                "LoxBridge - NEW Inputs"
            ),
        )

        self.assertEqual(
            delta_root.get("Title"),
            "LoxBridge - NEW Inputs",
        )

        self.assertEqual(
            delta_root.get("Port"),
            "7001",
        )

        commands = delta_root.findall(
            "VirtualInUdpCmd"
        )

        self.assertEqual(
            len(commands),
            1,
        )

        self.assertEqual(
            commands[0].get("Check"),
            "new_event=\\v",
        )

        self.assertEqual(
            commands[0].get("Analog"),
            "false",
        )

    def test_empty_delta_removes_old_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = (
                Path(temp)
                / "delta.xml"
            )

            path.write_text(
                "OLD",
                encoding="utf-8",
            )

            root = ET.Element(
                "VirtualInUdp"
            )

            written = (
                save_delta_or_remove(
                    root=root,
                    added_count=0,
                    path=path,
                )
            )

            self.assertFalse(
                written
            )

            self.assertFalse(
                path.exists()
            )

    def test_non_empty_delta_is_saved(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = (
                Path(temp)
                / "delta.xml"
            )

            root = ET.Element(
                "VirtualInUdp",
                {
                    "Title":
                        "LoxBridge - NEW Inputs",
                    "Port": "7001",
                },
            )

            ET.SubElement(
                root,
                "Info",
                {
                    "templateType": "1",
                    "minVersion":
                        "17010630",
                },
            )

            ET.SubElement(
                root,
                "VirtualInUdpCmd",
                {
                    "Title": "New",
                    "Check": "new=\\v",
                    "Analog": "false",
                },
            )

            written = (
                save_delta_or_remove(
                    root=root,
                    added_count=1,
                    path=path,
                )
            )

            self.assertTrue(
                written
            )

            self.assertTrue(
                path.exists()
            )

            parsed = ET.parse(
                path
            ).getroot()

            self.assertEqual(
                len(
                    parsed.findall(
                        "VirtualInUdpCmd"
                    )
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()