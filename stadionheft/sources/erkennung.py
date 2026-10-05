"""Daten anhand ihrer *Struktur* erkennen, nicht anhand fester Feldnamen.

Warum dieses Modul existiert
============================

Der erste Versuch, FuPa anzubinden, ging so: eine geratene Adresse, feste
Feldnamen. Stimmt eine der beiden Annahmen nicht, kommt gar nichts an -- und
niemand sieht, woran es lag.

Dieses Modul dreht den Spiess um. Es bekommt **irgendein** JSON und sucht
darin selbst nach den Listen, die wie eine Tabelle, eine Torschuetzenliste,
eine Spielerstatistik oder ein Spielplan aussehen. Erkannt wird an der Form:

* Eine **Tabellenzeile** hat einen Mannschaftsnamen und Punkte -- oder
  Siege/Unentschieden/Niederlagen.
* Eine **Torschuetzenzeile** hat einen Spielernamen, Tore und meist einen
  Verein.
* Eine **Spielerzeile** hat einen Spielernamen und Einsatzdaten
  (Spiele, Minuten, Karten).
* Ein **Spiel** hat zwei Mannschaften und ein Datum.

Damit ist es egal, ob das Feld ``points``, ``punkte``, ``pts`` oder
``totalPoints`` heisst und wie tief es verschachtelt liegt.

Das ist bewusst nachsichtig: Lieber eine Liste mit ein paar leeren Spalten als
eine leere Seite. Was erkannt wurde, steht anschliessend im Protokoll.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from ..logging_setup import logger
from ..models import Spiel, SpielerZeile, TabellenZeile, TorjaegerZeile

# ---------------------------------------------------------------------------
# Feldnamen erkennen
# ---------------------------------------------------------------------------

def _normal(name: str) -> str:
    """'goalsFor' -> 'goalsfor',  'Tore_Gesamt' -> 'toregesamt'."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


#: Synonyme je Feld. Reihenfolge = Vorrang.
FELDER: dict[str, tuple[str, ...]] = {
    # Die kurzen deutschen Spaltenkuerzel stammen von Vereinsseiten: Dort
    # heisst die Spalte "Pl.", nicht "position". Nach _normal bleibt "pl".
    "platz":        ("place", "position", "rank", "platz", "pos", "rang", "nr",
                     "pl"),
    "mannschaft":   ("teamname", "clubname", "team", "club", "mannschaft",
                     "verein", "name"),
    "spiele":       ("matches", "games", "played", "appearances", "spiele",
                     "sp", "gamesplayed", "matchesplayed"),
    "siege":        ("wins", "won", "siege", "s", "victories"),
    "unentschieden": ("draws", "drawn", "unentschieden", "u", "ties"),
    "niederlagen":  ("losses", "lost", "niederlagen", "n", "defeats"),
    "tore":         ("goals", "goalsfor", "goalsscored", "tore", "torejeschossen",
                     "scored", "goalsshot"),
    "gegentore":    ("goalsagainst", "goalsconceded", "gegentore", "conceded",
                     "gt"),
    "punkte":       ("points", "punkte", "pts", "totalpoints", "pkt"),
    "spieler":      ("playername", "player", "spieler", "name", "fullname",
                     "displayname"),
    "vorlagen":     ("assists", "vorlagen", "assist"),
    "minuten":      ("minutes", "minutesplayed", "minuten", "min"),
    "gelb":         ("yellowcards", "yellow", "gelb", "yellowcard"),
    "gelb_rot":     ("yellowredcards", "yellowred", "gelbrot", "secondyellow"),
    "rot":          ("redcards", "red", "rot", "redcard"),
    "eingewechselt": ("substitutedin", "subin", "in", "eingewechselt", "comeon"),
    "ausgewechselt": ("substitutedout", "subout", "out", "ausgewechselt"),
    "elfmeter":     ("penalties", "penalty", "elfmeter", "11m"),
    "heim":         ("hometeam", "home", "hometeamname", "heim", "heimmannschaft"),
    "gast":         ("awayteam", "away", "awayteamname", "gast", "gastmannschaft",
                     "guest"),
    "anstoss":      ("kickoff", "kickoffdate", "scheduleddate", "startdate",
                     "date", "datetime", "anstoss", "datum", "begin"),
    "wettbewerb":   ("competition", "league", "competitionname", "leaguename",
                     "wettbewerb", "liga"),
    "spielort":     ("venue", "ground", "location", "spielort", "stadium"),
    "spieltag":     ("matchday", "round", "spieltag", "matchdaynumber"),
}


def _text_aus(wert: Any) -> str:
    """Holt einen Namen -- auch wenn er in einem Unterobjekt steckt."""
    if wert is None:
        return ""
    if isinstance(wert, str):
        return wert.strip()
    if isinstance(wert, (int, float)):
        return str(wert)
    if isinstance(wert, dict):
        for schluessel in ("name", "displayName", "fullName", "shortName",
                           "title", "clubName", "teamName"):
            if schluessel in wert:
                return _text_aus(wert[schluessel])
        # Vor- und Nachname getrennt?
        vor = wert.get("firstName") or wert.get("vorname") or ""
        nach = wert.get("lastName") or wert.get("nachname") or ""
        if vor or nach:
            return f"{vor} {nach}".strip()
    return ""


#: Felder, unter denen eine Datenquelle den technischen Bezeichner einer
#: Mannschaft fuehrt. Reihenfolge = Vorrang: Ein sprechender Bezeichner ist
#: brauchbarer als eine blosse Nummer, weil sich daraus eine Seitenadresse
#: bauen laesst.
KENNUNG_FELDER: tuple[str, ...] = (
    "slug", "seoname", "seourl", "permalink", "urlname", "shortname",
    "url", "link", "href", "path", "id", "teamid", "clubid",
)


def _kennung_aus(wert: Any, tiefe: int = 0) -> str:
    """Der technische Bezeichner einer Mannschaft, falls einer mitgeliefert wird.

    Mal steht dort ein Kuerzel, mal eine volle Adresse, mal nur eine Nummer.
    Aus einer Adresse wird das letzte Wegstueck genommen -- genau das ist bei
    FuPa der Team-Bezeichner.
    """
    if tiefe > 2 or wert is None or isinstance(wert, bool):
        return ""
    if isinstance(wert, int):
        return str(wert)
    if isinstance(wert, str):
        text = wert.strip().strip("/")
        if not text:
            return ""
        if "://" in text or text.startswith("/"):
            text = text.rsplit("/", 1)[-1]
        # Ein Bezeichner enthaelt keine Leerzeichen -- sonst ist es ein Name.
        return text if text and " " not in text else ""
    if isinstance(wert, dict):
        for schluessel in KENNUNG_FELDER:
            for name, inhalt in wert.items():
                if _normal(name) == schluessel:
                    gefunden = _kennung_aus(inhalt, tiefe + 1)
                    if gefunden:
                        return gefunden
    return ""


def _zahl_aus(wert: Any) -> int | None:
    if isinstance(wert, bool):
        return None
    if isinstance(wert, int):
        return wert
    if isinstance(wert, float):
        return int(wert)
    if isinstance(wert, str):
        # "9." in einer Platzspalte, "+14" in einer Differenzspalte: Auf
        # einer Vereinsseite stehen Zahlen so, wie man sie liest.
        treffer = re.fullmatch(r"\s*([+-]?\d+)\s*\.?\s*", wert)
        if treffer:
            return int(treffer.group(1).lstrip("+"))
    if isinstance(wert, dict):
        for schluessel in ("value", "count", "total"):
            if schluessel in wert:
                return _zahl_aus(wert[schluessel])
    return None


#: "18:4" -- Tore und Gegentore in einer Spalte.
_TORPAAR = re.compile(r"\s*(\d{1,3})\s*[:\-]\s*(\d{1,3})\s*")
#: "3-1-3" -- Siege, Unentschieden, Niederlagen in einer Spalte.
_SUN = re.compile(r"\s*(\d{1,2})\s*[-/:]\s*(\d{1,2})\s*[-/:]\s*(\d{1,2})\s*")


class Zeile:
    """Ein flach durchsuchbarer Blick auf ein JSON-Objekt.

    Verschachtelte Objekte werden mit eingesammelt, damit ``team.name`` unter
    dem Schluessel ``teamname`` auffindbar ist.
    """

    def __init__(self, roh: dict) -> None:
        self.roh = roh
        self.flach: dict[str, Any] = {}
        self._einsammeln(roh, "", 0)
        self._zusammengesetzte_spalten_trennen()

    def _einsammeln(self, knoten: Any, praefix: str, tiefe: int) -> None:
        if tiefe > 3 or not isinstance(knoten, dict):
            return
        for schluessel, wert in knoten.items():
            name = _normal(f"{praefix}{schluessel}")
            self.flach.setdefault(name, wert)
            if isinstance(wert, dict):
                self.flach.setdefault(_normal(schluessel), wert)
                self._einsammeln(wert, f"{schluessel}", tiefe + 1)

    def _zusammengesetzte_spalten_trennen(self) -> None:
        """'18:4' und '3-1-3' in einzelne Werte zerlegen.

        Gedruckte Tabellen fassen zusammen, was zusammengehoert: eine Spalte
        "Tore" mit ``18:4`` statt zweier Spalten, eine Spalte "S-U-N" mit
        ``3-1-3``. Eine JSON-Schnittstelle macht das nie -- eine
        Vereinsseite fast immer.

        Die Trennung steht hier und nicht im HTML-Leser, weil sie nichts mit
        HTML zu tun hat: Es ist eine Schreibweise von Werten, und die kann
        aus jeder Quelle kommen.
        """
        for name in FELDER["tore"]:
            treffer = _TORPAAR.fullmatch(str(self.flach.get(name, "")))
            if treffer:
                self.flach[name] = treffer.group(1)
                self.flach.setdefault("gegentore", treffer.group(2))
                break

        for name, wert in list(self.flach.items()):
            if not isinstance(wert, str):
                continue
            # Nur Spalten, deren Name nach "S-U-N" aussieht -- sonst wuerde
            # ein Datum wie "3-1-2026" zur Bilanz.
            if name not in ("sun", "suns", "bilanz", "snu"):
                continue
            treffer = _SUN.fullmatch(wert)
            if treffer:
                self.flach.setdefault("siege", treffer.group(1))
                self.flach.setdefault("unentschieden", treffer.group(2))
                self.flach.setdefault("niederlagen", treffer.group(3))
                break

    def hat(self, feld: str) -> bool:
        return any(name in self.flach for name in FELDER.get(feld, ()))

    def text(self, feld: str, standard: str = "") -> str:
        for name in FELDER.get(feld, ()):
            if name in self.flach:
                gefunden = _text_aus(self.flach[name])
                if gefunden:
                    return gefunden
        return standard

    def zahl(self, feld: str, standard: int = 0) -> int:
        for name in FELDER.get(feld, ()):
            if name in self.flach:
                gefunden = _zahl_aus(self.flach[name])
                if gefunden is not None:
                    return gefunden
        return standard

    def zahl_oder_nichts(self, feld: str) -> int | None:
        for name in FELDER.get(feld, ()):
            if name in self.flach:
                gefunden = _zahl_aus(self.flach[name])
                if gefunden is not None:
                    return gefunden
        return None

    def kennung(self, feld: str) -> str:
        """Der technische Bezeichner hinter einem Feld, z. B. der Team-Slug.

        Erst wird im Unterobjekt gesucht (``homeTeam.slug``), dann unter den
        zusammengesetzten Namen, die beim Flachklopfen entstanden sind
        (``hometeamslug``). Sprechende Bezeichner haben Vorrang vor Nummern.
        """
        nummer = ""
        for name in FELDER.get(feld, ()):
            kandidaten = [self.flach[name]] if name in self.flach else []
            kandidaten += [self.flach[f"{name}{k}"] for k in KENNUNG_FELDER
                           if f"{name}{k}" in self.flach]
            for kandidat in kandidaten:
                gefunden = _kennung_aus(kandidat)
                if not gefunden:
                    continue
                if not gefunden.isdigit():
                    return gefunden
                nummer = nummer or gefunden
        return nummer


# ---------------------------------------------------------------------------
# Alle Listen im JSON einsammeln
# ---------------------------------------------------------------------------

def alle_listen(knoten: Any, tiefe: int = 0) -> Iterable[list[dict]]:
    """Liefert jede Liste von Objekten, die irgendwo im JSON steckt."""
    if tiefe > 12:
        return
    if isinstance(knoten, list):
        objekte = [e for e in knoten if isinstance(e, dict)]
        if len(objekte) >= 2:
            yield objekte
        for eintrag in knoten:
            yield from alle_listen(eintrag, tiefe + 1)
    elif isinstance(knoten, dict):
        for wert in knoten.values():
            yield from alle_listen(wert, tiefe + 1)


# ---------------------------------------------------------------------------
# Bewerten: wie gut passt eine Liste zu einer Erwartung?
# ---------------------------------------------------------------------------

def _punkte_tabelle(zeilen: list[Zeile]) -> float:
    anteil = lambda pruef: sum(1 for z in zeilen if pruef(z)) / len(zeilen)
    mannschaft = anteil(lambda z: bool(z.text("mannschaft")))
    punkte = anteil(lambda z: z.zahl_oder_nichts("punkte") is not None)
    bilanz = anteil(lambda z: z.hat("siege") and z.hat("niederlagen"))
    if mannschaft < 0.6 or (punkte < 0.6 and bilanz < 0.6):
        return 0.0
    # Spielerzeilen haben oft auch "team" -- Minuten/Karten sprechen dagegen
    stoerung = anteil(lambda z: z.hat("minuten") or z.hat("gelb"))
    return mannschaft + punkte + bilanz - 2 * stoerung


def _punkte_torjaeger(zeilen: list[Zeile]) -> float:
    anteil = lambda pruef: sum(1 for z in zeilen if pruef(z)) / len(zeilen)
    spieler = anteil(lambda z: bool(z.text("spieler")))
    tore = anteil(lambda z: z.zahl_oder_nichts("tore") is not None)
    if spieler < 0.6 or tore < 0.6:
        return 0.0
    verein = anteil(lambda z: bool(z.text("mannschaft")))
    # Eine Torschuetzenliste ist nach Toren sortiert und hat kaum Nullen
    mit_toren = anteil(lambda z: z.zahl("tore") > 0)
    einsatzdaten = anteil(lambda z: z.hat("minuten") or z.hat("gelb")
                          or z.hat("eingewechselt"))
    return spieler + tore + verein + mit_toren - 1.5 * einsatzdaten


def _punkte_spieler(zeilen: list[Zeile]) -> float:
    anteil = lambda pruef: sum(1 for z in zeilen if pruef(z)) / len(zeilen)
    spieler = anteil(lambda z: bool(z.text("spieler")))
    if spieler < 0.6:
        return 0.0
    einsatz = anteil(lambda z: z.hat("spiele") or z.hat("minuten"))
    karten = anteil(lambda z: z.hat("gelb") or z.hat("rot"))
    wechsel = anteil(lambda z: z.hat("eingewechselt") or z.hat("ausgewechselt"))
    if einsatz < 0.5:
        return 0.0
    return spieler + einsatz + karten + wechsel


def _punkte_spiele(zeilen: list[Zeile]) -> float:
    anteil = lambda pruef: sum(1 for z in zeilen if pruef(z)) / len(zeilen)
    paarung = anteil(lambda z: bool(z.text("heim")) and bool(z.text("gast")))
    datum = anteil(lambda z: bool(z.text("anstoss")))
    if paarung < 0.6:
        return 0.0
    return paarung + datum


# ---------------------------------------------------------------------------
# Oeffentliche Erkennungsfunktionen
# ---------------------------------------------------------------------------

def _beste_liste(nutzlast: Any, bewerten, mindestens: float = 1.2
                 ) -> tuple[list[Zeile], float]:
    beste: list[Zeile] = []
    bester_wert = mindestens
    for roh in alle_listen(nutzlast):
        zeilen = [Zeile(e) for e in roh]
        wert = bewerten(zeilen)
        # Bei Gleichstand gewinnt die laengere Liste (vollstaendigere Tabelle)
        if wert > bester_wert or (wert == bester_wert and len(zeilen) > len(beste)):
            beste, bester_wert = zeilen, wert
    return beste, bester_wert


def tabelle_erkennen(nutzlast: Any, eigener_verein: str = "") -> list[TabellenZeile]:
    zeilen, wert = _beste_liste(nutzlast, _punkte_tabelle)
    if not zeilen:
        return []
    logger().debug("Tabelle erkannt: %d Zeilen (Güte %.2f)", len(zeilen), wert)

    kern = _vereinskern(eigener_verein)
    ergebnis: list[TabellenZeile] = []
    for nr, z in enumerate(zeilen, 1):
        name = z.text("mannschaft")
        ergebnis.append(TabellenZeile(
            platz=z.zahl("platz", nr),
            mannschaft=name,
            spiele=z.zahl("spiele"),
            siege=z.zahl("siege"),
            unentschieden=z.zahl("unentschieden"),
            niederlagen=z.zahl("niederlagen"),
            tore=z.zahl("tore"),
            gegentore=z.zahl("gegentore"),
            punkte=z.zahl("punkte"),
            eigene=bool(kern) and kern in name.lower(),
        ))
    return ergebnis


def torjaeger_erkennen(nutzlast: Any, eigener_verein: str = "") -> list[TorjaegerZeile]:
    zeilen, wert = _beste_liste(nutzlast, _punkte_torjaeger)
    if not zeilen:
        return []
    logger().debug("Torschützenliste erkannt: %d Zeilen (Güte %.2f)",
                   len(zeilen), wert)

    kern = _vereinskern(eigener_verein)
    ergebnis: list[TorjaegerZeile] = []
    for nr, z in enumerate(zeilen, 1):
        verein = z.text("mannschaft")
        ergebnis.append(TorjaegerZeile(
            platz=z.zahl("platz", nr),
            spieler=z.text("spieler"),
            mannschaft=verein,
            tore=z.zahl("tore"),
            vorlagen=z.zahl("vorlagen"),
            spiele=z.zahl("spiele"),
            eigene=bool(kern) and kern in verein.lower(),
        ))
    return ergebnis


def spieler_erkennen(nutzlast: Any) -> list[SpielerZeile]:
    zeilen, wert = _beste_liste(nutzlast, _punkte_spieler)
    if not zeilen:
        return []
    logger().debug("Spielerstatistik erkannt: %d Zeilen (Güte %.2f)",
                   len(zeilen), wert)

    ergebnis: list[SpielerZeile] = []
    for nr, z in enumerate(zeilen, 1):
        getroffen, gesamt = _elfmeter(z)
        ergebnis.append(SpielerZeile(
            platz=z.zahl("platz", nr),
            spieler=z.text("spieler"),
            spiele=z.zahl("spiele"),
            tore=z.zahl("tore"),
            vorlagen=z.zahl("vorlagen"),
            elfmeter_getroffen=getroffen,
            elfmeter_gesamt=gesamt,
            gelb=z.zahl("gelb"),
            gelb_rot=z.zahl("gelb_rot"),
            rot=z.zahl("rot"),
            eingewechselt=z.zahl("eingewechselt"),
            ausgewechselt=z.zahl("ausgewechselt"),
            minuten=z.zahl("minuten"),
        ))
    return ergebnis


def spiele_erkennen(nutzlast: Any, eigener_verein: str = "") -> list[Spiel]:
    zeilen, wert = _beste_liste(nutzlast, _punkte_spiele, mindestens=0.8)
    if not zeilen:
        return []
    logger().debug("Spielplan erkannt: %d Partien (Güte %.2f)", len(zeilen), wert)

    kern = _vereinskern(eigener_verein)
    ergebnis: list[Spiel] = []
    for z in zeilen:
        heim, gast = z.text("heim"), z.text("gast")
        ergebnis.append(Spiel(
            heim=heim,
            gast=gast,
            wettbewerb=z.text("wettbewerb"),
            anstoss=_iso(z.text("anstoss")),
            spielort=z.text("spielort"),
            heimspiel=bool(kern) and kern in heim.lower(),
            spieltag=z.text("spieltag"),
            ergebnis=_ergebnis(z),
            heim_kennung=z.kennung("heim"),
            gast_kennung=z.kennung("gast"),
        ))
    return ergebnis


# ---------------------------------------------------------------------------
# Kleinkram
# ---------------------------------------------------------------------------

def _vereinskern(name: str) -> str:
    """'SV Wörnitzstein-Berg' -> 'wörnitzstein' (zum Wiedererkennen)."""
    kern = (name or "").replace("e.V.", "")
    kern = re.sub(r"\b(sv|tsv|fc|sg|vfl|tsg|spvgg|djk|1\.)\b", "", kern,
                  flags=re.IGNORECASE)
    kern = kern.split("-")[0].strip().lower()
    return kern


def _elfmeter(z: Zeile) -> tuple[int, int]:
    for name in FELDER["elfmeter"]:
        if name in z.flach:
            wert = z.flach[name]
            if isinstance(wert, str) and "/" in wert:
                links, _, rechts = wert.partition("/")
                return (_zahl_aus(links) or 0, _zahl_aus(rechts) or 0)
            zahl = _zahl_aus(wert)
            if zahl is not None:
                return (zahl, zahl)
    return (0, 0)


#: Ein fertig formuliertes Ergebnis, z. B. "2:1". Manche Quellen liefern das
#: statt zweier Torzahlen -- Kalenderdateien etwa.
_FERTIGES_ERGEBNIS = re.compile(r"^\s*(\d{1,2})\s*:\s*(\d{1,2})\s*$")


def _ergebnis(z: Zeile) -> str:
    heim = None
    gast = None
    for name, wert in z.flach.items():
        if name in ("homegoals", "goalshome", "resulthome", "hometeamgoals"):
            heim = _zahl_aus(wert)
        elif name in ("awaygoals", "goalsaway", "resultaway", "awayteamgoals"):
            gast = _zahl_aus(wert)
    if heim is not None and gast is not None:
        return f"{heim}:{gast}"

    # Kein Torpaar gefunden -- steht das Ergebnis vielleicht schon fertig da?
    for name in ("ergebnis", "result", "score", "endstand"):
        wert = z.flach.get(name)
        if isinstance(wert, str):
            treffer = _FERTIGES_ERGEBNIS.match(wert)
            if treffer:
                return f"{int(treffer.group(1))}:{int(treffer.group(2))}"
    return ""


def _iso(wert: str) -> str:
    if not wert:
        return ""
    text = str(wert).strip().replace("Z", "+00:00")
    from datetime import datetime
    for muster in (None, "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S",
                   "%Y-%m-%d"):
        try:
            if muster is None:
                return datetime.fromisoformat(text).replace(tzinfo=None).isoformat()
            return datetime.strptime(text, muster).isoformat()
        except ValueError:
            continue
    return ""
