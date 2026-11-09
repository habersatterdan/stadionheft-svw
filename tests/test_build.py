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
from stadionheft.models import GegnerDaten, MannschaftsDaten, Spiel, TabellenZeile
from stadionheft.render.pages import POKAL_SEITEN, STANDARD_SEITEN, LayoutWerte

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
    assert "Trennseite" in text and "Der Gegner" in text
    assert "Saisonbilanz" not in text
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


POKAL = "Frauen-Bezirkspokal Schwaben"
LIGA = "Frauen-Bezirksliga Nord"


def _pokaldaten() -> MannschaftsDaten:
    """Damen 1 am 26.10.2026: Viertelfinale gegen einen Gegner aus der
    Bezirksoberliga -- Ligaspiele und ein anderer Pokal dazwischen."""
    naechstes = Spiel(heim="SVW", gast="TSV Nördlingen", wettbewerb=POKAL,
                      spieltag="Viertelfinale", anstoss="2026-10-31T16:00:00")
    return MannschaftsDaten(
        anzeigename="Damen 1", liga=LIGA,
        tabelle=[TabellenZeile(platz=1, mannschaft="SVW"),
                 TabellenZeile(platz=2, mannschaft="B")],
        torjaeger=[],
        spiele=[
            Spiel(heim="SVW", gast="Maihingen", wettbewerb=POKAL, spieltag="1. Runde",
                  anstoss="2026-08-29T16:00:00", ergebnis="2:0"),
            Spiel(heim="Maihingen", gast="SVW", wettbewerb=LIGA, heimspiel=False,
                  anstoss="2026-09-12T16:00:00", ergebnis="0:2"),
            Spiel(heim="Bissingen", gast="SVW", wettbewerb=POKAL, heimspiel=False,
                  spieltag="2. Runde", anstoss="2026-10-03T16:00:00",
                  ergebnis="1:2"),
            Spiel(heim="SVW", gast="X", wettbewerb="Kreispokal", spieltag="1. Runde",
                  anstoss="2026-07-20T18:00:00", ergebnis="0:3"),
            naechstes,
        ],
        naechstes_spiel=naechstes,
        gegner_daten=GegnerDaten(
            name="TSV Nördlingen",
            tabelle=[TabellenZeile(platz=1, mannschaft="X"),
                     TabellenZeile(platz=2, mannschaft="Y")],
            spiele=[
                Spiel(heim="Wechingen", gast="TSV Nördlingen", wettbewerb=POKAL,
                      heimspiel=False, spieltag="2. Runde",
                      anstoss="2026-10-04T15:00:00", ergebnis="5:6"),
                Spiel(heim="TSV Nördlingen", gast="FC Augsburg",
                      wettbewerb="Frauen-Bezirksoberliga Schwaben",
                      anstoss="2026-10-24T15:00:00", ergebnis="1:1"),
            ]),
    )


def test_pokalspiel_ohne_liga_nur_pokalergebnisse():
    """Pokal: weder die eigene Liga noch die des Gegners -- nur der Pokalweg."""
    daten = _pokaldaten()
    assert daten.pokalspiel is True
    folge = seitenfolge(daten)
    assert folge == list(POKAL_SEITEN)
    for liga_seite in ("tabelle", "torjaeger", "tabelle_gegner", "torjaeger_gegner"):
        assert liga_seite not in folge


def test_pokalweg_nur_derselbe_wettbewerb():
    daten = _pokaldaten()
    assert [s.spieltag for s in daten.pokalweg] == ["1. Runde", "2. Runde"]
    assert [s.ergebnis for s in daten.pokalweg_gegner] == ["5:6"]
    assert daten.pokalweg_gegner[0].ausgang == "S"


def test_pokalseiten_ohne_liganamen(konfiguration: Konfiguration, tmp_path):
    from stadionheft.render.pages import SeitenRenderer
    renderer = SeitenRenderer(konfiguration, tmp_path)
    daten = _pokaldaten()
    texte = {}
    for nr, art in enumerate(seitenfolge(daten), 1):
        reader = PdfReader(str(renderer.mannschaftsseite(art, daten, nr)))
        assert len(reader.pages) == 1, art
        texte[art] = " ".join(reader.pages[0].extract_text().split())
        assert LIGA not in texte[art], art
    assert "Viertelfinale" in texte["trenner"]
    assert "2. Runde" in texte["pokalweg"] and "5:6" in texte["pokalweg"]
    assert "Tabellenplatz" not in texte["vergleich"]


def test_ligaspiel_bleibt_wie_bisher():
    daten = _pokaldaten()
    daten.naechstes_spiel = Spiel(heim="SVW", gast="B", wettbewerb=LIGA,
                                  anstoss="2026-11-07T16:00:00")
    assert daten.pokalspiel is False
    assert daten.pokalweg == []
    assert "tabelle" in seitenfolge(daten)


# ---------------------------------------------------------------------------
# Spielfreie Mannschaft
# ---------------------------------------------------------------------------

def _ausgabe_mit_spielfrei():
    from stadionheft.models import Ausgabe
    h1 = MannschaftsDaten(anzeigename="Herren 1", schluessel="h1", liga=LIGA,
                          naechstes_spiel=Spiel(heim="SVW", gast="A", heimspiel=True,
                                                anstoss="2026-10-31T14:00:00"))
    h2 = MannschaftsDaten(anzeigename="Herren 2", schluessel="h2", liga=LIGA,
                          tabelle=[TabellenZeile(platz=3, mannschaft="Herren 2", punkte=9)],
                          naechstes_spiel=Spiel(heim="SVW II", gast="B", heimspiel=True,
                                                anstoss="2026-11-08T12:30:00"))
    d1 = MannschaftsDaten(anzeigename="Damen 1", schluessel="d1", liga=LIGA,
                          naechstes_spiel=Spiel(heim="C", gast="SVW", heimspiel=False,
                                                anstoss="2026-11-01T16:00:00"))
    return Ausgabe(mannschaften=[h1, h2, d1])


def test_spielfrei_erkannt_ab_grenze():
    from stadionheft.models import spielfreie_markieren
    ausgabe = _ausgabe_mit_spielfrei()
    frei = spielfreie_markieren(ausgabe, tage=4)
    assert [m.anzeigename for m in frei] == ["Herren 2"]
    h2 = ausgabe.mannschaften[1]
    assert h2.heftspiel is None and h2.gegner == "" and h2.pokalspiel is False
    # Grosszuegige Grenze: dann spielt auch Herren 2 "an diesem Wochenende".
    assert spielfreie_markieren(ausgabe, tage=10) == []


def test_spielfrei_nicht_auf_deckblatt_und_kopfdatum():
    from stadionheft.models import spielfreie_markieren
    from stadionheft.render.pages import deckblatt_spieltage, kopfdatum
    ausgabe = _ausgabe_mit_spielfrei()
    spielfreie_markieren(ausgabe)
    assert kopfdatum(ausgabe) == "31.10.–01.11.2026"
    paarungen = [s["paarung"] for t in deckblatt_spieltage(ausgabe) for s in t["spiele"]]
    assert paarungen == ["Herren 1 – A"]


def test_spielfrei_seiten(konfiguration: Konfiguration, tmp_path):
    from stadionheft.models import spielfreie_markieren
    from stadionheft.render.pages import SPIELFREI_SEITEN, SeitenRenderer
    ausgabe = _ausgabe_mit_spielfrei()
    spielfreie_markieren(ausgabe)
    h2, d1 = ausgabe.mannschaften[1], ausgabe.mannschaften[2]
    assert seitenfolge(h2) == list(SPIELFREI_SEITEN)
    assert "tabelle" not in seitenfolge(MannschaftsDaten(spielfrei=True))
    assert "vergleich" in seitenfolge(d1)
    renderer = SeitenRenderer(konfiguration, tmp_path)
    reader = PdfReader(str(renderer.mannschaftsseite("spielfrei", h2, 2)))
    assert len(reader.pages) == 1
    text = " ".join(reader.pages[0].extract_text().split())
    assert "spielfrei" in text and "08.11.2026" in text and "3. Platz" in text


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


def test_eine_mannschaft_ohne_daten_haelt_den_lauf_nicht_auf(
        konfiguration: Konfiguration):
    """Der haeufigste Fall im Alltag: Noch nicht alle Mannschaften gepflegt.

    Aus dem Bericht vom 30.09.2026: Fuer Herren 1 lagen alle CSV-Dateien vor,
    fuer die uebrigen vier noch keine -- und der komplette Lauf brach ab. Am
    Ende gab es keine einzige Datei, obwohl eine haette entstehen koennen.
    """
    from stadionheft.tools.beispieldaten import vorlagen_schreiben

    konfiguration.roh["datenquelle"]["fallback_modus"] = ""
    vorlagen_schreiben(konfiguration, nur_vorlagen=False)
    for datei in konfiguration.eingabe_ordner.glob("damen1_*.csv"):
        datei.unlink()

    ergebnis = dateien_erstellen(konfiguration, ["herren1", "damen1"],
                                 datenquelle="manuell")

    assert [d.schluessel for d in ergebnis.dateien] == ["herren1"]
    assert ergebnis.dateien[0].pdf.exists()
    assert any("Damen 1" in w for w in ergebnis.warnungen), ergebnis.warnungen


def test_ohne_daten_fuer_alle_bleibt_es_ein_fehler(konfiguration: Konfiguration):
    """Wenn gar nichts geht, muss es auch gesagt werden -- nicht nur gewarnt."""
    konfiguration.roh["datenquelle"]["fallback_modus"] = ""
    konfiguration.eingabe_ordner.mkdir(parents=True, exist_ok=True)

    with pytest.raises(StadionheftFehler):
        dateien_erstellen(konfiguration, ["herren1", "damen1"],
                          datenquelle="manuell")


def test_ersatzquelle_gewinnt_nur_wenn_sie_mehr_liefert(
        konfiguration: Konfiguration):
    """Die Ersatzquelle darf das bessere Ergebnis nicht verdraengen.

    'manuell' kennt hier nur Herren 1. Waere der Wechsel bedingungslos, kaeme
    aus einer vollstaendigen Demo-Antwort eine einzige Datei statt zweien.
    """
    from stadionheft.tools.beispieldaten import vorlagen_schreiben

    konfiguration.roh["datenquelle"]["fallback_modus"] = "manuell"
    vorlagen_schreiben(konfiguration, nur_vorlagen=False)
    for datei in konfiguration.eingabe_ordner.glob("damen1_*.csv"):
        datei.unlink()

    ergebnis = dateien_erstellen(konfiguration, ["herren1", "damen1"],
                                 datenquelle="demo")

    assert ergebnis.verwendete_quelle == "demo"
    assert len(ergebnis.dateien) == 2


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


def test_kein_todo_platzhalter_im_pdf(konfiguration: Konfiguration):
    """'TODO: Liga eintragen' darf nicht in den Druck gehen.

    Genau das stand am 30.09.2026 auf den Trennseiten von vier der fuenf
    Mannschaftsdateien.
    """
    konfiguration.roh["mannschaften"]["damen1"]["liga"] = "TODO: Liga eintragen"

    ergebnis = dateien_erstellen(konfiguration, ["damen1"])

    text = " ".join(s.extract_text()
                    for s in PdfReader(str(ergebnis.dateien[0].pdf)).pages)
    assert "TODO" not in text


def test_spielerstatistik_nach_einsaetzen_und_minuten_hoechstens_22():
    from stadionheft.models import SpielerZeile
    from stadionheft.render.pages import spieler_rangfolge

    kader = [SpielerZeile(platz=nr, spieler=f"S{nr}", spiele=nr % 5,
                          minuten=nr * 10) for nr in range(1, 31)]
    gedruckt = spieler_rangfolge(kader)

    assert len(gedruckt) == 22
    assert [z.platz for z in gedruckt] == list(range(1, 23))
    reihenfolge = [(z.spiele, z.minuten) for z in gedruckt]
    assert reihenfolge == sorted(reihenfolge, reverse=True)
    # Die Daten selbst (Snapshot) bleiben, wie sie waren
    assert [z.platz for z in kader] == list(range(1, 31))


def test_saisonbilanz_ist_keine_seite_mehr():
    assert "bilanz" not in STANDARD_SEITEN


def test_ohne_balken_nur_der_inhalt(konfiguration: Konfiguration):
    """Wunsch der Layouterin: Kopf-/Fussbalken stehen schon in ihrer Datei."""
    mit = dateien_erstellen(konfiguration, ["herren1"]).dateien[0]
    seite = STANDARD_SEITEN.index("spielerstatistik")
    text_mit = PdfReader(str(mit.pdf)).pages[seite].extract_text()
    assert "Wörnitzstein am Ball" in text_mit and "Spielerstatistik" in text_mit

    konfiguration.roh["layout"]["balken"] = False
    ohne = dateien_erstellen(konfiguration, ["herren1"]).dateien[0]
    leser = PdfReader(str(ohne.pdf))
    text_ohne = leser.pages[seite].extract_text()
    assert "Wörnitzstein am Ball" not in text_ohne
    assert "Spielerstatistik" not in text_ohne
    # Der Inhalt selbst ist noch da, Seitenzahl und Format unveraendert
    assert "Spieler" in text_ohne
    assert len(leser.pages) == mit.seitenzahl
    assert leser.pages[seite].mediabox == PdfReader(str(mit.pdf)).pages[seite].mediabox
