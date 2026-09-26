"""Der Container darf auch ohne gueltige Konfiguration starten.

Sonst laeuft er auf der NAS in eine Neustartschleife und der Benutzer sieht
nur „Seite nicht erreichbar" statt des Hinweises, was zu tun ist.
"""

from __future__ import annotations

import importlib

import pytest

from stadionheft.errors import KonfigurationsFehler


@pytest.fixture
def wsgi_ohne_konfiguration(monkeypatch):
    def kaputt(*_a, **_k):
        raise KonfigurationsFehler(
            "config.yaml nicht gefunden.",
            benutzer_text="Die Konfiguration fehlt noch.",
            hinweis="Bitte config.example.yaml kopieren.")

    monkeypatch.setattr("stadionheft.web.app_erzeugen", kaputt)
    modul = importlib.reload(importlib.import_module("stadionheft.web.wsgi"))
    modul.app.config["TESTING"] = True
    return modul.app.test_client()


def test_start_ohne_konfiguration_zeigt_anleitung(wsgi_ohne_konfiguration):
    antwort = wsgi_ohne_konfiguration.get("/")
    assert antwort.status_code == 503
    text = antwort.get_data(as_text=True)
    assert "Einrichtung nicht abgeschlossen" in text
    assert "config.example.yaml" in text


def test_jede_adresse_zeigt_dieselbe_anleitung(wsgi_ohne_konfiguration):
    assert wsgi_ohne_konfiguration.get("/lauf/xyz").status_code == 503


def test_wsgi_startet_mit_gueltiger_konfiguration(konfiguration, monkeypatch):
    monkeypatch.setattr("stadionheft.web.Konfiguration.laden",
                        classmethod(lambda cls, *a, **k: konfiguration))
    modul = importlib.reload(importlib.import_module("stadionheft.web.wsgi"))
    modul.app.config["TESTING"] = True
    antwort = modul.app.test_client().get("/")
    assert antwort.status_code == 200
    assert "Aktuelle Seiten erzeugen" in antwort.get_data(as_text=True)
