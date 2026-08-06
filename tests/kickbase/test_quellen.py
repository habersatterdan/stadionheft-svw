"""Datenquellen: Umwandlung der Kickbase-Kuerzel, Spielplan, Verletzungstexte.

Es wird bewusst **nicht** ueber das Netz getestet. Stattdessen werden echte
Antwortformen nachgebildet -- so faellt auf, wenn die Umwandlung kaputtgeht,
ohne dass jemand seine Zugangsdaten braucht.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from kickbase.errors import AnmeldeFehler
from kickbase.models import Spieler
from kickbase.quellen.kickbase_api import (KickbaseQuelle, _liste, _wert,
                                           _zahl, _zu_datum, namen_ergaenzen)
from kickbase.quellen.openligadb import (Begegnung, Ligalage,
                                         OpenLigaDbQuelle, namen_schluessel,
                                         saison_bestimmen)
from kickbase.quellen.verletzungen import (BEGRIFFE, VerletzungsQuelle,
                                           text_aus_html)


# -- Kickbase: Feldnamen ---------------------------------------------------


def test_wert_nimmt_den_ersten_treffer():
    assert _wert({"n": "Grifo"}, "fn", "n", standard="") == "Grifo"
    assert _wert({"fn": "Vincenzo", "n": "Grifo"}, "fn", "n") == "Vincenzo"


def test_wert_liefert_den_standard_bei_fehlendem_feld():
    """Ein umbenanntes Feld darf eine Luecke ergeben, keinen Absturz."""
    assert _wert({"irgendwas": 1}, "mv", standard=0) == 0
    assert _wert(None, "mv", standard=0) == 0
    assert _zahl({"mv": "keine Zahl"}, "mv") == 0


def test_liste_findet_die_uebliche_verpackung():
    assert _liste({"it": [1, 2]}) == [1, 2]
    assert _liste({"items": [3]}) == [3]
    assert _liste([4, 5]) == [4, 5]
    assert _liste({"unbekannt": 1}) == []


@pytest.mark.parametrize("roh, erwartet", [
    ("2026-02-26T18:30:00Z", date(2026, 2, 26)),
    ("2026-02-26", date(2026, 2, 26)),
    (1772131800, date(2026, 2, 26)),           # Unix-Sekunden
    (1772131800000, date(2026, 2, 26)),        # Unix-Millisekunden
    (0, None),
    ("", None),
    (None, None),
    ("Unfug", None),
])
def test_datumsformate_werden_erkannt(roh, erwartet):
    assert _zu_datum(roh) == erwartet


def test_kaderzeile_wird_zu_einem_spieler():
    """Aufbau wie in der echten Antwort von /v4/leagues/{id}/squad."""
    quelle = KickbaseQuelle("", "")
    spieler = quelle._spieler_aus_kurzform({
        "i": "118", "n": "Grifo", "st": 0, "pos": 3, "mv": 10973197,
        "mvt": 2, "p": 1659, "ap": 72, "tid": "5",
    })
    assert spieler.id == "118"
    assert spieler.nachname == "Grifo"
    assert spieler.marktwert == 10973197
    assert spieler.positions_name == "Mittelfeld"
    assert spieler.status_name == "Fit"
    assert spieler.einsatzbereit is True


def test_spieler_im_unterfeld_wird_gefunden():
    """Auf dem Transfermarkt steckt der Spieler manchmal eine Ebene tiefer."""
    quelle = KickbaseQuelle("", "")
    spieler = quelle._spieler_aus_kurzform(
        {"player": {"i": "7", "n": "Musiala", "mv": 30_000_000, "pos": 3}})
    assert spieler.id == "7"
    assert spieler.marktwert == 30_000_000


def test_anmeldung_ohne_zugangsdaten_meldet_sich_klar():
    with pytest.raises(AnmeldeFehler) as fehler:
        KickbaseQuelle("", "").anmelden()
    assert "KICKBASE_EMAIL" in (fehler.value.hinweis or "")


def test_vereinsnamen_werden_nachgetragen():
    spieler = [Spieler(id="1", team_id="5"), Spieler(id="2", team_id="99")]
    namen_ergaenzen(spieler, {"5": "SC Freiburg"})
    assert spieler[0].team_name == "SC Freiburg"
    assert spieler[1].team_name == ""


# -- OpenLigaDB ------------------------------------------------------------


@pytest.mark.parametrize("name, erwartet", [
    ("1. FC Köln", "koeln"),
    ("FC Koeln", "koeln"),
    ("1.FC Köln", "koeln"),
    ("FC Bayern München", "bayernmuenchen"),
    ("Bayern München", "bayernmuenchen"),
    ("Bor. Mönchengladbach", "moenchengladbach"),
])
def test_vereinsnamen_werden_vergleichbar_gemacht(name, erwartet):
    assert namen_schluessel(name) == erwartet


def test_kurzform_wird_dem_vollen_namen_zugeordnet():
    """Kickbase sagt 'Bayern', OpenLigaDB 'FC Bayern München'."""
    lage = Ligalage(namen={"bayernmuenchen": "FC Bayern München"},
                    tabelle={"bayernmuenchen": 1})
    assert lage.aufloesen("Bayern") == "bayernmuenchen"
    assert lage.platz("Bayern") == 1


def test_mehrdeutige_namen_werden_nicht_geraten():
    """Lieber keine Zuordnung als eine falsche."""
    lage = Ligalage(namen={"bayernmuenchen": "FC Bayern München",
                           "bayernleverkusen": "Bayer Leverkusen"})
    assert lage.aufloesen("Bayern") == ""


def test_naechste_gegner_beruecksichtigen_heimrecht_und_reihenfolge():
    lage = Ligalage(
        namen={"freiburg": "SC Freiburg", "augsburg": "FC Augsburg",
               "koeln": "1. FC Köln"},
        begegnungen=[
            Begegnung(spieltag=9, anstoss=datetime(2026, 3, 1), heim="SC Freiburg",
                      gast="FC Augsburg", beendet=True),
            Begegnung(spieltag=11, anstoss=datetime(2026, 3, 15), heim="1. FC Köln",
                      gast="SC Freiburg"),
            Begegnung(spieltag=10, anstoss=datetime(2026, 3, 8), heim="SC Freiburg",
                      gast="1. FC Köln"),
        ])
    gegner = lage.naechste_gegner("SC Freiburg", 2)
    assert gegner == [("1. FC Köln", True), ("1. FC Köln", False)], \
        "Beendete Spiele zaehlen nicht, und sortiert wird nach Anstoss."


def test_spielplan_ueberlebt_das_speichern_und_laden():
    lage = Ligalage(tabelle={"freiburg": 4}, namen={"freiburg": "SC Freiburg"},
                    aktueller_spieltag=9,
                    begegnungen=[Begegnung(spieltag=10, anstoss=datetime(2026, 3, 8),
                                           heim="SC Freiburg", gast="FC Augsburg")])
    zurueck = Ligalage.aus_dict(lage.als_dict())
    assert zurueck.platz("SC Freiburg") == 4
    assert zurueck.begegnungen[0].gast == "FC Augsburg"
    assert zurueck.aktueller_spieltag == 9


@pytest.mark.parametrize("tag, saison", [
    (date(2026, 8, 20), 2026),
    (date(2027, 3, 1), 2026),
    (date(2026, 6, 30), 2025),
])
def test_saison_wird_richtig_bestimmt(tag, saison):
    assert saison_bestimmen(tag) == saison


def test_openligadb_antwort_wird_umgewandelt():
    quelle = OpenLigaDbQuelle()
    begegnung = quelle._begegnung({
        "team1": {"teamName": "SC Freiburg"},
        "team2": {"teamName": "FC Augsburg"},
        "group": {"groupOrderID": 12},
        "matchDateTime": "2026-03-08T15:30:00",
        "matchIsFinished": True,
        "matchResults": [{"pointsTeam1": 1, "pointsTeam2": 0},
                         {"pointsTeam1": 2, "pointsTeam2": 1}],
    })
    assert begegnung.spieltag == 12
    assert begegnung.beendet is True
    assert (begegnung.tore_heim, begegnung.tore_gast) == (2, 1), \
        "Es zaehlt das Endergebnis, nicht die Halbzeit."


def test_unvollstaendige_spiele_werden_uebersprungen():
    assert OpenLigaDbQuelle()._begegnung({"team1": {}, "team2": {}}) is None


# -- Verletzungsmeldungen --------------------------------------------------


def test_sichtbarer_text_wird_aus_html_gezogen():
    html = """<html><head><style>p {color:red}</style></head>
              <body><script>var x = "unsichtbar";</script>
              <p>Meier f&auml;llt aus</p></body></html>"""
    text = text_aus_html(html)
    assert "Meier fällt aus" in text
    assert "unsichtbar" not in text
    assert "color" not in text


def test_meldung_wird_nur_bei_passendem_umfeld_erkannt():
    bekannte = {"brandtner": "1000", "sonnleitner": "1001"}
    text = ("Brandtner hat sich einen Muskelfaserriss zugezogen und fällt "
            "vier Wochen aus. Sonnleitner traf zweimal und war der beste "
            "Spieler auf dem Platz.")
    treffer = VerletzungsQuelle._auswerten(text, bekannte, "Testquelle")

    assert len(treffer) == 1
    assert treffer[0].spieler_id == "1000"
    assert "Muskelfaserriss" in treffer[0].text


def test_kurze_und_mehrdeutige_namen_werden_ausgelassen():
    """Ein falsch zugeordneter Verletzter waere schlimmer als keiner."""
    spieler = [Spieler(id="1", nachname="Kim"),
               Spieler(id="2", nachname="Müller"),
               Spieler(id="3", nachname="Müller"),
               Spieler(id="4", nachname="Brandtner")]
    index = VerletzungsQuelle._suchindex(spieler)
    assert index == {"brandtner": "4"}


def test_kickbase_meldung_hat_vorrang():
    spieler = Spieler(id="1", nachname="Brandtner",
                      verletzungsmeldung="Kreuzbandriss",
                      verletzungsquelle="Kickbase")
    from kickbase.quellen.verletzungen import Meldung, Verletzungslage
    lage = Verletzungslage(meldungen={
        "1": Meldung(spieler_id="1", text="Irgendwas anderes", quelle="Webseite")})
    assert lage.anwenden([spieler]) == 0
    assert spieler.verletzungsmeldung == "Kreuzbandriss"


def test_begriffsliste_deckt_die_haeufigsten_faelle_ab():
    for begriff in ("verletzt", "gesperrt", "muskelfaserriss", "aufbautraining"):
        assert begriff in BEGRIFFE
