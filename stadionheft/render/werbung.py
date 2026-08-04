"""Werbeblöcke aus einem Ordner zusammenstellen.

Statt einer grossen ``werbung_vorne.pdf`` liegt jede Anzeige als eigene Datei
in einem Ordner. Das Programm baut den Block bei jedem Lauf neu zusammen:

* **Anzeige dazu?** Datei in den Ordner legen.
* **Anzeige raus?** Datei loeschen oder in den Unterordner ``_pausiert``
  verschieben.
* **Reihenfolge aendern?** Zahl am Dateianfang aendern.

Damit muss niemand mehr eine Sammel-PDF neu erzeugen, und der Ordner in der
Dateistation ist gleichzeitig die Uebersicht, welche Anzeigen im Heft sind.

Befristete Anzeigen
-------------------
Manche Anzeigen gelten nur bis zu einem bestimmten Tag -- eine Ankuendigung
fuer ein Spiel oder ein Fest zum Beispiel. Solche Anzeigen bekommen das Datum
in den Dateinamen::

    10_bayern-freundschaftsspiel__bis_2026-08-01.pdf
    20_sommerfest__ab_2026-06-01__bis_2026-07-15.pdf

Ab dem Tag nach ``__bis_`` faellt die Anzeige von selbst aus dem Heft. Vor dem
Tag in ``__ab_`` erscheint sie noch nicht. So kann niemand vergessen, eine
abgelaufene Ankuendigung herauszunehmen.

Reihenfolge
-----------
Sortiert wird nach Dateiname. Deshalb bewaehrt sich eine Zahl am Anfang, am
besten in Zehnerschritten -- dann laesst sich spaeter etwas dazwischen
schieben, ohne alles umzubenennen::

    10_teamshop.pdf
    20_jako-katalog-1.pdf
    21_jako-katalog-2.pdf
    30_ullmann.pdf
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from ..logging_setup import logger

#: Unterordner, dessen Inhalt bewusst ignoriert wird.
PAUSIERT = "_pausiert"

_AB = re.compile(r"__ab[_-](\d{4}-\d{2}-\d{2})", re.IGNORECASE)
_BIS = re.compile(r"__bis[_-](\d{4}-\d{2}-\d{2})", re.IGNORECASE)


@dataclass
class Anzeige:
    pfad: Path
    ab: date | None = None
    bis: date | None = None

    @property
    def titel(self) -> str:
        """Dateiname ohne Sortierzahl und Datumsangaben -- fuer Meldungen."""
        stamm = self.pfad.stem
        stamm = _AB.sub("", _BIS.sub("", stamm))
        return re.sub(r"^\d+[_-]", "", stamm).replace("_", " ").strip() or self.pfad.stem

    def gilt_am(self, tag: date) -> bool:
        if self.ab and tag < self.ab:
            return False
        if self.bis and tag > self.bis:
            return False
        return True


def _datum(text: str, muster: re.Pattern) -> date | None:
    treffer = muster.search(text)
    if not treffer:
        return None
    try:
        return datetime.strptime(treffer.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def anzeigen_lesen(ordner: Path) -> list[Anzeige]:
    """Alle PDF-Dateien eines Ordners als Anzeigen, sortiert nach Dateiname."""
    if not ordner.exists() or not ordner.is_dir():
        return []
    dateien = sorted(
        (p for p in ordner.iterdir()
         if p.is_file() and p.suffix.lower() == ".pdf" and not p.name.startswith(".")),
        key=lambda p: p.name.lower(),
    )
    return [Anzeige(pfad=p, ab=_datum(p.stem, _AB), bis=_datum(p.stem, _BIS))
            for p in dateien]


def werbeblock(ordner: Path, stichtag: date | None = None
               ) -> tuple[list[Anzeige], list[str]]:
    """Stellt die an ``stichtag`` gueltigen Anzeigen zusammen.

    Rueckgabe: (gueltige Anzeigen in Reihenfolge, Hinweistexte fuer den Benutzer)
    """
    tag = stichtag or date.today()
    hinweise: list[str] = []

    if not ordner.exists():
        return [], [f"Der Werbeordner {ordner} existiert nicht – "
                    f"dieser Block bleibt leer."]

    alle = anzeigen_lesen(ordner)
    if not alle:
        return [], [f"Im Ordner {ordner.name} liegt keine einzige PDF-Anzeige – "
                    f"dieser Block bleibt leer."]

    gueltig: list[Anzeige] = []
    for anzeige in alle:
        if anzeige.gilt_am(tag):
            gueltig.append(anzeige)
        elif anzeige.bis and tag > anzeige.bis:
            text = (f"Anzeige „{anzeige.titel}“ ist seit dem "
                    f"{anzeige.bis:%d.%m.%Y} abgelaufen und wurde nicht "
                    f"eingebunden.")
            logger().info("%s", text)
            hinweise.append(text)
        else:
            text = (f"Anzeige „{anzeige.titel}“ startet erst am "
                    f"{anzeige.ab:%d.%m.%Y} und wurde noch nicht eingebunden.")
            logger().info("%s", text)
            hinweise.append(text)

    pausiert = ordner / PAUSIERT
    if pausiert.is_dir():
        anzahl = len(list(pausiert.glob("*.pdf")))
        if anzahl:
            hinweise.append(
                f"{anzahl} Anzeige(n) liegen in {ordner.name}/{PAUSIERT} "
                f"und sind damit bewusst ausgeblendet.")

    logger().info("Werbeblock %s: %d von %d Anzeigen eingebunden.",
                  ordner.name, len(gueltig), len(alle))
    return gueltig, hinweise
