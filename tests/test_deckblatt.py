"""Deckblatt: Titelbild, Heimspiele der Ausgabe, Ansprechpartner."""

from __future__ import annotations

import zipfile

from pypdf import PdfReader

from stadionheft.build import dateien_erstellen
from stadionheft.config import Konfiguration
from stadionheft.models import Ausgabe, MannschaftsDaten, Spiel
from stadionheft.render.pages import deckblatt_spieltage, kopfdatum


def _mannschaft(name: str, anstoss: str, heim: bool, gegner: str,
                liga: str = "Kreisklasse") -> MannschaftsDaten:
    spiel = Spiel(heim="SV Wörnitzstein-Berg" if heim else gegner,
                  gast=gegner if heim else "SV Wörnitzstein-Berg",
                  anstoss=anstoss, heimspiel=heim, wettbewerb=liga)
    return MannschaftsDaten(schluessel=name.lower().replace(" ", ""),
                            anzeigename=name, naechstes_spiel=spiel)


AUSGABE = Ausgabe(mannschaften=[
    _mannschaft("Herren 2", "2026-10-18T15:00:00", False, "FC Mertingen"),
    _mannschaft("Damen 1", "2026-10-17T17:00:00", True, "SpVgg Joshofen-Bergheim"),
    _mannschaft("Herren 1", "2026-10-16T19:00:00", True, "TSV Hollenbach",
                "Bezirksliga Schwaben Nord"),
    _mannschaft("Damen 2", "2026-10-17T15:00:00", True, "SG Alerheim / Wechingen"),
])


def test_nur_heimspiele_nach_tagen_und_uhrzeit():
    tage = deckblatt_spieltage(AUSGABE, "SVW")
    assert [t["wochentag"] for t in tage] == ["Freitag", "Samstag"]
    assert [s["paarung"] for s in tage[0]["spiele"]] == [
        "SVW Herren 1 – TSV Hollenbach"]
    # Samstag: Damen 2 (15 Uhr) vor Damen 1 (17 Uhr), Herren 2 auswaerts fehlt
    assert [s["paarung"] for s in tage[1]["spiele"]] == [
        "SVW Damen 2 – SG Alerheim / Wechingen",
        "SVW Damen 1 – SpVgg Joshofen-Bergheim"]
    assert tage[0]["spiele"][0]["wettbewerb"] == "Bezirksliga Schwaben Nord"
    assert tage[0]["spiele"][0]["uhrzeit"] == "19:00 Uhr"


def test_nur_auswaertsspiele_ergibt_leeren_kasten():
    ausgabe = Ausgabe(mannschaften=[
        _mannschaft("Herren 2", "2026-10-18T15:00:00", False, "FC Mertingen")])
    assert deckblatt_spieltage(ausgabe) == []


def test_kopfdatum():
    assert kopfdatum(AUSGABE) == "16.–18.10.2026"
    ein_tag = Ausgabe(mannschaften=[AUSGABE.mannschaften[2]])
    assert kopfdatum(ein_tag) == "Freitag 16.10.2026"
    ueber_monat = Ausgabe(mannschaften=[
        _mannschaft("A", "2026-10-31T15:00:00", True, "X"),
        _mannschaft("B", "2026-11-01T15:00:00", True, "Y")])
    assert kopfdatum(ueber_monat) == "31.10.–01.11.2026"
    assert kopfdatum(Ausgabe()) == ""


def test_deckblatt_als_erste_datei_mit_ansprechpartnern(konfiguration: Konfiguration):
    konfiguration.roh["deckblatt"]["aktiv"] = True
    konfiguration.roh["deckblatt"]["ansprechpartner"] = [
        {"funktion": "Vorstand", "name": "Erika Muster",
         "kontakt": "0123 / 4567 • vorstand@example.org"},
        {"funktion": "", "name": "ohne Funktion faellt weg", "kontakt": ""},
    ]
    ergebnis = dateien_erstellen(konfiguration, ["herren1", "damen1"])

    deckblatt = ergebnis.dateien[0]
    assert deckblatt.schluessel == "" and deckblatt.anzeigename == "Deckblatt"
    assert deckblatt.pdf.name.endswith("_Deckblatt.pdf")
    assert deckblatt.seitenzahl == 2
    leser = PdfReader(str(deckblatt.pdf))
    assert "Wir begrüßen unsere Gäste" in leser.pages[0].extract_text()
    zweite = leser.pages[1].extract_text()
    assert "Erika Muster" in zweite and "ohne Funktion" not in zweite
    # Ohne Titelbild: Platzhalter und ein Hinweis
    assert any("Titelbild" in w for w in ergebnis.warnungen)
    # Die Mannschaftsdateien bleiben unveraendert dahinter
    assert [d.schluessel for d in ergebnis.dateien[1:]] == ["herren1", "damen1"]
    with zipfile.ZipFile(ergebnis.archiv) as archiv:
        assert deckblatt.pdf.name in archiv.namelist()


def test_titelbild_aus_dem_eingabeordner(konfiguration: Konfiguration):
    from PIL import Image

    konfiguration.roh["deckblatt"]["aktiv"] = True
    Image.new("RGB", (40, 30), (0, 120, 0)).save(
        konfiguration.eingabe_ordner / "Titelbild.JPEG", "JPEG")
    ergebnis = dateien_erstellen(konfiguration, ["herren1"])
    assert not any("Titelbild" in w for w in ergebnis.warnungen)
    assert ergebnis.dateien[0].pdf.exists()


def test_ohne_ansprechpartner_nur_titelseite(konfiguration: Konfiguration):
    konfiguration.roh["deckblatt"]["aktiv"] = True
    konfiguration.roh["deckblatt"]["ansprechpartner"] = []
    ergebnis = dateien_erstellen(konfiguration, ["herren1"])
    assert ergebnis.dateien[0].seitenzahl == 1


def test_filestation_legt_nicht_automatisch_ab(konfiguration: Konfiguration,
                                              monkeypatch):
    """Die File-Station-Ablage laeuft nur auf Knopfdruck -- nie im Lauf."""
    from stadionheft import build

    konfiguration.roh["nas"]["aktiv"] = True
    konfiguration.roh["nas"]["modus"] = "filestation"

    def verboten(*_a, **_k):
        raise AssertionError("NAS-Ablage im Lauf aufgerufen")

    monkeypatch.setattr(build.NasAblage, "ablegen_mehrere", verboten)
    ergebnis = dateien_erstellen(konfiguration, ["herren1"])
    assert ergebnis.nas_ziel == ""


def test_mehrseitiger_text_bleibt_zwischen_den_balken(konfiguration: Konfiguration,
                                                      tmp_path):
    """Gesehen 15.10.2026 im Vorwort: Text lief in den Fussbalken und begann
    auf der Folgeseite ueber dem Kopfbalken."""
    from stadionheft.render.pages import SeitenRenderer

    renderer = SeitenRenderer(konfiguration, tmp_path)
    text = "\n\n".join(f"Absatz {i}: " + "Lorem ipsum dolor sit amet. " * 20
                       for i in range(20))
    leser = PdfReader(str(renderer.freitextseite("Vorwort", text, "probe")))
    assert len(leser.pages) >= 2
    mm = 72 / 25.4
    for seite in leser.pages:
        hoehe = float(seite.mediabox.height)
        hoehen: list[tuple[str, float]] = []

        def merken(text, cm, tm, _font, _size):
            if text.strip():
                # Textposition (tm) mit der Seitentransformation (cm) verrechnet
                y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                hoehen.append((text.strip(), y))

        seite.extract_text(visitor_text=merken)
        inhalt = [y for t, y in hoehen
                  if t not in ("Vorwort", "Wörnitzstein am Ball")]
        assert inhalt
        # unter dem Kopfbereich (44 mm + 3 mm Anschnitt) und ueber dem Fussbalken
        assert max(inhalt) <= hoehe - 44 * mm
        assert min(inhalt) >= 20 * mm
        assert any(t == "Vorwort" for t, _ in hoehen)


def test_hochgeladenes_titelbild_hat_vorrang_vor_der_nas(
        konfiguration: Konfiguration, tmp_path, monkeypatch):
    from PIL import Image

    from stadionheft.storage import filestation

    konfiguration.roh["deckblatt"]["aktiv"] = True
    konfiguration.roh["nas"].update({"aktiv": True, "modus": "filestation"})

    def nicht_fragen(*_a, **_k):
        raise AssertionError("Vorlage-Titelbild darf nicht geholt werden")

    monkeypatch.setattr(filestation, "titelbild_holen", nicht_fragen)
    monkeypatch.setattr(filestation, "ansprechpartner_von_nas", lambda *_a: None)
    bild = tmp_path / "Titelbild.png"
    Image.new("RGB", (40, 30), (200, 0, 0)).save(bild)

    ergebnis = dateien_erstellen(konfiguration, ["herren1"], titelbild=bild)
    deckblatt = ergebnis.dateien[0]
    assert deckblatt.anzeigename == "Deckblatt"
    assert not any("Kein Titelbild" in w for w in deckblatt.warnungen)
