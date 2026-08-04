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
``<schluessel>_spielplan.csv``     alle Spiele der Saison, eine Zeile je Partie:
                                   heim;gast;wettbewerb;datum;uhrzeit;spielort;
                                   heimspiel;spieltag;ergebnis
``<schluessel>_spielbericht.md``   Freitext (Markdown oder einfacher Text)
===============================  ==========================================

Der **Spielplan** ist der Schluessel zu wenig Pflegeaufwand: einmal im Sommer
ausfuellen, danach sucht das Programm bei jedem Heft anhand des Datums selbst
heraus, gegen wen als naechstes gespielt wird. Wer lieber vor jedem Heft eine
einzelne Partie eintraegt, kann stattdessen
``<schluessel>_naechstes_spiel.csv`` mit genau einer Zeile verwenden.

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
import re
from pathlib import Path

from ..config import Konfiguration, Mannschaft
from ..errors import ManuelleDatenFehlenFehler
from ..logging_setup import logger
from ..models import (MannschaftsDaten, Spiel, SpielerZeile, TabellenZeile,
                      TorjaegerZeile, spiele_einordnen)
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

        # Spielplan zuerst -- erst danach ist bekannt, wer der Gegner ist.
        if self._spielplan(mannschaft, daten):
            gefunden += 1

        self._gegnerkader(mannschaft, daten)

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

    # -- Spielplan ----------------------------------------------------------

    def _spielplan(self, mannschaft: Mannschaft, daten: MannschaftsDaten) -> bool:
        """Liest den Spielplan und sucht die Partie, die als naechste ansteht.

        Zwei Dateinamen sind erlaubt:

        * ``<team>_spielplan.csv``       -- **empfohlen**: alle Spiele der
          Saison. Einmal im Sommer ausfuellen, danach findet das Programm zu
          jedem Heft automatisch die richtige Partie. Auch das zuletzt
          gespielte Spiel wird so erkannt.
        * ``<team>_naechstes_spiel.csv`` -- eine einzelne Partie, die vor
          jedem Heft von Hand geaendert wird.

        Liegen beide Dateien vor, gewinnt der Spielplan.
        """
        for art in ("spielplan", "naechstes_spiel"):
            zeilen = self._lesen(mannschaft, art, daten, still=True)
            if not zeilen:
                continue

            spiele = [Spiel.aus_csv(z) for z in zeilen]
            for spiel in spiele:
                if not spiel.wettbewerb:
                    spiel.wettbewerb = mannschaft.liga

            if art == "naechstes_spiel":
                # Der Benutzer sagt hier ausdruecklich "das ist die naechste
                # Partie" -- das wird uebernommen, auch wenn das Datum schon
                # vorbei ist (z. B. Heft am Abend des Spieltags nachdrucken).
                daten.naechstes_spiel = spiele[0]
            else:
                # Im Spielplan entscheidet immer das Datum -- auch dann, wenn
                # nur eine einzige Partie eingetragen ist.
                daten.naechstes_spiel, daten.letztes_spiel = spiele_einordnen(spiele)

            if daten.naechstes_spiel is None:
                daten.warnungen.append(
                    f"In {mannschaft.schluessel}_{art}.csv steht kein Spiel, das "
                    f"noch bevorsteht – alle Termine liegen in der Vergangenheit. "
                    f"Bitte den Spielplan ergänzen.")
                return False

            logger().info("%s: nächstes Spiel %s am %s",
                          mannschaft.anzeigename,
                          daten.naechstes_spiel.paarung or "?",
                          daten.naechstes_spiel.datum or "ohne Datum")
            return True

        logger().info("Kein Spielplan für %s – Gegner und Anstoß bleiben leer.",
                      mannschaft.schluessel)
        daten.warnungen.append(
            f"Weder {mannschaft.schluessel}_spielplan.csv noch "
            f"{mannschaft.schluessel}_naechstes_spiel.csv gefunden – "
            f"Gegner, Datum und Anstoß fehlen im Heft.")
        return False

    # -- Gegnerkader --------------------------------------------------------

    def _gegnerkader(self, mannschaft: Mannschaft, daten: MannschaftsDaten) -> None:
        """Sucht den Kader des naechsten Gegners.

        Zwei Ablagen sind moeglich -- die erste ist die sichere:

        * ``<team>_gegner_<gegnername>.csv`` -- je Gegner eine Datei, z. B.
          ``herren1_gegner_sg-alerheim.csv``. Einmal je Saison fuer alle
          Ligagegner angelegt, passt danach immer die richtige Liste.
        * ``<team>_gegner_spieler.csv`` -- eine einzige Datei, die vor jedem
          Heft von Hand ausgetauscht wird.

        Beim zweiten Weg kann die Liste unbemerkt zum falschen Gegner
        gehoeren. Deshalb wird dann ausdruecklich darauf hingewiesen.
        """
        gegner = daten.naechstes_spiel.gegner if daten.naechstes_spiel else ""

        if gegner:
            datei = self.ordner / f"{mannschaft.schluessel}_gegner_{_slug(gegner)}.csv"
            if datei.exists():
                daten.gegner_spieler = [SpielerZeile.aus_csv(z)
                                        for z in csv_lesen(datei)]
                logger().info("Gegnerkader aus %s (%d Spieler).",
                              datei.name, len(daten.gegner_spieler))
                return

        zeilen = self._lesen(mannschaft, "gegner_spieler", daten, still=True)
        if not zeilen:
            if gegner:
                daten.warnungen.append(
                    f"Kein Kader für {gegner} hinterlegt – die Seite "
                    f"„Vorstellung Gegner“ bleibt leer. Erwartet wird "
                    f"{mannschaft.schluessel}_gegner_{_slug(gegner)}.csv")
            return

        daten.gegner_spieler = [SpielerZeile.aus_csv(z) for z in zeilen]
        if gegner:
            daten.warnungen.append(
                f"Der Gegnerkader stammt aus der allgemeinen Datei "
                f"{mannschaft.schluessel}_gegner_spieler.csv. Bitte prüfen, ob "
                f"die Spieler wirklich zu {gegner} gehören – die Datei wird "
                f"nicht automatisch zum Gegner passend gewechselt. "
                f"Dauerhafte Lösung: je Gegner eine Datei "
                f"{mannschaft.schluessel}_gegner_{_slug(gegner)}.csv anlegen.")

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

    @staticmethod
    def _dateiname_gegner(gegner: str) -> str:
        return _slug(gegner)

    def _eigener_kern(self) -> str:
        """Kurzform des Vereinsnamens zum Hervorheben eigener Zeilen."""
        kern = (self.vereinsname or "").replace("SV", "").replace("e.V.", "").strip()
        return kern.split("-")[0].strip()


def _slug(name: str) -> str:
    """'SG Alerheim' -> 'sg-alerheim'  (fuer Dateinamen je Gegner)."""
    text = (name or "").lower()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(alt, neu)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")
