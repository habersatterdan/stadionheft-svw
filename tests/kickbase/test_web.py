"""Weboberflaeche: alle Seiten erreichbar, Filter wirken, Schutz greift."""

from __future__ import annotations

import base64

import pytest

from kickbase.config import Konfiguration
from kickbase.dienst import Berater
from kickbase.web import app_erzeugen
from kickbase.web.diagramm import euro_kurz, marktwertdiagramm, sparklinie


@pytest.fixture
def client(konfiguration: Konfiguration):
    app = app_erzeugen(konfiguration, planer_starten=False)
    app.config["BERATER"].abrufen()
    return app.test_client()


@pytest.mark.parametrize("pfad", ["/", "/markt", "/kandidaten", "/hilfe",
                                  "/status.json", "/bericht.json", "/gesundheit"])
def test_alle_seiten_antworten(client, pfad):
    antwort = client.get(pfad)
    assert antwort.status_code == 200


def test_startseite_zeigt_kader_und_demohinweis(client):
    text = client.get("/").get_data(as_text=True)
    assert "Mein Team" in text
    assert "Demomodus" in text
    assert "Verkaufsvorschläge" in text


def test_spielerseite_zeigt_alle_kennzahlen(client, konfiguration):
    spieler = Berater(konfiguration).speicher.spieler_laden()[0]
    text = client.get(f"/spieler/{spieler.id}").get_data(as_text=True)

    assert spieler.name in text
    for ueberschrift in ("Verfügbarkeit", "Form", "Einsatzzeit",
                         "Marktwerttrend", "Preis-Leistung", "Bewertungsniveau"):
        assert ueberschrift in text
    assert "Wie die Note zustande kommt" in text


def test_unbekannter_spieler_ergibt_eine_verstaendliche_seite(client):
    antwort = client.get("/spieler/gibtsnicht")
    assert antwort.status_code == 404
    assert "kennt der Berater nicht" in antwort.get_data(as_text=True)


def test_kandidatenfilter_wirken(client):
    alle = client.get("/kandidaten").get_data(as_text=True)
    nur_sturm = client.get("/kandidaten?position=4").get_data(as_text=True)
    assert alle.count("Mittelfeld") > nur_sturm.count("Mittelfeld")

    guenstig = client.get("/kandidaten?hoechstpreis=3").get_data(as_text=True)
    assert "Treffer" in guenstig


def test_filter_vertragen_unsinnige_eingaben(client):
    for anhang in ("?position=abc", "?hoechstpreis=viel", "?position=-1"):
        assert client.get(f"/kandidaten{anhang}").status_code == 200


def test_bericht_als_json_ist_auswertbar(client):
    daten = client.get("/bericht.json").get_json()
    assert "eigene" in daten and daten["eigene"]
    erster = daten["eigene"][0]
    assert {"name", "empfehlung", "gesamtpunkte", "kennzahlen"} <= set(erster)
    assert erster["kennzahlen"][0]["begruendung"]


def test_abruf_kehrt_sofort_zurueck(client):
    antwort = client.post("/abruf")
    assert antwort.status_code == 302


def test_passwortschutz_sperrt_und_laesst_mit_passwort_durch(tmp_path, monkeypatch):
    monkeypatch.setenv("KICKBASE_WEB_PASSWORT", "geheim")
    konfiguration = Konfiguration({
        "speicher": {"datenbank": str(tmp_path / "k.sqlite3")},
        "protokoll": {"ordner": str(tmp_path / "logs")},
        "abruf": {"automatisch": False},
        "web": {"passwortschutz": True, "benutzer": "daniel"},
    })
    client = app_erzeugen(konfiguration, planer_starten=False).test_client()

    assert client.get("/").status_code == 401
    # Der Gesundheitscheck des Containers muss trotzdem durchkommen.
    assert client.get("/gesundheit").status_code == 200

    schluessel = base64.b64encode(b"daniel:geheim").decode()
    assert client.get("/", headers={"Authorization": f"Basic {schluessel}"}
                      ).status_code == 200

    falsch = base64.b64encode(b"daniel:falsch").decode()
    assert client.get("/", headers={"Authorization": f"Basic {falsch}"}
                      ).status_code == 401


# -- Diagramme -------------------------------------------------------------


def test_marktwertdiagramm_rechnet_koordinaten(konfiguration):
    from datetime import date, timedelta

    from kickbase.models import Marktwertpunkt

    heute = date.today()
    verlauf = [Marktwertpunkt(tag=heute - timedelta(days=30 - t),
                              wert=1_000_000 + t * 50_000) for t in range(31)]
    diagramm = marktwertdiagramm(verlauf)

    assert diagramm.leer is False
    assert len(diagramm.punkte) == 31
    assert diagramm.hoechst.wert == 2_500_000
    assert diagramm.tiefst.wert == 1_000_000
    # Steigende Werte muessen nach oben gehen -- in SVG heisst das: kleineres y.
    assert diagramm.punkte[-1].y < diagramm.punkte[0].y
    assert diagramm.punkte_json[0]["beschriftung"]


def test_diagramm_mit_zu_wenig_punkten_bleibt_leer():
    assert marktwertdiagramm([]).leer is True
    assert sparklinie([]) == ""


def test_euro_wird_deutsch_geschrieben():
    assert euro_kurz(1_234_567) == "1,23 Mio."
    assert euro_kurz(450_000) == "450 Tsd."
