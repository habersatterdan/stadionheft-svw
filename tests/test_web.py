from __future__ import annotations

import time

from stadionheft import programmstand
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
    assert "Aktuelle Seiten erzeugen" in text


def test_fusszeile_nennt_den_programmstand(konfiguration: Konfiguration):
    """Ohne diese Angabe merkt niemand, dass der Container alten Code faehrt.

    Genau das ist auf der NAS die haeufigste Stoerung -- und die einzige, die
    keine Fehlermeldung erzeugt.
    """
    text = _client(konfiguration).get("/").get_data(as_text=True)
    assert "Stand:" in text
    assert programmstand() in text


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


def test_kompletter_durchlauf_ueber_die_oberflaeche(konfiguration: Konfiguration):
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
    dateien = zustand["ergebnis"]["dateien"]
    assert len(dateien) == 1
    assert dateien[0]["mannschaft"] == "Herren 1"
    assert dateien[0]["seitenzahl"] == 6
    assert zustand["ergebnis"]["stand"]
    assert any("Herren 1" in z["text"] for z in zustand["protokoll"])

    # Das ZIP enthaelt alles, die Einzeldatei ist trotzdem direkt erreichbar
    archiv = client.get(f"/lauf/{lauf_id}/download")
    assert archiv.status_code == 200
    assert archiv.data[:2] == b"PK"

    einzeln = client.get(f"/lauf/{lauf_id}/datei/0")
    assert einzeln.status_code == 200
    assert einzeln.data[:4] == b"%PDF"

    assert client.get(f"/lauf/{lauf_id}/datei/7").status_code == 404


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


# ---------------------------------------------------------------------------
# Ablage auf der NAS per Knopf (File Station)
# ---------------------------------------------------------------------------

def _fertiger_lauf(client) -> str:
    antwort = client.post("/erstellen", data={"mannschaften": ["herren1"]})
    lauf_id = antwort.headers["Location"].rstrip("/").split("/")[-1]
    for _ in range(120):
        if client.get(f"/lauf/{lauf_id}/status").get_json()["fertig"]:
            return lauf_id
        time.sleep(0.5)
    raise AssertionError("Lauf wurde nicht fertig")


def _warten_auf_ablage(client, lauf_id: str) -> dict:
    for _ in range(100):
        zustand = client.get(f"/lauf/{lauf_id}/nas/status").get_json()
        if zustand.get("fertig"):
            return zustand
        time.sleep(0.05)
    raise AssertionError("Ablage wurde nicht fertig")


def test_nas_knopf_nur_bei_filestation(konfiguration: Konfiguration):
    client = _client(konfiguration)
    lauf_id = _fertiger_lauf(client)
    assert "Auf die NAS legen" not in client.get(f"/lauf/{lauf_id}").get_data(as_text=True)
    assert client.post(f"/lauf/{lauf_id}/nas", json={"ordnername": "x"}).status_code == 404


def test_nas_ablage_ueber_die_oberflaeche(konfiguration: Konfiguration, monkeypatch):
    from stadionheft.storage import filestation

    konfiguration.roh["nas"].update({"aktiv": True, "modus": "filestation"})
    aufrufe: list[dict] = []
    ergebnisse = [False, True]

    def ablage(k, ordnername, dateien, fs=None, fortsetzen=False, melden=None):
        aufrufe.append({"name": ordnername, "fortsetzen": fortsetzen,
                        "dateien": [(s, p.name) for s, p in dateien]})
        bericht = filestation.AblageBericht(ordner=f"/S/{ordnername}",
                                            angelegt=True,
                                            erfolgreich=ergebnisse.pop(0))
        if not bericht.erfolgreich:
            bericht.fehler = "Relay weg"
        return bericht

    monkeypatch.setattr(filestation, "ablage_ausfuehren", ablage)
    client = _client(konfiguration)
    lauf_id = _fertiger_lauf(client)
    assert "Auf die NAS legen" in client.get(f"/lauf/{lauf_id}").get_data(as_text=True)

    # Erster Versuch bricht ab ...
    assert client.post(f"/lauf/{lauf_id}/nas",
                       json={"ordnername": " 09  Ausgabe 301026"}).get_json()["gestartet"]
    zustand = _warten_auf_ablage(client, lauf_id)
    assert zustand["bericht"]["erfolgreich"] is False
    assert aufrufe[0]["fortsetzen"] is False
    assert aufrufe[0]["dateien"][0][0] == "herren1"

    # ... der zweite mit demselben Namen setzt den Ordner fort
    client.post(f"/lauf/{lauf_id}/nas", json={"ordnername": "09 Ausgabe 301026"})
    zustand = _warten_auf_ablage(client, lauf_id)
    assert zustand["bericht"]["erfolgreich"] is True
    assert aufrufe[1]["fortsetzen"] is True

    # Ein drittes Mal gibt es nicht -- das Heft liegt schon dort
    antwort = client.post(f"/lauf/{lauf_id}/nas", json={"ordnername": "10 Ausgabe"})
    assert antwort.status_code == 409 and len(aufrufe) == 2


def test_nas_ablage_anderer_name_setzt_nicht_fort(konfiguration: Konfiguration,
                                                  monkeypatch):
    from stadionheft.storage import filestation

    konfiguration.roh["nas"].update({"aktiv": True, "modus": "filestation"})
    aufrufe: list[bool] = []

    def ablage(k, ordnername, dateien, fs=None, fortsetzen=False, melden=None):
        aufrufe.append(fortsetzen)
        return filestation.AblageBericht(angelegt=True, erfolgreich=False)

    monkeypatch.setattr(filestation, "ablage_ausfuehren", ablage)
    client = _client(konfiguration)
    lauf_id = _fertiger_lauf(client)
    client.post(f"/lauf/{lauf_id}/nas", json={"ordnername": "09 Ausgabe"})
    _warten_auf_ablage(client, lauf_id)
    client.post(f"/lauf/{lauf_id}/nas", json={"ordnername": "09 Ausgabe b"})
    _warten_auf_ablage(client, lauf_id)
    assert aufrufe == [False, False]


def test_gesamtheft_knopf_nur_wenn_eingeschaltet(konfiguration: Konfiguration):
    client = _client(konfiguration)
    assert client.get("/heft").status_code == 404
    assert "Gesamtes Heft bauen" not in client.get("/").get_data(as_text=True)


def test_gesamtheft_knopf_sichtbar(konfiguration: Konfiguration, monkeypatch):
    from stadionheft import gesamtheft

    konfiguration.roh["nas"].update({"aktiv": True, "modus": "filestation"})
    konfiguration.roh["heft"]["gesamt_aktiv"] = True
    monkeypatch.setattr(gesamtheft, "ausgaben_auflisten",
                        lambda k: ["09 Ausgabe 301026", "08 Ausgabe 161026"])
    client = _client(konfiguration)
    assert "Gesamtes Heft bauen" in client.get("/").get_data(as_text=True)
    seite = client.get("/heft").get_data(as_text=True)
    assert "<option>09 Ausgabe 301026</option>" in seite
    hilfe = client.get("/hilfe").get_data(as_text=True)
    assert "Das gesamte Heft bauen" in hilfe and "Neue Saison" in hilfe


# ---------------------------------------------------------------------------
# Titelbild von Hand hochladen
# ---------------------------------------------------------------------------

JPG = b"\xff\xd8\xff\xe0" + b"0" * 64


def test_startseite_bietet_titelbild_an(konfiguration: Konfiguration):
    html = _client(konfiguration).get("/").get_data(as_text=True)
    assert 'name="titelbild"' in html and "multipart/form-data" in html


def test_titelbild_kein_bild_wird_abgelehnt(konfiguration: Konfiguration):
    import io
    antwort = _client(konfiguration).post(
        "/erstellen", content_type="multipart/form-data",
        data={"mannschaften": ["herren1"],
              "titelbild": (io.BytesIO(b"%PDF-1.4"), "titel.jpg")})
    assert antwort.status_code == 400
    assert "JPG- oder PNG" in antwort.get_data(as_text=True)


def test_titelbild_geht_ans_deckblatt_und_auf_die_nas(konfiguration: Konfiguration,
                                                     monkeypatch):
    import io

    from stadionheft import build
    from stadionheft.storage import filestation

    konfiguration.roh["nas"].update({"aktiv": True, "modus": "filestation"})
    gesehen: dict = {}
    echt = build.dateien_erstellen

    def erstellen(k, mannschaften, **argumente):
        gesehen["titelbild"] = argumente.get("titelbild")
        argumente["titelbild"] = None
        return echt(k, mannschaften, **argumente)

    def ablage(k, ordnername, dateien, fs=None, fortsetzen=False, melden=None):
        gesehen["dateien"] = [(s, p.name) for s, p in dateien]
        return filestation.AblageBericht(ordner=f"/S/{ordnername}",
                                         angelegt=True, erfolgreich=True)

    import stadionheft.web as web
    monkeypatch.setattr(web, "dateien_erstellen", erstellen)
    monkeypatch.setattr(filestation, "ablage_ausfuehren", ablage)
    client = _client(konfiguration)
    antwort = client.post(
        "/erstellen", content_type="multipart/form-data",
        data={"mannschaften": ["herren1"],
              "titelbild": (io.BytesIO(JPG), "IMG_2026.JPEG")})
    lauf_id = antwort.headers["Location"].rstrip("/").split("/")[-1]
    for _ in range(120):
        if client.get(f"/lauf/{lauf_id}/status").get_json()["fertig"]:
            break
        time.sleep(0.5)
    assert gesehen["titelbild"].name == "Titelbild.jpg"
    assert gesehen["titelbild"].read_bytes() == JPG

    client.post(f"/lauf/{lauf_id}/nas", json={"ordnername": "09 Ausgabe"})
    _warten_auf_ablage(client, lauf_id)
    assert ("", "Titelbild.jpg") in gesehen["dateien"]
