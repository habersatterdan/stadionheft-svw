"""Schreibt CSV-Vorlagen fuer die manuelle Eingabe.

Damit muss niemand die Spaltennamen aus der Dokumentation abtippen:
``python -m stadionheft.cli beispieldaten`` legt fuer jede aktive Mannschaft
die passenden Dateien an -- entweder nur mit Kopfzeile oder gleich mit
Beispielwerten zum Ueberschreiben.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from ..config import Konfiguration
from ..sources.demo import DemoQuelle

SPALTEN: dict[str, list[str]] = {
    "tabelle": ["platz", "mannschaft", "spiele", "siege", "unentschieden",
                "niederlagen", "tore", "gegentore", "punkte", "zusatz"],
    "torjaeger": ["platz", "spieler", "mannschaft", "tore", "vorlagen", "spiele"],
    "spieler": ["platz", "spieler", "spiele", "tore", "vorlagen", "elfmeter",
                "gelb", "gelb_rot", "rot", "ein", "aus", "minuten"],
    "gegner_spieler": ["platz", "spieler", "spiele", "tore", "vorlagen", "elfmeter",
                       "gelb", "gelb_rot", "rot", "ein", "aus", "minuten"],
    "spielplan": ["heim", "gast", "wettbewerb", "datum", "uhrzeit",
                  "spielort", "heimspiel", "spieltag", "ergebnis"],
}


def _csv_text(spalten: list[str], zeilen: list[list]) -> str:
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";", lineterminator="\n")
    schreiber.writerow(spalten)
    for zeile in zeilen:
        schreiber.writerow(zeile)
    return puffer.getvalue()


def vorlagen_schreiben(konfiguration: Konfiguration,
                       nur_vorlagen: bool = True) -> list[Path]:
    """Legt die CSV-Dateien im Eingabeordner an (vorhandene bleiben unberuehrt)."""
    ordner = konfiguration.eingabe_ordner
    ordner.mkdir(parents=True, exist_ok=True)
    demo = DemoQuelle(konfiguration)
    geschrieben: list[Path] = []

    for mannschaft in konfiguration.aktive_mannschaften():
        daten = demo.hole(mannschaft)
        inhalte: dict[str, list[list]] = {art: [] for art in SPALTEN}

        if not nur_vorlagen:
            inhalte["tabelle"] = [
                [z.platz, z.mannschaft, z.spiele, z.siege, z.unentschieden,
                 z.niederlagen, z.tore, z.gegentore, z.punkte, z.zusatz]
                for z in daten.tabelle]
            inhalte["torjaeger"] = [
                [z.platz, z.spieler, z.mannschaft, z.tore, z.vorlagen, z.spiele]
                for z in daten.torjaeger]
            inhalte["spieler"] = [
                [z.platz, z.spieler, z.spiele, z.tore, z.vorlagen, z.elfmeter,
                 z.gelb, z.gelb_rot, z.rot, z.eingewechselt, z.ausgewechselt,
                 z.minuten]
                for z in daten.spieler]
            inhalte["gegner_spieler"] = [
                [z.platz, z.spieler, z.spiele, z.tore, z.vorlagen, z.elfmeter,
                 z.gelb, z.gelb_rot, z.rot, z.eingewechselt, z.ausgewechselt,
                 z.minuten]
                for z in daten.gegner_spieler]
            for spiel in (daten.letztes_spiel, daten.naechstes_spiel):
                if spiel:
                    inhalte["spielplan"].append([
                        spiel.heim, spiel.gast, spiel.wettbewerb, spiel.datum,
                        spiel.uhrzeit.replace(" Uhr", ""), spiel.spielort,
                        "ja" if spiel.heimspiel else "nein", spiel.spieltag,
                        spiel.ergebnis])

        for art, spalten in SPALTEN.items():
            ziel = ordner / f"{mannschaft.schluessel}_{art}.csv"
            if ziel.exists():
                continue
            ziel.write_text(_csv_text(spalten, inhalte[art]), encoding="utf-8-sig")
            geschrieben.append(ziel)

    vorwort = ordner / "vorwort.md"
    if not vorwort.exists():
        vorwort.write_text(
            "Liebe Gäste, liebe Fans,\n\n"
            "hier steht der Text für das Vorwort. Die erste kurze Zeile wird "
            "als Überschrift gesetzt, danach folgen ganz normale Absätze – "
            "getrennt durch eine Leerzeile.\n\n"
            "Der Text läuft automatisch zweispaltig und bei Bedarf auf die "
            "nächste Seite weiter.\n",
            encoding="utf-8")
        geschrieben.append(vorwort)

    liesmich = ordner / "LIESMICH.txt"
    if not liesmich.exists():
        liesmich.write_text(_liesmich(konfiguration), encoding="utf-8")
        geschrieben.append(liesmich)

    return geschrieben


def _liesmich(konfiguration: Konfiguration) -> str:
    zeilen = [
        "EINGABEORDNER FÜR DAS STADIONHEFT",
        "=" * 40,
        "",
        "In diesem Ordner liegen die Daten, die von Hand gepflegt werden.",
        "Alle CSV-Dateien lassen sich direkt in Excel öffnen und bearbeiten.",
        "Beim Speichern bitte das Format 'CSV UTF-8 (durch Trennzeichen",
        "getrennt)' wählen.",
        "",
        "Dateien je Mannschaft:",
        "",
    ]
    for mannschaft in konfiguration.aktive_mannschaften():
        zeilen.append(f"  {mannschaft.anzeigename} ({mannschaft.schluessel}):")
        for art in SPALTEN:
            zeilen.append(f"    {mannschaft.schluessel}_{art}.csv")
        zeilen.append(f"    {mannschaft.schluessel}_spielbericht.md   (optional)")
        zeilen.append("")
    zeilen += [
        "Weitere Dateien:",
        "  vorwort.md      Text für die Vorwortseite",
        "  titelbild.jpg   Foto für die Titelseite (optional)",
        "",
        "Fehlt eine Datei, bleibt nur die betreffende Seite leer – das Heft",
        "wird trotzdem erzeugt.",
        "",
        "",
        "DER SPIELPLAN ERSPART DIR DIE MEISTE ARBEIT",
        "-" * 43,
        "",
        "In <mannschaft>_spielplan.csv gehören ALLE Spiele der Saison –",
        "eine Zeile je Partie. Das trägt man einmal im Sommer ein.",
        "",
        "Danach schaut das Programm bei jedem Heft auf das heutige Datum und",
        "sucht sich selbst heraus:",
        "  - gegen wen als nächstes gespielt wird (Titelseite, Gegnerseite)",
        "  - wann und wo (Datum, Uhrzeit, Heim oder Auswärts)",
        "  - welches Spiel zuletzt war (für den Spielbericht)",
        "",
        "Beispiel:",
        "",
        "  heim;gast;wettbewerb;datum;uhrzeit;spielort;heimspiel;spieltag;ergebnis",
        "  TG Lauingen;SV Wörnitzstein-Berg;Bezirksliga;26.07.2026;15:00;;nein;1;0:4",
        "  SV Wörnitzstein-Berg;TSV Meitingen;Bezirksliga;29.07.2026;18:30;Wörnitzstein;ja;2;",
        "  SV Wörnitzstein-Berg;SG Alerheim;Bezirksliga;02.08.2026;15:00;Wörnitzstein;ja;3;",
        "",
        "Die Spalte 'ergebnis' bleibt leer, solange nicht gespielt wurde.",
        "Sie wird nur für die Anzeige des letzten Spiels gebraucht – für die",
        "Auswahl der nächsten Partie zählt allein das Datum.",
    ]
    return "\n".join(zeilen) + "\n"
