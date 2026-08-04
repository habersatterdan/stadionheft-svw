from __future__ import annotations

from pathlib import Path

import pytest

from stadionheft.config import Konfiguration
from stadionheft.errors import ManuelleDatenFehlenFehler
from stadionheft.sources.base import quelle_erzeugen
from stadionheft.sources.cache import DateiCache
from stadionheft.sources.fupa_api import _liste_finden, _text, _zahl
from stadionheft.sources.manuell import ManuelleQuelle, csv_lesen


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def test_demoquelle_liefert_echte_beispielzahlen(konfiguration: Konfiguration):
    quelle = quelle_erzeugen("demo", konfiguration)
    daten = quelle.hole(konfiguration.mannschaft("herren1"))
    assert len(daten.tabelle) == 16
    assert daten.tabelle[1].mannschaft == "Wörnitzstein"
    assert daten.tabelle[1].eigene is True
    assert daten.naechstes_spiel.gast == "TSV Meitingen"
    assert len(daten.gegner_spieler) == 20


def test_demoquelle_erfindet_daten_fuer_unbekannte_mannschaft(
        konfiguration: Konfiguration):
    quelle = quelle_erzeugen("demo", konfiguration)
    daten = quelle.hole(konfiguration.mannschaft("damen1"))
    assert daten.tabelle and daten.spieler and daten.naechstes_spiel
    assert any("Beispieldaten" in w for w in daten.warnungen)


# ---------------------------------------------------------------------------
# Manuell / CSV
# ---------------------------------------------------------------------------

def _csv(pfad: Path, inhalt: str, kodierung: str = "utf-8") -> None:
    pfad.write_text(inhalt, encoding=kodierung)


def test_csv_lesen_erkennt_semikolon(tmp_path: Path):
    datei = tmp_path / "t.csv"
    _csv(datei, "platz;mannschaft;punkte\n1;FC X;12\n")
    assert csv_lesen(datei) == [{"platz": "1", "mannschaft": "FC X", "punkte": "12"}]


def test_csv_lesen_erkennt_komma(tmp_path: Path):
    datei = tmp_path / "t.csv"
    _csv(datei, "platz,mannschaft,punkte\n1,FC X,12\n")
    assert csv_lesen(datei)[0]["mannschaft"] == "FC X"


def test_csv_lesen_vertraegt_bom_und_grossschreibung(tmp_path: Path):
    datei = tmp_path / "t.csv"
    _csv(datei, "Platz;Mannschaft;Pkt.\n1;FC X;12\n", "utf-8-sig")
    zeile = csv_lesen(datei)[0]
    assert zeile["platz"] == "1" and zeile["pkt"] == "12"


def test_csv_lesen_vertraegt_windows_kodierung(tmp_path: Path):
    datei = tmp_path / "t.csv"
    _csv(datei, "mannschaft\nWörnitzstein\n", "cp1252")
    assert csv_lesen(datei)[0]["mannschaft"] == "Wörnitzstein"


def test_manuelle_quelle_liest_dateien(konfiguration: Konfiguration):
    ordner = konfiguration.eingabe_ordner
    _csv(ordner / "herren1_tabelle.csv",
         "platz;mannschaft;spiele;siege;unentschieden;niederlagen;tore;gegentore;punkte\n"
         "1;Wörnitzstein;1;1;0;0;4;0;3\n2;TSV Meitingen;1;0;1;0;0;0;1\n")
    _csv(ordner / "herren1_naechstes_spiel.csv",
         "heim;gast;datum;uhrzeit;heimspiel\nSVW;TSV Meitingen;29.07.2026;18:30;ja\n")
    (ordner / "herren1_spielbericht.md").write_text("Titel\n\nAbsatz.", encoding="utf-8")

    daten = ManuelleQuelle(konfiguration).hole(konfiguration.mannschaft("herren1"))
    assert len(daten.tabelle) == 2
    assert daten.tabelle[0].eigene is True
    assert daten.naechstes_spiel.gegner == "TSV Meitingen"
    # Liga wird aus der Konfiguration ergaenzt, wenn die CSV keine enthaelt
    assert daten.naechstes_spiel.wettbewerb == "Bezirksliga Schwaben Nord"
    assert "Absatz." in daten.spielbericht
    # Fehlende Dateien -> Warnung, kein Abbruch
    assert any("torjaeger" in w for w in daten.warnungen)


def test_manuelle_quelle_ohne_dateien_meldet_klaren_fehler(
        konfiguration: Konfiguration):
    with pytest.raises(ManuelleDatenFehlenFehler) as fehler:
        ManuelleQuelle(konfiguration).hole(konfiguration.mannschaft("herren1"))
    assert "herren1_tabelle.csv" in (fehler.value.hinweis or "")


# ---------------------------------------------------------------------------
# FuPa-Hilfsfunktionen (ohne Netz)
# ---------------------------------------------------------------------------

def test_liste_finden_greift_tief_verschachtelt():
    nutzlast = {"data": {"standings": {"rows": [{"a": 1}, {"a": 2}]}}}
    assert len(_liste_finden(nutzlast)) == 2


def test_liste_finden_bei_flacher_liste():
    assert _liste_finden([{"a": 1}]) == [{"a": 1}]


def test_liste_finden_ohne_treffer():
    assert _liste_finden({"a": 1, "b": "text"}) == []


def test_text_liest_punktpfad_und_faellt_zurueck():
    eintrag = {"team": {"name": "SVW"}}
    assert _text(eintrag, "teamName", "team.name") == "SVW"
    assert _text(eintrag, "fehlt", standard="—") == "—"


def test_zahl_ignoriert_unlesbare_werte():
    assert _zahl({"x": "abc"}, "x", standard=7) == 7
    assert _zahl({"x": "12"}, "x") == 12


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def test_cache_schreibt_und_liest(tmp_path: Path):
    cache = DateiCache(tmp_path / "c", gueltigkeit_minuten=60)
    cache.schreiben("https://x/y", {"a": 1})
    assert cache.lesen("https://x/y") == {"a": 1}


def test_cache_gibt_abgelaufene_daten_nur_auf_wunsch(tmp_path: Path):
    cache = DateiCache(tmp_path / "c", gueltigkeit_minuten=0)
    cache.schreiben("k", {"a": 1})
    assert cache.lesen("k") is None
    assert cache.lesen("k", auch_veraltet=True) == {"a": 1}


def test_cache_aus_liefert_nichts(tmp_path: Path):
    cache = DateiCache(tmp_path / "c", aktiv=False)
    cache.schreiben("k", {"a": 1})
    assert cache.lesen("k") is None


# ---------------------------------------------------------------------------
# Spielplan und Gegnerkader
# ---------------------------------------------------------------------------

SPIELPLAN_KOPF = ("heim;gast;wettbewerb;datum;uhrzeit;spielort;heimspiel;"
                  "spieltag;ergebnis\n")


def _spielplan_anlegen(konfiguration: Konfiguration, zeilen: str) -> None:
    (konfiguration.eingabe_ordner / "herren1_spielplan.csv").write_text(
        SPIELPLAN_KOPF + zeilen, encoding="utf-8")
    (konfiguration.eingabe_ordner / "herren1_tabelle.csv").write_text(
        "platz;mannschaft;punkte\n1;Wörnitzstein;3\n", encoding="utf-8")


def test_spielplan_waehlt_partie_nach_datum(konfiguration: Konfiguration,
                                            monkeypatch):
    """Der Kern der Anforderung: es zaehlt das heutige Datum."""
    _spielplan_anlegen(konfiguration,
        "TG Lauingen;SVW;Bezirksliga;26.07.2026;15:00;;nein;1;0:4\n"
        "SVW;TSV Meitingen;Bezirksliga;29.07.2026;18:30;;ja;2;\n"
        "SVW;SG Alerheim;Bezirksliga;09.08.2026;15:00;;ja;3;\n")

    import stadionheft.models as modelle
    from datetime import datetime as echte_zeit

    class Heute(echte_zeit):
        @classmethod
        def now(cls, tz=None):
            return echte_zeit(2026, 8, 4, 10, 0)

    monkeypatch.setattr(modelle, "datetime", Heute)

    daten = ManuelleQuelle(konfiguration).hole(konfiguration.mannschaft("herren1"))
    assert daten.naechstes_spiel.gegner == "SG Alerheim"
    assert daten.naechstes_spiel.datum == "09.08.2026"
    assert daten.letztes_spiel.gegner == "TSV Meitingen"


def test_spielplan_ohne_kuenftige_partie_warnt(konfiguration: Konfiguration,
                                               monkeypatch):
    _spielplan_anlegen(konfiguration,
        "SVW;TSV Meitingen;Bezirksliga;29.07.2026;18:30;;ja;2;3:1\n")

    import stadionheft.models as modelle
    from datetime import datetime as echte_zeit

    class Spaeter(echte_zeit):
        @classmethod
        def now(cls, tz=None):
            return echte_zeit(2027, 1, 1)

    monkeypatch.setattr(modelle, "datetime", Spaeter)

    daten = ManuelleQuelle(konfiguration).hole(konfiguration.mannschaft("herren1"))
    assert daten.naechstes_spiel is None
    assert any("Vergangenheit" in w for w in daten.warnungen)


def test_gegnerkader_je_gegner_wird_bevorzugt(konfiguration: Konfiguration):
    _spielplan_anlegen(konfiguration,
        "SVW;SG Alerheim;Bezirksliga;31.12.2099;15:00;;ja;3;\n")
    ordner = konfiguration.eingabe_ordner
    (ordner / "herren1_gegner_spieler.csv").write_text(
        "platz;spieler\n1;Falscher Kader\n", encoding="utf-8")
    (ordner / "herren1_gegner_sg-alerheim.csv").write_text(
        "platz;spieler\n1;Richtiger Kader\n", encoding="utf-8")

    daten = ManuelleQuelle(konfiguration).hole(konfiguration.mannschaft("herren1"))
    assert daten.gegner_spieler[0].spieler == "Richtiger Kader"
    assert not any("allgemeinen Datei" in w for w in daten.warnungen)


def test_allgemeiner_gegnerkader_wird_beanstandet(konfiguration: Konfiguration):
    """Ein statischer Kader kann zum falschen Gegner gehoeren - das muss
    dem Benutzer auffallen."""
    _spielplan_anlegen(konfiguration,
        "SVW;SG Alerheim;Bezirksliga;31.12.2099;15:00;;ja;3;\n")
    (konfiguration.eingabe_ordner / "herren1_gegner_spieler.csv").write_text(
        "platz;spieler\n1;Irgendwer\n", encoding="utf-8")

    daten = ManuelleQuelle(konfiguration).hole(konfiguration.mannschaft("herren1"))
    assert daten.gegner_spieler[0].spieler == "Irgendwer"
    assert any("SG Alerheim" in w and "prüfen" in w for w in daten.warnungen)


def test_fehlender_gegnerkader_nennt_den_dateinamen(konfiguration: Konfiguration):
    _spielplan_anlegen(konfiguration,
        "SVW;SG Alerheim;Bezirksliga;31.12.2099;15:00;;ja;3;\n")
    daten = ManuelleQuelle(konfiguration).hole(konfiguration.mannschaft("herren1"))
    assert any("herren1_gegner_sg-alerheim.csv" in w for w in daten.warnungen)


def test_umlaute_im_gegnernamen():
    from stadionheft.sources.manuell import _slug
    assert _slug("Türk Gücü Lauingen") == "tuerk-guecue-lauingen"
    assert _slug("TSV Nördlingen II") == "tsv-noerdlingen-ii"
