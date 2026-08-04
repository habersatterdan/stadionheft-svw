"""Datenmodelle.

Die Felder sind bewusst genau an den Spalten ausgerichtet, die im bisherigen
Stadionheft aus FuPa uebernommen wurden (siehe docs/ANALYSE_VORLAGE.md):

* Tabelle          -- Pl. | Team | Sp. | S-U-N | Tore | Diff | Pkt.
* Torschuetzen     -- Pl. | Spieler (Verein) | Tore | Assists | Sp.
* Spielerstatistik -- Pl. | Spieler | Spiele | Tore | Assists | 11m | Gelb |
                      Gelb-Rot | Rot | Ein. | Aus. | Min.

Alle Klassen sind reine Datencontainer und lassen sich verlustfrei nach JSON
serialisieren. Das ist die Grundlage fuer den "Snapshot": jeder Heft-Lauf legt
die verwendeten Rohdaten ab und ist damit spaeter exakt reproduzierbar.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from datetime import datetime, timedelta
from typing import Any


def _als_int(wert: Any, standard: int = 0) -> int:
    try:
        return int(str(wert).strip())
    except (TypeError, ValueError):
        return standard


def _als_text(wert: Any, standard: str = "") -> str:
    if wert is None:
        return standard
    return str(wert).strip()


class _Basis:
    """Gemeinsame Hilfsmethoden fuer alle Modelle."""

    def to_dict(self) -> dict:
        return asdict(self)  # type: ignore[arg-type]

    @classmethod
    def from_dict(cls, daten: dict):
        erlaubt = {f.name for f in fields(cls)}  # type: ignore[arg-type]
        return cls(**{k: v for k, v in (daten or {}).items() if k in erlaubt})


# ---------------------------------------------------------------------------
# Tabelle
# ---------------------------------------------------------------------------

@dataclass
class TabellenZeile(_Basis):
    platz: int = 0
    mannschaft: str = ""
    spiele: int = 0
    siege: int = 0
    unentschieden: int = 0
    niederlagen: int = 0
    tore: int = 0
    gegentore: int = 0
    punkte: int = 0
    zusatz: str = ""          # z. B. "(Auf)", "(Ab)"
    eigene: bool = False      # eigene Mannschaft -> wird hervorgehoben

    @property
    def differenz(self) -> int:
        return self.tore - self.gegentore

    @property
    def bilanz(self) -> str:
        return f"{self.siege}-{self.unentschieden}-{self.niederlagen}"

    @property
    def torverhaeltnis(self) -> str:
        return f"{self.tore}:{self.gegentore}"

    @classmethod
    def aus_csv(cls, zeile: dict, eigener_name: str = "") -> "TabellenZeile":
        mannschaft = _als_text(zeile.get("mannschaft") or zeile.get("team"))
        return cls(
            platz=_als_int(zeile.get("platz") or zeile.get("pl")),
            mannschaft=mannschaft,
            spiele=_als_int(zeile.get("spiele") or zeile.get("sp")),
            siege=_als_int(zeile.get("siege") or zeile.get("s")),
            unentschieden=_als_int(zeile.get("unentschieden") or zeile.get("u")),
            niederlagen=_als_int(zeile.get("niederlagen") or zeile.get("n")),
            tore=_als_int(zeile.get("tore")),
            gegentore=_als_int(zeile.get("gegentore")),
            punkte=_als_int(zeile.get("punkte") or zeile.get("pkt")),
            zusatz=_als_text(zeile.get("zusatz")),
            eigene=bool(eigener_name) and eigener_name.lower() in mannschaft.lower(),
        )


# ---------------------------------------------------------------------------
# Torschuetzen
# ---------------------------------------------------------------------------

@dataclass
class TorjaegerZeile(_Basis):
    platz: int = 0
    spieler: str = ""
    mannschaft: str = ""
    tore: int = 0
    vorlagen: int = 0
    spiele: int = 0
    eigene: bool = False

    @classmethod
    def aus_csv(cls, zeile: dict, eigener_name: str = "") -> "TorjaegerZeile":
        mannschaft = _als_text(zeile.get("mannschaft") or zeile.get("verein"))
        return cls(
            platz=_als_int(zeile.get("platz") or zeile.get("pl")),
            spieler=_als_text(zeile.get("spieler") or zeile.get("name")),
            mannschaft=mannschaft,
            tore=_als_int(zeile.get("tore")),
            vorlagen=_als_int(zeile.get("vorlagen") or zeile.get("assists")),
            spiele=_als_int(zeile.get("spiele") or zeile.get("sp")),
            eigene=bool(eigener_name) and eigener_name.lower() in mannschaft.lower(),
        )


# ---------------------------------------------------------------------------
# Spielerstatistik
# ---------------------------------------------------------------------------

@dataclass
class SpielerZeile(_Basis):
    platz: int = 0
    spieler: str = ""
    spiele: int = 0
    tore: int = 0
    vorlagen: int = 0
    elfmeter_getroffen: int = 0
    elfmeter_gesamt: int = 0
    gelb: int = 0
    gelb_rot: int = 0
    rot: int = 0
    eingewechselt: int = 0
    ausgewechselt: int = 0
    minuten: int = 0

    @property
    def elfmeter(self) -> str:
        return f"{self.elfmeter_getroffen}/{self.elfmeter_gesamt}"

    @classmethod
    def aus_csv(cls, zeile: dict) -> "SpielerZeile":
        # "11m" kommt bei FuPa als "1/1" -> in zwei Felder zerlegen
        elf_getroffen = zeile.get("elfmeter_getroffen")
        elf_gesamt = zeile.get("elfmeter_gesamt")
        roh = _als_text(zeile.get("elfmeter") or zeile.get("11m"))
        if elf_getroffen is None and "/" in roh:
            teile = roh.split("/", 1)
            elf_getroffen, elf_gesamt = teile[0], teile[1]
        return cls(
            platz=_als_int(zeile.get("platz") or zeile.get("pl")),
            spieler=_als_text(zeile.get("spieler") or zeile.get("name")),
            spiele=_als_int(zeile.get("spiele")),
            tore=_als_int(zeile.get("tore")),
            vorlagen=_als_int(zeile.get("vorlagen") or zeile.get("assists")),
            elfmeter_getroffen=_als_int(elf_getroffen),
            elfmeter_gesamt=_als_int(elf_gesamt),
            gelb=_als_int(zeile.get("gelb")),
            gelb_rot=_als_int(zeile.get("gelb_rot")),
            rot=_als_int(zeile.get("rot")),
            eingewechselt=_als_int(zeile.get("eingewechselt") or zeile.get("ein")),
            ausgewechselt=_als_int(zeile.get("ausgewechselt") or zeile.get("aus")),
            minuten=_als_int(zeile.get("minuten") or zeile.get("min")),
        )


# ---------------------------------------------------------------------------
# Spiel / Begegnung
# ---------------------------------------------------------------------------

WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
              "Freitag", "Samstag", "Sonntag"]


@dataclass
class Spiel(_Basis):
    heim: str = ""
    gast: str = ""
    wettbewerb: str = ""
    anstoss: str = ""          # ISO-Format, z. B. "2026-07-29T18:30:00"
    spielort: str = ""
    heimspiel: bool = True
    spieltag: str = ""
    ergebnis: str = ""         # nur bei bereits gespielten Partien

    # -- abgeleitete Anzeigewerte -------------------------------------------

    @property
    def anstoss_dt(self) -> datetime | None:
        if not self.anstoss:
            return None
        try:
            return datetime.fromisoformat(self.anstoss)
        except ValueError:
            return None

    @property
    def wochentag(self) -> str:
        dt = self.anstoss_dt
        return WOCHENTAGE[dt.weekday()] if dt else ""

    @property
    def datum(self) -> str:
        dt = self.anstoss_dt
        return f"{dt:%d.%m.%Y}" if dt else ""

    @property
    def uhrzeit(self) -> str:
        dt = self.anstoss_dt
        return f"{dt:%H:%M} Uhr" if dt else ""

    @property
    def paarung(self) -> str:
        return f"{self.heim} - {self.gast}" if self.heim or self.gast else ""

    @property
    def gegner(self) -> str:
        return self.gast if self.heimspiel else self.heim

    @classmethod
    def aus_csv(cls, zeile: dict) -> "Spiel":
        heimspiel = _als_text(zeile.get("heimspiel", "ja")).lower() in (
            "ja", "true", "1", "heim", "j", "x")
        anstoss = _als_text(zeile.get("anstoss"))
        if not anstoss:
            # Alternative Schreibweise: getrennte Spalten datum + uhrzeit
            datum = _als_text(zeile.get("datum"))
            uhrzeit = _als_text(zeile.get("uhrzeit")) or "00:00"
            if datum:
                for muster in ("%d.%m.%Y", "%Y-%m-%d"):
                    try:
                        d = datetime.strptime(datum, muster)
                        h, m = (uhrzeit.replace("Uhr", "").strip()
                                .split(":") + ["0"])[:2]
                        anstoss = d.replace(hour=_als_int(h),
                                            minute=_als_int(m)).isoformat()
                        break
                    except ValueError:
                        continue
        return cls(
            heim=_als_text(zeile.get("heim")),
            gast=_als_text(zeile.get("gast")),
            wettbewerb=_als_text(zeile.get("wettbewerb") or zeile.get("liga")),
            anstoss=anstoss,
            spielort=_als_text(zeile.get("spielort") or zeile.get("ort")),
            heimspiel=heimspiel,
            spieltag=_als_text(zeile.get("spieltag")),
            ergebnis=_als_text(zeile.get("ergebnis")),
        )


def spiele_einordnen(spiele: list["Spiel"], stichtag: datetime | None = None,
                     vorlauf_stunden: float = 3.0
                     ) -> tuple["Spiel | None", "Spiel | None"]:
    """Sucht aus einem Spielplan das naechste und das letzte Spiel.

    Massgeblich ist **das Datum**, nicht die Reihenfolge in der Liste und auch
    nicht, ob schon ein Ergebnis eingetragen ist. Genau so soll sich das Heft
    verhalten: Es wird am Erstellungstag geschaut, welche Partie als naechste
    ansteht.

    ``vorlauf_stunden`` sorgt dafuer, dass ein Spiel am selben Tag noch als
    "naechstes" gilt, waehrend es laeuft. Wer das Heft am Spieltag um 17 Uhr
    fuer den Anstoss um 15 Uhr nachdruckt, bekommt weiter die richtige Partie
    aufs Titelblatt.

    Rueckgabe: ``(naechstes, letztes)``. Spiele ohne verwertbares Datum werden
    uebergangen; gibt es gar kein Datum, faellt die Funktion auf die
    Listenreihenfolge zurueck (erstes ohne Ergebnis = naechstes).
    """
    jetzt = stichtag or datetime.now()
    grenze = jetzt - timedelta(hours=vorlauf_stunden)

    mit_datum = [s for s in spiele if s.anstoss_dt is not None]
    if not mit_datum:
        ohne_ergebnis = [s for s in spiele if not s.ergebnis]
        mit_ergebnis = [s for s in spiele if s.ergebnis]
        return (ohne_ergebnis[0] if ohne_ergebnis else None,
                mit_ergebnis[-1] if mit_ergebnis else None)

    mit_datum.sort(key=lambda s: s.anstoss_dt)  # type: ignore[arg-type,return-value]
    kuenftig = [s for s in mit_datum if s.anstoss_dt >= grenze]  # type: ignore[operator]
    vergangen = [s for s in mit_datum if s.anstoss_dt < grenze]  # type: ignore[operator]

    return (kuenftig[0] if kuenftig else None,
            vergangen[-1] if vergangen else None)


# ---------------------------------------------------------------------------
# Zusammenfassung je Mannschaft
# ---------------------------------------------------------------------------

@dataclass
class MannschaftsDaten(_Basis):
    schluessel: str = ""
    anzeigename: str = ""
    gruppe: str = ""
    untertitel: str = ""
    liga: str = ""
    fupa_team_url: str = ""

    tabelle: list[TabellenZeile] = field(default_factory=list)
    torjaeger: list[TorjaegerZeile] = field(default_factory=list)
    spieler: list[SpielerZeile] = field(default_factory=list)
    gegner_spieler: list[SpielerZeile] = field(default_factory=list)
    naechstes_spiel: Spiel | None = None
    letztes_spiel: Spiel | None = None
    spielbericht: str = ""

    #: Woher stammen die Daten? "api" | "manuell" | "demo"
    quelle: str = ""
    #: Nicht-toedliche Probleme, die dem Benutzer angezeigt werden sollen.
    warnungen: list[str] = field(default_factory=list)

    @property
    def gegner(self) -> str:
        return self.naechstes_spiel.gegner if self.naechstes_spiel else ""

    def to_dict(self) -> dict:
        return {
            "schluessel": self.schluessel,
            "anzeigename": self.anzeigename,
            "gruppe": self.gruppe,
            "untertitel": self.untertitel,
            "liga": self.liga,
            "fupa_team_url": self.fupa_team_url,
            "tabelle": [z.to_dict() for z in self.tabelle],
            "torjaeger": [z.to_dict() for z in self.torjaeger],
            "spieler": [z.to_dict() for z in self.spieler],
            "gegner_spieler": [z.to_dict() for z in self.gegner_spieler],
            "naechstes_spiel": self.naechstes_spiel.to_dict() if self.naechstes_spiel else None,
            "letztes_spiel": self.letztes_spiel.to_dict() if self.letztes_spiel else None,
            "spielbericht": self.spielbericht,
            "quelle": self.quelle,
            "warnungen": list(self.warnungen),
        }

    @classmethod
    def from_dict(cls, daten: dict) -> "MannschaftsDaten":
        daten = daten or {}
        return cls(
            schluessel=daten.get("schluessel", ""),
            anzeigename=daten.get("anzeigename", ""),
            gruppe=daten.get("gruppe", ""),
            untertitel=daten.get("untertitel", ""),
            liga=daten.get("liga", ""),
            fupa_team_url=daten.get("fupa_team_url", ""),
            tabelle=[TabellenZeile.from_dict(z) for z in daten.get("tabelle", [])],
            torjaeger=[TorjaegerZeile.from_dict(z) for z in daten.get("torjaeger", [])],
            spieler=[SpielerZeile.from_dict(z) for z in daten.get("spieler", [])],
            gegner_spieler=[SpielerZeile.from_dict(z)
                            for z in daten.get("gegner_spieler", [])],
            naechstes_spiel=(Spiel.from_dict(daten["naechstes_spiel"])
                             if daten.get("naechstes_spiel") else None),
            letztes_spiel=(Spiel.from_dict(daten["letztes_spiel"])
                           if daten.get("letztes_spiel") else None),
            spielbericht=daten.get("spielbericht", ""),
            quelle=daten.get("quelle", ""),
            warnungen=list(daten.get("warnungen", [])),
        )


# ---------------------------------------------------------------------------
# Die komplette Ausgabe
# ---------------------------------------------------------------------------

@dataclass
class Ausgabe(_Basis):
    """Alles, was fuer genau ein Stadionheft gebraucht wird."""

    saison: str = ""
    spieltag: str = ""
    #: Die Partie, die auf der Titelseite steht.
    titelspiel: Spiel | None = None
    mannschaften: list[MannschaftsDaten] = field(default_factory=list)
    erstellt_am: str = ""
    erzeugt_von: str = ""
    warnungen: list[str] = field(default_factory=list)
    #: Die Seitenreihenfolge dieses Laufs. Gehoert in den Snapshot -- sonst
    #: koennte ein spaeterer Neuaufbau bei geaendertem Heftplan ein anderes
    #: Heft ergeben.
    heftplan: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "format_version": 1,
            "saison": self.saison,
            "spieltag": self.spieltag,
            "titelspiel": self.titelspiel.to_dict() if self.titelspiel else None,
            "mannschaften": [m.to_dict() for m in self.mannschaften],
            "erstellt_am": self.erstellt_am,
            "erzeugt_von": self.erzeugt_von,
            "warnungen": list(self.warnungen),
            "heftplan": list(self.heftplan),
        }

    @classmethod
    def from_dict(cls, daten: dict) -> "Ausgabe":
        daten = daten or {}
        return cls(
            saison=daten.get("saison", ""),
            spieltag=daten.get("spieltag", ""),
            titelspiel=(Spiel.from_dict(daten["titelspiel"])
                        if daten.get("titelspiel") else None),
            mannschaften=[MannschaftsDaten.from_dict(m)
                          for m in daten.get("mannschaften", [])],
            erstellt_am=daten.get("erstellt_am", ""),
            erzeugt_von=daten.get("erzeugt_von", ""),
            warnungen=list(daten.get("warnungen", [])),
            heftplan=list(daten.get("heftplan", [])),
        )
