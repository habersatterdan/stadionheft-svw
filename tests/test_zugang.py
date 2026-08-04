"""Passwortschutz der Weboberflaeche."""

from __future__ import annotations

import base64

import pytest

from stadionheft.config import Konfiguration
from stadionheft.web import app_erzeugen


def _mit_schutz(konfiguration: Konfiguration, monkeypatch,
                passwort: str = "geheim", benutzer: str = "svw"):
    konfiguration.roh["zugang"] = {
        "passwortschutz": True,
        "benutzername": benutzer,
        "passwort_umgebungsvariable": "TEST_PASSWORT",
    }
    monkeypatch.setenv("TEST_PASSWORT", passwort)
    app = app_erzeugen(konfiguration)
    app.config["TESTING"] = True
    return app.test_client()


def _kopf(benutzer: str, passwort: str) -> dict:
    roh = base64.b64encode(f"{benutzer}:{passwort}".encode()).decode()
    return {"Authorization": f"Basic {roh}"}


def test_ohne_schutz_ist_alles_offen(konfiguration: Konfiguration):
    app = app_erzeugen(konfiguration)
    app.config["TESTING"] = True
    assert app.test_client().get("/").status_code == 200


def test_mit_schutz_ohne_anmeldung_401(konfiguration: Konfiguration, monkeypatch):
    antwort = _mit_schutz(konfiguration, monkeypatch).get("/")
    assert antwort.status_code == 401
    assert "Basic" in antwort.headers["WWW-Authenticate"]


def test_richtige_anmeldung_kommt_durch(konfiguration: Konfiguration, monkeypatch):
    client = _mit_schutz(konfiguration, monkeypatch)
    antwort = client.get("/", headers=_kopf("svw", "geheim"))
    assert antwort.status_code == 200
    assert "Stadionheft erstellen" in antwort.get_data(as_text=True)


@pytest.mark.parametrize("benutzer,passwort", [
    ("svw", "falsch"),
    ("fremd", "geheim"),
    ("", ""),
])
def test_falsche_anmeldung_wird_abgewiesen(konfiguration: Konfiguration,
                                           monkeypatch, benutzer, passwort):
    client = _mit_schutz(konfiguration, monkeypatch)
    assert client.get("/", headers=_kopf(benutzer, passwort)).status_code == 401


def test_auch_unterseiten_sind_geschuetzt(konfiguration: Konfiguration, monkeypatch):
    client = _mit_schutz(konfiguration, monkeypatch)
    for pfad in ("/hilfe", "/fupa-test", "/lauf/xyz"):
        assert client.get(pfad).status_code == 401, pfad


def test_gesundheitscheck_bleibt_offen(konfiguration: Konfiguration, monkeypatch):
    """Sonst wuerde der Container sich selbst als krank melden."""
    client = _mit_schutz(konfiguration, monkeypatch)
    antwort = client.get("/gesundheit")
    assert antwort.status_code == 200
    assert antwort.get_json() == {"status": "ok"}


def test_ohne_gesetztes_passwort_kommt_niemand_rein(konfiguration: Konfiguration,
                                                    monkeypatch):
    """Ein vergessenes Passwort darf den Schutz nicht stillschweigend
    aushebeln -- lieber gesperrt als offen."""
    konfiguration.roh["zugang"] = {
        "passwortschutz": True,
        "benutzername": "svw",
        "passwort_umgebungsvariable": "GIBTS_NICHT",
    }
    monkeypatch.delenv("GIBTS_NICHT", raising=False)
    app = app_erzeugen(konfiguration)
    app.config["TESTING"] = True
    client = app.test_client()
    assert client.get("/").status_code == 401
    assert client.get("/", headers=_kopf("svw", "")).status_code == 401
