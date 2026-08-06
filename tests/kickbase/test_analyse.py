"""Die Bewertungslogik -- der Teil, auf den es wirklich ankommt."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from kickbase.analyse import kennzahlen as kz
from kickbase.analyse.bewertung import Referenzwerte, bewerten
from kickbase.config import Konfiguration
from kickbase.models import Marktwertpunkt, Spieler, Spieltagsleistung
from kickbase.quellen.openligadb import Begegnung, Ligalage


def spieler_bauen(**felder) -> Spieler:
    grund = dict(id="1", vorname="Test", nachname="Spieler", team_id="2",
                 team_name="FC Bayern München", position=3, status=0,
                 marktwert=10_000_000, punkte_schnitt=80, spiele=10)
    grund.update(felder)
    return Spieler(**grund)


def leistungen_anhaengen(spieler: Spieler, punkte: list[int],
                         minuten: list[int] | None = None) -> Spieler:
    minuten = minuten or [90] * len(punkte)
    heute = date.today()
    for stelle, (p, m) in enumerate(zip(punkte, minuten)):
        spieler.leistungen.append(Spieltagsleistung(
            spieltag=stelle + 1, punkte=p, minuten=m, gespielt=True,
            datum=heute - timedelta(days=7 * (len(punkte) - stelle))))
    return spieler


def verlauf_anhaengen(spieler: Spieler, werte: list[int]) -> Spieler:
    heute = date.today()
    spieler.verlauf = [
        Marktwertpunkt(tag=heute - timedelta(days=len(werte) - 1 - i), wert=w)
        for i, w in enumerate(werte)]
    return spieler


# -- Einzelne Kennzahlen ---------------------------------------------------


def test_verfuegbarkeit_bestraft_verletzung_deutlich():
    fit = kz.verfuegbarkeit(spieler_bauen(status=0))
    verletzt = kz.verfuegbarkeit(spieler_bauen(status=1))
    gesperrt = kz.verfuegbarkeit(spieler_bauen(status=8))

    assert fit.punkte > 0
    assert verletzt.punkte < -50
    assert gesperrt.punkte < -50
    assert "Verletzt" in verletzt.begruendung


def test_verfuegbarkeit_kennt_unbekannte_statuscodes():
    """Kickbase ergaenzt gelegentlich neue Codes -- das darf nichts sprengen."""
    kennzahl = kz.verfuegbarkeit(spieler_bauen(status=999))
    assert kennzahl.punkte < 0
    assert "nicht bekannt" in kennzahl.begruendung


def test_form_erkennt_aufwaertstrend():
    spieler = leistungen_anhaengen(spieler_bauen(punkte_schnitt=60),
                                   [40, 50, 90, 110, 130])
    kennzahl = kz.form(spieler, 5)
    assert kennzahl.punkte > 20
    assert "über" in kennzahl.begruendung


def test_form_erkennt_abwaertstrend():
    spieler = leistungen_anhaengen(spieler_bauen(punkte_schnitt=90),
                                   [120, 100, 40, 20, 10])
    assert kz.form(spieler, 5).punkte < -20


def test_form_ohne_daten_bleibt_neutral():
    kennzahl = kz.form(spieler_bauen(), 5)
    assert kennzahl.punkte == 0
    assert kennzahl.anzeige == "zu wenig Daten"


def test_einsatzzeit_erkennt_stammspieler_und_bankdruecker():
    stamm = leistungen_anhaengen(spieler_bauen(), [80] * 5, [90, 90, 88, 90, 85])
    bank = leistungen_anhaengen(spieler_bauen(), [5] * 5, [0, 12, 0, 8, 15])

    assert kz.einsatzzeit(stamm, 5).punkte > 30
    assert kz.einsatzzeit(bank, 5).punkte < -40


def test_einsatzzeit_schlaegt_bei_drei_spielen_ohne_einsatz_alarm():
    spieler = leistungen_anhaengen(spieler_bauen(), [90, 80, 0, 0, 0],
                                   [90, 90, 0, 0, 0])
    kennzahl = kz.einsatzzeit(spieler, 5)
    assert kennzahl.punkte <= -80
    assert "ohne Einsatz" in kennzahl.begruendung


def test_marktwerttrend_rechnet_prozentual():
    steigend = verlauf_anhaengen(spieler_bauen(marktwert=11_000_000),
                                 [10_000_000] * 24 + [10_500_000] * 6 + [11_000_000])
    assert kz.marktwerttrend(steigend).punkte > 0

    fallend = verlauf_anhaengen(spieler_bauen(marktwert=9_000_000),
                                [10_000_000] * 24 + [9_500_000] * 6 + [9_000_000])
    assert kz.marktwerttrend(fallend).punkte < 0


def test_marktwerttrend_nutzt_ersatzweise_den_kickbase_pfeil():
    kennzahl = kz.marktwerttrend(spieler_bauen(marktwert_trend=1))
    assert kennzahl.punkte > 0
    assert "Kickbase meldet" in kennzahl.begruendung


def test_preis_leistung_vergleicht_mit_der_position():
    guenstig = spieler_bauen(marktwert=5_000_000, punkte_schnitt=80)   # 16 Pkt/Mio
    teuer = spieler_bauen(marktwert=20_000_000, punkte_schnitt=80)     # 4 Pkt/Mio

    assert kz.preis_leistung(guenstig, vergleich=8.0).punkte > 30
    assert kz.preis_leistung(teuer, vergleich=8.0).punkte < -30


def test_preis_leistung_rechnet_mit_dem_angebotspreis():
    spieler = spieler_bauen(marktwert=10_000_000, punkte_schnitt=80)
    zum_marktwert = kz.preis_leistung(spieler, vergleich=8.0)
    mit_aufschlag = kz.preis_leistung(spieler, vergleich=8.0, preis=15_000_000)
    assert mit_aufschlag.punkte < zum_marktwert.punkte
    assert "über dem Marktwert" in mit_aufschlag.begruendung


def test_gegnerstaerke_belohnt_schwache_gegner():
    lage = Ligalage(
        tabelle={"bayernmuenchen": 1, "augsburg": 18, "koeln": 17},
        namen={"bayernmuenchen": "FC Bayern München", "augsburg": "FC Augsburg",
               "koeln": "1. FC Köln"},
        begegnungen=[
            Begegnung(spieltag=5, anstoss=None, heim="FC Bayern München",
                      gast="FC Augsburg"),
            Begegnung(spieltag=6, anstoss=None, heim="1. FC Köln",
                      gast="FC Bayern München"),
        ])
    leicht = kz.gegnerstaerke(spieler_bauen(team_name="FC Bayern München"), lage)
    assert leicht.punkte > 20

    schwer = kz.gegnerstaerke(spieler_bauen(team_name="FC Augsburg"), lage)
    assert schwer.punkte < 0


def test_gegnerstaerke_ohne_spielplan_bleibt_neutral():
    kennzahl = kz.gegnerstaerke(spieler_bauen(), None)
    assert kennzahl.punkte == 0
    assert "Kein Spielplan" in kennzahl.begruendung


def test_bewertungsniveau_ist_gegenlaeufig_zum_preis():
    hoch = verlauf_anhaengen(spieler_bauen(marktwert=12_000_000),
                             list(range(8_000_000, 12_000_001, 200_000)))
    tief = verlauf_anhaengen(spieler_bauen(marktwert=8_000_000),
                             list(range(12_000_000, 7_999_999, -200_000)))
    assert kz.bewertungsniveau(hoch).punkte < 0
    assert kz.bewertungsniveau(tief).punkte > 0


# -- Gesamtnote ------------------------------------------------------------


@pytest.fixture
def referenz() -> Referenzwerte:
    return Referenzwerte(punkte_je_million={1: 8.0, 2: 8.0, 3: 8.0, 4: 8.0})


def test_starker_spieler_wird_zum_kauf(referenz):
    spieler = leistungen_anhaengen(
        spieler_bauen(marktwert=6_000_000, punkte_schnitt=85),
        [70, 80, 110, 120, 130])
    verlauf_anhaengen(spieler, [5_000_000] * 20 + [5_500_000] * 10 + [6_000_000] * 5)

    bewertung = bewerten(spieler, referenz, Konfiguration({}))
    assert bewertung.gesamtpunkte > 15
    assert bewertung.stufe in ("kaufen", "beobachten")


def test_verletzter_wird_nie_zum_kauf_hochgerechnet(referenz):
    """Die wichtigste Vorrangregel: gute Zahlen aus gesunden Zeiten
    duerfen einen Langzeitverletzten nicht schoenrechnen."""
    spieler = leistungen_anhaengen(
        spieler_bauen(marktwert=4_000_000, punkte_schnitt=120, status=1),
        [130, 140, 150, 160, 170])

    bewertung = bewerten(spieler, referenz, Konfiguration({}))
    assert bewertung.gesamtpunkte <= -45
    assert bewertung.stufe == "verkaufen"
    assert "Verletzt" in bewertung.uebersteuerung


def test_gesperrter_wird_gedeckelt(referenz):
    spieler = leistungen_anhaengen(
        spieler_bauen(marktwert=4_000_000, punkte_schnitt=120, status=8),
        [130, 140, 150, 160, 170])
    bewertung = bewerten(spieler, referenz, Konfiguration({}))
    assert bewertung.gesamtpunkte <= -20
    assert "Gesperrt" in bewertung.uebersteuerung


def test_duenne_datengrundlage_daempft_die_note(referenz):
    viele = leistungen_anhaengen(
        spieler_bauen(spiele=10, marktwert=5_000_000), [100] * 5)
    wenige = leistungen_anhaengen(
        spieler_bauen(spiele=1, marktwert=5_000_000), [100] * 5)

    note_viele = bewerten(viele, referenz, Konfiguration({})).gesamtpunkte
    bewertung_wenige = bewerten(wenige, referenz, Konfiguration({}))
    assert abs(bewertung_wenige.gesamtpunkte) < abs(note_viele)
    assert any("dünn" in w for w in bewertung_wenige.warnungen)


def test_zu_hoher_angebotspreis_deckelt_die_note(referenz):
    spieler = leistungen_anhaengen(
        spieler_bauen(marktwert=5_000_000, punkte_schnitt=90), [120] * 5)
    verlauf_anhaengen(spieler, [4_000_000] * 25 + [5_000_000] * 6)

    fair = bewerten(spieler, referenz, Konfiguration({}), preis=5_000_000)
    teuer = bewerten(spieler, referenz, Konfiguration({}), preis=8_000_000)
    assert teuer.gesamtpunkte <= 10
    assert teuer.gesamtpunkte < fair.gesamtpunkte
    assert "zu teuer" in teuer.uebersteuerung


def test_gewichte_wirken_sich_aus(referenz):
    spieler = leistungen_anhaengen(
        spieler_bauen(status=2, punkte_schnitt=90), [120] * 5)

    egal = Konfiguration({"analyse": {"gewichte": {"verfuegbarkeit": 0.1}}})
    wichtig = Konfiguration({"analyse": {"gewichte": {"verfuegbarkeit": 3.0}}})
    assert (bewerten(spieler, referenz, wichtig).gesamtpunkte
            < bewerten(spieler, referenz, egal).gesamtpunkte)


def test_jede_kennzahl_traegt_eine_begruendung(referenz):
    spieler = leistungen_anhaengen(spieler_bauen(), [80] * 5)
    bewertung = bewerten(spieler, referenz, Konfiguration({}))
    assert len(bewertung.kennzahlen) == 7
    for kennzahl in bewertung.kennzahlen:
        assert kennzahl.begruendung.strip(), f"{kennzahl.name} ohne Begruendung"
        assert -100 <= kennzahl.punkte <= 100


def test_referenzwerte_nutzen_den_median():
    spieler = [spieler_bauen(id=str(i), position=3, marktwert=10_000_000,
                             punkte_schnitt=p, spiele=10)
               for i, p in enumerate([50, 60, 70, 80, 5000])]
    referenz = Referenzwerte.aus_spielern(spieler)
    # Der Ausreisser mit 5000 Punkten darf den Massstab nicht verzerren.
    assert referenz.vergleich(3) == pytest.approx(7.0)
