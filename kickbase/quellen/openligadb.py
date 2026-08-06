"""Spielplan und Tabelle von OpenLigaDB.

OpenLigaDB ist eine frei zugaengliche, gemeinschaftlich gepflegte Datenbank
der Bundesligaspiele. Sie braucht keinen Schluessel und keine Anmeldung und
liefert genau das, was Kickbase nicht hergibt: **wer als naechstes gegen wen
spielt**. Daraus entsteht die Gegnerstaerke -- ein Stuermer vor zwei Spielen
gegen Tabellenletzte ist mehr wert als derselbe Stuermer vor Bayern und
Leverkusen.

Die Vereins-IDs von OpenLigaDB und Kickbase sind verschieden. Verbunden wird
deshalb ueber den Vereinsnamen; :func:`namen_schluessel` macht aus
"1. FC Köln", "FC Koeln" und "1.FC Koln" denselben Suchbegriff.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ..errors import QuelleNichtErreichbarFehler
from ..logging_setup import logger
from .http import DateiCache, HttpQuelle

BASIS_URL = "https://api.openligadb.de"

#: Wortbestandteile, die zur Unterscheidung nichts beitragen.
_FUELLWOERTER = {
    "fc", "sv", "sc", "vfb", "vfl", "tsg", "bsc", "bv", "borussia", "bor",
    "1899", "1", "04", "05", "07", "09", "1846", "1900", "1901", "e", "v",
    "ev", "spvgg", "fsv", "tsv", "sg", "spielvereinigung", "club", "verein",
}


def namen_schluessel(name: str) -> str:
    """Macht aus einem Vereinsnamen einen vergleichbaren Suchbegriff.

    >>> namen_schluessel("1. FC Köln")
    'koeln'
    >>> namen_schluessel("Bor. Mönchengladbach")
    'moenchengladbach'
    """
    text = (name or "").lower().strip()
    text = (text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
                .replace("ß", "ss"))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(z for z in text if not unicodedata.combining(z))
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    teile = [t for t in text.split() if t and t not in _FUELLWOERTER]
    return "".join(teile) or re.sub(r"[^a-z0-9]+", "", text)


@dataclass
class Begegnung:
    """Ein Spiel aus dem Spielplan."""

    spieltag: int
    anstoss: datetime | None
    heim: str
    gast: str
    beendet: bool = False
    tore_heim: int = 0
    tore_gast: int = 0

    def gegner_von(self, verein: str) -> tuple[str, bool] | None:
        """Gibt (Gegner, Heimspiel) zurueck -- oder None, wenn nicht beteiligt."""
        schluessel = namen_schluessel(verein)
        if namen_schluessel(self.heim) == schluessel:
            return self.gast, True
        if namen_schluessel(self.gast) == schluessel:
            return self.heim, False
        return None


@dataclass
class Ligalage:
    """Tabelle und Restspielplan in einer auswertbaren Form."""

    tabelle: dict[str, int] = field(default_factory=dict)      # Schluessel -> Platz
    namen: dict[str, str] = field(default_factory=dict)        # Schluessel -> Anzeigename
    begegnungen: list[Begegnung] = field(default_factory=list)
    aktueller_spieltag: int = 0
    stand: str = ""

    @property
    def mannschaften(self) -> int:
        return max(len(self.tabelle), 18)

    def aufloesen(self, verein: str) -> str:
        """Findet den passenden Schluessel zu einem Vereinsnamen.

        Noetig, weil Kickbase und OpenLigaDB verschieden ausfuehrlich sind:
        "Bayern" bei der einen, "FC Bayern München" bei der anderen Quelle.
        Erst wird exakt gesucht, dann ueber gemeinsame Wortanfaenge -- aber
        nur, wenn das Ergebnis eindeutig ist. Lieber keine Zuordnung als eine
        falsche.
        """
        schluessel = namen_schluessel(verein)
        if not schluessel:
            return ""
        if schluessel in self.namen:
            return schluessel
        for pruefung in (
                lambda k: k.startswith(schluessel) or schluessel.startswith(k),
                lambda k: schluessel in k or k in schluessel):
            treffer = [k for k in self.namen if pruefung(k)]
            if len(treffer) == 1:
                return treffer[0]
        return ""

    def platz(self, verein: str) -> int:
        """Tabellenplatz eines Vereins, 0 wenn unbekannt."""
        return self.tabelle.get(self.aufloesen(verein), 0)

    def naechste_gegner(self, verein: str, anzahl: int = 2) -> list[tuple[str, bool]]:
        """Die naechsten Gegner samt Heimrecht, chronologisch."""
        schluessel = self.aufloesen(verein)
        if not schluessel:
            return []
        offen = [b for b in self.begegnungen if not b.beendet]
        offen.sort(key=lambda b: (b.anstoss or datetime.max, b.spieltag))
        ergebnis: list[tuple[str, bool]] = []
        for begegnung in offen:
            if namen_schluessel(begegnung.heim) == schluessel:
                ergebnis.append((begegnung.gast, True))
            elif namen_schluessel(begegnung.gast) == schluessel:
                ergebnis.append((begegnung.heim, False))
            if len(ergebnis) >= anzahl:
                break
        return ergebnis

    def als_dict(self) -> dict:
        return {
            "tabelle": self.tabelle,
            "namen": self.namen,
            "aktueller_spieltag": self.aktueller_spieltag,
            "stand": self.stand,
            "begegnungen": [
                {"spieltag": b.spieltag,
                 "anstoss": b.anstoss.isoformat() if b.anstoss else None,
                 "heim": b.heim, "gast": b.gast, "beendet": b.beendet,
                 "tore_heim": b.tore_heim, "tore_gast": b.tore_gast}
                for b in self.begegnungen],
        }

    @classmethod
    def aus_dict(cls, d: dict) -> "Ligalage":
        lage = cls(tabelle={k: int(v) for k, v in (d.get("tabelle") or {}).items()},
                   namen=dict(d.get("namen") or {}),
                   aktueller_spieltag=int(d.get("aktueller_spieltag") or 0),
                   stand=str(d.get("stand") or ""))
        for b in d.get("begegnungen") or []:
            anstoss = b.get("anstoss")
            lage.begegnungen.append(Begegnung(
                spieltag=int(b.get("spieltag") or 0),
                anstoss=datetime.fromisoformat(anstoss) if anstoss else None,
                heim=str(b.get("heim") or ""), gast=str(b.get("gast") or ""),
                beendet=bool(b.get("beendet")),
                tore_heim=int(b.get("tore_heim") or 0),
                tore_gast=int(b.get("tore_gast") or 0)))
        return lage


def saison_bestimmen(heute: date | None = None) -> int:
    """Die Saison, die OpenLigaDB gerade fuehrt.

    Die Bundesligasaison 2026/27 heisst dort ``2026``. Ab Juli zaehlt das
    laufende Jahr, davor das vorige.
    """
    tag = heute or date.today()
    return tag.year if tag.month >= 7 else tag.year - 1


class OpenLigaDbQuelle(HttpQuelle):
    """Holt Tabelle und Spielplan der Bundesliga."""

    name = "OpenLigaDB"

    def __init__(self, liga: str = "bl1", saison: int | str = "",
                 cache: DateiCache | None = None) -> None:
        super().__init__(cache=cache, pause_ms=200)
        self.liga = str(liga or "bl1")
        self.saison = int(saison) if str(saison).strip() else saison_bestimmen()

    def lage_holen(self) -> Ligalage:
        """Tabelle und Spielplan in einem Rutsch; Teilausfaelle sind erlaubt."""
        lage = Ligalage(stand=datetime.now().isoformat(timespec="minutes"))

        try:
            tabelle = self.holen(f"{BASIS_URL}/getbltable/{self.liga}/{self.saison}")
        except QuelleNichtErreichbarFehler as fehler:
            logger().warning("OpenLigaDB-Tabelle nicht abrufbar: %s", fehler)
            tabelle = []
        for platz, eintrag in enumerate(tabelle or [], start=1):
            name = str(eintrag.get("teamName") or eintrag.get("TeamName") or "")
            if not name:
                continue
            schluessel = namen_schluessel(name)
            lage.tabelle[schluessel] = platz
            lage.namen[schluessel] = name

        try:
            spiele = self.holen(f"{BASIS_URL}/getmatchdata/{self.liga}/{self.saison}")
        except QuelleNichtErreichbarFehler as fehler:
            logger().warning("OpenLigaDB-Spielplan nicht abrufbar: %s", fehler)
            spiele = []
        for spiel in spiele or []:
            begegnung = self._begegnung(spiel)
            if not begegnung:
                continue
            lage.begegnungen.append(begegnung)
            # Auch ohne Tabelle sollen Vereinsnamen zuordenbar sein.
            for name in (begegnung.heim, begegnung.gast):
                lage.namen.setdefault(namen_schluessel(name), name)
            if begegnung.beendet:
                lage.aktueller_spieltag = max(lage.aktueller_spieltag,
                                              begegnung.spieltag)
        return lage

    # -- Innereien ---------------------------------------------------------

    @staticmethod
    def _feld(daten: dict, *namen: str) -> Any:
        """OpenLigaDB liefert je nach Endpunkt gross- oder kleingeschrieben."""
        for name in namen:
            for variante in (name, name[0].upper() + name[1:]):
                if variante in daten and daten[variante] is not None:
                    return daten[variante]
        return None

    def _begegnung(self, spiel: dict) -> Begegnung | None:
        heim = self._feld(spiel, "team1") or {}
        gast = self._feld(spiel, "team2") or {}
        heim_name = str(self._feld(heim, "teamName") or "")
        gast_name = str(self._feld(gast, "teamName") or "")
        if not heim_name or not gast_name:
            return None

        gruppe = self._feld(spiel, "group") or {}
        anstoss_roh = self._feld(spiel, "matchDateTimeUTC", "matchDateTime")
        anstoss = None
        if anstoss_roh:
            try:
                anstoss = datetime.fromisoformat(
                    str(anstoss_roh).replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                anstoss = None

        tore_heim = tore_gast = 0
        ergebnisse = self._feld(spiel, "matchResults") or []
        if ergebnisse:
            letztes = ergebnisse[-1]
            tore_heim = int(self._feld(letztes, "pointsTeam1") or 0)
            tore_gast = int(self._feld(letztes, "pointsTeam2") or 0)

        return Begegnung(
            spieltag=int(self._feld(gruppe, "groupOrderID") or 0),
            anstoss=anstoss, heim=heim_name, gast=gast_name,
            beendet=bool(self._feld(spiel, "matchIsFinished")),
            tore_heim=tore_heim, tore_gast=tore_gast)
