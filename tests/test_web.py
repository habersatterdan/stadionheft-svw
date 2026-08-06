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


# ---------------------------------------------------------------------------
# FuPa-Verbindungstest
# ---------------------------------------------------------------------------

def test_fupa_testseite_erklaert_sich(konfiguration: Konfiguration):
    antwort = _client(konfiguration).get("/fupa-test")
    assert antwort.status_code == 200
    text = antwort.get_data(as_text=True)
    assert "Verbindung jetzt prüfen" in text
    assert "nichts verändert" in text


def test_fupa_test_zeigt_ergebnis(konfiguration: Konfiguration, monkeypatch):
    bericht = {
        "basis_url": "https://api.fupa.net/",
        "mannschaft": "herren1",
        "team_slug": "sv-woernitzstein-berg-m1-2026-27",
        "ablage": "/tmp/fupa_probe",
        "geprueft": 2,
        "ergebnisse": {
            "fupa.net/team/x/tabelle": {
                "url": "https://www.fupa.net/team/x/tabelle", "status": 200,
                "bewertung": "ok", "gefundene_zeilen": 16,
                "erkannt": {"tabelle": 16}},
            "api.fupa.net/y": {"url": "https://api.fupa.net/y", "status": 404,
                               "bewertung": "antwortet mit HTTP 404"},
        },
        "zusammenfassung": {"tabelle": 16},
    }
    monkeypatch.setattr("stadionheft.sources.fupa_api.probe_fupa",
                        lambda *a, **k: bericht)

    antwort = _client(konfiguration).post("/fupa-test",
                                          data={"mannschaft": "herren1"})
    assert antwort.status_code == 200
    text = antwort.get_data(as_text=True)
    assert "1 von 4 Datenteilen" in text
    assert "gefunden, 16 Zeilen" in text
    assert "Tabelle (16)" in text
    assert "Ergebnis herunterladen" in text


def test_fupa_test_zeigt_vollstaendigen_treffer(konfiguration: Konfiguration,
                                                monkeypatch):
    bericht = {
        "basis_url": "x", "mannschaft": "herren1", "team_slug": "s", "ablage": "",
        "geprueft": 10,
        "ergebnisse": {"fupa.net/team/s": {"bewertung": "ok", "status": 200,
                                           "erkannt": {"tabelle": 16}}},
        "zusammenfassung": {"tabelle": 16, "torjaeger": 20, "spieler": 22,
                            "spiele": 30},
    }
    monkeypatch.setattr("stadionheft.sources.fupa_api.probe_fupa",
                        lambda *a, **k: bericht)
    text = _client(konfiguration).post("/fupa-test", data={}).get_data(as_text=True)
    assert "Alle vier Datenteile wurden gefunden" in text
    assert "nicht gefunden" not in text


def test_fupa_test_ohne_treffer_bietet_keinen_download(konfiguration: Konfiguration,
                                                       monkeypatch):
    bericht = {
        "basis_url": "x", "mannschaft": "herren1", "team_slug": "s", "ablage": "",
        "geprueft": 1, "zusammenfassung": {},
        "ergebnisse": {"api.fupa.net/x": {"bewertung": "nicht erreichbar: timeout"}},
    }
    monkeypatch.setattr("stadionheft.sources.fupa_api.probe_fupa",
                        lambda *a, **k: bericht)
    text = _client(konfiguration).post("/fupa-test", data={}).get_data(as_text=True)
    assert "keine Spieldaten gefunden" in text
    assert "Ergebnis herunterladen" not in text


def test_fupa_test_faengt_fehler_ab(konfiguration: Konfiguration, monkeypatch):
    from stadionheft.errors import DatenquelleNichtErreichbarFehler

    def kaputt(*_a, **_k):
        raise DatenquelleNichtErreichbarFehler(
            "timeout", benutzer_text="FuPa ist nicht erreichbar.",
            hinweis="Später erneut versuchen.")

    monkeypatch.setattr("stadionheft.sources.fupa_api.probe_fupa", kaputt)
    antwort = _client(konfiguration).post("/fupa-test", data={})
    assert antwort.status_code == 200
    assert "FuPa ist nicht erreichbar." in antwort.get_data(as_text=True)


def test_download_ohne_ergebnis_ist_404(konfiguration: Konfiguration):
    assert _client(konfiguration).get("/fupa-test/download").status_code == 404
