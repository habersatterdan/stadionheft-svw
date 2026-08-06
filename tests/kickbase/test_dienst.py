"""Der Gesamtablauf: Abruf, Lagebericht, Zusammenfuehren von Spielerlisten."""

from __future__ import annotations

from kickbase.config import Konfiguration
from kickbase.dienst import Berater, Planer, _zusammenfuehren
from kickbase.models import Spieler


def test_demoabruf_liefert_einen_vollstaendigen_bericht(berater: Berater):
    bericht = berater.bericht()

    assert bericht.eigene, "Der Demokader darf nicht leer sein."
    assert bericht.transfermarkt
    assert bericht.kandidaten
    assert bericht.quellen["modus"] == "Demodaten"
    assert all(-100 <= b.gesamtpunkte <= 100 for b in bericht.eigene)


def test_bericht_ohne_daten_sagt_das_deutlich(konfiguration: Konfiguration):
    bericht = Berater(konfiguration).bericht()
    assert bericht.eigene == []
    assert any("Abruf" in w for w in bericht.warnungen)


def test_kandidaten_enthalten_keine_eigenen_spieler(berater: Berater):
    eigene = {b.spieler.id for b in berater.bericht().eigene}
    kandidaten = {b.spieler.id for b in berater.bericht().kandidaten}
    assert not (eigene & kandidaten)


def test_billige_spieler_bleiben_aus_den_kandidaten_draussen(konfiguration):
    konfiguration.roh["analyse"]["mindest_marktwert"] = 5_000_000
    berater = Berater(konfiguration)
    berater.abrufen()
    assert all(b.spieler.marktwert >= 5_000_000
               for b in berater.bericht().kandidaten)


def test_transfermarkt_wird_gegen_den_angebotspreis_bewertet(berater: Berater):
    bericht = berater.bericht()
    teuer = [b for b in bericht.transfermarkt
             if b.spieler.angebotspreis > b.spieler.marktwert * 1.2]
    for bewertung in teuer:
        assert bewertung.gesamtpunkte <= 10, \
            "Ein deutlicher Aufschlag muss die Note deckeln."


def test_zweiter_abruf_ersetzt_die_daten_statt_sie_zu_haeufen(berater: Berater):
    vorher = len(berater.speicher.spieler_laden())
    berater.abrufen()
    assert len(berater.speicher.spieler_laden()) == vorher


def test_ausfaelle_und_verkaufskandidaten_werden_erkannt(berater: Berater):
    bericht = berater.bericht()
    assert bericht.ausfaelle, "Die Demodaten enthalten bewusst Verletzte."
    for bewertung in bericht.ausfaelle:
        assert not bewertung.spieler.einsatzbereit


def test_gleichzeitige_abrufe_werden_abgewiesen(berater: Berater):
    """Der zweite Aufruf soll nicht warten, sondern zurueckmelden."""
    berater._sperre.acquire()
    try:
        ergebnis = berater.abrufen()
    finally:
        berater._sperre.release()
    assert ergebnis["erfolgreich"] is False
    assert "läuft bereits" in ergebnis["meldung"]


def test_spielerlisten_werden_sinnvoll_zusammengefuehrt():
    """Derselbe Spieler taucht in Kader, Markt und Wettbewerbsliste auf --
    jede Liste kennt andere Felder."""
    aus_wettbewerb = Spieler(id="7", nachname="Musiala", marktwert=30_000_000,
                             punkte_schnitt=95)
    aus_markt = Spieler(id="7", team_name="FC Bayern München",
                        auf_transfermarkt=True, angebotspreis=33_000_000,
                        status=2)

    _zusammenfuehren(aus_wettbewerb, aus_markt)
    assert aus_wettbewerb.team_name == "FC Bayern München"
    assert aus_wettbewerb.auf_transfermarkt is True
    assert aus_wettbewerb.angebotspreis == 33_000_000
    assert aus_wettbewerb.status == 2
    assert aus_wettbewerb.marktwert == 30_000_000, "Bekanntes wird nicht ueberschrieben."


def test_anreicherungsliste_nimmt_immer_kader_und_markt(konfiguration):
    konfiguration.roh["abruf"]["kandidaten_je_position"] = 1
    berater = Berater(konfiguration)
    spieler = [
        Spieler(id="1", im_eigenen_team=True, marktwert=200_000, position=3),
        Spieler(id="2", auf_transfermarkt=True, marktwert=200_000, position=3),
        Spieler(id="3", marktwert=20_000_000, position=3, punkte_schnitt=90),
        Spieler(id="4", marktwert=20_000_000, position=3, punkte_schnitt=10),
    ]
    auswahl = {s.id for s in berater._anreicherungsliste(spieler)}
    assert {"1", "2"} <= auswahl, "Kader und Markt sind Pflicht."
    assert "3" in auswahl, "Der punktstaerkere Kandidat wird bevorzugt."
    assert "4" not in auswahl


def test_planer_haelt_sich_an_das_intervall(konfiguration):
    konfiguration.roh["abruf"]["intervall_stunden"] = 6
    planer = Planer(Berater(konfiguration))
    assert planer.intervall_s == 6 * 3600

    konfiguration.roh["abruf"]["intervall_stunden"] = 0.01
    assert planer.intervall_s == 600, "Unter zehn Minuten wird nicht abgerufen."


def test_ausgeschalteter_planer_startet_keinen_faden(konfiguration):
    konfiguration.roh["abruf"]["automatisch"] = False
    planer = Planer(Berater(konfiguration))
    planer.starten()
    assert planer.faden is None
