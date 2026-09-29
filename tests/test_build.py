"""Der Lauf von der Mannschaftsauswahl bis zu den fertigen Dateien."""

from __future__ import annotations

import json
import zipfile

import pytest
from pypdf import PdfReader

from stadionheft.build import (dateien_aus_snapshot, dateien_erstellen,
                               seitenfolge)
from stadionheft.config import Konfiguration
from stadionheft.errors import StadionheftFehler
from stadionheft.models import GegnerDaten, MannschaftsDaten, TabellenZeile
from stadionheft.render.pages import STANDARD_SEITEN, LayoutWerte

A5_BREITE_PT = 419.53
A5_HOEHE_PT = 595.28


# ---------------------------------------------------------------------------
# Eine Datei je Mannschaft
# ---------------------------------------------------------------------------

def test_je_mannschaft_eine_datei(konfiguration: Konfiguration):
    ergebnis = dateien_erstellen(konfiguration, ["herren1", "damen1"])
    assert len(ergebnis.dateien) == 2
    assert {d.schluessel for d in ergebnis.dateien} == {"herren1", "damen1"}
    for datei in ergebnis.dateien:
        assert datei.pdf.exists()
        assert datei.seitenzahl == len(STANDARD_SEITEN)


def test_dateiname_nennt_datum_mannschaft_und_gegner(konfiguration: Konfiguration):
    ergebnis = dateien_erstellen(konfiguration, ["herren1"])
    name = ergebnis.dateien[0].pdf.name
    # Anstoss der Demo-Daten ist der 29.07.2026
    assert name.startswith("2026-07-29_")
    assert "Herren_1" in name
    assert "Meitingen" in name
    assert name.endswith(".pdf")


def test_alter_dateiname_ueberschreibt_nicht_alles(konfiguration: Konfiguration):
    """Eine Vorlage aus der Zeit des Gesamthefts darf keine Dateien fressen.

    `{datum_kompakt}_WaB_Druck.pdf` unterscheidet die Mannschaften nicht --
    im selben Ordner bliebe nur die letzte uebrig.
    """
    konfiguration.roh["ausgabe"]["dateiname"] = "{datum_kompakt}_WaB_Druck.pdf"
    ergebnis = dateien_erstellen(konfiguration, ["herren1", "damen1"])

    namen = [d.pdf.name for d in ergebnis.dateien]
    assert len(set(namen)) == 2, namen
    assert all(d.pdf.exists() for d in ergebnis.dateien)
    assert any("herren1" in n for n in namen)


def test_endformat_entspricht_der_vorlage(konfiguration: Konfiguration):
    ergebnis = dateien_erstellen(konfiguration, ["herren1"])
    for seite in PdfReader(str(ergebnis.dateien[0].pdf)).pages:
        assert float(seite.trimbox.width) == pytest.approx(A5_BREITE_PT, abs=1)
        assert float(seite.trimbox.height) == pytest.approx(A5_HOEHE_PT, abs=1)


def test_alle_seiten_haben_dieselbe_box(konfiguration: Konfiguration):
    """Wer die Dateien hintereinanderlegt, braucht ein einheitliches Format."""
    ergebnis = dateien_erstellen(konfiguration, ["herren1", "damen1"])
    boxen = set()
    for datei in ergebnis.dateien:
        for seite in PdfReader(str(datei.pdf)).pages:
            boxen.add((round(float(seite.mediabox.width)),
                       round(float(seite.mediabox.height))))
    assert len(boxen) == 1


def test_ohne_mannschaft_klare_meldung(konfiguration: Konfiguration):
    with pytest.raises(StadionheftFehler) as fehler:
        dateien_erstellen(konfiguration, [])
    assert "mindestens eine Mannschaft" in fehler.value.benutzer_text


# ---------------------------------------------------------------------------
# Das Archiv fuer die Uebergabe
# ---------------------------------------------------------------------------

def test_archiv_enthaelt_alle_dateien_und_eine_uebersicht(
        konfiguration: Konfiguration):
    ergebnis = dateien_erstellen(konfiguration, ["herren1", "damen1"])
    assert ergebnis.archiv and ergebnis.archiv.exists()

    with zipfile.ZipFile(ergebnis.archiv) as archiv:
        namen = archiv.namelist()
        text = archiv.read("UEBERSICHT.txt").decode("utf-8")

    assert "UEBERSICHT.txt" in namen
    for datei in ergebnis.dateien:
        assert datei.pdf.name in namen
    # Die Uebersicht muss erklaeren, was in welcher Reihenfolge drinsteht
    assert "Trennseite" in text and "Saisonbilanz" in text
    assert "Herren 1" in text


def test_alle_dateien_liegen_im_selben_ordner(konfiguration: Konfiguration):
    ergebnis = dateien_erstellen(konfiguration, ["herren1", "damen1"])
    assert ergebnis.ordner is not None
    assert {d.pdf.parent for d in ergebnis.dateien} == {ergebnis.ordner}


# ---------------------------------------------------------------------------
# Seitenfolge
# ---------------------------------------------------------------------------

def test_seitenfolge_ist_bei_allen_gleich():
    daten = MannschaftsDaten(anzeigename="Herren 1")
    assert seitenfolge(daten) == list(STANDARD_SEITEN)


def test_gegner_aus_anderer_liga_bekommt_eigene_tabelle():
    """Im Pokal spielt der Gegner woanders -- dann zaehlt seine Tabelle."""
    daten = MannschaftsDaten(
        anzeigename="Herren 1",
        tabelle=[TabellenZeile(platz=1, mannschaft="A"),
                 TabellenZeile(platz=2, mannschaft="B")],
        gegner_daten=GegnerDaten(
            name="FC Fremd",
            tabelle=[TabellenZeile(platz=1, mannschaft="X"),
                     TabellenZeile(platz=2, mannschaft="Y")],
            torjaeger=[]),
    )
    folge = seitenfolge(daten)
    assert "tabelle_gegner" in folge
    assert folge.index("tabelle_gegner") == folge.index("torjaeger") + 1


def test_gegner_aus_derselben_liga_bekommt_keine_zweite_tabelle():
    """Dieselbe Liga = dieselbe Tabelle. Zweimal waere Papierverschwendung."""
    gemeinsam = [TabellenZeile(platz=i, mannschaft=n)
                 for i, n in enumerate(["A", "B", "C", "D"], 1)]
    daten = MannschaftsDaten(anzeigename="Herren 1", tabelle=gemeinsam,
                             gegner_daten=GegnerDaten(name="B",
                                                      tabelle=list(gemeinsam)))
    assert daten.gleiche_liga is True
    assert "tabelle_gegner" not in seitenfolge(daten)


# ---------------------------------------------------------------------------
# Reproduzierbarkeit
# ---------------------------------------------------------------------------

def test_snapshot_erzeugt_dieselben_dateien(konfiguration: Konfiguration):
    erst = dateien_erstellen(konfiguration, ["herren1"], spieltag="2. Spieltag")
    assert erst.snapshot and erst.snapshot.exists()

    inhalt = json.loads(erst.snapshot.read_text(encoding="utf-8"))
    assert inhalt["spieltag"] == "2. Spieltag"
    assert inhalt["mannschaften"][0]["tabelle"][1]["mannschaft"] == "Wörnitzstein"
    assert inhalt["seitenfolge"] == list(STANDARD_SEITEN)

    erneut = dateien_aus_snapshot(konfiguration, erst.snapshot)
    assert [d.seitenzahl for d in erneut.dateien] == \
           [d.seitenzahl for d in erst.dateien]
    assert [d.pdf.name for d in erneut.dateien] == \
           [d.pdf.name for d in erst.dateien]


def test_snapshot_haelt_den_gegner_fest(konfiguration: Konfiguration):
    ergebnis = dateien_erstellen(konfiguration, ["herren1"])
    inhalt = json.loads(ergebnis.snapshot.read_text(encoding="utf-8"))
    gegner = inhalt["mannschaften"][0]["gegner_daten"]
    assert gegner["name"] == "TSV Meitingen"
    assert gegner["spieler"]


# ---------------------------------------------------------------------------
# Datenquellen und Rueckfall
# ---------------------------------------------------------------------------

def test_fallback_auf_ersatzquelle(konfiguration: Konfiguration):
    """Faellt die primaere Quelle aus, wird auf die Ersatzquelle umgeschaltet."""
    konfiguration.roh["datenquelle"]["fallback_modus"] = "demo"
    konfiguration.eingabe_ordner.mkdir(parents=True, exist_ok=True)
    # 'manuell' scheitert (keine Dateien) -> Ersatz 'demo' greift
    ergebnis = dateien_erstellen(konfiguration, ["herren1"], datenquelle="manuell")
    assert ergebnis.verwendete_quelle == "demo"
    assert any("umgeschaltet" in w for w in ergebnis.warnungen)


def test_leere_antwort_gilt_als_ausfall(konfiguration: Konfiguration, monkeypatch):
    """Eine Quelle, die zwar antwortet, aber nichts liefert, ist auch ein Ausfall.

    Sonst entstuenden Dateien mit lauter leeren Statistikseiten -- und das
    faellt erst beim Druck auf.
    """
    from stadionheft.sources.base import basis_daten, quelle_erzeugen

    class LeereQuelle:
        name = "api"

        def __init__(self, konfiguration):
            pass

        def hole(self, mannschaft):
            return basis_daten(mannschaft, "api")

    def ersatz(modus, k):
        return LeereQuelle(k) if modus == "api" else quelle_erzeugen(modus, k)

    monkeypatch.setattr("stadionheft.build.quelle_erzeugen", ersatz)
    konfiguration.roh["datenquelle"]["fallback_modus"] = "demo"

    ergebnis = dateien_erstellen(konfiguration, ["herren1"], datenquelle="api")
    assert ergebnis.verwendete_quelle == "demo"
    assert any("keine verwertbaren Daten" in w for w in ergebnis.warnungen)


def test_frisch_schaltet_den_zwischenspeicher_ab(konfiguration: Konfiguration):
    dateien_erstellen(konfiguration, ["herren1"], frisch=True)
    assert konfiguration.get("datenquelle.cache.aktiv") is False


# ---------------------------------------------------------------------------
# Rendering-Details
# ---------------------------------------------------------------------------

def test_schriftliste_wird_korrekt_gequotet():
    layout = LayoutWerte(schriftfamilie="Segoe UI, Source Sans 3, sans-serif")
    assert str(layout.schrift_css) == '"Segoe UI", "Source Sans 3", sans-serif'


def test_schriftliste_wehrt_ausbruch_ab():
    layout = LayoutWerte(schriftfamilie="A} body{display:none")
    assert "}" not in str(layout.schrift_css)
    assert "{" not in str(layout.schrift_css)
