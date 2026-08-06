"""Gemeinsame Vorbereitung fuer die Tests des Kickbase-Beraters.

Alle Tests laufen im Demomodus und in einem temporaeren Ordner: kein Netz,
keine Zugangsdaten, keine Spuren im Projektverzeichnis.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kickbase.config import Konfiguration
from kickbase.dienst import Berater


@pytest.fixture(autouse=True)
def ohne_zugangsdaten(monkeypatch):
    """Stellt sicher, dass kein echtes Konto benutzt wird.

    Sonst wuerde ein Entwickler mit gesetzten Umgebungsvariablen beim
    Testlauf versehentlich Kickbase anfragen.
    """
    for variable in ("KICKBASE_EMAIL", "KICKBASE_PASSWORT",
                     "KICKBASE_LIGA", "KICKBASE_WEB_PASSWORT"):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def konfiguration(tmp_path: Path) -> Konfiguration:
    return Konfiguration({
        "speicher": {"datenbank": str(tmp_path / "kickbase.sqlite3")},
        "protokoll": {"ordner": str(tmp_path / "logs")},
        "abruf": {"automatisch": False},
    })


@pytest.fixture
def berater(konfiguration: Konfiguration) -> Berater:
    """Ein Berater mit bereits geholten Demodaten."""
    dienst = Berater(konfiguration)
    dienst.abrufen()
    return dienst
