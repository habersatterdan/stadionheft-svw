"""Seiten aus einem bestehenden Stadionheft herausloesen.

Nicht jede Seite muss neu gesetzt werden. Kontaktlisten, Impressum, Werbung
und gestaltete Sonderseiten sind im alten Heft bereits fertig -- und sollen
sich gerade **nicht** aendern. Der schnellste und sicherste Weg ist deshalb,
sie als PDF-Seiten zu uebernehmen und im Heftplan als ``typ: pdf``
einzubinden.

Vorteile gegenueber dem Neusetzen:

* Das Ergebnis sieht **exakt** aus wie bisher -- keine abweichenden
  Zeilenumbrueche, keine Schriftunterschiede.
* Personenbezogene Daten (Telefonnummern, private E-Mail-Adressen) muessen
  nirgends abgetippt werden und landen nicht in einer Konfigurationsdatei.
* Kein Pflegeaufwand: Aendert sich ein Kontakt, wird die Seite einmal neu
  aus dem aktuellen Heft gezogen.

Aufruf::

    python -m stadionheft.cli seiten-uebernehmen \\
        --aus "20260728_WaB_Druck.pdf" --seiten 24-25 --als kontaktlisten
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from ..config import Konfiguration
from ..errors import VorlageFehltFehler
from ..logging_setup import logger


def seiten_bereich(text: str, anzahl: int) -> list[int]:
    """'24-25' oder '24,27' -> Liste 0-basierter Seitenindizes."""
    ergebnis: list[int] = []
    for teil in str(text).split(","):
        teil = teil.strip()
        if not teil:
            continue
        try:
            if "-" in teil:
                von, _, bis = teil.partition("-")
                start, ende = int(von), int(bis)
            else:
                start = ende = int(teil)
        except ValueError:
            raise VorlageFehltFehler(
                f"Ungueltige Seitenangabe '{teil}'.",
                benutzer_text=f"Die Seitenangabe '{teil}' ist nicht lesbar.",
                hinweis="Erlaubt sind z. B. '24', '24-25' oder '24,27'.") from None
        if start < 1 or ende > anzahl or start > ende:
            raise VorlageFehltFehler(
                f"Seiten {start}-{ende} liegen ausserhalb von 1-{anzahl}.",
                benutzer_text=(f"Die Seiten {start}-{ende} gibt es nicht – "
                               f"das Dokument hat {anzahl} Seiten."))
        ergebnis.extend(range(start - 1, ende))
    if not ergebnis:
        raise VorlageFehltFehler(
            "Keine Seiten angegeben.",
            benutzer_text="Es wurde keine Seite zum Übernehmen angegeben.")
    return ergebnis


def uebernehmen(konfiguration: Konfiguration, quelle: str | Path,
                seiten: str, name: str,
                zielordner: Path | None = None) -> tuple[Path, dict]:
    """Schneidet Seiten aus ``quelle`` heraus und legt sie als eigene PDF ab.

    Rueckgabe: (Zieldatei, Angaben zum Format fuer die Ausgabe an den Benutzer)
    """
    quell_pfad = Path(quelle).expanduser()
    if not quell_pfad.exists():
        raise VorlageFehltFehler(
            f"{quell_pfad} nicht gefunden.",
            benutzer_text=f"Die Datei '{quell_pfad}' wurde nicht gefunden.",
            hinweis="Bitte den vollstaendigen Pfad zum alten Stadionheft angeben.")

    try:
        leser = PdfReader(str(quell_pfad))
        if leser.is_encrypted:
            leser.decrypt("")
    except Exception as fehler:  # noqa: BLE001
        raise VorlageFehltFehler(
            f"{quell_pfad}: {fehler}",
            benutzer_text=f"Die Datei '{quell_pfad.name}' konnte nicht gelesen werden.",
            hinweis="Ist sie beschaedigt oder passwortgeschuetzt?") from fehler

    indizes = seiten_bereich(seiten, len(leser.pages))

    schreiber = PdfWriter()
    for index in indizes:
        schreiber.add_page(leser.pages[index])

    ordner = Path(zielordner) if zielordner else konfiguration.werbung_ordner
    ordner.mkdir(parents=True, exist_ok=True)
    ziel = ordner / (name if name.lower().endswith(".pdf") else f"{name}.pdf")
    with ziel.open("wb") as datei:
        schreiber.write(datei)

    erste = leser.pages[indizes[0]]
    trim = getattr(erste, "trimbox", None) or erste.mediabox
    angaben = {
        "seiten": len(indizes),
        "quelle_seiten": [i + 1 for i in indizes],
        "endformat_mm": (round(float(trim.width) / 72 * 25.4, 1),
                         round(float(trim.height) / 72 * 25.4, 1)),
    }
    logger().info("Seiten %s aus %s uebernommen -> %s",
                  angaben["quelle_seiten"], quell_pfad.name, ziel)
    return ziel, angaben


def einzeln_zerlegen(konfiguration: Konfiguration, quelle: str | Path,
                     seiten: str, zielordner: Path,
                     schrittweite: int = 10) -> list[Path]:
    """Zerlegt einen Seitenbereich in **eine PDF-Datei je Seite**.

    Gedacht fuer Werbeblöcke: danach liegt jede Anzeige als eigene Datei im
    Ordner und laesst sich einzeln austauschen, umsortieren oder befristen --
    siehe ``stadionheft/render/werbung.py``.

    Die Dateinamen werden in Zehnerschritten nummeriert, damit sich spaeter
    bequem etwas dazwischen schieben laesst.
    """
    quell_pfad = Path(quelle).expanduser()
    if not quell_pfad.exists():
        raise VorlageFehltFehler(
            f"{quell_pfad} nicht gefunden.",
            benutzer_text=f"Die Datei '{quell_pfad}' wurde nicht gefunden.")

    leser = PdfReader(str(quell_pfad))
    if leser.is_encrypted:
        leser.decrypt("")
    indizes = seiten_bereich(seiten, len(leser.pages))

    zielordner.mkdir(parents=True, exist_ok=True)
    geschrieben: list[Path] = []
    for lauf, index in enumerate(indizes, start=1):
        schreiber = PdfWriter()
        schreiber.add_page(leser.pages[index])
        ziel = zielordner / f"{lauf * schrittweite:03d}_anzeige_seite{index + 1}.pdf"
        with ziel.open("wb") as datei:
            schreiber.write(datei)
        geschrieben.append(ziel)

    logger().info("%d Einzelanzeigen nach %s geschrieben.",
                  len(geschrieben), zielordner)
    return geschrieben


#: Was typischerweise aus einem bestehenden Heft uebernommen wird.
#: Die Seitenzahlen stammen aus der Ausgabe vom 29.07.2026 und muessen bei
#: einem anders aufgebauten Heft angepasst werden.
VORSCHLAEGE = [
    ("kontaktlisten", "24-25", "Kontaktlisten (Vorstand, Trainer, Jugend)"),
    ("impressum", "27", "Impressum"),
    ("werbung_vorne", "4-11", "Werbeblock vorne"),
    ("werbung_hinten", "19-23", "Werbeblock hinten"),
    ("werbung_zwischen", "26", "Werbeseite zwischen den Mannschaftsblöcken"),
    ("ruecktitel", "28", "Rücktitel"),
]
