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
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from ..config import Konfiguration, Mannschaft
from ..errors import (AdresseGesperrtFehler, DatenNichtLesbarFehler,
                      DatenquelleNichtErreichbarFehler)
from ..logging_setup import logger
from ..models import (GegnerDaten, MannschaftsDaten, Spiel, SpielerZeile,
                      TabellenZeile, TorjaegerZeile, spiele_einordnen)
from .base import basis_daten
from .cache import DateiCache
from .erkennung import (spiele_erkennen, spieler_erkennen, tabelle_erkennen,
                        torjaeger_erkennen)
from .html_daten import json_aus_html

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
        # Frei ergaenzbare Adressen aus der Konfiguration. Falls FuPa etwas
        # umstellt, laesst sich hier eine Adresse nachtragen, ohne dass am
        # Programm etwas geaendert werden muss.
        self.zusatz_adressen: list[str] = [
            str(a) for a in (k.get("datenquelle.fupa.zusatz_adressen", []) or [])]
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
            int(k.get("datenquelle.cache.gueltigkeit_minuten", 15)),
            bool(k.get("datenquelle.cache.aktiv", True)),
        )
        self._letzte_anfrage = 0.0
        #: Wurde unterwegs auf abgelaufene Daten aus dem Zwischenspeicher
        #: zurueckgegriffen? Das muss im Heft stehen.
        self.veraltet_genutzt = False
        # Je Host eine eigene robots.txt: api.fupa.net und www.fupa.net sind
        # verschiedene Server und duerfen verschiedene Regeln haben.
        self._robots: dict[str, dict] = {}
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

    def robots_lage(self, host: str, schema: str = "https") -> dict:
        """Holt und bewertet die robots.txt eines Hosts -- einmal je Lauf.

        Bewusst **nicht** mit ``RobotFileParser.read()``. Dessen Verhalten ist
        strenger als der Standard: Antwortet der Server auf ``/robots.txt``
        mit 401 oder 403, setzt Python "alles verboten". RFC 9309 sagt dazu
        das Gegenteil (Abschnitt 2.3.1.4): Bei 4xx gibt es schlicht keine
        Regeln, der Abruf ist erlaubt.

        Der Unterschied ist hier nicht theoretisch. Ein API-Host hinter einer
        Schutzschicht beantwortet ``/robots.txt`` gern mit 403, ohne dass
        irgendwo eine Regel stuende -- und wir haetten uns selbst ausgesperrt,
        ohne dass FuPa je etwas verboten haette.

        Rueckgabe: ``{"status", "bewertung", "text", "regeln"}``.
        """
        if host in self._robots:
            return self._robots[host]

        lage: dict[str, Any] = {"status": None, "text": "", "regeln": None}
        parser = urllib.robotparser.RobotFileParser()
        adresse = f"{schema}://{host}/robots.txt"
        try:
            self._drosseln()
            antwort = self._sitzung().get(adresse, timeout=self.timeout)
            lage["status"] = antwort.status_code
            if antwort.status_code == 200:
                lage["text"] = (antwort.text or "")[:4000]
                parser.parse(lage["text"].splitlines())
                lage["bewertung"] = "Regeln gelesen"
            elif antwort.status_code == 429 or antwort.status_code >= 500:
                # RFC 9309, 2.3.1.3: unerreichbar -> vollstaendig sperren.
                parser.disallow_all = True
                lage["bewertung"] = (f"HTTP {antwort.status_code} - Server "
                                     f"ueberlastet oder gestoert, alles gesperrt")
            else:
                # RFC 9309, 2.3.1.4: 4xx -> es gibt keine Regeln.
                parser.parse([])
                lage["bewertung"] = (f"HTTP {antwort.status_code} - keine "
                                     f"robots.txt vorhanden, also keine Regeln")
        except Exception as fehler:                           # noqa: BLE001
            # Kommt die robots.txt gar nicht an, scheitert der eigentliche
            # Abruf ohnehin. Sich hier zu sperren brächte nichts.
            parser.parse([])
            lage["bewertung"] = f"nicht abrufbar ({fehler})"
            logger().info("robots.txt von %s nicht lesbar (%s).", host, fehler)

        lage["regeln"] = parser
        logger().info("robots.txt %s: %s", host, lage["bewertung"])
        self._robots[host] = lage
        return lage

    def _robots_erlaubt(self, url: str) -> bool:
        if not self.robots_beachten:
            return True
        teile = urlparse(url)
        lage = self.robots_lage(teile.netloc, teile.scheme or "https")
        return bool(lage["regeln"].can_fetch(self.user_agent, url))

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
            raise AdresseGesperrtFehler(
                f"robots.txt verbietet den Abruf von {url}.",
                benutzer_text=("FuPa erlaubt den automatischen Abruf dieser "
                               "Adresse nicht."),
                hinweis=("Diese Adresse wird uebersprungen. Andere Adressen "
                         "werden weiter probiert."),
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

    def abrufen(self, url: str):
        """Holt eine Adresse und gibt die rohe Antwort zurueck.

        Anders als :meth:`hole_json` wird hier **nicht** vorausgesetzt, dass
        JSON zurueckkommt: Die oeffentlichen FuPa-Seiten liefern HTML, in dem
        die Daten eingebettet sind. Der Accept-Kopf laesst deshalb beides zu.
        """
        if not self._robots_erlaubt(url):
            raise DatenquelleNichtErreichbarFehler(
                f"robots.txt verbietet den Abruf von {url}.",
                benutzer_text="FuPa erlaubt den automatischen Abruf dieser Seite nicht.",
                hinweis=("Bitte in der Konfiguration auf den Modus 'manuell' "
                         "umstellen und die Daten als CSV bereitstellen."),
            )

        import requests

        kopf = {"Accept": ("text/html,application/xhtml+xml,"
                           "application/json;q=0.9,*/*;q=0.8")}
        letzter_fehler: Exception | None = None
        for versuch in range(1, self.wiederholungen + 2):
            try:
                self._drosseln()
                logger().debug("GET %s (Versuch %d)", url, versuch)
                return self._sitzung().get(url, timeout=self.timeout, headers=kopf)
            except requests.RequestException as fehler:
                letzter_fehler = fehler
                if versuch <= self.wiederholungen:
                    wartezeit = 2 ** versuch
                    logger().warning("Abruf fehlgeschlagen (%s) - neuer Versuch in %ds.",
                                     fehler, wartezeit)
                    time.sleep(wartezeit)

        raise DatenquelleNichtErreichbarFehler(
            f"{url}: {letzter_fehler}",
            benutzer_text="FuPa ist im Moment nicht erreichbar.",
            hinweis=("Bitte Internetverbindung pruefen und spaeter erneut versuchen. "
                     "Alternativ im Programm auf 'Manuelle Eingabe' umstellen."),
        )

    def hole_nutzlasten(self, url: str) -> list[Any]:
        """Alle JSON-Daten hinter einer Adresse -- egal ob API oder Webseite.

        Kommt JSON zurueck, ist das die einzige Nutzlast. Kommt HTML zurueck,
        werden die eingebetteten JSON-Bloecke herausgeloest. Ein 404 oder eine
        leere Seite ist hier **kein Fehler**: Beim Durchprobieren mehrerer
        Adressen ist "hier ist nichts" eine voellig normale Antwort.
        """
        # Eigener Cache-Schluessel: Unter der blossen Adresse liegt
        # moeglicherweise schon eine Antwort von hole_json -- das ist etwas
        # anderes als eine Liste von Bloecken.
        schluessel = f"bloecke|{url}"
        zwischengespeichert = self.cache.lesen(schluessel)
        if isinstance(zwischengespeichert, list):
            logger().debug("Aus Cache: %s", url)
            return zwischengespeichert

        try:
            antwort = self.abrufen(url)
        except DatenquelleNichtErreichbarFehler:
            # Letzter Rettungsanker: Was beim letzten Mal ankam. Lieber ein
            # Heft mit ausgewiesen aelterem Stand als gar keines -- aber der
            # Stand wird auf jeder Seite genannt und oben gemeldet.
            veraltet = self.cache.lesen(schluessel, auch_veraltet=True)
            if isinstance(veraltet, list):
                self.veraltet_genutzt = True
                logger().warning(
                    "FuPa nicht erreichbar - verwende aeltere Daten fuer %s.", url)
                return veraltet
            raise

        if antwort.status_code in (403, 429):
            raise DatenquelleNichtErreichbarFehler(
                f"HTTP {antwort.status_code} fuer {url}",
                benutzer_text=("FuPa hat den automatischen Abruf abgelehnt "
                               f"(Code {antwort.status_code})."),
                hinweis=("Bitte spaeter erneut versuchen oder auf manuelle "
                         "Eingabe umstellen."),
            )
        if not antwort.ok:
            logger().debug("%s antwortet mit %d", url, antwort.status_code)
            return []

        bloecke = _nutzlasten_aus(antwort)
        self.cache.schreiben(schluessel, bloecke)
        return bloecke


def _nutzlasten_aus(antwort: Any) -> list[Any]:
    """Zerlegt eine HTTP-Antwort in die JSON-Bloecke, die darin stecken."""
    typ = (antwort.headers.get("Content-Type") or "").lower()
    if "json" in typ:
        try:
            return [antwort.json()]
        except (json.JSONDecodeError, ValueError):
            return []
    text = antwort.text or ""
    if not text.strip():
        return []
    # Manche Server melden text/plain, liefern aber JSON.
    if text.lstrip()[:1] in "[{":
        try:
            return [json.loads(text)]
        except (json.JSONDecodeError, ValueError):
            pass
    return json_aus_html(text)


# ---------------------------------------------------------------------------
# Datenquelle
# ---------------------------------------------------------------------------

#: Adressen, die der Reihe nach ausprobiert werden, bis verwertbare Daten
#: ankommen. ``{slug}`` wird durch den Team-Bezeichner ersetzt.
#:
#: Ganz oben stehen moegliche JSON-Schnittstellen, darunter die **oeffentlichen
#: Teamseiten**. Letztere sind der verlaessliche Teil: Ihre Adresse steht in
#: der Konfiguration und muss nicht geraten werden. Die Daten stecken dort im
#: eingebetteten JSON der Seite (siehe :mod:`stadionheft.sources.html_daten`).
#: Die Reihenfolge stammt aus einem echten Probelauf auf der NAS (29.09.2026):
#: Die Teamseite antwortet mit 200 und enthaelt eingebettetes JSON, die
#: Unterseiten antworten mit 404, und api.fupa.net ist per robots.txt
#: gesperrt. Das Sichere kommt deshalb zuerst.
KANDIDATEN: tuple[str, ...] = (
    # Die oeffentliche Teamseite -- geprueft, antwortet
    "https://www.fupa.net/team/{slug}",
    # Unterseiten: im Probelauf 404, aber billig mitzunehmen, falls FuPa sie
    # wieder einfuehrt. Nach dem ersten Fehlschlag werden sie im Lauf
    # uebersprungen.
    "https://www.fupa.net/team/{slug}/tabelle",
    "https://www.fupa.net/team/{slug}/spielplan",
    "https://www.fupa.net/team/{slug}/kader",
    "https://www.fupa.net/team/{slug}/statistiken",
    # Moegliche JSON-Schnittstellen. Derzeit per robots.txt gesperrt; sie
    # bleiben stehen, weil sich das aendern kann -- gesperrte Adressen kosten
    # keinen Abruf, nur einen Blick in die gemerkte robots.txt.
    "https://api.fupa.net/v1/teams/{slug}",
    "https://api.fupa.net/v1/teams/{slug}/standing",
    "https://api.fupa.net/v1/teams/{slug}/matches",
    "https://api.fupa.net/v1/teams/{slug}/players",
    "https://api.fupa.net/v1/teams/{slug}/topscorers",
)


def adressen_fuer_kennung(client: FupaClient, kennung: str,
                          team_url: str = "") -> list[str]:
    """Alle Adressen, die fuer einen Team-Bezeichner in Frage kommen.

    Reihenfolge: konfigurierte Endpunkte, dann die ausdruecklich bekannte
    Teamseite, dann frei ergaenzbare Zusatzadressen, zuletzt die
    Standardkandidaten. Doppelte Eintraege fallen heraus.
    """
    adressen: list[str] = []

    for name in client.endpunkte:
        try:
            adressen.append(client.url_fuer(name, team_slug=kennung))
        except DatenNichtLesbarFehler:
            continue

    # Eine ausdruecklich bekannte Teamseite ist die zuverlaessigste Adresse
    # ueberhaupt: Sie muss nicht geraten werden.
    if team_url:
        adressen.append(team_url.rstrip("/"))

    for muster in (*client.zusatz_adressen, *KANDIDATEN):
        try:
            adressen.append(muster.format(slug=kennung, team_slug=kennung))
        except (KeyError, IndexError):
            adressen.append(muster)

    gesehen: set[str] = set()
    eindeutig: list[str] = []
    for adresse in adressen:
        if adresse and adresse not in gesehen:
            gesehen.add(adresse)
            eindeutig.append(adresse)
    return eindeutig


def adressen_fuer(client: FupaClient, mannschaft: Mannschaft) -> list[str]:
    """Alle Adressen, die fuer eine konfigurierte Mannschaft in Frage kommen."""
    return adressen_fuer_kennung(client, mannschaft.fupa_slug,
                                 mannschaft.fupa_team_url)


def _kurz(adresse: str) -> str:
    """Adresse gekuerzt fuers Protokoll."""
    return adresse.replace("https://", "").replace("www.", "")


@dataclass
class Fund:
    """Was beim Abklappern einer Adressliste zusammengekommen ist."""

    tabelle: list[TabellenZeile] = field(default_factory=list)
    torjaeger: list[TorjaegerZeile] = field(default_factory=list)
    spieler: list[SpielerZeile] = field(default_factory=list)
    spiele: list[Spiel] = field(default_factory=list)
    abrufe: int = 0
    netzfehler: Exception | None = None

    @property
    def vollstaendig(self) -> bool:
        return bool(self.tabelle and self.torjaeger and self.spieler and self.spiele)

    @property
    def leer(self) -> bool:
        return not (self.tabelle or self.torjaeger or self.spieler or self.spiele)

    @property
    def liga(self) -> str:
        for spiel in self.spiele:
            if spiel.wettbewerb:
                return spiel.wettbewerb
        return ""


class FupaApiQuelle:
    """Holt Tabelle, Torjaeger, Spielerstatistik und Spielplan von FuPa.

    Vorgehen -- bewusst suchend statt raten:

    1. Alle in Frage kommenden Adressen werden der Reihe nach abgerufen
       (konfigurierte Endpunkte zuerst, dann die Teamseite, dann die
       Standardkandidaten).
    2. Von jeder Antwort wird alles eingesammelt, was JSON ist -- auch
       JSON, das in einer HTML-Seite eingebettet ist.
    3. :mod:`stadionheft.sources.erkennung` sucht darin nach dem, was wie
       eine Tabelle, eine Torschuetzenliste, eine Spielerstatistik oder ein
       Spielplan **aussieht** -- unabhaengig von den Feldnamen.
    4. Sobald alle vier Teile beisammen sind, wird abgebrochen. Es werden
       also nur so viele Seiten geholt wie noetig.

    Dasselbe Verfahren laeuft danach ein zweites Mal -- fuer den **naechsten
    Gegner**. Dessen Bezeichner steht im Spielplan, den Schritt 3 gerade
    erkannt hat. Er muss also weder erraten noch von Hand gepflegt werden.
    """

    name = "api"

    def __init__(self, konfiguration: Konfiguration) -> None:
        self.konfiguration = konfiguration
        self.client = FupaClient(konfiguration)
        self.vereinsname = konfiguration.vereinsname
        self.max_abrufe = int(konfiguration.get("datenquelle.fupa.max_abrufe", 12))
        self.gegner_abrufen = bool(
            konfiguration.get("datenquelle.fupa.gegner_abrufen", True))
        #: Von Hand hinterlegte Gegneradressen, falls der Spielplan keinen
        #: Bezeichner mitliefert. Schluessel = Vereinsname (klein geschrieben).
        self.gegner_adressen = {
            str(k).strip().lower(): str(v)
            for k, v in (konfiguration.get("datenquelle.fupa.gegner", {}) or {}).items()
        }
        #: Adressmuster, die in diesem Lauf schon nichts geliefert haben. Beim
        #: naechsten Team werden sie uebersprungen. Ohne das holt ein Heft mit
        #: fuenf Mannschaften dieselben Fehlschlaege zehnmal -- unnoetige Last
        #: fuer FuPa und unnoetige Wartezeit fuer uns.
        self._tote_muster: set[str] = set()
        #: Muster, die etwas geliefert haben, werden zuerst probiert.
        self._gute_muster: list[str] = []

    # -- Schnittstelle ------------------------------------------------------

    def hole(self, mannschaft: Mannschaft) -> MannschaftsDaten:
        daten = basis_daten(mannschaft, self.name)
        if not mannschaft.fupa_slug:
            raise DatenNichtLesbarFehler(
                f"Kein Team-Bezeichner in '{mannschaft.fupa_team_url}'.",
                benutzer_text=(f"Fuer {mannschaft.anzeigename} fehlt ein gueltiger "
                               f"FuPa-Link."),
                hinweis=("Erwartet wird eine Adresse der Form "
                         "https://www.fupa.net/team/<name>-<saison>"))

        logger().info("Hole FuPa-Daten fuer %s (%s) ...",
                      mannschaft.anzeigename, mannschaft.fupa_slug)

        fund = self._sammeln(adressen_fuer(self.client, mannschaft),
                             self.vereinsname, self.max_abrufe,
                             mannschaft.fupa_slug)
        if fund.abrufe == 0:
            raise fund.netzfehler or DatenquelleNichtErreichbarFehler(
                "Keine Adresse lieferte eine Antwort.",
                benutzer_text="Von FuPa kam keine verwertbare Antwort.",
                hinweis=("Bitte in der Oberflaeche auf 'FuPa-Verbindung pruefen' "
                         "klicken - dort steht, was genau zurueckkam."))

        daten.tabelle = fund.tabelle
        daten.torjaeger = fund.torjaeger
        daten.spieler = fund.spieler
        daten.spiele = fund.spiele
        daten.naechstes_spiel, daten.letztes_spiel = spiele_einordnen(fund.spiele)
        daten.liga = daten.liga or fund.liga
        daten.abgerufen_am = datetime.now().isoformat(timespec="seconds")
        daten.veraltet = self.client.veraltet_genutzt

        if self.gegner_abrufen:
            daten.gegner_daten = self._gegner_holen(daten)

        self._melden(daten)
        return daten

    # -- Suchen und erkennen ------------------------------------------------

    def _muster(self, adresse: str, kennung: str) -> str:
        """Die Adresse mit dem Team-Bezeichner wieder als Platzhalter.

        So laesst sich eine Erfahrung von einer Mannschaft auf die naechste
        uebertragen: Nicht *diese* Adresse war tot, sondern diese *Art* von
        Adresse.
        """
        return adresse.replace(kennung, "{slug}") if kennung else adresse

    def _sortieren(self, adressen: list[str], kennung: str) -> list[str]:
        """Bewaehrte Adressen zuerst, in diesem Lauf tote gar nicht.

        Zwei Sicherungen, damit die Abkuerzung nicht zur Falle wird:

        * Ein Muster, das schon einmal etwas geliefert hat, wird nie
          uebersprungen -- dass die Seite *dieser* Mannschaft fehlt, sagt
          nichts ueber die naechste.
        * Bliebe nichts uebrig, wird doch alles probiert. Lieber ein paar
          Abrufe zu viel als eine Mannschaft ohne jeden Versuch.
        """
        gut, offen = [], []
        for adresse in adressen:
            muster = self._muster(adresse, kennung)
            if muster in self._gute_muster:
                gut.append(adresse)
            elif muster not in self._tote_muster:
                offen.append(adresse)
        return (gut + offen) or list(adressen)

    def _sammeln(self, adressen: list[str], vereinsname: str,
                 hoechstens: int, kennung: str = "") -> Fund:
        """Adressen der Reihe nach abklappern und alles Erkannte sammeln."""
        fund = Fund()
        fehlschlaege = 0

        for adresse in self._sortieren(adressen, kennung):
            if fund.abrufe >= hoechstens or fund.vollstaendig:
                break
            try:
                bloecke = self.client.hole_nutzlasten(adresse)
            except AdresseGesperrtFehler:
                # Ein Verbot ist eine Auskunft, kein Ausfall: Diese Adresse
                # faellt endgueltig weg, der Rest wird ganz normal probiert.
                # Wuerde das als Netzfehler zaehlen, koennten drei gesperrte
                # Adressen am Anfang der Liste den ganzen Abruf abwuergen --
                # noch bevor die Teamseite an die Reihe kommt.
                logger().info("Uebersprungen (robots.txt): %s", _kurz(adresse))
                self._tote_muster.add(self._muster(adresse, kennung))
                continue
            except DatenquelleNichtErreichbarFehler as fehler:
                fund.netzfehler = fehler
                fehlschlaege += 1
                # Scheitern mehrere Adressen hintereinander am Netz, ist nicht
                # die Adresse das Problem, sondern die Verbindung. Dann bringt
                # Weiterprobieren nur Wartezeit.
                if fehlschlaege >= 3 and fund.abrufe == 0:
                    break
                continue
            except Exception as fehler:                       # noqa: BLE001
                logger().debug("%s nicht verwertbar: %s", adresse, fehler)
                continue

            fund.abrufe += 1
            muster = self._muster(adresse, kennung)
            if bloecke:
                self._auswerten(bloecke, fund, vereinsname, adresse)
                if muster not in self._gute_muster:
                    self._gute_muster.append(muster)
                self._tote_muster.discard(muster)
            elif muster not in self._gute_muster:
                # Ein bewaehrtes Muster wird nicht totgeschrieben, nur weil
                # es zu dieser einen Mannschaft nichts gibt.
                self._tote_muster.add(muster)
        return fund

    def _auswerten(self, bloecke: list[Any], fund: Fund, vereinsname: str,
                   adresse: str) -> None:
        """Nimmt aus jedem Block das Beste. Die laengere Liste gewinnt.

        Kommt dieselbe Tabelle auf mehreren Seiten vor, ist das kein Problem:
        Es bleibt die vollstaendigste Fassung stehen.
        """
        for block in bloecke:
            gefunden = tabelle_erkennen(block, vereinsname)
            if len(gefunden) > len(fund.tabelle):
                fund.tabelle = gefunden
                logger().info("Tabelle erkannt (%d Zeilen) auf %s",
                              len(gefunden), _kurz(adresse))

            schuetzen = torjaeger_erkennen(block, vereinsname)
            if len(schuetzen) > len(fund.torjaeger):
                fund.torjaeger = schuetzen
                logger().info("Torschuetzenliste erkannt (%d Zeilen) auf %s",
                              len(schuetzen), _kurz(adresse))

            kader = spieler_erkennen(block)
            if len(kader) > len(fund.spieler):
                fund.spieler = kader
                logger().info("Spielerstatistik erkannt (%d Zeilen) auf %s",
                              len(kader), _kurz(adresse))

            spielplan = spiele_erkennen(block, vereinsname)
            if len(spielplan) > len(fund.spiele):
                fund.spiele = spielplan
                logger().info("Spielplan erkannt (%d Partien) auf %s",
                              len(spielplan), _kurz(adresse))

    # -- Der naechste Gegner ------------------------------------------------

    def _gegner_holen(self, daten: MannschaftsDaten) -> GegnerDaten | None:
        """Holt die Zahlen des naechsten Gegners.

        Der Bezeichner steht im gerade erkannten Spielplan. Liefert die Quelle
        dort keinen, hilft nur noch eine von Hand hinterlegte Adresse -- dann
        wird das auch so gesagt, statt still eine leere Seite zu bauen.
        """
        spiel = daten.naechstes_spiel
        if spiel is None or not spiel.gegner:
            return None

        gegner = GegnerDaten(name=spiel.gegner, kennung=spiel.gegner_kennung)
        hinterlegt = self.gegner_adressen.get(gegner.name.strip().lower(), "")
        if hinterlegt:
            gegner.fupa_team_url = hinterlegt
            if not gegner.kennung:
                gegner.kennung = hinterlegt.rstrip("/").rsplit("/", 1)[-1]

        if not gegner.kennung and not gegner.fupa_team_url:
            daten.warnungen.append(
                f"Zu {gegner.name} liefert FuPa im Spielplan keinen "
                f"Team-Bezeichner. Die Gegnerseiten bleiben leer. Abhilfe: den "
                f"FuPa-Link des Gegners in config.yaml unter "
                f"datenquelle.fupa.gegner eintragen.")
            return gegner

        logger().info("Hole Gegnerdaten: %s (%s)", gegner.name,
                      gegner.kennung or gegner.fupa_team_url)
        fund = self._sammeln(
            adressen_fuer_kennung(self.client, gegner.kennung,
                                  gegner.fupa_team_url),
            gegner.name, self.max_abrufe, gegner.kennung)

        gegner.tabelle = fund.tabelle
        gegner.torjaeger = fund.torjaeger
        gegner.spieler = fund.spieler
        gegner.spiele = fund.spiele
        gegner.liga = fund.liga
        if not gegner.fupa_team_url and gegner.kennung:
            gegner.fupa_team_url = f"https://www.fupa.net/team/{gegner.kennung}"

        if fund.leer:
            daten.warnungen.append(
                f"Zu {gegner.name} kamen keine Zahlen an - die Gegnerseiten "
                f"bleiben leer. Der Rest des Hefts ist davon nicht betroffen.")
        return gegner

    # -- Rueckmeldung -------------------------------------------------------

    def _melden(self, daten: MannschaftsDaten) -> None:
        """Was nicht gefunden wurde, muss der Benutzer erfahren.

        Ein halb gefuelltes Heft ohne Hinweis waere schlimmer als eine leere
        Seite mit Erklaerung -- der Fehler faellt sonst erst im Druck auf.
        """
        fehlend = []
        if not daten.tabelle:
            fehlend.append("die Tabelle")
        if not daten.torjaeger:
            fehlend.append("die Torschützenliste")
        if not daten.spieler:
            fehlend.append("die Spielerstatistik")
        if not daten.naechstes_spiel:
            fehlend.append("das nächste Spiel")

        if fehlend:
            daten.warnungen.append(
                "Von FuPa konnte " + ", ".join(fehlend) + " nicht gelesen werden. "
                "Die betreffenden Seiten bleiben leer. Über den Knopf "
                "'FuPa-Verbindung prüfen' lässt sich nachsehen, was zurückkam.")
        if daten.veraltet:
            daten.warnungen.append(
                "FuPa war nicht erreichbar. Es wurden ältere Daten aus dem "
                "Zwischenspeicher verwendet – bitte den Stand auf den Seiten "
                "prüfen, bevor das Heft in den Druck geht.")
        if daten.naechstes_spiel:
            logger().info("Nächstes Spiel: %s am %s",
                          daten.naechstes_spiel.paarung or "?",
                          daten.naechstes_spiel.datum or "ohne Datum")


# ---------------------------------------------------------------------------
# Diagnose: welche Endpunkte antworten ueberhaupt?
# ---------------------------------------------------------------------------

def probe_fupa(konfiguration: Konfiguration, mannschaft_schluessel: str | None = None,
               ausgabe_ordner: Path | None = None) -> dict:
    """Probiert **alle** in Frage kommenden Adressen aus und berichtet.

    Getestet wird genau die Liste, die auch beim Hefterstellen abgeklappert
    wird (:func:`adressen_fuer`). Zu jeder Adresse steht im Bericht,

    * ob sie geantwortet hat und mit welchem Status,
    * wie viele JSON-Bloecke sich aus der Antwort gewinnen liessen,
    * und -- das Entscheidende -- was davon als Tabelle, Torschuetzenliste,
      Spielerstatistik oder Spielplan **erkannt** wurde.

    Die Rohantworten landen als JSON-Dateien im Arbeitsordner. Anders als
    frueher wird hier nichts abgebrochen: Der Bericht soll auch dann etwas
    aussagen, wenn die Haelfte der Adressen ins Leere laeuft.
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
    for alt in ziel.glob("*.json"):   # alte Laeufe nicht mit ausliefern
        alt.unlink(missing_ok=True)

    adressen = adressen_fuer(client, team)
    bericht: dict[str, Any] = {
        "basis_url": client.basis_url,
        "mannschaft": team.schluessel,
        "team_slug": team.fupa_slug,
        "geprueft": len(adressen),
        "ergebnisse": {},
        "ablage": str(ziel),
    }

    for nummer, url in enumerate(adressen, 1):
        eintrag: dict[str, Any] = {"url": url}
        try:
            antwort = client.abrufen(url)
            eintrag["status"] = antwort.status_code
            eintrag["inhaltstyp"] = (antwort.headers.get("Content-Type") or "")
            eintrag["groesse"] = len(antwort.content or b"")
            if not antwort.ok:
                eintrag["bewertung"] = f"antwortet mit HTTP {antwort.status_code}"
            else:
                bloecke = _nutzlasten_aus(antwort)
                eintrag["json_bloecke"] = len(bloecke)
                erkannt = _erkennungsbilanz(bloecke, konfiguration.vereinsname)
                eintrag["erkannt"] = erkannt
                if bloecke:
                    datei = ziel / f"{nummer:02d}_{_dateiname(url)}.json"
                    datei.write_text(
                        json.dumps(bloecke, ensure_ascii=False, indent=2),
                        encoding="utf-8")
                    eintrag["gespeichert"] = datei.name
                eintrag["gefundene_zeilen"] = sum(erkannt.values())
                if erkannt:
                    eintrag["bewertung"] = "ok"
                elif bloecke:
                    eintrag["bewertung"] = ("antwortet mit JSON, aber nichts davon "
                                            "sieht nach Spieldaten aus")
                else:
                    eintrag["bewertung"] = "antwortet, enthaelt aber kein JSON"
        except AdresseGesperrtFehler:
            eintrag["bewertung"] = ("laut robots.txt gesperrt - wird "
                                    "uebersprungen")
        except DatenquelleNichtErreichbarFehler as fehler:
            eintrag["bewertung"] = f"nicht erreichbar: {fehler.technisch}"
        except Exception as fehler:  # noqa: BLE001 - Diagnose soll nie abbrechen
            eintrag["bewertung"] = f"Fehler: {fehler}"
        bericht["ergebnisse"][_kurz(url)] = eintrag

    # Die robots.txt je Host mit ausweisen. Ohne sie laesst sich ein "gesperrt"
    # nicht deuten: Steht dort wirklich eine Regel, oder war die Datei nur
    # nicht lesbar? Das entscheidet, ob der Weg zu ist oder ob wir uns selbst
    # ausgesperrt haben.
    bericht["robots"] = {
        host: {"status": lage.get("status"),
               "bewertung": lage.get("bewertung", ""),
               "text": (lage.get("text") or "")[:1500]}
        for host, lage in client._robots.items()
    }
    bericht["zusammenfassung"] = _zusammenfassung(bericht["ergebnisse"])
    (ziel / "_bericht.json").write_text(
        json.dumps(bericht, ensure_ascii=False, indent=2), encoding="utf-8")
    # Zusaetzlich als Text: Wer den Test ueber den Aufgabenplaner der NAS
    # startet, sieht die Bildschirmausgabe nicht. Diese Datei laesst sich in
    # der File Station anklicken und lesen.
    (ziel / "_bericht.txt").write_text(bericht_als_text(bericht),
                                       encoding="utf-8")
    return bericht


#: Menschenlesbare Namen der vier Datenteile.
DATENTEILE = {"tabelle": "Tabelle", "torjaeger": "Torschützenliste",
              "spieler": "Spielerstatistik", "spiele": "Spielplan"}


def bericht_als_text(bericht: dict) -> str:
    """Der Probe-Bericht als lesbarer Text -- fuer Datei und Bildschirm."""
    zeilen: list[str] = [
        "FuPa-Verbindung geprüft",
        "=" * 40,
        f"Mannschaft   : {bericht.get('mannschaft', '?')} "
        f"({bericht.get('team_slug', '?')})",
        f"Adressen     : {bericht.get('geprueft', 0)} geprüft",
        "",
        "Ergebnis",
        "-" * 40,
    ]

    bilanz = bericht.get("zusammenfassung") or {}
    for schluessel, titel in DATENTEILE.items():
        anzahl = bilanz.get(schluessel)
        zeilen.append(f"  {titel:<18} "
                      + (f"gefunden ({anzahl} Zeilen)" if anzahl
                         else "NICHT gefunden"))

    zeilen += ["", "Im Einzelnen", "-" * 40]
    for name, eintrag in (bericht.get("ergebnisse") or {}).items():
        zeilen.append(f"  [{eintrag.get('status', '---')}] {name}")
        zeilen.append(f"        {eintrag.get('bewertung', '')}")
        if eintrag.get("erkannt"):
            teile = ", ".join(f"{DATENTEILE.get(s, s)}: {n}"
                              for s, n in eintrag["erkannt"].items())
            zeilen.append(f"        Erkannt: {teile}")

    robots = bericht.get("robots") or {}
    if robots:
        zeilen += ["", "robots.txt", "-" * 40]
        for host, lage in robots.items():
            zeilen.append(f"  {host}: {lage.get('bewertung', '')}")
            text = (lage.get("text") or "").strip()
            if text:
                for regel in text.splitlines()[:25]:
                    zeilen.append(f"      | {regel}")

    zeilen += ["", "Was das bedeutet", "-" * 40]
    if len(bilanz) == len(DATENTEILE):
        zeilen += [
            "  Alles Nötige wird gefunden. Der automatische Abruf funktioniert;",
            "  es ist nichts weiter einzustellen.",
        ]
    elif bilanz:
        zeilen += [
            "  Ein Teil wird gefunden, der Rest nicht. Was fehlt, bleibt im Heft",
            "  leer und muss über die CSV-Dateien gepflegt werden.",
            "  Die Dateien in diesem Ordner zeigen, was FuPa geliefert hat.",
        ]
    else:
        zeilen += [
            "  Es kamen keine Spieldaten an. Entweder ist FuPa von der NAS aus",
            "  nicht erreichbar, oder die Seiten sind anders aufgebaut als",
            "  erwartet. Das Heft entsteht weiterhin - mit den CSV-Dateien.",
        ]
    zeilen.append("")
    return "\n".join(zeilen)


def _erkennungsbilanz(bloecke: list[Any], vereinsname: str) -> dict[str, int]:
    """Was liess sich in diesen Bloecken erkennen? Nur nicht-leere Treffer."""
    bestes: dict[str, int] = {}
    for block in bloecke:
        for bezeichnung, treffer in (
                ("tabelle", tabelle_erkennen(block, vereinsname)),
                ("torjaeger", torjaeger_erkennen(block, vereinsname)),
                ("spieler", spieler_erkennen(block)),
                ("spiele", spiele_erkennen(block, vereinsname))):
            if len(treffer) > bestes.get(bezeichnung, 0):
                bestes[bezeichnung] = len(treffer)
    return {name: anzahl for name, anzahl in bestes.items() if anzahl}


def _zusammenfassung(ergebnisse: dict[str, dict]) -> dict[str, int]:
    """Beste Trefferzahl je Datenart ueber alle Adressen hinweg."""
    gesamt: dict[str, int] = {}
    for eintrag in ergebnisse.values():
        for name, anzahl in (eintrag.get("erkannt") or {}).items():
            gesamt[name] = max(gesamt.get(name, 0), anzahl)
    return gesamt


def _dateiname(url: str) -> str:
    """Aus einer Adresse einen brauchbaren Dateinamen machen."""
    roh = _kurz(url).replace("://", "_")
    sauber = "".join(z if z.isalnum() or z in "-_" else "_" for z in roh)
    return sauber.strip("_")[:60] or "antwort"
