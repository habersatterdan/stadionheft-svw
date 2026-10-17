"""Gesamtes Heft aus einem Ausgabe-Ordner -- gegen eine NAS im Speicher."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from stadionheft.build import dateien_erstellen
from stadionheft.config import Konfiguration
from stadionheft.errors import NasFehler
from stadionheft.gesamtheft import (Baustein, gesamtheft_bauen, plan_als_text,
                                    plan_erstellen, plan_lesen)
from stadionheft.storage.filestation import (ansprechpartner_lesen,
                                             ansprechpartner_schreiben,
                                             saison_anlegen, vorherige_saison)

SAISON = "/SVW/Stadionheft/Saison 26-27"


def _pdf(seiten: int = 1) -> bytes:
    schreiber = PdfWriter()
    for _ in range(seiten):
        schreiber.add_blank_page(width=420, height=595)
    puffer = io.BytesIO()
    schreiber.write(puffer)
    return puffer.getvalue()


def _bild() -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", (60, 40), (200, 0, 0)).save(puffer, "JPEG")
    return puffer.getvalue()


class SpeicherNas:
    """Ordner als Pfad -> {Name: bytes oder None (Ordner)}."""

    def __init__(self) -> None:
        self.baum: dict[str, dict[str, bytes | None]] = {"/SVW/Stadionheft": {}}
        self.geladen: list[str] = []
        self.hochgeladen: list[str] = []

    def ordner(self, pfad: str) -> None:
        if pfad in self.baum:
            return
        eltern, name = pfad.rsplit("/", 1)
        self.ordner(eltern)
        self.baum[eltern][name] = None
        self.baum[pfad] = {}

    def datei(self, pfad: str, inhalt: bytes) -> None:
        eltern, name = pfad.rsplit("/", 1)
        self.ordner(eltern)
        self.baum[eltern][name] = inhalt

    def auflisten(self, pfad: str) -> list[dict]:
        if pfad not in self.baum:
            from stadionheft.storage.filestation import FileStationFehler
            raise FileStationFehler("408", code=408)
        return [{"name": n, "path": f"{pfad}/{n}", "isdir": v is None,
                 "additional": {"size": len(v) if v is not None else 0,
                                "time": {"mtime": 1}}}
                for n, v in self.baum[pfad].items()]

    def herunterladen(self, pfad: str, ziel: Path) -> Path:
        eltern, name = pfad.rsplit("/", 1)
        self.geladen.append(pfad)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(self.baum[eltern][name])
        return ziel

    def hochladen(self, datei: Path, ordner: str, name: str = "") -> None:
        self.hochgeladen.append(f"{ordner}/{name or datei.name}")
        self.datei(f"{ordner}/{name or datei.name}", datei.read_bytes())

    def ordner_anlegen(self, eltern: str, name: str) -> str:
        self.ordner(f"{eltern}/{name}")
        return f"{eltern}/{name}"

    def kopieren(self, pfade: list[str], ziel: str) -> None:
        for quelle in pfade:
            name = quelle.rsplit("/", 1)[1]
            if quelle in self.baum:
                self.ordner(f"{ziel}/{name}")
                for kind, inhalt in list(self.baum[quelle].items()):
                    if inhalt is not None:
                        self.datei(f"{ziel}/{name}/{kind}", inhalt)
            else:
                eltern = quelle.rsplit("/", 1)[0]
                self.datei(f"{ziel}/{name}", self.baum[eltern][name])


@pytest.fixture
def heft_konfiguration(konfiguration: Konfiguration) -> Konfiguration:
    konfiguration.roh["saison"] = "2026/2027"
    konfiguration.roh["nas"].update({"aktiv": True, "modus": "filestation"})
    konfiguration.roh["nas"]["filestation"].update({
        "quickconnect_id": "test",
        "saison_ordner": "/SVW/Stadionheft/Saison {saison_kurz}",
        "vorlage_ordner": "00 Vorlage",
        "mannschaftsordner": {"herren1": "Herren 1", "damen1": "Damen1"}})
    konfiguration.roh["heft"].update({"gesamt_aktiv": True})
    return konfiguration


@pytest.fixture
def nas(heft_konfiguration: Konfiguration) -> SpeicherNas:
    """Ein Ausgabe-Ordner, wie ihn Knopf 1 anlegt -- plus Handarbeit."""
    heft_konfiguration.roh["deckblatt"]["aktiv"] = True
    lauf = dateien_erstellen(heft_konfiguration, ["herren1", "damen1"])
    ausgabe = f"{SAISON}/09 Ausgabe 290726"
    speicher = SpeicherNas()
    speicher.datei(f"{SAISON}/00 Vorlage/Titelbild.jpeg", _bild())
    # Das "schwarze Zwischenbild" der Mannschaft liegt in der Vorlage ...
    speicher.datei(f"{SAISON}/00 Vorlage/Herren 1/Liga.jpeg", _bild())
    speicher.datei(f"{ausgabe}/_daten/{lauf.snapshot.name}", lauf.snapshot.read_bytes())
    for d in lauf.dateien:
        unter = {"herren1": "Herren 1", "damen1": "Damen1"}.get(d.schluessel, "")
        speicher.datei(f"{ausgabe}/{unter + '/' if unter else ''}{d.pdf.name}",
                       d.pdf.read_bytes())
    speicher.datei(f"{ausgabe}/Titelbild.jpg", _bild())
    speicher.datei(f"{ausgabe}/Vorwort.txt",
                   "Liebe Fans,\n\nwillkommen zum Heimspiel.".encode())
    speicher.datei(f"{ausgabe}/Herren 1/Liga.jpeg", _bild())
    speicher.datei(f"{ausgabe}/Herren 1/Bericht.pdf", _pdf(2))
    speicher.datei(f"{ausgabe}/Herren 1/H1-Alles.odoc", b"odoc")
    speicher.datei(f"{ausgabe}/Damen1/Vorwort Trainer.docx", b"docx")
    speicher.datei(f"{ausgabe}/Jugend/Jugend.pdf", _pdf(1))
    speicher.datei(f"{ausgabe}/Jugend/@eaDir", b"x")      # Synology-Rest
    speicher.datei(f"{SAISON}/Allgemein/Werbung/A_Axa.pdf", _pdf(1))
    speicher.datei(f"{SAISON}/Allgemein/Werbung/B_Baecker.jpg", _bild())
    speicher.datei(f"{SAISON}/Allgemein/Werbung/Z_Rueckseite.pdf", _pdf(1))
    speicher.datei(f"{SAISON}/Allgemein/Ansprechpartner.txt", ansprechpartner_schreiben(
        [{"funktion": "Kassier", "name": "Erika Muster", "kontakt": "0123"}]).encode())
    return speicher


def _b(art: str, seiten: int, wert: str = "") -> Baustein:
    return Baustein(art, wert or f"{art}{seiten}", seiten=seiten)


def test_plan_verteilt_werbung_und_fuellt_auf_vier():
    vorne = [_b("deckblatt", 1), _b("vorwort", 1)]
    teams = [[_b("fupa", 6, "h1")], [_b("fupa", 6, "h2")], [_b("fupa", 6, "d1")]]
    hinten = [_b("ansprechpartner", 1)]
    werbung = [_b("werbung", 1, f"w{i}") for i in range(4)]
    plan = plan_erstellen(teams, vorne, hinten, werbung)
    assert sum(b.seiten for b in plan) % 4 == 0
    assert [b.art for b in plan[:2]] == ["deckblatt", "vorwort"]
    assert plan[-1].wert == "w3"                       # Rueckseite
    assert plan[-2].art == "leerseite"                 # Fueller vor der Rueckseite
    # Drei Anzeigen auf vier Luecken verteilt, nie zwei Mannschaften ohne
    # Anzeige dazwischen, wenn es genug gibt
    reihe = [b.wert for b in plan if b.art in ("fupa", "werbung", "ansprechpartner")]
    assert reihe.index("w0") < reihe.index("h1") or reihe.index("w0") < reihe.index("h2")
    assert {"w0", "w1", "w2"} <= set(reihe)


def test_plan_ohne_werbung_fuellt_hinten_auf():
    plan = plan_erstellen([[_b("fupa", 6, "h1")]], [_b("deckblatt", 1)], [], [])
    assert sum(b.seiten for b in plan) == 8
    assert [b.art for b in plan[-1:]] == ["leerseite"]


def test_heftplan_hin_und_zurueck():
    plan = [Baustein("deckblatt", seiten=1), Baustein("fupa", "herren1", seiten=6),
            Baustein("datei", "Herren 1/Bericht.pdf", seiten=2),
            Baustein("werbung", "Axa.pdf", seiten=1), Baustein("leerseite", seiten=1)]
    text = plan_als_text(plan, "09 Ausgabe")
    assert "# S. 2-7" in text and "Gesamt: 11 Seiten" in text
    gelesen, warnungen = plan_lesen(text + "\n[Quatsch] x\n")
    assert [(b.art, b.wert) for b in gelesen] == [(b.art, b.wert) for b in plan]
    assert len(warnungen) == 1 and "Quatsch" in warnungen[0]


def test_ansprechpartner_datei():
    eintraege = ansprechpartner_lesen(
        "# Kommentar\r\nKassier: Leinauer Dieter\r\n0906-23102 • kassier@x\r\n\r\n"
        "Trainer Damen II: Neubauer Anja\n 2.damen@x\n")
    assert eintraege == [
        {"funktion": "Kassier", "name": "Leinauer Dieter",
         "kontakt": "0906-23102 • kassier@x"},
        {"funktion": "Trainer Damen II", "name": "Neubauer Anja", "kontakt": "2.damen@x"}]


def test_saison_platzhalter(heft_konfiguration: Konfiguration):
    assert heft_konfiguration.nas_saison_ordner == SAISON
    heft_konfiguration.roh["saison"] = "2027/2028"
    assert heft_konfiguration.nas_saison_ordner == "/SVW/Stadionheft/Saison 27-28"
    assert heft_konfiguration.mit_saison("team/x-m1-{saison_slug}") == "team/x-m1-2027-28"
    assert heft_konfiguration.mit_saison("{andere} bleibt") == "{andere} bleibt"


def _zeilen(ergebnis) -> list[str]:
    return [z.split("#")[0].strip() for z in ergebnis.plan.splitlines()
            if z.startswith("[")]


def test_gesamtes_heft(heft_konfiguration: Konfiguration, nas: SpeicherNas):
    ergebnis = gesamtheft_bauen(heft_konfiguration, "09 Ausgabe 290726", fs=nas)

    leser = PdfReader(str(ergebnis.pdf))
    assert ergebnis.seitenzahl == len(leser.pages)
    assert ergebnis.seitenzahl % 4 == 0
    zeilen = _zeilen(ergebnis)
    assert zeilen[:2] == ["[Deckblatt]", "[Vorwort] Vorwort.txt"]
    # Je Mannschaft: Trenner, ihre Dateien, dann die FuPa-Seiten
    h1 = [zeilen.index(z) for z in ("[Trenner] herren1", "[Datei] Herren 1/Bericht.pdf",
                                    "[FuPa] herren1")]
    assert h1 == sorted(h1)
    assert zeilen.index("[FuPa] herren1") < zeilen.index("[Trenner] damen1") \
        < zeilen.index("[FuPa] damen1") < zeilen.index("[Datei] Jugend/Jugend.pdf")
    # ... das Zwischenbild aus der Vorlage steht nicht noch einmal als Datei drin
    assert "[Datei] Herren 1/Liga.jpeg" not in zeilen
    # Die Datei ohne Balken aus Knopf 1 wird durch die FuPa-Seiten ersetzt
    assert not any("_gegen_" in z for z in zeilen)
    assert zeilen[-1] == "[Werbung] Z_Rueckseite.pdf"
    assert "[Kontaktliste] Allgemein/Ansprechpartner.txt" in zeilen
    # Nicht Lesbares wird gemeldet, nicht verschluckt -- und kostet nicht das Heft
    assert any("H1-Alles.odoc" in w for w in ergebnis.warnungen)
    assert any("Vorwort Trainer.docx" in w and "nicht lesbar" in w
               for w in ergebnis.warnungen)
    assert not any("@eaDir" in z for z in zeilen + ergebnis.warnungen)
    # Titelbild aus dem Ausgabe-Ordner, Zwischenbild aus der Vorlage
    assert f"{SAISON}/09 Ausgabe 290726/Titelbild.jpg" in nas.geladen
    assert f"{SAISON}/00 Vorlage/Herren 1/Liga.jpeg" in nas.geladen
    # Mit Balken (die Mannschaftsdateien fuers Layout sind ohne)
    assert any("Wörnitzstein am Ball" in (s.extract_text() or "") for s in leser.pages)
    assert any("Spielbericht" in (s.extract_text() or "") for s in leser.pages)
    # Heft + Heftplan liegen im Ordner
    assert f"{SAISON}/09 Ausgabe 290726/Heftplan.txt" in nas.hochgeladen
    assert ergebnis.nas_datei.endswith("_WaB_Druck.pdf")

    # Zweiter Bau: nichts wird erneut geladen ...
    nas.geladen.clear()
    gesamtheft_bauen(heft_konfiguration, "09 Ausgabe 290726", fs=nas, neu_planen=True)
    assert not any("Werbung" in p for p in nas.geladen)


def _docx(absaetze: list[str], fett: tuple[int, ...] = ()) -> bytes:
    import zipfile

    def absatz(i: int, text: str) -> str:
        rpr = "<w:rPr><w:b/></w:rPr>" if i in fett else ""
        return f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("word/document.xml",
                   '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                   'wordprocessingml/2006/main"><w:body>'
                   + "".join(absatz(i, t) for i, t in enumerate(absaetze))
                   + "</w:body></w:document>")
    return puffer.getvalue()


def _quer_pdf() -> bytes:
    schreiber = PdfWriter()
    schreiber.add_blank_page(width=595, height=300)
    puffer = io.BytesIO()
    schreiber.write(puffer)
    return puffer.getvalue()


def test_heft_wie_in_der_layoutdatei(heft_konfiguration: Konfiguration,
                                     nas: SpeicherNas):
    """Werbung vorne/hinten/Rueckseite, halbe Anzeigen zu zweit, Grusswort als
    Word, Kontaktlisten mit Jugend, Impressum -- wie Ausgabe 08."""
    ordner = f"{SAISON}/09 Ausgabe 290726"
    del nas.baum[ordner]["Vorwort.txt"]
    nas.datei(f"{ordner}/Grußwort Stadionheft.docx",
              _docx(["Hallo zusammen,", "herzlich willkommen.", "Euer SVW"]))
    w = f"{SAISON}/Allgemein/Werbung"
    for name in list(nas.baum[w]):
        if nas.baum[w][name] is not None:
            del nas.baum[w][name]
    nas.datei(f"{w}/1 vorne/JAKO.pdf", _pdf(5))
    nas.datei(f"{w}/2 hinten/A_Sparkasse.pdf", _quer_pdf())
    nas.datei(f"{w}/2 hinten/B_Logo.pdf", _quer_pdf())
    nas.datei(f"{w}/2 hinten/C_EloTec.pdf", _pdf(1))
    nas.datei(f"{w}/3 Rückseite/MRplan.pdf", _pdf(1))
    nas.datei(f"{SAISON}/Allgemein/Kontakte_Jugend_2026.docx",
              _docx(["A-Jugend", "Watzl Nico • 0151-10304443 • a-jgd@x.de"]))
    nas.datei(f"{SAISON}/Allgemein/Impressum.pdf", _pdf(1))

    ergebnis = gesamtheft_bauen(heft_konfiguration, "09 Ausgabe 290726", fs=nas,
                                neu_planen=True)
    zeilen = _zeilen(ergebnis)
    assert zeilen[:3] == ["[Deckblatt]", "[Vorwort] Grußwort Stadionheft.docx",
                          "[Werbung] 1 vorne/JAKO.pdf"]
    # Mannschaften am Stueck, Werbung erst danach
    erste_hinten = zeilen.index("[Werbung] 2 hinten/A_Sparkasse.pdf + 2 hinten/B_Logo.pdf")
    assert zeilen.index("[FuPa] damen1") < erste_hinten
    assert zeilen[erste_hinten + 1] == "[Werbung] 2 hinten/C_EloTec.pdf"
    ende = zeilen[-4:]
    assert ende == ["[Kontaktliste] Allgemein/Ansprechpartner.txt",
                    "[Kontaktliste] Allgemein/Kontakte_Jugend_2026.docx",
                    "[Impressum] Allgemein/Impressum.pdf",
                    "[Werbung] 3 Rückseite/MRplan.pdf"]
    assert ergebnis.seitenzahl % 4 == 0
    leser = PdfReader(str(ergebnis.pdf))
    texte = [s.extract_text() or "" for s in leser.pages]
    assert any("Vorwort" in t and "herzlich willkommen" in t for t in texte)
    assert any("Kontaktlisten" in t and "A-Jugend" in t for t in texte)


def test_word_absaetze_und_ueberschriften(tmp_path):
    from stadionheft.gesamtheft import _sieht_aus_wie_ueberschrift, word_absaetze

    datei = tmp_path / "x.docx"
    datei.write_bytes(_docx(["Titel", "normal &amp; gut"], fett=(0,)))
    assert word_absaetze(datei) == [("Titel", True), ("normal & gut", False)]
    assert _sieht_aus_wie_ueberschrift("B-Juniorinnen")
    assert not _sieht_aus_wie_ueberschrift("Moll Lea • 0151-68528611 • x@y.de")


def test_spielbericht_und_halbe_seiten(tmp_path):
    from stadionheft.gesamtheft import MM, halbe_seiten, inhalt_einsetzen
    from stadionheft.render.pages import LayoutWerte

    rahmen = tmp_path / "rahmen.pdf"
    w = PdfWriter()
    w.add_blank_page(width=154 * MM, height=216 * MM)
    from pypdf.generic import RectangleObject
    w.pages[0].trimbox = RectangleObject((3 * MM, 3 * MM, 151 * MM, 213 * MM))
    with rahmen.open("wb") as strom:
        w.write(strom)
    artikel = tmp_path / "artikel.pdf"
    artikel.write_bytes(_pdf(2))
    ziel = inhalt_einsetzen(rahmen, artikel, tmp_path / "bericht.pdf")
    assert len(PdfReader(str(ziel)).pages) == 2          # je Artikelseite eine

    quer = tmp_path / "quer.pdf"
    quer.write_bytes(_quer_pdf())
    seite = PdfReader(str(halbe_seiten([quer, quer], LayoutWerte(),
                                       tmp_path / "halb.pdf"))).pages
    assert len(seite) == 1
    assert round(float(seite[0].trimbox.width) / MM) == 148


def test_eigener_heftplan_wird_befolgt(heft_konfiguration: Konfiguration,
                                       nas: SpeicherNas):
    ordner = f"{SAISON}/09 Ausgabe 290726"
    nas.datei(f"{ordner}/Heftplan.txt", (
        "# von Hand\n[Deckblatt]\n[Werbung] B_Baecker.jpg\n[FuPa] damen1\n"
        "[Datei] Herren 1/Bericht.pdf\n[Werbung] A_Axa.pdf\n").encode())
    ergebnis = gesamtheft_bauen(heft_konfiguration, "09 Ausgabe 290726", fs=nas)
    assert ergebnis.plan_von_hand
    zeilen = _zeilen(ergebnis)
    # Genau die Reihenfolge, aufgefuellt vor der letzten Seite
    assert zeilen[:4] == ["[Deckblatt]", "[Werbung] B_Baecker.jpg", "[FuPa] damen1",
                          "[Datei] Herren 1/Bericht.pdf"]
    assert zeilen[-1] == "[Werbung] A_Axa.pdf"
    assert ergebnis.seitenzahl % 4 == 0
    assert any("nicht durch 4 teilbar" in w for w in ergebnis.warnungen)
    # Der eigene Plan wird nicht ueberschrieben
    assert f"{ordner}/Heftplan.txt" not in nas.hochgeladen


def test_unbekannte_ausgabe(heft_konfiguration: Konfiguration, nas: SpeicherNas):
    with pytest.raises(NasFehler):
        gesamtheft_bauen(heft_konfiguration, "99 Ausgabe gibtsnicht", fs=nas)


def test_neue_saison(heft_konfiguration: Konfiguration, nas: SpeicherNas):
    heft_konfiguration.roh["saison"] = "2027/2028"
    bericht = saison_anlegen(heft_konfiguration, fs=nas)
    assert bericht.erfolgreich, bericht.fehler
    neu = "/SVW/Stadionheft/Saison 27-28"
    assert set(nas.baum[neu]) == {"00 Vorlage", "Allgemein"}
    assert "Titelbild.jpeg" in nas.baum[f"{neu}/00 Vorlage"]
    assert "Ansprechpartner.txt" in nas.baum[f"{neu}/Allgemein"]
    # Ein zweites Mal legt nichts an
    assert not saison_anlegen(heft_konfiguration, fs=nas).erfolgreich


def test_vorherige_saison():
    assert vorherige_saison(["Saison24-25", "Saison 26-27", "Allgemein"],
                            "Saison 27-28") == "Saison 26-27"
    assert vorherige_saison([], "Saison 27-28") == ""


def test_fremde_formate_werden_eingepasst(tmp_path):
    from stadionheft.gesamtheft import MM, auf_heftformat
    from stadionheft.render.pages import LayoutWerte

    schreiber = PdfWriter()
    schreiber.add_blank_page(width=210 * MM, height=297 * MM)   # A4
    schreiber.add_blank_page(width=210 * MM, height=148 * MM)   # A5 quer
    schreiber.add_blank_page(width=154 * MM, height=216 * MM)   # A5 + Anschnitt
    from pypdf.generic import RectangleObject
    schreiber.pages[2].trimbox = RectangleObject((3 * MM, 3 * MM, 151 * MM, 213 * MM))
    quelle = tmp_path / "anzeigen.pdf"
    with quelle.open("wb") as strom:
        schreiber.write(strom)

    ziel = auf_heftformat(quelle, LayoutWerte(), tmp_path / "heft.pdf")
    seiten = PdfReader(str(ziel)).pages
    for seite in seiten:
        assert round(float(seite.mediabox.width) / MM) == 154
        assert round(float(seite.mediabox.height) / MM) == 216
        assert round(float(seite.trimbox.width) / MM) == 148
    # Bereits passende Datei bleibt, wie sie ist
    nur_a5 = tmp_path / "a5.pdf"
    w = PdfWriter()
    w.add_blank_page(width=148 * MM, height=210 * MM)
    with nur_a5.open("wb") as strom:
        w.write(strom)
    assert auf_heftformat(nur_a5, LayoutWerte(), tmp_path / "x.pdf") == nur_a5


def test_doppelseite_wird_zerlegt_halbe_anzeige_nicht(tmp_path):
    """Teamshop-Flyer: A4 hoch + zwei A4-quer-Seiten = 1 + 4 Heftseiten.
    Eine A5-quer-Anzeige (gleiches Seitenverhaeltnis) bleibt eine Seite."""
    from stadionheft.gesamtheft import MM, auf_heftformat
    from stadionheft.render.pages import LayoutWerte

    w = PdfWriter()
    w.add_blank_page(width=210 * MM, height=297 * MM)
    w.add_blank_page(width=297 * MM, height=210 * MM)
    w.add_blank_page(width=297 * MM, height=210 * MM)
    flyer = tmp_path / "flyer.pdf"
    with flyer.open("wb") as strom:
        w.write(strom)
    seiten = PdfReader(str(auf_heftformat(flyer, LayoutWerte(),
                                          tmp_path / "f.pdf"))).pages
    assert len(seiten) == 5
    assert all(round(float(s.trimbox.width) / MM) == 148 for s in seiten)

    w = PdfWriter()
    w.add_blank_page(width=210 * MM, height=148 * MM)
    quer = tmp_path / "axa.pdf"
    with quer.open("wb") as strom:
        w.write(strom)
    assert len(PdfReader(str(auf_heftformat(quer, LayoutWerte(),
                                            tmp_path / "a.pdf"))).pages) == 1


def test_nur_die_neueste_fassung():
    from stadionheft.gesamtheft import HeftErgebnis, nur_neueste

    ergebnis = HeftErgebnis()
    namen = ["01 SVW_Flyer_Ausstattung_2025.pdf", "01 SVW_Flyer_Ausstattung_2026.pdf",
             "12082024_Anzeige_Augenblick.pdf", "Axa.pdf", "Kontakte_Jugend_2026.docx"]
    assert nur_neueste(namen, ergebnis) == [
        "01 SVW_Flyer_Ausstattung_2026.pdf", "12082024_Anzeige_Augenblick.pdf",
        "Axa.pdf", "Kontakte_Jugend_2026.docx"]
    assert len(ergebnis.warnungen) == 1 and "2025" in ergebnis.warnungen[0]
