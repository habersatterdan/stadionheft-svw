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
    """Prueft, welche FuPa-Endpunkte tatsaechlich antworten."""
    from .sources.fupa_api import probe_fupa

    k = _konfiguration(args)
    bericht = probe_fupa(k, args.mannschaft)

    print(f"Basis-URL   : {bericht['basis_url']}")
    print(f"Mannschaft  : {bericht['mannschaft']} ({bericht['team_slug']})")
    print(f"Rohantworten: {bericht['ablage']}")
    print()
    for name, eintrag in bericht["ergebnisse"].items():
        print(f"  {name:<12} {str(eintrag.get('status', '-')):<5} "
              f"{eintrag.get('bewertung', '')}")
        if eintrag.get("beispiel_felder"):
            felder = ", ".join(eintrag["beispiel_felder"][:12])
            print(f"               Felder: {felder}")
    print()
    print("Naechster Schritt: die gespeicherten JSON-Dateien ansehen und in")
    print("stadionheft/sources/fupa_api.py die Feldnamen ergaenzen, falls noetig.")
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
