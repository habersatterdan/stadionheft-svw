"""Ablage: eigene Marktwerthistorie, Abrufprotokoll, Notizen."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from kickbase.models import Marktwertpunkt, Spieler, Spieltagsleistung
from kickbase.speicher import Speicher


def test_spieler_ueberleben_speichern_und_laden(tmp_path: Path):
    speicher = Speicher(tmp_path / "k.sqlite3")
    spieler = Spieler(id="7", vorname="Jamal", nachname="Musiala",
                      team_name="FC Bayern München", position=3,
                      marktwert=30_000_000, punkte_schnitt=95)
    spieler.leistungen.append(Spieltagsleistung(spieltag=1, punkte=120,
                                                minuten=90, gespielt=True))
    speicher.spieler_speichern([spieler])

    zurueck = speicher.spieler_laden()
    assert len(zurueck) == 1
    assert zurueck[0].name == "Jamal Musiala"
    assert zurueck[0].marktwert == 30_000_000
    assert zurueck[0].leistungen[0].punkte == 120


def test_erneutes_speichern_ersetzt_statt_zu_verdoppeln(tmp_path: Path):
    speicher = Speicher(tmp_path / "k.sqlite3")
    speicher.spieler_speichern([Spieler(id="7", marktwert=30_000_000)])
    speicher.spieler_speichern([Spieler(id="7", marktwert=31_000_000)])

    geladen = speicher.spieler_laden()
    assert len(geladen) == 1
    assert geladen[0].marktwert == 31_000_000


def test_marktwerthistorie_waechst_ueber_die_abrufe(tmp_path: Path):
    """Der eigentliche Zweck der Datenbank: eine Reihe, die Kickbase nicht hat."""
    speicher = Speicher(tmp_path / "k.sqlite3")
    heute = date.today()
    spieler = Spieler(id="7", marktwert=30_000_000)
    spieler.verlauf = [
        Marktwertpunkt(tag=heute - timedelta(days=t), wert=29_000_000 + t)
        for t in range(1, 40)]
    speicher.spieler_speichern([spieler])

    reihe = speicher.marktwert_reihe("7")
    assert len(reihe) == 40, "39 gelieferte Punkte plus der heutige Tageswert"
    assert reihe[-1].tag == heute
    assert reihe[-1].wert == 30_000_000


def test_gelieferte_werte_ueberschreiben_keine_eigenen(tmp_path: Path):
    """Was der Berater selbst gemessen hat, ist die verlaesslichere Angabe."""
    speicher = Speicher(tmp_path / "k.sqlite3")
    heute = date.today()
    speicher.spieler_speichern([Spieler(id="7", marktwert=30_000_000)])

    nachtrag = Spieler(id="7", marktwert=30_000_000)
    nachtrag.verlauf = [Marktwertpunkt(tag=heute, wert=1)]
    speicher.spieler_speichern([nachtrag])

    assert speicher.marktwert_reihe("7")[-1].wert == 30_000_000


def test_alte_werte_werden_aufgeraeumt(tmp_path: Path):
    speicher = Speicher(tmp_path / "k.sqlite3")
    spieler = Spieler(id="7", marktwert=1_000_000)
    spieler.verlauf = [
        Marktwertpunkt(tag=date.today() - timedelta(days=500), wert=900_000)]
    speicher.spieler_speichern([spieler])

    assert speicher.aufraeumen(tage=400) == 1
    assert len(speicher.marktwert_reihe("7", tage=1000)) == 1


def test_abrufprotokoll_merkt_sich_den_letzten_lauf(tmp_path: Path):
    speicher = Speicher(tmp_path / "k.sqlite3")
    speicher.abruf_vermerken(False, meldung="Kickbase nicht erreichbar")
    speicher.abruf_vermerken(True, spieler=120, dauer_s=12.5, meldung="fertig")

    letzter = speicher.letzter_abruf()
    assert letzter["erfolgreich"] == 1
    assert letzter["spieler"] == 120
    assert len(speicher.abrufe()) == 2


def test_notizen_speichern_beliebige_strukturen(tmp_path: Path):
    speicher = Speicher(tmp_path / "k.sqlite3")
    speicher.notiz_setzen("liga", {"name": "HaramLig", "budget": 5_000_000})
    assert speicher.notiz_lesen("liga")["name"] == "HaramLig"
    assert speicher.notiz_lesen("gibtsnicht", "standard") == "standard"


def test_beschaedigter_eintrag_legt_nicht_alles_lahm(tmp_path: Path):
    """Ein kaputter Datensatz darf die anderen nicht mitnehmen."""
    import sqlite3

    speicher = Speicher(tmp_path / "k.sqlite3")
    speicher.spieler_speichern([Spieler(id="7", nachname="Musiala")])
    db = sqlite3.connect(tmp_path / "k.sqlite3")
    db.execute("INSERT INTO spieler (id, gespeichert, daten) VALUES "
               "('999', '2026-01-01', 'kein JSON')")
    db.commit()
    db.close()

    geladen = speicher.spieler_laden()
    assert [s.id for s in geladen] == ["7"]
