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
    heimspiel: bool = True     # aus Sicht der Mannschaft, zu der dieses Spiel gehoert
    spieltag: str = ""
    ergebnis: str = ""         # nur bei bereits gespielten Partien

    #: Bezeichner der beiden Mannschaften bei der Datenquelle, soweit sie
    #: mitgeliefert werden. Damit laesst sich die Seite des Gegners finden,
    #: ohne seinen Namen raten oder von Hand pflegen zu muessen.
    heim_kennung: str = ""
    gast_kennung: str = ""

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

    @property
    def gegner_kennung(self) -> str:
        return self.gast_kennung if self.heimspiel else self.heim_kennung

    @property
    def eigene_tore(self) -> int | None:
        """Tore der Mannschaft, zu der dieses Spiel gehoert."""
        tore = self._tore()
        if tore is None:
            return None
        return tore[0] if self.heimspiel else tore[1]

    @property
    def gegentore(self) -> int | None:
        tore = self._tore()
        if tore is None:
            return None
        return tore[1] if self.heimspiel else tore[0]

    @property
    def ausgang(self) -> str:
        """``S``, ``U``, ``N`` -- oder leer, solange nicht gespielt wurde."""
        eigene, fremde = self.eigene_tore, self.gegentore
        if eigene is None or fremde is None:
            return ""
        if eigene > fremde:
            return "S"
        return "U" if eigene == fremde else "N"

    @property
    def gespielt(self) -> bool:
        return self.ausgang != ""

    def _tore(self) -> tuple[int, int] | None:
        """Das Ergebnis als Zahlenpaar (Heim, Gast)."""
        if ":" not in self.ergebnis:
            return None
        heim, _, gast = self.ergebnis.partition(":")
        try:
            return int(heim.strip()), int(gast.strip())
        except ValueError:
            return None

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
# Abgeleitete Kennzahlen
#
# Bewusst hier und nicht in der Datenquelle: Diese Werte werden *gerechnet*,
# nicht geholt. Damit stimmen sie immer zu den Spielen, die tatsaechlich im
# Heft stehen -- auch wenn FuPa seine eigene Statistikseite anders zaehlt.
# ---------------------------------------------------------------------------

@dataclass
class FormEintrag(_Basis):
    """Ein gespieltes Spiel, verdichtet auf das, was die Formkurve zeigt."""

    ausgang: str = ""          # S | U | N
    gegner: str = ""
    ergebnis: str = ""
    heimspiel: bool = True
    datum: str = ""

    @property
    def beschriftung(self) -> str:
        ort = "H" if self.heimspiel else "A"
        return f"{ort} {self.gegner} {self.ergebnis}".strip()


def form_aus_spielen(spiele: list["Spiel"], anzahl: int = 5) -> list[FormEintrag]:
    """Die letzten ``anzahl`` gespielten Partien, aelteste zuerst.

    Aelteste zuerst, weil eine Formkurve von links nach rechts gelesen wird --
    das letzte Zeichen ist das juengste Spiel.
    """
    gespielt = [s for s in spiele if s.gespielt and s.anstoss_dt is not None]
    gespielt.sort(key=lambda s: s.anstoss_dt)      # type: ignore[arg-type,return-value]
    return [FormEintrag(ausgang=s.ausgang, gegner=s.gegner, ergebnis=s.ergebnis,
                        heimspiel=s.heimspiel, datum=s.datum)
            for s in gespielt[-anzahl:]]


@dataclass
class Teilbilanz(_Basis):
    """Bilanz ueber eine Teilmenge der Spiele, z. B. nur die Heimspiele."""

    spiele: int = 0
    siege: int = 0
    unentschieden: int = 0
    niederlagen: int = 0
    tore: int = 0
    gegentore: int = 0

    @property
    def punkte(self) -> int:
        return self.siege * 3 + self.unentschieden

    @property
    def bilanz(self) -> str:
        return f"{self.siege}-{self.unentschieden}-{self.niederlagen}"

    @property
    def torverhaeltnis(self) -> str:
        return f"{self.tore}:{self.gegentore}"

    @property
    def differenz(self) -> int:
        return self.tore - self.gegentore

    def _dazu(self, spiel: "Spiel") -> None:
        eigene, fremde = spiel.eigene_tore, spiel.gegentore
        if eigene is None or fremde is None:
            return
        self.spiele += 1
        self.tore += eigene
        self.gegentore += fremde
        if eigene > fremde:
            self.siege += 1
        elif eigene == fremde:
            self.unentschieden += 1
        else:
            self.niederlagen += 1


@dataclass
class Bilanz(_Basis):
    """Saisonzahlen, die sich aus dem Spielplan rechnen lassen."""

    gesamt: Teilbilanz = field(default_factory=Teilbilanz)
    heim: Teilbilanz = field(default_factory=Teilbilanz)
    auswaerts: Teilbilanz = field(default_factory=Teilbilanz)
    zu_null: int = 0
    ohne_eigenes_tor: int = 0
    hoechster_sieg: str = ""
    laengste_serie: str = ""

    @property
    def vorhanden(self) -> bool:
        return self.gesamt.spiele > 0

    @property
    def punkteschnitt(self) -> str:
        if not self.gesamt.spiele:
            return "-"
        return f"{self.gesamt.punkte / self.gesamt.spiele:.2f}".replace(".", ",")

    @property
    def tore_pro_spiel(self) -> str:
        if not self.gesamt.spiele:
            return "-"
        return f"{self.gesamt.tore / self.gesamt.spiele:.2f}".replace(".", ",")

    @property
    def gegentore_pro_spiel(self) -> str:
        if not self.gesamt.spiele:
            return "-"
        return f"{self.gesamt.gegentore / self.gesamt.spiele:.2f}".replace(".", ",")

    def to_dict(self) -> dict:
        return {
            "gesamt": self.gesamt.to_dict(),
            "heim": self.heim.to_dict(),
            "auswaerts": self.auswaerts.to_dict(),
            "zu_null": self.zu_null,
            "ohne_eigenes_tor": self.ohne_eigenes_tor,
            "hoechster_sieg": self.hoechster_sieg,
            "laengste_serie": self.laengste_serie,
        }

    @classmethod
    def from_dict(cls, daten: dict) -> "Bilanz":
        daten = daten or {}
        return cls(
            gesamt=Teilbilanz.from_dict(daten.get("gesamt", {})),
            heim=Teilbilanz.from_dict(daten.get("heim", {})),
            auswaerts=Teilbilanz.from_dict(daten.get("auswaerts", {})),
            zu_null=daten.get("zu_null", 0),
            ohne_eigenes_tor=daten.get("ohne_eigenes_tor", 0),
            hoechster_sieg=daten.get("hoechster_sieg", ""),
            laengste_serie=daten.get("laengste_serie", ""),
        )


SERIENNAMEN = {"S": ("Sieg", "Siege"), "U": ("Unentschieden", "Unentschieden"),
               "N": ("Niederlage", "Niederlagen")}


def bilanz_aus_spielen(spiele: list["Spiel"]) -> Bilanz:
    """Rechnet die Saisonbilanz aus den gespielten Partien."""
    gespielt = [s for s in spiele if s.gespielt and s.anstoss_dt is not None]
    gespielt.sort(key=lambda s: s.anstoss_dt)      # type: ignore[arg-type,return-value]

    bilanz = Bilanz()
    bester_abstand = -1
    for spiel in gespielt:
        bilanz.gesamt._dazu(spiel)
        (bilanz.heim if spiel.heimspiel else bilanz.auswaerts)._dazu(spiel)

        eigene, fremde = spiel.eigene_tore or 0, spiel.gegentore or 0
        if fremde == 0:
            bilanz.zu_null += 1
        if eigene == 0:
            bilanz.ohne_eigenes_tor += 1
        if eigene > fremde and eigene - fremde > bester_abstand:
            bester_abstand = eigene - fremde
            ort = "H" if spiel.heimspiel else "A"
            bilanz.hoechster_sieg = f"{eigene}:{fremde} ({ort} {spiel.gegner})"

    bilanz.laengste_serie = _laengste_serie(gespielt)
    return bilanz


def _laengste_serie(gespielt: list["Spiel"]) -> str:
    """Die laengste ununterbrochene Serie gleicher Ausgaenge im Klartext."""
    beste_laenge, bestes_zeichen = 0, ""
    laenge, zeichen = 0, ""
    for spiel in gespielt:
        if spiel.ausgang == zeichen:
            laenge += 1
        else:
            zeichen, laenge = spiel.ausgang, 1
        if laenge > beste_laenge:
            beste_laenge, bestes_zeichen = laenge, zeichen

    if beste_laenge < 2:
        return ""
    einzahl, mehrzahl = SERIENNAMEN.get(bestes_zeichen, ("Spiel", "Spiele"))
    return f"{beste_laenge} {einzahl if beste_laenge == 1 else mehrzahl} in Folge"


# ---------------------------------------------------------------------------
# Der naechste Gegner
# ---------------------------------------------------------------------------

@dataclass
class GegnerDaten(_Basis):
    """Was ueber den naechsten Gegner zusammengetragen wurde.

    Bewusst eine eigene Klasse und keine zweite ``MannschaftsDaten``: Der
    Gegner hat keinen Schluessel in unserer Konfiguration, keine Seitenliste
    und kein eigenes Kapitel im Heft. Er ist eine Beilage zu genau einer
    unserer Mannschaften.
    """

    name: str = ""
    kennung: str = ""              # Bezeichner bei der Datenquelle
    liga: str = ""
    fupa_team_url: str = ""

    tabelle: list[TabellenZeile] = field(default_factory=list)
    torjaeger: list[TorjaegerZeile] = field(default_factory=list)
    spieler: list[SpielerZeile] = field(default_factory=list)
    spiele: list[Spiel] = field(default_factory=list)

    @property
    def gefunden(self) -> bool:
        return bool(self.tabelle or self.torjaeger or self.spieler or self.spiele)

    @property
    def form(self) -> list[FormEintrag]:
        return form_aus_spielen(self.spiele)

    @property
    def bilanz(self) -> Bilanz:
        return bilanz_aus_spielen(self.spiele)

    @property
    def tabellenplatz(self) -> TabellenZeile | None:
        return _eigene_zeile(self.tabelle, self.name)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kennung": self.kennung,
            "liga": self.liga,
            "fupa_team_url": self.fupa_team_url,
            "tabelle": [z.to_dict() for z in self.tabelle],
            "torjaeger": [z.to_dict() for z in self.torjaeger],
            "spieler": [z.to_dict() for z in self.spieler],
            "spiele": [s.to_dict() for s in self.spiele],
        }

    @classmethod
    def from_dict(cls, daten: dict) -> "GegnerDaten":
        daten = daten or {}
        return cls(
            name=daten.get("name", ""),
            kennung=daten.get("kennung", ""),
            liga=daten.get("liga", ""),
            fupa_team_url=daten.get("fupa_team_url", ""),
            tabelle=[TabellenZeile.from_dict(z) for z in daten.get("tabelle", [])],
            torjaeger=[TorjaegerZeile.from_dict(z) for z in daten.get("torjaeger", [])],
            spieler=[SpielerZeile.from_dict(z) for z in daten.get("spieler", [])],
            spiele=[Spiel.from_dict(s) for s in daten.get("spiele", [])],
        )


def _eigene_zeile(tabelle: list[TabellenZeile], name: str) -> TabellenZeile | None:
    """Die Tabellenzeile einer Mannschaft -- erst ueber die Markierung, dann
    ueber den Namen."""
    for zeile in tabelle:
        if zeile.eigene:
            return zeile
    kern = (name or "").lower().strip()
    if not kern:
        return None
    for zeile in tabelle:
        if kern in zeile.mannschaft.lower() or zeile.mannschaft.lower() in kern:
            return zeile
    return None


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
    #: Der komplette Spielplan. Aus ihm ergeben sich naechstes und letztes
    #: Spiel, die Formkurve und die Saisonbilanz.
    spiele: list[Spiel] = field(default_factory=list)
    naechstes_spiel: Spiel | None = None
    letztes_spiel: Spiel | None = None

    #: Der naechste Gegner mit seinen eigenen Zahlen.
    gegner_daten: GegnerDaten | None = None

    #: Woher stammen die Daten? "api" | "manuell" | "demo"
    quelle: str = ""
    #: Wann wurden sie geholt? ISO-Zeitstempel. Steht auf jeder Seite.
    abgerufen_am: str = ""
    #: Kamen sie aus dem Zwischenspeicher, obwohl der abgelaufen war?
    veraltet: bool = False
    #: Nicht-toedliche Probleme, die dem Benutzer angezeigt werden sollen.
    warnungen: list[str] = field(default_factory=list)

    # -- abgeleitete Werte --------------------------------------------------

    @property
    def gegner(self) -> str:
        if self.gegner_daten and self.gegner_daten.name:
            return self.gegner_daten.name
        return self.naechstes_spiel.gegner if self.naechstes_spiel else ""

    @property
    def form(self) -> list[FormEintrag]:
        return form_aus_spielen(self.spiele)

    @property
    def bilanz(self) -> Bilanz:
        return bilanz_aus_spielen(self.spiele)

    @property
    def tabellenplatz(self) -> TabellenZeile | None:
        return _eigene_zeile(self.tabelle, self.anzeigename)

    @property
    def gleiche_liga(self) -> bool:
        """Spielt der Gegner in derselben Liga?

        Dann sind Tabelle und Torschuetzenliste fuer beide dieselben -- es
        waere unsinnig, sie zweimal ins Heft zu setzen.
        """
        if not self.gegner_daten or not self.gegner_daten.tabelle:
            return False
        eigene = {z.mannschaft for z in self.tabelle}
        fremde = {z.mannschaft for z in self.gegner_daten.tabelle}
        if not eigene or not fremde:
            return False
        gemeinsam = len(eigene & fremde)
        return gemeinsam >= max(2, min(len(eigene), len(fremde)) * 0.6)

    @property
    def abgerufen_lesbar(self) -> str:
        if not self.abgerufen_am:
            return ""
        try:
            dt = datetime.fromisoformat(self.abgerufen_am)
        except ValueError:
            return self.abgerufen_am
        return f"{dt:%d.%m.%Y, %H:%M} Uhr"

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
            "spiele": [s.to_dict() for s in self.spiele],
            "naechstes_spiel": self.naechstes_spiel.to_dict() if self.naechstes_spiel else None,
            "letztes_spiel": self.letztes_spiel.to_dict() if self.letztes_spiel else None,
            "gegner_daten": self.gegner_daten.to_dict() if self.gegner_daten else None,
            "quelle": self.quelle,
            "abgerufen_am": self.abgerufen_am,
            "veraltet": self.veraltet,
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
            spiele=[Spiel.from_dict(s) for s in daten.get("spiele", [])],
            naechstes_spiel=(Spiel.from_dict(daten["naechstes_spiel"])
                             if daten.get("naechstes_spiel") else None),
            letztes_spiel=(Spiel.from_dict(daten["letztes_spiel"])
                           if daten.get("letztes_spiel") else None),
            gegner_daten=(GegnerDaten.from_dict(daten["gegner_daten"])
                          if daten.get("gegner_daten") else None),
            quelle=daten.get("quelle", ""),
            abgerufen_am=daten.get("abgerufen_am", ""),
            veraltet=bool(daten.get("veraltet", False)),
            warnungen=list(daten.get("warnungen", [])),
        )


# ---------------------------------------------------------------------------
# Die komplette Ausgabe
# ---------------------------------------------------------------------------

@dataclass
class Ausgabe(_Basis):
    """Ein Lauf: alles, was bei einem Knopfdruck entstanden ist."""

    saison: str = ""
    spieltag: str = ""
    mannschaften: list[MannschaftsDaten] = field(default_factory=list)
    erstellt_am: str = ""
    erzeugt_von: str = ""
    warnungen: list[str] = field(default_factory=list)
    #: Die Seitenfolge, die je Mannschaft gesetzt wurde. Gehoert in den
    #: Snapshot, sonst koennte ein spaeterer Neuaufbau andere Seiten ergeben.
    seitenfolge: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "format_version": 2,
            "saison": self.saison,
            "spieltag": self.spieltag,
            "mannschaften": [m.to_dict() for m in self.mannschaften],
            "erstellt_am": self.erstellt_am,
            "erzeugt_von": self.erzeugt_von,
            "warnungen": list(self.warnungen),
            "seitenfolge": list(self.seitenfolge),
        }

    @classmethod
    def from_dict(cls, daten: dict) -> "Ausgabe":
        daten = daten or {}
        return cls(
            saison=daten.get("saison", ""),
            spieltag=daten.get("spieltag", ""),
            mannschaften=[MannschaftsDaten.from_dict(m)
                          for m in daten.get("mannschaften", [])],
            erstellt_am=daten.get("erstellt_am", ""),
            erzeugt_von=daten.get("erzeugt_von", ""),
            warnungen=list(daten.get("warnungen", [])),
            seitenfolge=list(daten.get("seitenfolge", [])),
        )
