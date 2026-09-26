from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from stadionheft.config import BEISPIEL_CONFIG, Konfiguration

PROJEKT = Path(__file__).resolve().parent.parent


@pytest.fixture
def konfiguration(tmp_path: Path) -> Konfiguration:
    """Konfiguration wie das Beispiel, aber mit Ordnern im temporaeren Verzeichnis."""
    daten = yaml.safe_load(BEISPIEL_CONFIG.read_text(encoding="utf-8"))
    for ordner in ("03_eingaben", "04_zwischenergebnisse", "05_ausgaben"):
        (tmp_path / ordner).mkdir(parents=True, exist_ok=True)

    # Tests duerfen nie ins Netz gehen. Wer den API-Modus prueft, setzt ihn
    # selbst und ersetzt dabei den HTTP-Teil.
    daten["datenquelle"]["modus"] = "demo"
    daten["datenquelle"]["manuell"]["ordner"] = str(tmp_path / "03_eingaben")
    daten["datenquelle"]["cache"]["ordner"] = str(tmp_path / "cache")
    daten["ausgabe"]["ordner"] = str(tmp_path / "05_ausgaben")
    daten["ausgabe"]["arbeitsordner"] = str(tmp_path / "04_zwischenergebnisse")
    daten["daten"] = {"wurzel": str(tmp_path)}
    daten["protokoll"]["ordner"] = str(tmp_path / "logs")
    # Nur zwei Mannschaften -> schnellere Tests
    daten["mannschaften"] = {
        k: v for k, v in daten["mannschaften"].items() if k in ("herren1", "damen1")
    }
    daten["mannschaften"]["damen1"]["liga"] = "Kreisliga Donau"
    return Konfiguration(daten, BEISPIEL_CONFIG)
