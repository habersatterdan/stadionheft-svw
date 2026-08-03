"""Eingebaute Beispieldaten.

Damit laesst sich das Programm sofort vorfuehren -- ohne Internet, ohne
CSV-Dateien, ohne FuPa. Fuer die Herren 1 sind es die echten Zahlen aus der
Ausgabe vom 29.07.2026; das erzeugte Heft laesst sich also direkt mit dem
bisherigen vergleichen. Fuer alle anderen Mannschaften werden plausible
Platzhalterwerte erzeugt.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from ..config import Konfiguration, Mannschaft
from ..models import MannschaftsDaten, Spiel, SpielerZeile, TabellenZeile, TorjaegerZeile
from .base import basis_daten

DATEN_DATEI = Path(__file__).with_name("demo_daten.json")

_PLATZHALTER_GEGNER = [
    "TSV Nachbardorf", "SV Beispielhausen", "FC Musterstadt", "SG Testtal",
    "TSV Vorlage", "SV Demokirchen", "FC Probeberg", "TSV Musterbach",
    "SV Beispielried", "FC Vorlagenheim", "SG Demoau", "TSV Testheim",
]
_PLATZHALTER_SPIELER = [
    "Anna Beispiel", "Ben Muster", "Clara Demo", "David Probe", "Emma Test",
    "Felix Vorlage", "Greta Beispiel", "Hannes Muster", "Ida Demo",
    "Jonas Probe", "Klara Test", "Lukas Vorlage", "Mia Beispiel",
    "Noah Muster", "Olivia Demo", "Paul Probe",
]


class DemoQuelle:
    name = "demo"

    def __init__(self, konfiguration: Konfiguration) -> None:
        self.konfiguration = konfiguration
        try:
            self.daten = json.loads(DATEN_DATEI.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.daten = {}

    def hole(self, mannschaft: Mannschaft) -> MannschaftsDaten:
        eintrag = self.daten.get(mannschaft.schluessel)
        if eintrag:
            return self._aus_json(mannschaft, eintrag)
        return self._erfinden(mannschaft)

    # -- Echte Beispieldaten ------------------------------------------------

    def _aus_json(self, mannschaft: Mannschaft, eintrag: dict) -> MannschaftsDaten:
        daten = basis_daten(mannschaft, self.name)
        daten.tabelle = [
            TabellenZeile(platz=z[0], mannschaft=z[1], spiele=z[2], siege=z[3],
                          unentschieden=z[4], niederlagen=z[5], tore=z[6],
                          gegentore=z[7], punkte=z[8], zusatz=z[9],
                          eigene="wörnitzstein" in z[1].lower())
            for z in eintrag.get("tabelle", [])
        ]
        daten.torjaeger = [
            TorjaegerZeile(platz=z[0], spieler=z[1], mannschaft=z[2], tore=z[3],
                           vorlagen=z[4], spiele=z[5],
                           eigene="wörnitzstein" in z[2].lower())
            for z in eintrag.get("torjaeger", [])
        ]
        daten.spieler = [self._spieler_zeile(z) for z in eintrag.get("spieler", [])]
        daten.gegner_spieler = [self._spieler_zeile(z)
                                for z in eintrag.get("gegner_spieler", [])]
        if eintrag.get("naechstes_spiel"):
            daten.naechstes_spiel = Spiel.from_dict(eintrag["naechstes_spiel"])
        if eintrag.get("letztes_spiel"):
            daten.letztes_spiel = Spiel.from_dict(eintrag["letztes_spiel"])
        daten.spielbericht = eintrag.get("spielbericht", "")
        daten.warnungen.append(
            "Beispieldaten (Demo-Modus) - diese Zahlen sind nicht aktuell.")
        return daten

    @staticmethod
    def _spieler_zeile(z: list) -> SpielerZeile:
        getroffen, _, gesamt = str(z[5]).partition("/")
        return SpielerZeile(
            platz=z[0], spieler=z[1], spiele=z[2], tore=z[3], vorlagen=z[4],
            elfmeter_getroffen=int(getroffen or 0), elfmeter_gesamt=int(gesamt or 0),
            gelb=z[6], gelb_rot=z[7], rot=z[8], eingewechselt=z[9],
            ausgewechselt=z[10], minuten=z[11],
        )

    # -- Erfundene Platzhalterdaten -----------------------------------------

    def _erfinden(self, mannschaft: Mannschaft) -> MannschaftsDaten:
        daten = basis_daten(mannschaft, self.name)
        eigener = self.konfiguration.vereinsname or "SV Wörnitzstein-Berg"
        namen = [eigener, *_PLATZHALTER_GEGNER]

        for nr, name in enumerate(namen, start=1):
            siege = max(0, 8 - nr // 2)
            unentschieden = nr % 3
            niederlagen = max(0, 10 - siege - unentschieden)
            daten.tabelle.append(TabellenZeile(
                platz=nr, mannschaft=name,
                spiele=siege + unentschieden + niederlagen,
                siege=siege, unentschieden=unentschieden, niederlagen=niederlagen,
                tore=30 - nr, gegentore=8 + nr, punkte=siege * 3 + unentschieden,
                eigene=(nr == 1),
            ))

        for nr, name in enumerate(_PLATZHALTER_SPIELER[:10], start=1):
            daten.torjaeger.append(TorjaegerZeile(
                platz=nr, spieler=name,
                mannschaft=eigener if nr % 3 == 0 else _PLATZHALTER_GEGNER[nr % 6],
                tore=max(1, 12 - nr), vorlagen=max(0, 5 - nr // 2), spiele=10,
                eigene=(nr % 3 == 0),
            ))

        for nr, name in enumerate(_PLATZHALTER_SPIELER, start=1):
            daten.spieler.append(SpielerZeile(
                platz=nr, spieler=name, spiele=max(0, 11 - nr // 2),
                tore=max(0, 6 - nr // 2), vorlagen=max(0, 4 - nr // 3),
                elfmeter_getroffen=1 if nr == 3 else 0,
                elfmeter_gesamt=1 if nr == 3 else 0,
                gelb=nr % 3, gelb_rot=0, rot=0,
                eingewechselt=nr % 4, ausgewechselt=nr % 5,
                minuten=max(0, 900 - nr * 45),
            ))

        anstoss = (datetime.now() + timedelta(days=3)).replace(
            hour=15, minute=0, second=0, microsecond=0)
        daten.naechstes_spiel = Spiel(
            heim=f"{self.konfiguration.get('verein.kurzname', 'SVW')} "
                 f"{mannschaft.anzeigename}",
            gast=_PLATZHALTER_GEGNER[0],
            wettbewerb=mannschaft.liga or "Beispielliga",
            anstoss=anstoss.isoformat(),
            spielort="Sportgelände Wörnitzstein",
            heimspiel=True,
        )
        daten.warnungen.append(
            f"Fuer {mannschaft.anzeigename} liegen nur erfundene Beispieldaten vor.")
        return daten
