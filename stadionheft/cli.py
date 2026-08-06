"""Kommandozeile.

Fuer Administratoren und fuer automatische Ablaeufe (z. B. ein Aufgabenplan
auf der NAS). Normale Benutzer verwenden die Weboberflaeche.

    python -m stadionheft.cli pruefen
    python -m stadionheft.cli mannschaften
    python -m stadionheft.cli erstellen --mannschaften herren1,damen1
    python -m stadionheft.cli erstellen --snapshot daten/05_ausgaben/xy_snapshot.json
    python -m stadionheft.cli probe-fupa
    python -m stadionheft.cli beispieldaten
    python -m stadionheft.cli web
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import BEISPIEL_CONFIG, Konfiguration, STANDARD_CONFIG
from .errors import StadionheftFehler
from .logging_setup import einrichten, logger


def _konfiguration(args) -> Konfiguration:
    k = Konfiguration.laden(args.config)
    einrichten(k.pfad(k.get("protokoll.ordner"), "logs"),
               str(k.get("protokoll.level", "INFO")))
    for warnung in k.warnungen:
        logger().warning("%s", warnung)
    return k


# ---------------------------------------------------------------------------
# Befehle
# ---------------------------------------------------------------------------

def befehl_pruefen(args) -> int:
    """Konfiguration, Vorlagen und NAS pruefen, ohne etwas zu erzeugen."""
    k = _konfiguration(args)
    print(f"Konfiguration : {k.quelle}")
    print(f"Verein        : {k.vereinsname}")
    print(f"Saison        : {k.saison}")
    print(f"Datenquelle   : {k.get('datenquelle.modus')} "
          f"(Ersatz: {k.get('datenquelle.fallback_modus') or 'keine'})")
    print()

    print("Mannschaften:")
    for m in k.mannschaften.values():
        marke = "x" if m.aktiv else " "
        slug = m.fupa_slug or "KEIN TEAM-BEZEICHNER"
        print(f"  [{marke}] {m.schluessel:<10} {m.anzeigename:<12} "
              f"{m.liga or '(keine Liga)':<28} {slug}")
    print()

    print("Ordner:")
    for name, pfad in (("Eingaben", k.eingabe_ordner),
                       ("Werbung", k.werbung_ordner),
                       ("Zwischenergebnisse", k.arbeits_ordner),
                       ("Ausgaben", k.ausgabe_ordner)):
        print(f"  {'OK ' if pfad.exists() else 'FEHLT'}  {name:<20} {pfad}")

    logo = k.logo_pfad
    print(f"  {'OK ' if logo.exists() else 'FEHLT'}  {'Vereinswappen':<20} {logo}")
    print()

    from .storage.nas import NasAblage
    erreichbar, meldung = NasAblage(k).erreichbar()
    print(f"NAS: {'OK' if erreichbar else 'PROBLEM'} – {meldung}")

    if k.warnungen:
        print("\nHinweise:")
        for warnung in k.warnungen:
            print(f"  - {warnung}")

    print("\nKonfiguration ist gueltig.")
    return 0


def befehl_mannschaften(args) -> int:
    k = _konfiguration(args)
    for m in k.aktive_mannschaften():
        print(f"{m.schluessel}\t{m.anzeigename}\t{m.liga}\t{m.fupa_team_url}")
    return 0


def befehl_erstellen(args) -> int:
    from .build import heft_aus_snapshot, heft_erstellen

    k = _konfiguration(args)

    if args.snapshot:
        ergebnis = heft_aus_snapshot(k, Path(args.snapshot),
                                     dateiname=args.dateiname or "",
                                     nas_hochladen=args.nas)
    else:
        if args.mannschaften:
            auswahl = [t.strip() for t in args.mannschaften.split(",") if t.strip()]
        else:
            auswahl = [m.schluessel for m in k.aktive_mannschaften()]
        for name in auswahl:
            k.mannschaft(name)      # wirft bei unbekanntem Schluessel
        ergebnis = heft_erstellen(
            k, auswahl,
            spieltag=args.spieltag or "",
            datenquelle=args.quelle,
            dateiname=args.dateiname or "",
            erzeugt_von=args.benutzer or "Kommandozeile",
            titelspiel_von=args.titelspiel or "",
            nas_hochladen=args.nas,
        )

    print()
    print(f"Stadionheft erstellt : {ergebnis.pdf}")
    print(f"Seiten               : {ergebnis.seitenzahl}")
    print(f"Datenquelle          : {ergebnis.verwendete_quelle}")
    if ergebnis.snapshot:
        print(f"Snapshot             : {ergebnis.snapshot}")
    if ergebnis.nas_ziel:
        print(f"Auf NAS              : {ergebnis.nas_ziel}")
    if ergebnis.warnungen:
        print("\nHinweise:")
        for warnung in ergebnis.warnungen:
            print(f"  - {warnung}")
    return 0


def befehl_probe(args) -> int:
    """Prueft, welche FuPa-Adressen antworten und was sich daraus lesen laesst."""
    from .sources.fupa_api import bericht_als_text, probe_fupa

    k = _konfiguration(args)
    bericht = probe_fupa(k, args.mannschaft)

    print(bericht_als_text(bericht))
    print(f"Dieser Bericht und die Rohantworten liegen in:\n  {bericht['ablage']}")
    return 0


def befehl_beispieldaten(args) -> int:
    """Legt CSV-Vorlagen fuer die manuelle Eingabe an."""
    from .tools.beispieldaten import vorlagen_schreiben

    k = _konfiguration(args)
    dateien = vorlagen_schreiben(k, nur_vorlagen=not args.mit_daten)
    print(f"{len(dateien)} Dateien geschrieben nach {k.eingabe_ordner}:")
    for datei in dateien:
        print(f"  {datei.name}")
    return 0


def befehl_uebernehmen(args) -> int:
    """Seiten aus einem bestehenden Heft als feste PDF-Seiten uebernehmen."""
    from .tools.seiten_uebernehmen import (VORSCHLAEGE, einzeln_zerlegen,
                                           uebernehmen)

    k = _konfiguration(args)

    if args.einzeln:
        if not args.seiten:
            print("Bitte --seiten angeben, z. B. --seiten 4-11")
            return 1
        ordner = (Path(args.ordner) if args.ordner
                  else k.werbung_ordner / (args.als or "block"))
        dateien = einzeln_zerlegen(k, args.aus, args.seiten, ordner)
        print(f"{len(dateien)} Einzelanzeigen geschrieben nach {ordner}:")
        for datei in dateien:
            print(f"  {datei.name}")
        print("\nJetzt sinnvoll umbenennen, z. B.:")
        print("  010_teamshop.pdf")
        print("  020_jako-katalog-1.pdf")
        print("\nBefristete Anzeigen bekommen das Enddatum in den Namen:")
        print("  010_bayern-spiel__bis_2026-08-01.pdf")
        print("  -> faellt ab dem 02.08.2026 automatisch aus dem Heft.")
        print("\nIm Heftplan wird der Ordner so eingebunden:")
        print("  - typ: werbeblock")
        print(f"    ordner: \"02_werbung/{ordner.name}\"")
        return 0

    if args.alles:
        auftraege = [(name, seiten, titel) for name, seiten, titel in VORSCHLAEGE]
        print("Uebernehme die ueblichen Seiten aus dem alten Heft.")
        print("(Seitenzahlen der Ausgabe vom 29.07.2026 - bei abweichendem")
        print(" Heftaufbau bitte einzeln mit --seiten arbeiten.)\n")
    else:
        if not args.seiten or not args.als:
            print("Bitte --seiten und --als angeben, oder --alles verwenden.\n")
            print("Ueblich sind:")
            for name, seiten, titel in VORSCHLAEGE:
                print(f"  --seiten {seiten:<6} --als {name:<18} # {titel}")
            return 1
        auftraege = [(args.als, args.seiten, "")]

    for name, seiten, titel in auftraege:
        try:
            ziel, angaben = uebernehmen(k, args.aus, seiten, name)
        except StadionheftFehler as fehler:
            print(f"  UEBERSPRUNGEN {name:<18} {fehler.benutzer_text}")
            continue
        breite, hoehe = angaben["endformat_mm"]
        print(f"  OK {name:<18} Seite(n) {seiten:<6} -> {ziel.name} "
              f"({angaben['seiten']} S., {breite} x {hoehe} mm)"
              + (f"  # {titel}" if titel else ""))

    print(f"\nAbgelegt in: {k.werbung_ordner}")
    print("\nIm Heftplan (config/heftplan.yaml) werden diese Dateien mit")
    print("  - typ: pdf")
    print("    quelle: \"02_werbung/<dateiname>.pdf\"")
    print("eingebunden. Die Beispieldatei heftplan.example.yaml zeigt es.")
    return 0


def befehl_web(args) -> int:
    from .web import app_erzeugen

    k = _konfiguration(args)
    app = app_erzeugen(k)
    print(f"Weboberflaeche laeuft auf http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


def befehl_init(args) -> int:
    """Legt config/config.yaml aus der Beispieldatei an."""
    if STANDARD_CONFIG.exists() and not args.ueberschreiben:
        print(f"{STANDARD_CONFIG} existiert bereits. Mit --ueberschreiben erzwingen.")
        return 1
    STANDARD_CONFIG.write_text(BEISPIEL_CONFIG.read_text(encoding="utf-8"),
                               encoding="utf-8")
    from .config import BEISPIEL_HEFTPLAN, STANDARD_HEFTPLAN
    if not STANDARD_HEFTPLAN.exists():
        STANDARD_HEFTPLAN.write_text(BEISPIEL_HEFTPLAN.read_text(encoding="utf-8"),
                                     encoding="utf-8")
    print(f"Angelegt: {STANDARD_CONFIG}")
    print(f"Angelegt: {STANDARD_HEFTPLAN}")
    print("\nBitte jetzt die mit TODO markierten Werte ausfuellen.")
    return 0


# ---------------------------------------------------------------------------

def parser_bauen() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stadionheft",
        description="Stadionheft-Generator des SV Wörnitzstein-Berg")
    p.add_argument("--config", help="Pfad zu config.yaml "
                                    "(Standard: config/config.yaml)")
    unter = p.add_subparsers(dest="befehl", required=True)

    b = unter.add_parser("init", help="config.yaml aus der Beispieldatei anlegen")
    b.add_argument("--ueberschreiben", action="store_true")
    b.set_defaults(funktion=befehl_init)

    b = unter.add_parser("pruefen", help="Konfiguration, Ordner und NAS pruefen")
    b.set_defaults(funktion=befehl_pruefen)

    b = unter.add_parser("mannschaften", help="konfigurierte Mannschaften auflisten")
    b.set_defaults(funktion=befehl_mannschaften)

    b = unter.add_parser("erstellen", help="Stadionheft erzeugen")
    b.add_argument("--mannschaften",
                   help="Kommaliste, z. B. herren1,damen1 (Standard: alle aktiven)")
    b.add_argument("--spieltag", help="Freitext, z. B. '3. Spieltag'")
    b.add_argument("--quelle", choices=["api", "manuell", "demo"],
                   help="Datenquelle abweichend von der Konfiguration")
    b.add_argument("--dateiname", help="Dateiname der Ausgabe")
    b.add_argument("--benutzer", help="Name fuer das Protokoll/Impressum")
    b.add_argument("--titelspiel", help="Mannschaft, deren Spiel auf den Titel kommt")
    b.add_argument("--snapshot", help="fruehere Snapshot-Datei erneut bauen")
    nas = b.add_mutually_exclusive_group()
    nas.add_argument("--nas", dest="nas", action="store_true", default=None,
                     help="auf die NAS hochladen")
    nas.add_argument("--ohne-nas", dest="nas", action="store_false",
                     help="NAS-Upload ueberspringen")
    b.set_defaults(funktion=befehl_erstellen)

    b = unter.add_parser("probe-fupa",
                         help="FuPa-Endpunkte testen und Rohantworten speichern")
    b.add_argument("--mannschaft", help="Schluessel, z. B. herren1")
    b.set_defaults(funktion=befehl_probe)

    b = unter.add_parser("beispieldaten",
                         help="CSV-Vorlagen fuer die manuelle Eingabe schreiben")
    b.add_argument("--mit-daten", action="store_true",
                   help="mit ausgefuellten Beispielwerten statt nur Kopfzeilen")
    b.set_defaults(funktion=befehl_beispieldaten)

    b = unter.add_parser(
        "seiten-uebernehmen",
        help="Seiten aus einem bestehenden Heft als feste PDF-Seiten uebernehmen")
    b.add_argument("--aus", required=True,
                   help="Pfad zum bestehenden Stadionheft (PDF)")
    b.add_argument("--seiten", help="z. B. 24-25 oder 24,27")
    b.add_argument("--als", help="Dateiname ohne Endung, z. B. kontaktlisten")
    b.add_argument("--alles", action="store_true",
                   help="alle ueblichen Seiten auf einmal (Kontakte, Impressum, "
                        "Werbung, Ruecktitel)")
    b.add_argument("--einzeln", action="store_true",
                   help="Seitenbereich in einzelne Anzeigen-PDFs zerlegen "
                        "(fuer typ: werbeblock)")
    b.add_argument("--ordner", help="Zielordner fuer --einzeln")
    b.set_defaults(funktion=befehl_uebernehmen)

    b = unter.add_parser("web", help="Weboberflaeche starten")
    b.add_argument("--host", default="0.0.0.0")
    b.add_argument("--port", type=int, default=8080)
    b.add_argument("--debug", action="store_true")
    b.set_defaults(funktion=befehl_web)

    return p


def main(argv: list[str] | None = None) -> int:
    args = parser_bauen().parse_args(argv)
    einrichten()
    try:
        return args.funktion(args)
    except StadionheftFehler as fehler:
        print(f"\nFEHLER: {fehler.benutzer_text}", file=sys.stderr)
        if fehler.hinweis:
            print(f"\n{fehler.hinweis}", file=sys.stderr)
        logger().debug("Technisch: %s", fehler.technisch)
        return 2
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
