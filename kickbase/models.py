"""Datenmodelle des Kickbase-Beraters.

Diese Klassen sind die *einzige* Stelle, an der Kickbase-Kuerzel wie ``mv``
oder ``ap`` in sprechende Namen uebersetzt werden. Alles weitere -- Analyse,
Oberflaeche, Kommandozeile -- arbeitet ausschliesslich mit diesen Objekten.
Wenn Kickbase seine Feldnamen aendert, ist nur ``quellen/kickbase_api.py``
betroffen, nicht das restliche Programm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

# --------------------------------------------------------------------------
# Feste Zuordnungen aus der Kickbase-Welt
# --------------------------------------------------------------------------

POSITIONEN = {1: "Torwart", 2: "Abwehr", 3: "Mittelfeld", 4: "Sturm"}

#: Statuscodes, wie Kickbase sie im Feld ``st`` liefert.
#: Unbekannte Codes werden nicht als Fehler behandelt, sondern als
#: "unklar" gefuehrt -- Kickbase ergaenzt gelegentlich neue Werte.
STATUS_TEXTE = {
    0: "Fit",
    1: "Verletzt",
    2: "Angeschlagen",
    4: "Aufbautraining",
    8: "Rotsperre",
    16: "Gelbsperre",
    32: "Nicht im Kader",
    64: "Abwesend",
    128: "Reha",
    256: "Vereinslos",
}

#: Status, bei denen der Spieler am naechsten Spieltag sicher ausfaellt.
STATUS_AUSFALL = {1, 8, 16, 32, 64, 128, 256}

#: Status, bei denen ein Einsatz fraglich ist.
STATUS_FRAGLICH = {2, 4}


def status_text(code: int) -> str:
    return STATUS_TEXTE.get(int(code or 0), f"Status {code}")


def position_text(code: int) -> str:
    return POSITIONEN.get(int(code or 0), "unbekannt")


# --------------------------------------------------------------------------
# Bausteine
# --------------------------------------------------------------------------


@dataclass
class Marktwertpunkt:
    """Ein Tageswert aus dem Marktwertverlauf."""

    tag: date
    wert: int

    def als_dict(self) -> dict:
        return {"tag": self.tag.isoformat(), "wert": self.wert}

    @classmethod
    def aus_dict(cls, d: dict) -> "Marktwertpunkt":
        return cls(tag=date.fromisoformat(d["tag"]), wert=int(d["wert"]))


@dataclass
class Spieltagsleistung:
    """Was ein Spieler an einem Spieltag gebracht hat."""

    spieltag: int
    punkte: int = 0
    minuten: int = 0
    status: int = 0
    datum: date | None = None
    eigenes_team_id: str = ""
    gegner_team_id: str = ""
    heimspiel: bool = True
    gespielt: bool = False

    @property
    def eingesetzt(self) -> bool:
        return self.minuten > 0

    @property
    def startelf(self) -> bool:
        """Faustregel: wer 60 Minuten und mehr spielt, hat begonnen."""
        return self.minuten >= 60

    def als_dict(self) -> dict:
        d = dict(self.__dict__)
        d["datum"] = self.datum.isoformat() if self.datum else None
        return d

    @classmethod
    def aus_dict(cls, d: dict) -> "Spieltagsleistung":
        d = dict(d)
        if d.get("datum"):
            d["datum"] = date.fromisoformat(d["datum"])
        else:
            d["datum"] = None
        return cls(**d)


@dataclass
class Spieler:
    """Ein Bundesligaspieler mit allem, was der Berater ueber ihn weiss."""

    id: str
    vorname: str = ""
    nachname: str = ""
    team_id: str = ""
    team_name: str = ""
    position: int = 0
    status: int = 0

    marktwert: int = 0
    marktwert_trend: int = 0          # Kickbase-Kuerzel mvt: 1 steigend, 2 fallend
    punkte_gesamt: int = 0
    punkte_schnitt: int = 0
    spiele: int = 0
    tore: int = 0
    vorlagen: int = 0
    minuten_gesamt: int = 0

    #: Nur gesetzt, wenn der Spieler jemandem in der Liga gehoert.
    besitzer: str = ""
    im_eigenen_team: bool = False
    #: Preis, zu dem der Spieler gerade auf dem Transfermarkt steht.
    angebotspreis: int = 0
    auf_transfermarkt: bool = False

    verlauf: list[Marktwertpunkt] = field(default_factory=list)
    leistungen: list[Spieltagsleistung] = field(default_factory=list)

    #: Zusatzmeldung aus einer Verletzungsquelle (kicker, Ligainsider, ...).
    verletzungsmeldung: str = ""
    verletzungsquelle: str = ""

    # -- Abgeleitetes ------------------------------------------------------

    @property
    def name(self) -> str:
        voll = f"{self.vorname} {self.nachname}".strip()
        return voll or self.nachname or self.vorname or f"Spieler {self.id}"

    @property
    def kurzname(self) -> str:
        return self.nachname or self.name

    @property
    def positions_name(self) -> str:
        return position_text(self.position)

    @property
    def status_name(self) -> str:
        return status_text(self.status)

    @property
    def faellt_aus(self) -> bool:
        return int(self.status) in STATUS_AUSFALL

    @property
    def fraglich(self) -> bool:
        return int(self.status) in STATUS_FRAGLICH

    @property
    def einsatzbereit(self) -> bool:
        return not self.faellt_aus and not self.fraglich

    @property
    def marktwert_mio(self) -> float:
        return round(self.marktwert / 1_000_000, 2)

    def letzte_leistungen(self, anzahl: int) -> list[Spieltagsleistung]:
        """Die letzten ``anzahl`` *gespielten* Spieltage, aeltester zuerst."""
        gespielt = [l for l in self.leistungen if l.gespielt]
        gespielt.sort(key=lambda l: l.spieltag)
        return gespielt[-anzahl:] if anzahl > 0 else gespielt

    def marktwert_vor(self, tagen: int) -> int:
        """Marktwert vor ``tagen`` Tagen, 0 wenn nicht bekannt.

        Der Verlauf hat gelegentlich Luecken (Kickbase liefert nicht jeden
        Tag). Deshalb wird der zeitlich naechstgelegene Punkt genommen, statt
        auf einen exakten Treffer zu bestehen.
        """
        if not self.verlauf:
            return 0
        sortiert = sorted(self.verlauf, key=lambda p: p.tag)
        ziel = sortiert[-1].tag.toordinal() - int(tagen)
        passend = min(sortiert, key=lambda p: abs(p.tag.toordinal() - ziel))
        # Zu grosse Abweichung ist keine brauchbare Auskunft.
        if abs(passend.tag.toordinal() - ziel) > max(3, tagen // 3):
            return 0
        return passend.wert

    def als_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()
             if k not in ("verlauf", "leistungen")}
        d["verlauf"] = [p.als_dict() for p in self.verlauf]
        d["leistungen"] = [l.als_dict() for l in self.leistungen]
        return d

    @classmethod
    def aus_dict(cls, d: dict) -> "Spieler":
        d = dict(d)
        verlauf = [Marktwertpunkt.aus_dict(p) for p in d.pop("verlauf", [])]
        leistungen = [Spieltagsleistung.aus_dict(l) for l in d.pop("leistungen", [])]
        bekannt = {f for f in cls.__dataclass_fields__}
        spieler = cls(**{k: v for k, v in d.items() if k in bekannt})
        spieler.verlauf = verlauf
        spieler.leistungen = leistungen
        return spieler


@dataclass
class Kennzahl:
    """Eine einzelne Bewertungsgroesse -- immer mit Begruendung.

    ``punkte`` liegt zwischen -100 (klar negativ) und +100 (klar positiv).
    Die Gewichtung kommt aus der Konfiguration, damit jeder die Analyse an
    seinen Spielstil anpassen kann, ohne Code zu aendern.
    """

    schluessel: str
    name: str
    anzeige: str
    punkte: float
    gewicht: float
    begruendung: str

    @property
    def beitrag(self) -> float:
        return self.punkte * self.gewicht

    @property
    def richtung(self) -> str:
        if self.punkte >= 15:
            return "gut"
        if self.punkte <= -15:
            return "schlecht"
        return "neutral"

    def als_dict(self) -> dict:
        return {
            "schluessel": self.schluessel, "name": self.name,
            "anzeige": self.anzeige, "punkte": round(self.punkte, 1),
            "gewicht": self.gewicht, "begruendung": self.begruendung,
            "beitrag": round(self.beitrag, 1), "richtung": self.richtung,
        }


#: Empfehlungsstufen von "unbedingt kaufen" bis "unbedingt verkaufen".
EMPFEHLUNGEN = [
    ("kaufen", "Kaufen", 35),
    ("beobachten", "Beobachten", 15),
    ("halten", "Halten", -15),
    ("pruefen", "Verkauf prüfen", -35),
    ("verkaufen", "Verkaufen", -1000),
]


@dataclass
class Bewertung:
    """Das Ergebnis der Analyse fuer genau einen Spieler."""

    spieler: Spieler
    gesamtpunkte: float = 0.0
    kennzahlen: list[Kennzahl] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    #: Harte Regeln, die das Punktesystem uebersteuert haben.
    uebersteuerung: str = ""

    @property
    def stufe(self) -> str:
        for schluessel, _, grenze in EMPFEHLUNGEN:
            if self.gesamtpunkte >= grenze:
                return schluessel
        return "verkaufen"

    @property
    def empfehlung(self) -> str:
        for schluessel, text, grenze in EMPFEHLUNGEN:
            if self.gesamtpunkte >= grenze:
                return text
        return "Verkaufen"

    @property
    def staerkste_gruende(self) -> list[Kennzahl]:
        """Die drei Kennzahlen mit dem groessten Einfluss aufs Ergebnis."""
        return sorted(self.kennzahlen, key=lambda k: abs(k.beitrag),
                      reverse=True)[:3]

    def als_dict(self) -> dict:
        return {
            "spieler_id": self.spieler.id,
            "name": self.spieler.name,
            "team": self.spieler.team_name,
            "position": self.spieler.positions_name,
            "marktwert": self.spieler.marktwert,
            "status": self.spieler.status_name,
            "gesamtpunkte": round(self.gesamtpunkte, 1),
            "empfehlung": self.empfehlung,
            "stufe": self.stufe,
            "uebersteuerung": self.uebersteuerung,
            "warnungen": self.warnungen,
            "kennzahlen": [k.als_dict() for k in self.kennzahlen],
        }


@dataclass
class Spieltagsinfo:
    """Naechster Gegner einer Mannschaft, fuer die Gegnerstaerke."""

    team_id: str
    gegner_team_id: str = ""
    gegner_name: str = ""
    heimspiel: bool = True
    anstoss: datetime | None = None


@dataclass
class Lagebericht:
    """Alles, was die Oberflaeche fuer eine Ansicht braucht."""

    erstellt: datetime
    liga_name: str = ""
    budget: int = 0
    teamwert: int = 0
    eigene: list[Bewertung] = field(default_factory=list)
    transfermarkt: list[Bewertung] = field(default_factory=list)
    kandidaten: list[Bewertung] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    quellen: dict[str, str] = field(default_factory=dict)

    @property
    def verkaufskandidaten(self) -> list[Bewertung]:
        return [b for b in self.eigene if b.stufe in ("verkaufen", "pruefen")]

    @property
    def ausfaelle(self) -> list[Bewertung]:
        return [b for b in self.eigene
                if b.spieler.faellt_aus or b.spieler.fraglich]
