"""Datenabruf von FuPa.

WICHTIGER HINWEIS -- bitte vor dem Scharfschalten lesen
=======================================================

FuPa (fupa.net) veroeffentlicht **keine oeffentlich dokumentierte, zugesagte
API**. Die Web-Oberflaeche von FuPa laedt ihre Inhalte zwar ueber interne
JSON-Schnittstellen nach, diese sind aber:

* nicht dokumentiert,
* nicht versioniert zugesichert,
* jederzeit ohne Ankuendigung aenderbar.

Deshalb ist dieses Modul bewusst so gebaut:

1. **Alle Endpunkte stehen in der Konfiguration**, nicht im Code.
   Aendert FuPa etwas, wird config/config.yaml angepasst -- kein Programmcode.
2. **Die Feldzuordnung ist nachsichtig.** Es wird nach mehreren moeglichen
   Feldnamen gesucht, statt genau einen zu erwarten.
3. **Es gibt ein Diagnosewerkzeug** (``python -m stadionheft.cli probe-fupa``),
   das die konfigurierten Endpunkte ausprobiert und die Rohantwort speichert.
   Damit laesst sich die Zuordnung ohne Raten festlegen.
4. **Es gibt immer einen Ausweg**: schlaegt der Abruf fehl, kann automatisch
   auf den Modus "manuell" (CSV) umgeschaltet werden.

Fairness gegenueber dem Betreiber (und damit auch Eigeninteresse):

* Es wird ein sprechender User-Agent mit Kontaktadresse gesendet.
* Zwischen zwei Anfragen liegt eine konfigurierbare Pause.
* Die robots.txt wird ausgewertet und respektiert.
* Es werden nur die wenigen Seiten geholt, die fuer ein Heft noetig sind
  (Groessenordnung: ein Dutzend Abrufe alle zwei Wochen).

Rechtliches siehe docs/KONZEPT.md, Abschnitt "Rechtliche Hinweise".
"""

from __future__ import annotations

import json
import time
import urllib.robotparser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from ..config import Konfiguration, Mannschaft
from ..errors import DatenNichtLesbarFehler, DatenquelleNichtErreichbarFehler
from ..logging_setup import logger
from ..models import (MannschaftsDaten, Spiel, SpielerZeile, TabellenZeile,
                      TorjaegerZeile, spiele_einordnen)
from .base import basis_daten
from .cache import DateiCache

# ---------------------------------------------------------------------------
# Nachsichtige Feldsuche
# ---------------------------------------------------------------------------

def _wert(quelle: Any, *namen: str, standard: Any = None) -> Any:
    """Erster vorhandener Wert aus mehreren moeglichen Feldnamen.

    Unterstuetzt auch Punktpfade: ``_wert(d, "team.name")``.
    """
    if not isinstance(quelle, dict):
        return standard
    for name in namen:
        knoten: Any = quelle
        for teil in name.split("."):
            if isinstance(knoten, dict) and teil in knoten:
                knoten = knoten[teil]
            else:
                knoten = None
                break
        if knoten not in (None, ""):
            return knoten
    return standard


def _zahl(quelle: Any, *namen: str, standard: int = 0) -> int:
    roh = _wert(quelle, *namen, standard=standard)
    try:
        return int(roh)
    except (TypeError, ValueError):
        return standard


def _text(quelle: Any, *namen: str, standard: str = "") -> str:
    roh = _wert(quelle, *namen, standard=standard)
    if isinstance(roh, dict):
        roh = _wert(roh, "name", "displayName", "title", standard="")
    return str(roh).strip() if roh is not None else standard


def _liste_finden(nutzlast: Any, *schluessel: str) -> list[dict]:
    """Findet die eigentliche Datenliste in einer JSON-Antwort.

    JSON-Antworten verpacken Listen gern unterschiedlich tief
    (``{"data": {"rows": [...]}}``). Statt eine feste Struktur zu erwarten,
    wird zuerst unter bekannten Schluesseln gesucht und danach die erste
    gefundene Liste von Objekten genommen.
    """
    if isinstance(nutzlast, list):
        return [e for e in nutzlast if isinstance(e, dict)]
    if not isinstance(nutzlast, dict):
        return []
    for name in (*schluessel, "data", "items", "results", "rows", "entries",
                 "standings", "table", "players", "matches", "scorers"):
        if name in nutzlast:
            treffer = _liste_finden(nutzlast[name])
            if treffer:
                return treffer
    for wert in nutzlast.values():
        if isinstance(wert, (list, dict)):
            treffer = _liste_finden(wert)
            if treffer:
                return treffer
    return []


# ---------------------------------------------------------------------------
# HTTP-Client
# ---------------------------------------------------------------------------

class FupaClient:
    """Duenner HTTP-Client mit Wiederholung, Pause und robots.txt-Pruefung."""

    def __init__(self, konfiguration: Konfiguration) -> None:
        k = konfiguration
        self.basis_url = str(k.get("datenquelle.fupa.basis_url",
                                   "https://api.fupa.net")).rstrip("/") + "/"
        self.endpunkte: dict[str, str] = dict(
            k.get("datenquelle.fupa.endpunkte", {}) or {})
        self.timeout = float(k.get("datenquelle.fupa.timeout_sekunden", 20))
        self.wiederholungen = int(k.get("datenquelle.fupa.wiederholungen", 2))
        self.pause = float(k.get(
            "datenquelle.fupa.pause_zwischen_anfragen_sekunden", 1.5))
        self.user_agent = str(k.get("datenquelle.fupa.user_agent",
                                    "SVW-Stadionheft/0.1"))
        self.robots_beachten = bool(k.get("datenquelle.fupa.robots_txt_beachten", True))
        self.cache = DateiCache(
            k.pfad(k.get("datenquelle.cache.ordner"),
                   "daten/04_zwischenergebnisse/cache"),
            int(k.get("datenquelle.cache.gueltigkeit_minuten", 120)),
            bool(k.get("datenquelle.cache.aktiv", True)),
        )
        self._letzte_anfrage = 0.0
        self._robots: urllib.robotparser.RobotFileParser | None = None
        self._session = None

    # -- Hilfen -------------------------------------------------------------

    def _sitzung(self):
        if self._session is None:
            try:
                import requests
            except ImportError as fehler:  # pragma: no cover
                raise DatenquelleNichtErreichbarFehler(
                    "Paket 'requests' fehlt.",
                    benutzer_text="Ein benoetigtes Programmpaket fehlt auf dem Server.",
                    hinweis="Bitte 'pip install -r requirements.txt' ausfuehren.",
                ) from fehler
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                "Accept-Language": "de-DE,de;q=0.9",
            })
        return self._session

    def _robots_erlaubt(self, url: str) -> bool:
        if not self.robots_beachten:
            return True
        if self._robots is None:
            teile = urlparse(url)
            self._robots = urllib.robotparser.RobotFileParser()
            self._robots.set_url(f"{teile.scheme}://{teile.netloc}/robots.txt")
            try:
                self._robots.read()
            except Exception as fehler:  # robots.txt nicht abrufbar
                logger().info("robots.txt nicht lesbar (%s) - Abruf wird fortgesetzt.",
                              fehler)
                self._robots = urllib.robotparser.RobotFileParser()
                self._robots.parse([])   # leere Regeln = alles erlaubt
        return self._robots.can_fetch(self.user_agent, url)

    def _drosseln(self) -> None:
        wartezeit = self.pause - (time.monotonic() - self._letzte_anfrage)
        if wartezeit > 0:
            time.sleep(wartezeit)
        self._letzte_anfrage = time.monotonic()

    # -- Oeffentlich --------------------------------------------------------

    def url_fuer(self, endpunkt: str, **platzhalter: str) -> str:
        vorlage = self.endpunkte.get(endpunkt)
        if not vorlage:
            raise DatenNichtLesbarFehler(
                f"Kein Endpunkt '{endpunkt}' konfiguriert.",
                benutzer_text=f"Fuer '{endpunkt}' ist keine FuPa-Adresse hinterlegt.",
                hinweis=("Bitte in config/config.yaml unter "
                         "datenquelle.fupa.endpunkte ergaenzen."),
            )
        return urljoin(self.basis_url, vorlage.format(**platzhalter).lstrip("/"))

    def hole_json(self, url: str, pflicht: bool = True) -> Any | None:
        """Holt eine URL als JSON. Bei ``pflicht=False`` wird None zurueckgegeben."""
        zwischengespeichert = self.cache.lesen(url)
        if zwischengespeichert is not None:
            logger().debug("Aus Cache: %s", url)
            return zwischengespeichert

        if not self._robots_erlaubt(url):
            raise DatenquelleNichtErreichbarFehler(
                f"robots.txt verbietet den Abruf von {url}.",
                benutzer_text="FuPa erlaubt den automatischen Abruf dieser Seite nicht.",
                hinweis=("Bitte in der Konfiguration auf den Modus 'manuell' "
                         "umstellen und die Daten als CSV bereitstellen."),
            )

        import requests
        letzter_fehler: Exception | None = None
        for versuch in range(1, self.wiederholungen + 2):
            try:
                self._drosseln()
                logger().debug("GET %s (Versuch %d)", url, versuch)
                antwort = self._sitzung().get(url, timeout=self.timeout)
                if antwort.status_code == 404:
                    if pflicht:
                        raise DatenNichtLesbarFehler(
                            f"404 fuer {url}",
                            benutzer_text="Eine FuPa-Adresse wurde nicht gefunden (404).",
                            hinweis=("Wahrscheinlich stimmt der Team-Link oder die "
                                     "Saison nicht mehr. Bitte fupa_team_url in "
                                     "config/config.yaml pruefen."),
                        )
                    return None
                if antwort.status_code in (403, 429):
                    raise DatenquelleNichtErreichbarFehler(
                        f"HTTP {antwort.status_code} fuer {url}",
                        benutzer_text=("FuPa hat den automatischen Abruf abgelehnt "
                                       f"(Code {antwort.status_code})."),
                        hinweis=("Bitte spaeter erneut versuchen oder auf manuelle "
                                 "Eingabe umstellen."),
                    )
                antwort.raise_for_status()
                daten = antwort.json()
                self.cache.schreiben(url, daten)
                return daten
            except (DatenNichtLesbarFehler, DatenquelleNichtErreichbarFehler):
                raise
            except json.JSONDecodeError as fehler:
                raise DatenNichtLesbarFehler(
                    f"Antwort von {url} ist kein JSON: {fehler}",
                    benutzer_text="FuPa hat eine unerwartete Antwort geliefert.",
                    hinweis=("Vermutlich hat sich die Schnittstelle geaendert. Bitte "
                             "'probe-fupa' ausfuehren und die Konfiguration anpassen."),
                ) from fehler
            except requests.RequestException as fehler:
                letzter_fehler = fehler
                if versuch <= self.wiederholungen:
                    wartezeit = 2 ** versuch
                    logger().warning("Abruf fehlgeschlagen (%s) - neuer Versuch in %ds.",
                                     fehler, wartezeit)
                    time.sleep(wartezeit)

        # Letzter Rettungsanker: veralteter Cache
        veraltet = self.cache.lesen(url, auch_veraltet=True)
        if veraltet is not None:
            logger().warning("FuPa nicht erreichbar - verwende aeltere Daten aus dem Cache.")
            return veraltet
        raise DatenquelleNichtErreichbarFehler(
            f"{url}: {letzter_fehler}",
            benutzer_text="FuPa ist im Moment nicht erreichbar.",
            hinweis=("Bitte Internetverbindung pruefen und spaeter erneut versuchen. "
                     "Alternativ im Programm auf 'Manuelle Eingabe' umstellen."),
        )


# ---------------------------------------------------------------------------
# Datenquelle
# ---------------------------------------------------------------------------

class FupaApiQuelle:
    """Holt Tabelle, Torjaeger, Spielerstatistik und naechstes Spiel von FuPa."""

    name = "api"

    def __init__(self, konfiguration: Konfiguration) -> None:
        self.konfiguration = konfiguration
        self.client = FupaClient(konfiguration)
        self.vereinsname = konfiguration.vereinsname

    def hole(self, mannschaft: Mannschaft) -> MannschaftsDaten:
        daten = basis_daten(mannschaft, self.name)
        slug = mannschaft.fupa_slug
        if not slug:
            raise DatenNichtLesbarFehler(
                f"Kein Team-Bezeichner in '{mannschaft.fupa_team_url}'.",
                benutzer_text=(f"Fuer {mannschaft.anzeigename} fehlt ein gueltiger "
                               f"FuPa-Link."),
                hinweis=("Erwartet wird eine Adresse der Form "
                         "https://www.fupa.net/team/<name>-<saison>"),
            )

        logger().info("Hole FuPa-Daten fuer %s (%s) ...", mannschaft.anzeigename, slug)

        daten.tabelle = self._tabelle(slug, daten)
        daten.torjaeger = self._torjaeger(slug, daten)
        daten.spieler = self._spieler(slug, daten)
        self._spiele(slug, daten)
        return daten

    # -- Einzelteile --------------------------------------------------------

    def _sicher(self, beschreibung: str, daten: MannschaftsDaten, funktion):
        """Fuehrt einen Teilabruf aus; ein Fehlschlag ist nur eine Warnung."""
        try:
            return funktion()
        except DatenquelleNichtErreichbarFehler:
            raise      # Netzausfall betrifft alles -> nach oben durchreichen
        except Exception as fehler:
            logger().warning("%s konnte nicht geladen werden: %s", beschreibung, fehler)
            daten.warnungen.append(
                f"{beschreibung} konnte nicht von FuPa geladen werden "
                f"- die Seite bleibt leer.")
            return None

    def _tabelle(self, slug: str, daten: MannschaftsDaten) -> list[TabellenZeile]:
        def laden():
            nutzlast = self.client.hole_json(
                self.client.url_fuer("tabelle", team_slug=slug), pflicht=False)
            zeilen: list[TabellenZeile] = []
            for nr, eintrag in enumerate(_liste_finden(nutzlast, "standing", "table"), 1):
                name = _text(eintrag, "team.name", "teamName", "name", "club.name")
                zeilen.append(TabellenZeile(
                    platz=_zahl(eintrag, "place", "position", "rank", "platz",
                                standard=nr),
                    mannschaft=name,
                    spiele=_zahl(eintrag, "matches", "games", "played", "spiele"),
                    siege=_zahl(eintrag, "wins", "won", "siege"),
                    unentschieden=_zahl(eintrag, "draws", "drawn", "unentschieden"),
                    niederlagen=_zahl(eintrag, "losses", "lost", "niederlagen"),
                    tore=_zahl(eintrag, "goals", "goalsFor", "goalsScored", "tore"),
                    gegentore=_zahl(eintrag, "goalsAgainst", "goalsConceded",
                                    "gegentore"),
                    punkte=_zahl(eintrag, "points", "punkte"),
                    eigene=bool(self.vereinsname) and self._ist_eigene(name),
                ))
            return zeilen
        return self._sicher("Die Tabelle", daten, laden) or []

    def _torjaeger(self, slug: str, daten: MannschaftsDaten) -> list[TorjaegerZeile]:
        def laden():
            nutzlast = self.client.hole_json(
                self.client.url_fuer("torjaeger", team_slug=slug), pflicht=False)
            zeilen: list[TorjaegerZeile] = []
            for nr, eintrag in enumerate(_liste_finden(nutzlast, "scorers", "topscorers"), 1):
                verein = _text(eintrag, "team.name", "club.name", "teamName")
                zeilen.append(TorjaegerZeile(
                    platz=_zahl(eintrag, "place", "position", "rank", standard=nr),
                    spieler=self._spielername(eintrag),
                    mannschaft=verein,
                    tore=_zahl(eintrag, "goals", "tore"),
                    vorlagen=_zahl(eintrag, "assists", "vorlagen"),
                    spiele=_zahl(eintrag, "matches", "games", "spiele"),
                    eigene=self._ist_eigene(verein),
                ))
            return zeilen
        return self._sicher("Die Torschuetzenliste", daten, laden) or []

    def _spieler(self, slug: str, daten: MannschaftsDaten) -> list[SpielerZeile]:
        def laden():
            nutzlast = self.client.hole_json(
                self.client.url_fuer("spieler", team_slug=slug), pflicht=False)
            return self._spielerliste(nutzlast)
        return self._sicher("Die Spielerstatistik", daten, laden) or []

    def _spielerliste(self, nutzlast: Any) -> list[SpielerZeile]:
        zeilen: list[SpielerZeile] = []
        for nr, eintrag in enumerate(_liste_finden(nutzlast, "players", "squad"), 1):
            elfmeter = _text(eintrag, "penalties", "penalty", standard="0/0")
            getroffen, _, gesamt = elfmeter.partition("/")
            zeilen.append(SpielerZeile(
                platz=_zahl(eintrag, "place", "position", "rank", standard=nr),
                spieler=self._spielername(eintrag),
                spiele=_zahl(eintrag, "matches", "games", "appearances", "spiele"),
                tore=_zahl(eintrag, "goals", "tore"),
                vorlagen=_zahl(eintrag, "assists", "vorlagen"),
                elfmeter_getroffen=_zahl({"w": getroffen}, "w"),
                elfmeter_gesamt=_zahl({"w": gesamt}, "w"),
                gelb=_zahl(eintrag, "yellowCards", "yellow", "gelb"),
                gelb_rot=_zahl(eintrag, "yellowRedCards", "yellowRed", "gelbRot"),
                rot=_zahl(eintrag, "redCards", "red", "rot"),
                eingewechselt=_zahl(eintrag, "substitutedIn", "subIn", "in"),
                ausgewechselt=_zahl(eintrag, "substitutedOut", "subOut", "out"),
                minuten=_zahl(eintrag, "minutes", "minutesPlayed", "minuten"),
            ))
        return zeilen

    def _spiele(self, slug: str, daten: MannschaftsDaten) -> None:
        """Ermittelt die naechste und die letzte Partie -- anhand des Datums.

        Bewusst nicht "erster Eintrag ohne Ergebnis": Spielplaene kommen nicht
        immer sortiert, und ein noch nicht nachgetragenes Ergebnis wuerde sonst
        eine laengst gespielte Partie auf die Titelseite bringen.
        """
        def laden():
            nutzlast = self.client.hole_json(
                self.client.url_fuer("spielplan", team_slug=slug), pflicht=False)
            spiele = [self._spiel_aus(e)
                      for e in _liste_finden(nutzlast, "matches", "fixtures")]
            return spiele_einordnen(spiele)

        ergebnis = self._sicher("Der Spielplan", daten, laden)
        if ergebnis:
            daten.naechstes_spiel, daten.letztes_spiel = ergebnis
        if daten.naechstes_spiel is None:
            daten.warnungen.append(
                "Es wurde kein kommendes Spiel gefunden - moeglicherweise ist "
                "die Saison zu Ende oder der Spielplan noch nicht "
                "veroeffentlicht. Bitte Gegner, Datum und Anstoss von Hand "
                "eintragen.")
        else:
            logger().info("Naechstes Spiel: %s am %s",
                          daten.naechstes_spiel.paarung or "?",
                          daten.naechstes_spiel.datum or "ohne Datum")

    def _spiel_aus(self, eintrag: dict) -> Spiel:
        heim = _text(eintrag, "homeTeam.name", "home.name", "homeTeamName", "heim")
        gast = _text(eintrag, "awayTeam.name", "away.name", "awayTeamName", "gast")
        anstoss = _text(eintrag, "kickoff", "kickoffDate", "date", "startDate",
                        "scheduledDate")
        tore_heim = _wert(eintrag, "homeGoals", "result.home", "goalsHome")
        tore_gast = _wert(eintrag, "awayGoals", "result.away", "goalsAway")
        ergebnis = ""
        if tore_heim is not None and tore_gast is not None:
            ergebnis = f"{tore_heim}:{tore_gast}"
        return Spiel(
            heim=heim,
            gast=gast,
            wettbewerb=_text(eintrag, "competition.name", "league.name", "competition"),
            anstoss=_iso(anstoss),
            spielort=_text(eintrag, "venue.name", "ground", "location", "spielort"),
            heimspiel=self._ist_eigene(heim),
            spieltag=_text(eintrag, "matchday", "round", "spieltag"),
            ergebnis=ergebnis,
        )

    # -- Kleinkram ----------------------------------------------------------

    @staticmethod
    def _spielername(eintrag: dict) -> str:
        name = _text(eintrag, "player.name", "playerName", "name", "spieler")
        if name:
            return name
        vor = _text(eintrag, "player.firstName", "firstName")
        nach = _text(eintrag, "player.lastName", "lastName")
        return f"{vor} {nach}".strip()

    def _ist_eigene(self, name: str) -> bool:
        if not name or not self.vereinsname:
            return False
        # "SV Wörnitzstein-Berg" vs. FuPa-Kurzform "Wörnitzstein"
        kern = self.vereinsname.replace("SV", "").replace("e.V.", "").strip()
        kern = kern.split("-")[0].strip().lower()
        return bool(kern) and kern in name.lower()


def _iso(wert: str) -> str:
    """Normalisiert einen Zeitstempel nach ISO 8601 ohne Zeitzone."""
    if not wert:
        return ""
    text = str(wert).strip().replace("Z", "+00:00")
    try:
        from datetime import datetime
        return datetime.fromisoformat(text).replace(tzinfo=None).isoformat()
    except ValueError:
        return text


# ---------------------------------------------------------------------------
# Diagnose: welche Endpunkte antworten ueberhaupt?
# ---------------------------------------------------------------------------

def probe_fupa(konfiguration: Konfiguration, mannschaft_schluessel: str | None = None,
               ausgabe_ordner: Path | None = None) -> dict:
    """Probiert die konfigurierten Endpunkte aus und speichert die Rohantworten.

    Ergebnis: ein Bericht (dict) mit Status je Endpunkt. Die Rohantworten
    landen als JSON-Dateien im Arbeitsordner -- daraus laesst sich die exakte
    Feldzuordnung ablesen, ohne raten zu muessen.
    """
    client = FupaClient(konfiguration)
    client.cache.aktiv = False        # Diagnose soll wirklich abfragen

    aktive = konfiguration.aktive_mannschaften()
    if mannschaft_schluessel:
        aktive = [konfiguration.mannschaft(mannschaft_schluessel)]
    if not aktive:
        raise DatenNichtLesbarFehler(
            "Keine aktive Mannschaft.",
            benutzer_text="Es ist keine aktive Mannschaft konfiguriert.")
    team = aktive[0]

    ziel = Path(ausgabe_ordner or konfiguration.arbeits_ordner) / "fupa_probe"
    ziel.mkdir(parents=True, exist_ok=True)

    bericht: dict[str, Any] = {
        "basis_url": client.basis_url,
        "mannschaft": team.schluessel,
        "team_slug": team.fupa_slug,
        "ergebnisse": {},
        "ablage": str(ziel),
    }

    import requests
    for name in client.endpunkte:
        eintrag: dict[str, Any] = {}
        try:
            url = client.url_fuer(name, team_slug=team.fupa_slug)
            eintrag["url"] = url
            client._drosseln()
            antwort = client._sitzung().get(url, timeout=client.timeout)
            eintrag["status"] = antwort.status_code
            eintrag["inhaltstyp"] = antwort.headers.get("Content-Type", "")
            if antwort.ok and "json" in eintrag["inhaltstyp"]:
                nutzlast = antwort.json()
                datei = ziel / f"{name}.json"
                datei.write_text(json.dumps(nutzlast, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
                eintrag["gespeichert"] = str(datei)
                treffer = _liste_finden(nutzlast)
                eintrag["gefundene_zeilen"] = len(treffer)
                eintrag["beispiel_felder"] = sorted(treffer[0].keys()) if treffer else []
                eintrag["bewertung"] = "ok" if treffer else "antwortet, aber keine Liste erkannt"
            else:
                eintrag["bewertung"] = "kein verwertbares JSON"
        except requests.RequestException as fehler:
            eintrag["bewertung"] = f"nicht erreichbar: {fehler}"
        except Exception as fehler:  # noqa: BLE001 - Diagnose soll nie abbrechen
            eintrag["bewertung"] = f"Fehler: {fehler}"
        bericht["ergebnisse"][name] = eintrag

    (ziel / "_bericht.json").write_text(
        json.dumps(bericht, ensure_ascii=False, indent=2), encoding="utf-8")
    return bericht
