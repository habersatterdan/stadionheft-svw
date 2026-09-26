"""Setzt das fertige Stadionheft aus Einzel-PDFs zusammen.

Zwei Sorten Seiten treffen hier aufeinander:

* **erzeugte Seiten** aus WeasyPrint (Titel, Tabellen, Statistiken, ...)
* **feste Seiten** als fertige PDF-Dateien (Werbeanzeigen, Grafikseiten aus
  InDesign, Ruecktitel)

Die beiden Sorten haben in aller Regel leicht unterschiedliche Seitenboxen:
das InDesign-Original der Vorlage hat eine MediaBox von 461,5 x 637,3 pt
(Endformat 148 x 210 mm plus Platz fuer Schnittmarken), WeasyPrint liefert
Endformat plus Anschnitt. Damit die Druckerei kein gemischtes Dokument
bekommt, werden hier **alle Seiten auf eine gemeinsame Seitenbox gebracht**
und mittig ausgerichtet. Das Endformat (TrimBox) bleibt dabei erhalten.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject

from ..errors import RenderFehler, VorlageFehltFehler
from ..logging_setup import logger

#: Groessere Abweichung als das gilt als echter Formatunterschied (in pt).
TOLERANZ = 1.0


@dataclass
class Heftseite:
    """Ein Eintrag in der Montageliste."""

    pfad: Path
    beschreibung: str = ""
    seiten: str = ""          # "" = alle, sonst "1" oder "2-4"
    pflicht: bool = True


@dataclass
class MontageErgebnis:
    ziel: Path
    seitenzahl: int = 0
    warnungen: list[str] = field(default_factory=list)
    quellen: list[str] = field(default_factory=list)


def _seiten_auswahl(text: str, anzahl: int) -> list[int]:
    """'2-4' -> [1,2,3] (0-basiert). Leer -> alle Seiten."""
    if not text:
        return list(range(anzahl))
    ergebnis: list[int] = []
    for teil in str(text).split(","):
        teil = teil.strip()
        if not teil:
            continue
        if "-" in teil:
            von, _, bis = teil.partition("-")
            start = max(1, int(von or 1))
            ende = min(anzahl, int(bis or anzahl))
            ergebnis.extend(range(start - 1, ende))
        else:
            nr = int(teil)
            if 1 <= nr <= anzahl:
                ergebnis.append(nr - 1)
    return ergebnis or list(range(anzahl))


def _box(seite: PageObject, name: str) -> RectangleObject | None:
    try:
        return getattr(seite, name)
    except Exception:  # noqa: BLE001 - Box fehlt schlicht
        return None


def _masse(box) -> tuple[float, float]:
    return float(box.width), float(box.height)


def zusammenfuegen(eintraege: list[Heftseite], ziel: Path) -> MontageErgebnis:
    """Fuegt alle Eintraege in der angegebenen Reihenfolge zu einer PDF zusammen."""
    ergebnis = MontageErgebnis(ziel=ziel)
    quellen: list[tuple[PageObject, str]] = []

    # 1. Alle Seiten einlesen ------------------------------------------------
    for eintrag in eintraege:
        pfad = Path(eintrag.pfad)
        if not pfad.exists():
            if eintrag.pflicht:
                raise VorlageFehltFehler(
                    f"Datei fehlt: {pfad}",
                    benutzer_text=f"Die Datei '{pfad.name}' wurde nicht gefunden.",
                    hinweis=(f"Erwartet unter: {pfad}\n"
                             f"Bitte die Datei dort ablegen oder den Eintrag im "
                             f"Heftplan auf 'optional: true' setzen."),
                )
            warnung = (f"{eintrag.beschreibung or pfad.name} wurde übersprungen "
                       f"– Datei nicht gefunden ({pfad}).")
            logger().warning(warnung)
            ergebnis.warnungen.append(warnung)
            continue

        try:
            leser = PdfReader(str(pfad))
            if leser.is_encrypted:
                leser.decrypt("")
            auswahl = _seiten_auswahl(eintrag.seiten, len(leser.pages))
            for index in auswahl:
                quellen.append((leser.pages[index],
                                eintrag.beschreibung or pfad.name))
        except VorlageFehltFehler:
            raise
        except Exception as fehler:  # noqa: BLE001
            if eintrag.pflicht:
                raise RenderFehler(
                    f"{pfad}: {fehler}",
                    benutzer_text=f"Die PDF-Datei '{pfad.name}' konnte nicht "
                                  f"gelesen werden.",
                    hinweis="Bitte pruefen, ob die Datei beschaedigt oder "
                            "passwortgeschuetzt ist.",
                ) from fehler
            warnung = f"{pfad.name} konnte nicht gelesen werden ({fehler}) – übersprungen."
            logger().warning(warnung)
            ergebnis.warnungen.append(warnung)

    if not quellen:
        raise RenderFehler(
            "Keine einzige Seite zum Zusammenfuegen.",
            benutzer_text="Es konnte keine einzige Seite erzeugt werden.",
            hinweis="Bitte Heftplan und Eingabedaten pruefen.",
        )

    # 2. Gemeinsames Seitenformat bestimmen ---------------------------------
    breiten = [_masse(s.mediabox)[0] for s, _ in quellen]
    hoehen = [_masse(s.mediabox)[1] for s, _ in quellen]
    ziel_breite, ziel_hoehe = max(breiten), max(hoehen)

    trim_masse = set()
    for seite, _ in quellen:
        trim = _box(seite, "trimbox") or seite.mediabox
        trim_masse.add((round(float(trim.width), 1), round(float(trim.height), 1)))
    if len(trim_masse) > 1:
        warnung = ("Nicht alle Seiten haben dasselbe Endformat: "
                   + "; ".join(f"{b:.0f}x{h:.0f} pt" for b, h in sorted(trim_masse))
                   + ". Bitte vor dem Druck pruefen.")
        logger().warning(warnung)
        ergebnis.warnungen.append(warnung)

    # 3. Seiten zentriert auf das gemeinsame Format legen -------------------
    schreiber = PdfWriter()
    for seite, beschreibung in quellen:
        breite, hoehe = _masse(seite.mediabox)
        gleich = (abs(breite - ziel_breite) < TOLERANZ
                  and abs(hoehe - ziel_hoehe) < TOLERANZ
                  and abs(float(seite.mediabox.left)) < TOLERANZ
                  and abs(float(seite.mediabox.bottom)) < TOLERANZ)
        if gleich:
            schreiber.add_page(seite)
            ergebnis.quellen.append(beschreibung)
            continue

        dx = (ziel_breite - breite) / 2 - float(seite.mediabox.left)
        dy = (ziel_hoehe - hoehe) / 2 - float(seite.mediabox.bottom)
        neu = PageObject.create_blank_page(width=ziel_breite, height=ziel_hoehe)
        neu.merge_transformed_page(seite, Transformation().translate(dx, dy))

        trim = _box(seite, "trimbox")
        if trim is not None:
            neu.trimbox = RectangleObject((
                float(trim.left) + dx, float(trim.bottom) + dy,
                float(trim.right) + dx, float(trim.top) + dy,
            ))
        bleed = _box(seite, "bleedbox")
        if bleed is not None:
            neu.bleedbox = RectangleObject((
                float(bleed.left) + dx, float(bleed.bottom) + dy,
                float(bleed.right) + dx, float(bleed.top) + dy,
            ))
        schreiber.add_page(neu)
        ergebnis.quellen.append(beschreibung)

    # 4. Speichern -----------------------------------------------------------
    ziel.parent.mkdir(parents=True, exist_ok=True)
    try:
        with ziel.open("wb") as datei:
            schreiber.write(datei)
    except OSError as fehler:
        raise RenderFehler(
            f"{ziel}: {fehler}",
            benutzer_text=f"Das fertige Heft konnte nicht gespeichert werden "
                          f"({ziel}).",
            hinweis="Bitte pruefen, ob der Ordner existiert und beschreibbar ist.",
        ) from fehler

    ergebnis.seitenzahl = len(schreiber.pages)
    logger().info("Zusammengefuegt: %d Seiten -> %s", ergebnis.seitenzahl, ziel)
    # Bewusst kein Hinweis auf Seitenzahlen in Vierer-Schritten: Diese Datei
    # ist ein Baustein, kein fertiges Heft. Ueber die Gesamtseitenzahl
    # entscheidet, wer das Heft zusammenbaut.
    return ergebnis
