from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path


class TemplateGenerator:

    VERSION = "0.1.0"

    TEMPLATE_NAME = "homey"
    TEMPLATE_ID = "homey"
    XML_FILE = "homey.xml"
    OUTPUT_FILE = "Homey.LxAddon"

    def __init__(
        self,
        output_dir: str | Path = "output",
    ):
        self.output_dir = Path(output_dir)

    def build(
        self,
        xml: bytes,
    ) -> Path:

        if not isinstance(xml, bytes):
            raise TypeError(
                "XML musí být předáno jako bytes."
            )

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = self.output_dir / self.OUTPUT_FILE

        descriptor = self._create_descriptor()

        with zipfile.ZipFile(
            output_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:

            archive.writestr(
                "desc.json",
                json.dumps(
                    descriptor,
                    indent=4,
                    ensure_ascii=False,
                ),
            )

            archive.writestr(
                self.XML_FILE,
                xml,
            )

        return output_path

    def _create_descriptor(self) -> dict[str, str]:

        return {
            "type": "template",
            "name": self.TEMPLATE_NAME,
            "uuid": str(uuid.uuid4()),
            "version": self.VERSION,
            "id": self.TEMPLATE_ID,
            "file": self.XML_FILE,
            "templateType": "1",
        }