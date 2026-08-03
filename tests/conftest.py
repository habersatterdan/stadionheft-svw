from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from stadionheft.config import BEISPIEL_CONFIG, Konfiguration

PROJEKT = Path(__file__).resolve().parent.parent


@pytest.fixture
def konfiguration(tmp_path: Path) -> Konfiguration:
    """Konfiguration wie das Beispiel, aber mit Ordnern im temporaeren Verzeichnis."""
    daten = yaml.safe_load(BEISPIEL_CONFIG.read_text(encoding="utf-8"))
    for ordner in ("03_eingaben", "04_zwischenergebnisse", "05_ausgaben", "02_werbung"):
        (tmp_path / ordner).mkdir(parents=True, exist_ok=True)

    daten["datenquelle"]["manuell"]["ordner"] = str(tmp_path / "03_eingaben")
    daten["datenquelle"]["cache"]["ordner"] = str(tmp_path / "cache")
    daten["ausgabe"]["ordner"] = str(tmp_path / "05_ausgaben")
    daten["ausgabe"]["arbeitsordner"] = str(tmp_path / "04_zwischenergebnisse")
    daten["daten"] = {"wurzel": str(tmp_path), "werbung": str(tmp_path / "02_werbung")}
    daten["protokoll"]["ordner"] = str(tmp_path / "logs")
    # Nur zwei Mannschaften -> schnellere Tests
    daten["mannschaften"] = {
        k: v for k, v in daten["mannschaften"].items() if k in ("herren1", "damen1")
    }
    daten["mannschaften"]["damen1"]["liga"] = "Kreisliga Donau"
    return Konfiguration(daten, BEISPIEL_CONFIG)


@pytest.fixture
def heftplan_minimal() -> list[dict]:
    """Heftplan ohne externe PDF-Dateien -- fuer schnelle Tests."""
    return [
        {"typ": "titelseite"},
        {"typ": "mannschaftsbloecke"},
        {"typ": "impressum"},
    ]


@pytest.fixture
def werbe_pdf(konfiguration: Konfiguration) -> Path:
    """Eine zweiseitige 'Werbeanzeige' im Format der bestehenden Vorlage
    (MediaBox 461,5 x 637,3 pt) -- prueft die Formatvereinheitlichung."""
    from pypdf import PdfWriter, PageObject

    schreiber = PdfWriter()
    for _ in range(2):
        schreiber.add_page(PageObject.create_blank_page(width=461.53, height=637.28))
    ziel = konfiguration.werbung_ordner / "werbung.pdf"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with ziel.open("wb") as datei:
        schreiber.write(datei)
    return ziel
