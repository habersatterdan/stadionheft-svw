"""Kommandozeile des Kickbase-Beraters.

Fuer alles, was ohne Browser gehen soll -- etwa ein naechtlicher Abruf per
Cron oder eine schnelle Antwort auf "wen soll ich verkaufen?" direkt im
Terminal::

    kickbase abruf
    kickbase team
    kickbase markt
    kickbase kandidaten --position 4 --hoechstpreis 12
    kickbase spieler 1234
    kickbase web
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .analyse.bewertung import Referenzwerte, bewerten
from .config import Konfiguration
from .dienst import Berater
from .errors import KickbaseFehler
from .logging_setup import einrichten, logger
from .models import POSITIONEN, Bewertung

#: Zeichen statt Farben -- die laufen auch in Protokolldateien und auf der NAS.
_ZEICHEN = {
    "kaufen": "++", "beobachten": " +", "halten": "  ",
    "pruefen": " -", "verkaufen": "--",
}


def _euro(betrag: float) -> str:
    if abs(betrag) >= 1_000_000:
        return f"{betrag / 1_000_000:>6.2f} Mio".replace(".", ",")
    return f"{betrag / 1000:>6.0f} Tsd"


def _zeile(bewertung: Bewertung, mit_preis: bool = False) -> str:
    s = bewertung.spieler
    preis = s.angebotspreis if (mit_preis and s.angebotspreis) else s.marktwert
    return (f"{_ZEICHEN.get(bewertung.stufe, '  ')} "
            f"{bewertung.gesamtpunkte:>6.1f}  "
            f"{s.kurzname[:22]:<22} "
            f"{s.positions_name[:10]:<10} "
            f"{(s.team_name or '?')[:18]:<18} "
            f"{_euro(preis)}  "
            f"{bewertung.empfehlung}")


def _tabelle_ausgeben(liste: Sequence[Bewertung], ueberschrift: str,
                      mit_preis: bool = False, ausfuehrlich: bool = False,
                      grenze: int = 0) -> None:
    print()
    print(ueberschrift)
    print("-" * len(ueberschrift))
    if not liste:
        print("  (nichts vorhanden)")
        return
    for bewertung in (liste[:grenze] if grenze else liste):
        print(_zeile(bewertung, mit_preis))
        if bewertung.uebersteuerung:
            print(f"        ! {bewertung.uebersteuerung}")
        if ausfuehrlich:
            for kennzahl in bewertung.staerkste_gruende:
                print(f"          - {kennzahl.name}: {kennzahl.begruendung}")


def _berater(args) -> Berater:
    konfiguration = Konfiguration.laden(args.config)
    einrichten(konfiguration.pfad(konfiguration.get("protokoll.ordner"), "logs"),
               "DEBUG" if args.ausfuehrlich else
               str(konfiguration.get("protokoll.level", "INFO")))
    for warnung in konfiguration.warnungen:
        logger().warning(warnung)
    return Berater(konfiguration)


# -- Befehle ---------------------------------------------------------------


def befehl_abruf(args) -> int:
    berater = _berater(args)
    ergebnis = berater.abrufen()
    print(ergebnis.get("meldung", ""))
    if not ergebnis.get("erfolgreich"):
        if ergebnis.get("hinweis"):
            print(f"Hinweis: {ergebnis['hinweis']}")
        return 1
    print(f"Dauer: {ergebnis.get('dauer_s', 0)} Sekunden.")
    return 0


def befehl_team(args) -> int:
    berater = _berater(args)
    bericht = berater.bericht()
    for warnung in bericht.warnungen:
        print(f"Hinweis: {warnung}")
    print(f"\nLiga: {bericht.liga_name or 'unbekannt'} · "
          f"Budget: {_euro(bericht.budget)} €")

    if bericht.ausfaelle:
        _tabelle_ausgeben(bericht.ausfaelle, "Ausfälle und Wackelkandidaten",
                          ausfuehrlich=args.ausfuehrlich)
    _tabelle_ausgeben(bericht.verkaufskandidaten, "Verkaufsvorschläge",
                      ausfuehrlich=args.ausfuehrlich)
    _tabelle_ausgeben(bericht.eigene, "Kompletter Kader",
                      ausfuehrlich=args.ausfuehrlich)
    return 0


def befehl_markt(args) -> int:
    berater = _berater(args)
    bericht = berater.bericht()
    _tabelle_ausgeben(bericht.transfermarkt, "Transfermarkt (Bewertung gegen Angebotspreis)",
                      mit_preis=True, ausfuehrlich=args.ausfuehrlich)
    return 0


def befehl_kandidaten(args) -> int:
    berater = _berater(args)
    bericht = berater.bericht()
    liste = bericht.kandidaten
    if args.position:
        liste = [b for b in liste if b.spieler.position == args.position]
    if args.hoechstpreis:
        grenze = args.hoechstpreis * 1_000_000
        liste = [b for b in liste if b.spieler.marktwert <= grenze]
    if args.nur_fit:
        liste = [b for b in liste if b.spieler.einsatzbereit]

    ueberschrift = "Kaufkandidaten"
    if args.position:
        ueberschrift += f" – {POSITIONEN.get(args.position, args.position)}"
    _tabelle_ausgeben(liste, ueberschrift, ausfuehrlich=args.ausfuehrlich,
                      grenze=args.anzahl)
    return 0


def befehl_spieler(args) -> int:
    berater = _berater(args)
    alle = berater.speicher.spieler_laden()
    gesucht = str(args.spieler).lower()
    treffer = [s for s in alle
               if s.id == gesucht or gesucht in s.name.lower()]
    if not treffer:
        print(f"Kein Spieler zu '{args.spieler}' gefunden.")
        return 1
    if len(treffer) > 1 and not any(s.id == gesucht for s in treffer):
        print("Mehrere Treffer – bitte genauer angeben:")
        for s in treffer[:15]:
            print(f"  {s.id:>8}  {s.name} ({s.team_name})")
        return 1

    spieler = next((s for s in treffer if s.id == gesucht), treffer[0])
    referenz = Referenzwerte.aus_spielern(alle)
    bewertung = bewerten(spieler, referenz, berater.k, berater.ligalage(),
                         spieler.angebotspreis or None)

    print(f"\n{spieler.name} – {spieler.team_name or 'Verein unbekannt'} "
          f"({spieler.positions_name})")
    print(f"Marktwert {_euro(spieler.marktwert)} € · "
          f"Ø {spieler.punkte_schnitt} Punkte · Status: {spieler.status_name}")
    print(f"\nEmpfehlung: {bewertung.empfehlung} "
          f"(Note {bewertung.gesamtpunkte:.1f})")
    if bewertung.uebersteuerung:
        print(f"Vorrangregel: {bewertung.uebersteuerung}")
    for warnung in bewertung.warnungen:
        print(f"Hinweis: {warnung}")

    print("\nKennzahlen:")
    for kennzahl in bewertung.kennzahlen:
        print(f"  {kennzahl.name:<18} {kennzahl.punkte:>6.0f} "
              f"(Gewicht {kennzahl.gewicht:.1f})  {kennzahl.anzeige}")
        print(f"      {kennzahl.begruendung}")
    return 0


def befehl_web(args) -> int:
    from .web import app_erzeugen

    konfiguration = Konfiguration.laden(args.config)
    app = app_erzeugen(konfiguration)
    print(f"Kickbase-Berater läuft auf http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
    return 0


# -- Argumente -------------------------------------------------------------


def parser_bauen() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kickbase",
        description="Analyse und Kauf-/Verkaufshinweise für Kickbase.")
    parser.add_argument("--config", help="Pfad zu einer eigenen kickbase.yaml")
    parser.add_argument("-v", "--ausfuehrlich", action="store_true",
                        help="Begründungen und ausführliches Protokoll anzeigen")

    unter = parser.add_subparsers(dest="befehl", required=True)

    p = unter.add_parser("abruf", help="Daten von Kickbase und OpenLigaDB holen")
    p.set_defaults(funktion=befehl_abruf)

    p = unter.add_parser("team", help="Eigenen Kader bewerten")
    p.set_defaults(funktion=befehl_team)

    p = unter.add_parser("markt", help="Transfermarkt der Liga bewerten")
    p.set_defaults(funktion=befehl_markt)

    p = unter.add_parser("kandidaten", help="Kaufkandidaten aus der ganzen Liga")
    p.add_argument("--position", type=int, choices=sorted(POSITIONEN),
                   help="1 Torwart, 2 Abwehr, 3 Mittelfeld, 4 Sturm")
    p.add_argument("--hoechstpreis", type=float,
                   help="Obergrenze für den Marktwert in Millionen")
    p.add_argument("--nur-fit", dest="nur_fit", action="store_true",
                   help="Verletzte und Gesperrte ausblenden")
    p.add_argument("--anzahl", type=int, default=25,
                   help="Wie viele Zeilen (Standard: 25)")
    p.set_defaults(funktion=befehl_kandidaten)

    p = unter.add_parser("spieler", help="Einen Spieler im Detail ansehen")
    p.add_argument("spieler", help="Spieler-ID oder Teil des Namens")
    p.set_defaults(funktion=befehl_spieler)

    p = unter.add_parser("web", help="Weboberfläche starten")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8090)
    p.set_defaults(funktion=befehl_web)

    return parser


def main(argumente: Sequence[str] | None = None) -> int:
    args = parser_bauen().parse_args(argumente)
    try:
        return int(args.funktion(args))
    except KickbaseFehler as fehler:
        print(f"\nFehler: {fehler.benutzer_text}", file=sys.stderr)
        if fehler.hinweis:
            print(f"Hinweis: {fehler.hinweis}", file=sys.stderr)
        if args.ausfuehrlich:
            print(f"Technisch: {fehler.technisch}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
