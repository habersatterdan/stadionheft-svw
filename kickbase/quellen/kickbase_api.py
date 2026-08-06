"""Zugriff auf die Kickbase-Schnittstelle (Version 4).

Wichtig zum Verstaendnis:

* Diese Schnittstelle ist **nicht offiziell dokumentiert**. Sie ist die, die
  auch die Kickbase-App benutzt. Feldnamen sind stark abgekuerzt (``mv`` =
  Marktwert, ``ap`` = Durchschnittspunkte) und koennen sich ohne Ankuendigung
  aendern. Deshalb liest dieses Modul jedes Feld ueber :func:`_wert` mit
  mehreren moeglichen Namen und einem Standardwert -- ein umbenanntes Feld
  fuehrt so zu einer Luecke, nicht zum Absturz.
* Abgefragt werden ausschliesslich **eigene Daten** mit den eigenen
  Zugangsdaten, in normaler Geschwindigkeit und mit Pausen zwischen den
  Anfragen. Der Berater schreibt nichts zurueck: er kauft, verkauft und bietet
  nicht. Alle Entscheidungen trifft weiterhin der Mensch in der App.

Alles, was hier an Kuerzeln hereinkommt, verlaesst das Modul als sauberes
:class:`~kickbase.models.Spieler`-Objekt.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable

from ..errors import AnmeldeFehler, QuelleNichtErreichbarFehler
from ..logging_setup import logger
from ..models import Marktwertpunkt, Spieler, Spieltagsleistung
from .http import DateiCache, HttpQuelle

BASIS_URL = "https://api.kickbase.com"


def _wert(daten: Any, *namen: str, standard: Any = None) -> Any:
    """Liest das erste vorhandene Feld aus mehreren moeglichen Namen."""
    if not isinstance(daten, dict):
        return standard
    for name in namen:
        if name in daten and daten[name] is not None:
            return daten[name]
    return standard


def _zahl(daten: Any, *namen: str, standard: int = 0) -> int:
    roh = _wert(daten, *namen, standard=standard)
    try:
        return int(float(roh))
    except (TypeError, ValueError):
        return standard


def _liste(daten: Any, *namen: str) -> list:
    """Kickbase verpackt Listen mal in ``it``, mal in ``items``, mal direkt."""
    if isinstance(daten, list):
        return daten
    roh = _wert(daten, *namen, "it", "items", "players", "pl", standard=[])
    return roh if isinstance(roh, list) else []


def _zu_datum(roh: Any) -> date | None:
    """Wandelt die verschiedenen Datumsformate der Schnittstelle um.

    Vorgefunden wurden bisher: ISO-Text (``2026-02-26T18:30:00Z``),
    Unix-Sekunden, Unix-Millisekunden und ein Tagesindex seit 1970.
    """
    if roh in (None, ""):
        return None
    if isinstance(roh, str):
        text = roh.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            try:
                return date.fromisoformat(text[:10])
            except ValueError:
                return None
    try:
        zahl = float(roh)
    except (TypeError, ValueError):
        return None
    if zahl <= 0:
        return None
    try:
        if zahl > 1e12:            # Millisekunden
            return datetime.fromtimestamp(zahl / 1000, tz=timezone.utc).date()
        if zahl > 1e9:             # Sekunden
            return datetime.fromtimestamp(zahl, tz=timezone.utc).date()
        if zahl > 10000:           # Tage seit 1970 waeren unrealistisch gross
            return None
        return date.fromordinal(date(1970, 1, 1).toordinal() + int(zahl))
    except (OverflowError, OSError, ValueError):
        return None


class KickbaseQuelle(HttpQuelle):
    """Meldet sich an und liefert Spieler-, Liga- und Marktdaten."""

    name = "Kickbase"

    def __init__(self, email: str, passwort: str, *,
                 cache: DateiCache | None = None,
                 wettbewerb_id: str = "1",
                 pause_ms: int = 250) -> None:
        super().__init__(cache=cache, pause_ms=pause_ms)
        self._email = email
        self._passwort = passwort
        self.wettbewerb_id = str(wettbewerb_id)
        self.token = ""
        self.benutzername = ""
        self.benutzer_id = ""

    # -- Anmeldung ---------------------------------------------------------

    def anmelden(self) -> None:
        """Holt einen Zugangsschluessel und legt ihn in die Sitzung."""
        if not self._email or not self._passwort:
            raise AnmeldeFehler(
                "Keine Zugangsdaten gesetzt.",
                benutzer_text="Es sind keine Kickbase-Zugangsdaten hinterlegt.",
                hinweis="KICKBASE_EMAIL und KICKBASE_PASSWORT setzen.")

        antwort = self.anfragen(
            "POST", f"{BASIS_URL}/v4/user/login",
            json_daten={"em": self._email, "pass": self._passwort,
                        "loy": False, "rep": {}})

        if antwort.status_code in (400, 401, 403):
            raise AnmeldeFehler(
                f"Anmeldung abgelehnt (Code {antwort.status_code}).",
                hinweis="Stimmen E-Mail und Passwort? In der Kickbase-App "
                        "pruefen, ob die Anmeldung dort funktioniert.")
        if antwort.status_code >= 400:
            raise QuelleNichtErreichbarFehler(
                f"Anmeldung fehlgeschlagen (Code {antwort.status_code}).")

        try:
            daten = antwort.json()
        except ValueError as fehler:
            raise AnmeldeFehler("Anmeldeantwort war kein JSON.") from fehler

        self.token = str(_wert(daten, "tkn", "token", "accessToken", standard=""))
        if not self.token:
            raise AnmeldeFehler(
                "Antwort enthielt keinen Zugangsschluessel.",
                hinweis="Vermutlich hat Kickbase die Schnittstelle geaendert.")

        benutzer = _wert(daten, "u", "user", standard={}) or {}
        self.benutzername = str(_wert(benutzer, "name", "n", "unm", standard=""))
        self.benutzer_id = str(_wert(benutzer, "id", "i", standard=""))
        self.sitzung.headers["Authorization"] = f"Bearer {self.token}"
        logger().info("Bei Kickbase angemeldet%s.",
                      f" als {self.benutzername}" if self.benutzername else "")

    def _sicherstellen(self) -> None:
        if not self.token:
            self.anmelden()

    def _get(self, pfad: str, **kwargs) -> Any:
        self._sicherstellen()
        return self.holen(f"{BASIS_URL}{pfad}", **kwargs)

    # -- Ligen -------------------------------------------------------------

    def ligen(self) -> list[dict]:
        """Alle Ligen, in denen der angemeldete Benutzer mitspielt."""
        daten = self._get("/v4/leagues/selection")
        ligen = []
        for eintrag in _liste(daten):
            ligen.append({
                "id": str(_wert(eintrag, "i", "id", standard="")),
                "name": str(_wert(eintrag, "n", "name", standard="Liga")),
                "budget": _zahl(eintrag, "b", "budget"),
                "teamwert": _zahl(eintrag, "tv", "teamValue"),
                "platz": _zahl(eintrag, "pl", "placement"),
                "mitspieler": _zahl(eintrag, "un", "userCount"),
            })
        return [l for l in ligen if l["id"]]

    def liga_waehlen(self, liga_id: str = "") -> dict:
        """Nimmt die angegebene Liga -- oder die erste, wenn nichts gesetzt ist."""
        alle = self.ligen()
        if not alle:
            raise QuelleNichtErreichbarFehler(
                "Kickbase meldet keine Liga fuer dieses Konto.",
                benutzer_text="Zu diesem Konto wurde keine Liga gefunden.",
                hinweis="In der Kickbase-App pruefen, ob eine Liga aktiv ist.")
        if liga_id:
            for liga in alle:
                if liga["id"] == str(liga_id):
                    return liga
            raise QuelleNichtErreichbarFehler(
                f"Liga {liga_id} nicht im Konto gefunden.",
                benutzer_text=f"Die eingestellte Liga-ID {liga_id} gibt es in "
                              "diesem Konto nicht.",
                hinweis="Bekannte Ligen: " + ", ".join(
                    f"{l['name']} ({l['id']})" for l in alle))
        return alle[0]

    def budget(self, liga_id: str) -> int:
        try:
            daten = self._get(f"/v4/leagues/{liga_id}/me/budget")
        except QuelleNichtErreichbarFehler:
            return 0
        return _zahl(daten, "b", "budget", "value")

    # -- Spieler -----------------------------------------------------------

    def eigener_kader(self, liga_id: str) -> list[Spieler]:
        """Die eigenen Spieler samt Marktwert, Punkten und Status."""
        daten = self._get(f"/v4/leagues/{liga_id}/squad")
        spieler = [self._spieler_aus_kurzform(e) for e in _liste(daten)]
        for s in spieler:
            s.im_eigenen_team = True
        return [s for s in spieler if s.id]

    def transfermarkt(self, liga_id: str) -> list[Spieler]:
        """Wer gerade in der Liga zum Verkauf steht."""
        daten = self._get(f"/v4/leagues/{liga_id}/market")
        ergebnis: list[Spieler] = []
        for eintrag in _liste(daten):
            spieler = self._spieler_aus_kurzform(eintrag)
            if not spieler.id:
                continue
            spieler.auf_transfermarkt = True
            spieler.angebotspreis = (_zahl(eintrag, "prc", "price", "offer")
                                     or spieler.marktwert)
            verkaeufer = _wert(eintrag, "u", "usr", "seller", standard={})
            if isinstance(verkaeufer, dict):
                spieler.besitzer = str(_wert(verkaeufer, "unm", "n", "name", standard=""))
            elif isinstance(verkaeufer, str):
                spieler.besitzer = verkaeufer
            ergebnis.append(spieler)
        return ergebnis

    def wettbewerbsspieler(self, position: int | None = None) -> list[Spieler]:
        """Alle Bundesligaspieler -- die Grundlage fuer die Kandidatensuche."""
        params: dict[str, Any] = {}
        if position:
            params["position"] = position
        daten = self._get(f"/v4/competitions/{self.wettbewerb_id}/players",
                          params=params or None)
        spieler = [self._spieler_aus_kurzform(e) for e in _liste(daten)]
        return [s for s in spieler if s.id]

    def spieler_details(self, liga_id: str, spieler_id: str) -> dict:
        """Stammdaten eines Spielers (Vorname, Verein, Tore, Karten, ...)."""
        return self._get(f"/v4/leagues/{liga_id}/players/{spieler_id}")

    def marktwertverlauf(self, liga_id: str, spieler_id: str,
                         tage: int = 92) -> list[Marktwertpunkt]:
        daten = self._get(
            f"/v4/leagues/{liga_id}/players/{spieler_id}/marketvalue/{int(tage)}")
        punkte: list[Marktwertpunkt] = []
        for eintrag in _liste(daten):
            tag = _zu_datum(_wert(eintrag, "dt", "d", "day", "date"))
            wert = _zahl(eintrag, "mv", "v", "value")
            if tag and wert > 0:
                punkte.append(Marktwertpunkt(tag=tag, wert=wert))
        punkte.sort(key=lambda p: p.tag)
        return punkte

    def leistungen(self, liga_id: str, spieler_id: str) -> list[Spieltagsleistung]:
        """Spieltag fuer Spieltag: Punkte, Minuten, Gegner.

        Die Schnittstelle liefert alle Saisons; ausgewertet wird die letzte,
        also die laufende.
        """
        daten = self._get(f"/v4/leagues/{liga_id}/players/{spieler_id}/performance")
        saisons = _liste(daten)
        if not saisons:
            return []
        aktuelle = saisons[-1]
        eigenes_team = ""
        ergebnis: list[Spieltagsleistung] = []
        for eintrag in _liste(aktuelle, "ph"):
            eigenes_team = str(_wert(eintrag, "pt", standard=eigenes_team) or eigenes_team)
            t1 = str(_wert(eintrag, "t1", standard=""))
            t2 = str(_wert(eintrag, "t2", standard=""))
            heim = bool(eigenes_team and eigenes_team == t1)
            gegner = t2 if heim else t1
            minuten = _zahl(eintrag, "mp", "min", "minutesPlayed")
            punkte = _zahl(eintrag, "p", "tp", "points")
            datum = _zu_datum(_wert(eintrag, "md", "d", "date"))
            # "Gespielt" heisst: das Spiel hat stattgefunden. Ein Spieler mit
            # 0 Minuten war dann auf der Bank -- das ist eine Information,
            # keine fehlende Angabe.
            gespielt = bool(datum and datum <= date.today()) or minuten > 0
            ergebnis.append(Spieltagsleistung(
                spieltag=_zahl(eintrag, "day", "md_no", standard=len(ergebnis) + 1),
                punkte=punkte, minuten=minuten,
                status=_zahl(eintrag, "st"), datum=datum,
                eigenes_team_id=eigenes_team, gegner_team_id=gegner,
                heimspiel=heim, gespielt=gespielt))
        return ergebnis

    def anreichern(self, liga_id: str, spieler: Spieler, *,
                   marktwert_tage: int = 92,
                   mit_verlauf: bool = True) -> Spieler:
        """Ergaenzt einen Spieler um Details, Verlauf und Spieltagsleistungen.

        Jeder Teil wird einzeln abgesichert: faellt der Marktwertverlauf aus,
        bleibt der Rest trotzdem nutzbar.
        """
        try:
            details = self.spieler_details(liga_id, spieler.id)
            self._details_uebernehmen(spieler, details)
        except QuelleNichtErreichbarFehler as fehler:
            logger().debug("Keine Details fuer %s: %s", spieler.id, fehler)

        try:
            spieler.leistungen = self.leistungen(liga_id, spieler.id)
        except QuelleNichtErreichbarFehler as fehler:
            logger().debug("Keine Leistungsdaten fuer %s: %s", spieler.id, fehler)

        if mit_verlauf:
            try:
                spieler.verlauf = self.marktwertverlauf(
                    liga_id, spieler.id, marktwert_tage)
            except QuelleNichtErreichbarFehler as fehler:
                logger().debug("Kein Marktwertverlauf fuer %s: %s", spieler.id, fehler)
        return spieler

    # -- Umwandlung --------------------------------------------------------

    def _spieler_aus_kurzform(self, eintrag: dict) -> Spieler:
        """Kaderzeile oder Marktzeile -> Spieler-Objekt."""
        spieler_daten = eintrag
        # Auf dem Transfermarkt steckt der Spieler manchmal in einem Unterfeld.
        if isinstance(_wert(eintrag, "pl", "player"), dict):
            spieler_daten = _wert(eintrag, "pl", "player")

        return Spieler(
            id=str(_wert(spieler_daten, "i", "id", "pi", standard="")),
            vorname=str(_wert(spieler_daten, "fn", "firstName", standard="")),
            nachname=str(_wert(spieler_daten, "n", "ln", "lastName", standard="")),
            team_id=str(_wert(spieler_daten, "tid", "teamId", standard="")),
            team_name=str(_wert(spieler_daten, "tn", "teamName", standard="")),
            position=_zahl(spieler_daten, "pos", "position"),
            status=_zahl(spieler_daten, "st", "status"),
            marktwert=_zahl(spieler_daten, "mv", "marketValue"),
            marktwert_trend=_zahl(spieler_daten, "mvt", "marketValueTrend"),
            punkte_gesamt=_zahl(spieler_daten, "p", "tp", "points"),
            punkte_schnitt=_zahl(spieler_daten, "ap", "averagePoints"),
            spiele=_zahl(spieler_daten, "smc", "matches"),
        )

    def _details_uebernehmen(self, spieler: Spieler, details: dict) -> None:
        spieler.vorname = str(_wert(details, "fn", standard=spieler.vorname))
        spieler.nachname = str(_wert(details, "ln", standard=spieler.nachname))
        spieler.team_id = str(_wert(details, "tid", standard=spieler.team_id))
        spieler.team_name = str(_wert(details, "tn", standard=spieler.team_name))
        spieler.position = _zahl(details, "pos", standard=spieler.position)
        spieler.status = _zahl(details, "st", standard=spieler.status)
        spieler.marktwert = _zahl(details, "mv", standard=spieler.marktwert)
        spieler.marktwert_trend = _zahl(details, "mvt", standard=spieler.marktwert_trend)
        spieler.punkte_gesamt = _zahl(details, "tp", standard=spieler.punkte_gesamt)
        spieler.punkte_schnitt = _zahl(details, "ap", standard=spieler.punkte_schnitt)
        spieler.spiele = _zahl(details, "smc", standard=spieler.spiele)
        spieler.tore = _zahl(details, "g", standard=spieler.tore)
        spieler.vorlagen = _zahl(details, "a", standard=spieler.vorlagen)
        spieler.minuten_gesamt = _zahl(details, "sec") // 60 or spieler.minuten_gesamt

        # ``stl`` enthaelt Klartextmeldungen zu Verletzung oder Sperre.
        for eintrag in _liste(details, "stl"):
            text = str(_wert(eintrag, "t", "text", "n", standard="")).strip()
            if text:
                spieler.verletzungsmeldung = text
                spieler.verletzungsquelle = "Kickbase"
                break

    # -- Mannschaften ------------------------------------------------------

    def mannschaftsnamen(self) -> dict[str, str]:
        """Zuordnung Team-ID -> Vereinsname aus der Bundesligatabelle."""
        try:
            daten = self._get(f"/v4/competitions/{self.wettbewerb_id}/table")
        except QuelleNichtErreichbarFehler:
            return {}
        namen: dict[str, str] = {}
        for eintrag in _liste(daten):
            tid = str(_wert(eintrag, "tid", "i", "id", standard=""))
            name = str(_wert(eintrag, "tn", "n", "name", standard=""))
            if tid and name:
                namen[tid] = name
        return namen

    def tabelle(self) -> list[dict]:
        """Aktuelle Bundesligatabelle -- Grundlage der Gegnerstaerke."""
        try:
            daten = self._get(f"/v4/competitions/{self.wettbewerb_id}/table")
        except QuelleNichtErreichbarFehler:
            return []
        tabelle = []
        for platz, eintrag in enumerate(_liste(daten), start=1):
            tabelle.append({
                "team_id": str(_wert(eintrag, "tid", "i", "id", standard="")),
                "name": str(_wert(eintrag, "tn", "n", "name", standard="")),
                "platz": _zahl(eintrag, "cpl", "pl", "rank", standard=platz),
                "punkte": _zahl(eintrag, "sp", "pts", "points"),
                "tordifferenz": _zahl(eintrag, "gd", "goalDiff"),
            })
        return [t for t in tabelle if t["team_id"]]


def namen_ergaenzen(spieler: Iterable[Spieler], namen: dict[str, str]) -> None:
    """Traegt fehlende Vereinsnamen nach (die Kaderliste liefert nur IDs)."""
    for s in spieler:
        if not s.team_name and s.team_id in namen:
            s.team_name = namen[s.team_id]
