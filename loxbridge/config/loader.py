from pathlib import Path

import yaml


class ConfigLoader:
    def __init__(self, filename: str = "config/config.yaml") -> None:
        self.filename = Path(filename)

    def load(self) -> dict:
        if not self.filename.exists():
            raise FileNotFoundError(
                f"Konfigurační soubor nenalezen: {self.filename.resolve()}"
            )

        with self.filename.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file)

        if not isinstance(config, dict):
            raise ValueError("Konfigurační soubor musí obsahovat YAML objekt.")

        return config