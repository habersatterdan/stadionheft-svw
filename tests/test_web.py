from __future__ import annotations

import time

from stadionheft.config import Konfiguration
from stadionheft.web import app_erzeugen


def _client(konfiguration: Konfiguration):
    app = app_erzeugen(konfiguration)
    app.config["TESTING"] = True
    return app.test_client()


def test_startseite_zeigt_mannschaften(konfiguration: Konfiguration):
    antwort = _client(konfiguration).get("/")
    assert antwort.status_code == 200
    text = antwort.get_data(as_text=True)
    assert "Herren 1" in text and "Damen 1" in text
    assert "Stadionheft erstellen" in text


def test_hilfeseite(konfiguration: Konfiguration):
    antwort = _client(konfiguration).get("/hilfe")
    assert antwort.status_code == 200
    assert "FuPa ist nicht erreichbar" in antwort.get_data(as_text=True)


def test_ohne_auswahl_freundliche_meldung(konfiguration: Konfiguration):
    antwort = _client(konfiguration).post("/erstellen", data={})
    assert antwort.status_code == 400
    assert "mindestens eine Mannschaft" in antwort.get_data(as_text=True)


def test_unbekannter_lauf_ergibt_404(konfiguration: Konfiguration):
    antwort = _client(konfiguration).get("/lauf/gibtsnicht")
    assert antwort.status_code == 404
    assert "Seite nicht gefunden" in antwort.get_data(as_text=True)


def test_kompletter_durchlauf_ueber_die_oberflaeche(konfiguration: Konfiguration,
                                                    monkeypatch, heftplan_minimal):
    monkeypatch.setattr("stadionheft.build.heftplan_laden",
                        lambda *a, **k: heftplan_minimal)
    client = _client(konfiguration)

    antwort = client.post("/erstellen",
                          data={"mannschaften": ["herren1"], "benutzer": "Tester"})
    assert antwort.status_code == 302
    lauf_id = antwort.headers["Location"].rstrip("/").split("/")[-1]

    for _ in range(120):
        zustand = client.get(f"/lauf/{lauf_id}/status").get_json()
        if zustand["fertig"]:
            break
        time.sleep(0.5)
    else:
        raise AssertionError("Lauf wurde nicht fertig")

    assert zustand["erfolgreich"] is True, zustand.get("fehler")
    assert zustand["ergebnis"]["seitenzahl"] == 7
    assert any("Herren 1" in z["text"] for z in zustand["protokoll"])

    download = client.get(f"/lauf/{lauf_id}/download")
    assert download.status_code == 200
    assert download.data[:4] == b"%PDF"
