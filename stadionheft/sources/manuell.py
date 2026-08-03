"""Manuelle Datenquelle: CSV-/Textdateien aus dem Eingabeordner.

Das ist der **verlaessliche Weg**, der ohne jede Abhaengigkeit von FuPa
funktioniert -- und gleichzeitig der empfohlene Einstieg: Zahlen einmal in
Excel eintragen (oder aus FuPa kopieren), als CSV speichern, fertig.

Erwartete Dateien je Mannschaft (``<schluessel>`` = herren1, damen1, ...):

===============================  ==========================================
Datei                            Inhalt
===============================  ==========================================
``<schluessel>_tabelle.csv``       platz;mannschaft;spiele;siege;unentschieden;
                                   niederlagen;tore;gegentore;punkte;zusatz
``<schluessel>_torjaeger.csv``     platz;spieler;mannschaft;tore;vorlagen;spiele
``<schluessel>_spieler.csv``       platz;spieler;spiele;tore;vorlagen;elfmeter;
                                   gelb;gelb_rot;rot;ein;aus;minuten
``<schluessel>_gegner_spieler.csv``  wie ``_spieler.csv`` (Kader des Gegners)
``<schluessel>_naechstes_spiel.csv`` heim;gast;wettbewerb;datum;uhrzeit;
                                   spielort;heimspiel;spieltag
``<schluessel>_spielbericht.md``   Freitext (Markdown oder einfacher Text)
===============================  ==========================================

Robust gegen die ueblichen Excel-Eigenheiten:

* Trennzeichen ``;`` oder ``,`` wird automatisch erkannt.
* Kodierung UTF-8, UTF-8-BOM und Windows-1252 werden unterstuetzt.
* Spaltenueberschriften sind gross/klein egal, deutsche und englische
  Bezeichnungen werden akzeptiert (``tore`` / ``goals``, ``sp`` / ``spiele``).
* Fehlt eine Datei, bleibt nur die betreffende Seite leer -- der Rest des
  Hefts wird trotzdem erzeugt.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..config import Konfiguration, Mannschaft
from ..errors import ManuelleDatenFehlenFehler
from ..logging_setup import logger
from ..models import MannschaftsDaten, Spiel, SpielerZeile, TabellenZeile, TorjaegerZeile
from .base import basis_daten

KODIERUNGEN = ("utf-8-sig", "utf-8", "cp1252")


def csv_lesen(datei: Path) -> list[dict]:
    """Liest eine CSV-Datei als Liste von Zeilen-Woerterbuechern."""
    text = None
    for kodierung in KODIERUNGEN:
        try:
            text = datei.read_text(encoding=kodierung)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ManuelleDatenFehlenFehler(
            f"{datei} ist in keiner bekannten Zeichenkodierung lesbar.",
            benutzer_text=f"Die Datei {datei.name} konnte nicht gelesen werden.",
            hinweis="Bitte in Excel als 'CSV UTF-8' speichern.")

    text = text.lstrip("﻿")
    kopf = text.splitlines()[0] if text.splitlines() else ""
    trenner = ";" if kopf.count(";") >= kopf.count(",") else ","

    zeilen: list[dict] = []
    for roh in csv.DictReader(text.splitlines(), delimiter=trenner):
        sauber = {
            (schluessel or "").strip().lower().replace(" ", "_")
            .replace(".", "").replace("-", "_"): (wert or "").strip()
            for schluessel, wert in roh.items()
        }
        if any(sauber.values()):
            zeilen.append(sauber)
    return zeilen


class ManuelleQuelle:
    """Liest die Daten einer Mannschaft aus dem Eingabeordner."""

    name = "manuell"

    def __init__(self, konfiguration: Konfiguration) -> None:
        self.konfiguration = konfiguration
        self.ordner = konfiguration.eingabe_ordner
        self.vereinsname = konfiguration.vereinsname

    # -- Schnittstelle ------------------------------------------------------

    def hole(self, mannschaft: Mannschaft) -> MannschaftsDaten:
        daten = basis_daten(mannschaft, self.name)
        if not self.ordner.exists():
            raise ManuelleDatenFehlenFehler(
                f"Eingabeordner {self.ordner} fehlt.",
                benutzer_text=f"Der Eingabeordner {self.ordner} existiert nicht.",
                hinweis=("Bitte den Ordner anlegen und die CSV-Dateien "
                         "hineinkopieren (Vorlagen: daten/03_eingaben/vorlagen/)."))

        kern = self._eigener_kern()
        gefunden = 0

        zeilen = self._lesen(mannschaft, "tabelle", daten)
        if zeilen:
            daten.tabelle = [TabellenZeile.aus_csv(z, kern) for z in zeilen]
            gefunden += 1

        zeilen = self._lesen(mannschaft, "torjaeger", daten)
        if zeilen:
            daten.torjaeger = [TorjaegerZeile.aus_csv(z, kern) for z in zeilen]
            gefunden += 1

        zeilen = self._lesen(mannschaft, "spieler", daten)
        if zeilen:
            daten.spieler = [SpielerZeile.aus_csv(z) for z in zeilen]
            gefunden += 1

        zeilen = self._lesen(mannschaft, "gegner_spieler", daten, still=True)
        if zeilen:
            daten.gegner_spieler = [SpielerZeile.aus_csv(z) for z in zeilen]

        zeilen = self._lesen(mannschaft, "naechstes_spiel", daten)
        if zeilen:
            daten.naechstes_spiel = Spiel.aus_csv(zeilen[0])
            if not daten.naechstes_spiel.wettbewerb:
                daten.naechstes_spiel.wettbewerb = mannschaft.liga
            gefunden += 1

        bericht = self._textdatei(mannschaft, "spielbericht")
        if bericht:
            daten.spielbericht = bericht

        if gefunden == 0:
            raise ManuelleDatenFehlenFehler(
                f"Keine Eingabedateien fuer {mannschaft.schluessel} in {self.ordner}.",
                benutzer_text=(f"Fuer {mannschaft.anzeigename} wurden keine "
                               f"Eingabedateien gefunden."),
                hinweis=(f"Erwartet werden Dateien wie "
                         f"{mannschaft.schluessel}_tabelle.csv im Ordner "
                         f"{self.ordner}."))
        return daten

    # -- Hilfen -------------------------------------------------------------

    def _pfad(self, mannschaft: Mannschaft, art: str) -> Path:
        return self.ordner / f"{mannschaft.schluessel}_{art}.csv"

    def _lesen(self, mannschaft: Mannschaft, art: str, daten: MannschaftsDaten,
               still: bool = False) -> list[dict]:
        datei = self._pfad(mannschaft, art)
        if not datei.exists():
            if not still:
                logger().info("Keine Datei %s - Seite '%s' bleibt leer.",
                              datei.name, art)
                daten.warnungen.append(
                    f"Die Datei {datei.name} fehlt - die zugehoerige Seite "
                    f"bleibt leer.")
            return []
        zeilen = csv_lesen(datei)
        logger().info("%s: %d Zeilen gelesen.", datei.name, len(zeilen))
        return zeilen

    def _textdatei(self, mannschaft: Mannschaft, art: str) -> str:
        for endung in (".md", ".txt"):
            datei = self.ordner / f"{mannschaft.schluessel}_{art}{endung}"
            if datei.exists():
                for kodierung in KODIERUNGEN:
                    try:
                        return datei.read_text(encoding=kodierung).strip()
                    except UnicodeDecodeError:
                        continue
        return ""

    def _eigener_kern(self) -> str:
        """Kurzform des Vereinsnamens zum Hervorheben eigener Zeilen."""
        kern = (self.vereinsname or "").replace("SV", "").replace("e.V.", "").strip()
        return kern.split("-")[0].strip()
