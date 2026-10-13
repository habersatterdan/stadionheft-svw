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


@pytest.fixture
def stichtag_5_oktober(monkeypatch):
    """Haelt 'heute' fuer die Spiel-Einordnung auf den 05.10.2026 fest.

    Die Testseiten tragen feste Termine (letztes Spiel Ende September/2.10.,
    naechstes am 11.10.). Mit der echten Uhr kippte der Test, sobald der
    11.10. vorbei war -- und mit ihm der Image-Bau.
    """
    from datetime import datetime

    from stadionheft.models import spiele_einordnen
    from stadionheft.sources import fupa_api

    def fest(spiele, stichtag=None, *args, **kwargs):
        return spiele_einordnen(spiele, stichtag or datetime(2026, 10, 5, 12, 0),
                                *args, **kwargs)

    monkeypatch.setattr(fupa_api, "spiele_einordnen", fest)
