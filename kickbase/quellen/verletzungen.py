"""Zusaetzliche Verletzungsmeldungen von Fussballseiten (optional).

**Bitte zuerst lesen.** Der verlaesslichste Verletzungshinweis kommt von
Kickbase selbst: das Feld ``st`` unterscheidet fit, angeschlagen, verletzt,
Aufbautraining und Sperre und ist die Grundlage jeder Bewertung. Dieses Modul
ist nur die Kuer -- es holt *Klartextmeldungen* dazu ("Muskelfaserriss, faellt
vier Wochen aus"), die Kickbase nicht liefert.

Wie es arbeitet und warum so:

* Es wird **kein seitenspezifischer Parser** gebaut. Solche Parser gehen beim
  naechsten Umbau der Seite kaputt. Stattdessen wird der Text der Seite
  eingelesen und nach den Namen der Spieler durchsucht, die ohnehin schon
  bekannt sind. Steht in der Umgebung eines Namens ein Verletzungsbegriff,
  gilt das als Meldung.
* ``robots.txt`` wird vorher gefragt. Sagt eine Seite Nein, wird sie nicht
  abgerufen.
* Faellt eine Seite aus oder aendert ihren Aufbau, liefert das Modul einfach
  nichts. Die Bewertung laeuft dann wie vorher mit dem Kickbase-Status.

Standardmaessig ist diese Quelle **ausgeschaltet**. Wer sie einschaltet,
sollte sich vergewissern, dass die Nutzungsbedingungen der jeweiligen Seite
das Auslesen erlauben.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from ..errors import QuelleNichtErreichbarFehler
from ..logging_setup import logger
from ..models import Spieler
from .http import KENNUNG, DateiCache, HttpQuelle

#: Begriffe, die eine Meldung als verletzungsrelevant ausweisen.
BEGRIFFE = (
    "verletzt", "verletzung", "muskelfaserriss", "muskelbündelriss",
    "muskelbuendelriss", "kreuzband", "meniskus", "bänderriss", "baenderriss",
    "zerrung", "prellung", "bruch", "operation", "operiert", "reha",
    "aufbautraining", "angeschlagen", "fällt aus", "faellt aus", "ausfall",
    "fehlt", "pausiert", "sperre", "gesperrt", "rotsperre", "gelbsperre",
    "adduktoren", "achillessehne", "schambein", "syndesmose", "innenband",
    "außenband", "aussenband", "wadenprobleme", "knieprobleme", "erkrankt",
    "grippe", "infekt", "sehnenriss", "anriss", "fraktur",
)

#: Trennzeichen zwischen zwei Aussagen. Der senkrechte Strich steht fuer die
#: Grenze zweier HTML-Bausteine (siehe :func:`text_aus_html`) -- so werden
#: Tabellenzeilen genauso sauber getrennt wie Saetze im Fliesstext.
_SATZGRENZE = re.compile(r"[.!?|;\n]+")

#: Laenger als das wird ein Ausschnitt in der Oberflaeche nicht angezeigt.
HOECHSTLAENGE = 220


class _TextSammler(HTMLParser):
    """Zieht den sichtbaren Text aus einer HTML-Seite.

    Bewusst ohne Fremdbibliothek: der Standard-Parser genuegt voellig, und
    das Projekt bleibt ohne zusaetzliche Abhaengigkeit installierbar.
    """

    _UEBERSPRINGEN = {"script", "style", "noscript", "svg", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.teile: list[str] = []
        self._tiefe = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._UEBERSPRINGEN:
            self._tiefe += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._UEBERSPRINGEN and self._tiefe:
            self._tiefe -= 1

    def handle_data(self, daten: str) -> None:
        if not self._tiefe and daten.strip():
            self.teile.append(daten.strip())

    @property
    def text(self) -> str:
        # Mit senkrechtem Strich verbunden, damit spaeter erkennbar bleibt, wo
        # ein Baustein aufhoert -- sonst verschmelzen Tabellenzeilen zu einem
        # einzigen Satz und eine Verletzungsmeldung faerbt auf den naechsten
        # Spieler ab.
        return re.sub(r"[ \t]+", " ", " | ".join(self.teile))


def text_aus_html(html: str) -> str:
    sammler = _TextSammler()
    try:
        sammler.feed(html)
    except Exception as fehler:  # defekte Seiten sind kein Programmfehler
        logger().debug("HTML nicht vollstaendig lesbar: %s", fehler)
    return sammler.text


@dataclass
class Meldung:
    """Ein Fund zu genau einem Spieler."""

    spieler_id: str
    text: str
    quelle: str


@dataclass
class Verletzungslage:
    """Alle Funds aller eingeschalteten Seiten."""

    meldungen: dict[str, Meldung] = field(default_factory=dict)
    geprueft: list[str] = field(default_factory=list)
    fehler: list[str] = field(default_factory=list)

    def anwenden(self, spieler: Iterable[Spieler]) -> int:
        """Schreibt die Meldungen in die Spielerobjekte."""
        anzahl = 0
        for s in spieler:
            meldung = self.meldungen.get(s.id)
            # Eine Kickbase-eigene Meldung ist verlaesslicher und bleibt stehen.
            if meldung and s.verletzungsquelle != "Kickbase":
                s.verletzungsmeldung = meldung.text
                s.verletzungsquelle = meldung.quelle
                anzahl += 1
        return anzahl


class VerletzungsQuelle(HttpQuelle):
    """Durchsucht konfigurierte Seiten nach Meldungen zu bekannten Spielern."""

    name = "Verletzungsmeldungen"

    def __init__(self, seiten: list[dict], cache: DateiCache | None = None) -> None:
        super().__init__(cache=cache, pause_ms=1000, versuche=2)
        self.seiten = [s for s in (seiten or []) if isinstance(s, dict) and s.get("url")]

    # -- Hoeflichkeit ------------------------------------------------------

    def _erlaubt(self, url: str) -> bool:
        """Fragt die robots.txt der Seite."""
        try:
            teile = urlparse(url)
            regeln = RobotFileParser()
            regeln.set_url(f"{teile.scheme}://{teile.netloc}/robots.txt")
            regeln.read()
            return regeln.can_fetch(KENNUNG, url)
        except Exception as fehler:
            # Keine robots.txt erreichbar: im Zweifel nicht abrufen.
            logger().warning("robots.txt von %s nicht lesbar (%s) - Seite wird "
                             "uebersprungen.", url, fehler)
            return False

    # -- Abruf -------------------------------------------------------------

    def lage_holen(self, spieler: Iterable[Spieler]) -> Verletzungslage:
        lage = Verletzungslage()
        bekannte = self._suchindex(spieler)
        if not bekannte:
            return lage

        for seite in self.seiten:
            url = str(seite.get("url"))
            bezeichnung = str(seite.get("name") or urlparse(url).netloc or url)
            if not self._erlaubt(url):
                lage.fehler.append(f"{bezeichnung}: laut robots.txt nicht erlaubt.")
                continue
            try:
                html = self.text_holen(url)
            except QuelleNichtErreichbarFehler as fehler:
                lage.fehler.append(f"{bezeichnung}: {fehler.benutzer_text}")
                continue

            treffer = self._auswerten(text_aus_html(html), bekannte, bezeichnung)
            for meldung in treffer:
                lage.meldungen.setdefault(meldung.spieler_id, meldung)
            lage.geprueft.append(f"{bezeichnung}: {len(treffer)} Meldungen")
            logger().info("%s: %d Meldungen gefunden.", bezeichnung, len(treffer))

        return lage

    # -- Innereien ---------------------------------------------------------

    @staticmethod
    def _suchindex(spieler: Iterable[Spieler]) -> dict[str, str]:
        """Nachname -> Spieler-ID, nur bei eindeutigen und langen Namen.

        Kurze oder mehrfach vorkommende Nachnamen ("Kim", "Müller") werden
        weggelassen. Eine falsche Zuordnung waere schlimmer als eine fehlende.
        """
        zaehler: dict[str, list[str]] = {}
        for s in spieler:
            name = (s.nachname or "").strip()
            if len(name) < 5:
                continue
            zaehler.setdefault(name.lower(), []).append(s.id)
        return {name: ids[0] for name, ids in zaehler.items() if len(ids) == 1}

    @staticmethod
    def _auswerten(text: str, bekannte: dict[str, str],
                   quelle: str) -> list[Meldung]:
        """Findet Meldungen satzweise.

        Entscheidend ist, dass Name und Verletzungsbegriff **im selben Satz**
        stehen. Ein Umfeld von n Zeichen genuegt nicht: in "Meier faellt vier
        Wochen aus. Schmidt traf doppelt" stuende Schmidt sonst als verletzt
        da, obwohl er getroffen hat.
        """
        gefunden: list[Meldung] = []
        for satz in _SATZGRENZE.split(text):
            sauber = satz.strip()
            if len(sauber) < 10:
                continue
            klein = sauber.lower()
            if not any(begriff in klein for begriff in BEGRIFFE):
                continue
            for name, spieler_id in bekannte.items():
                if name in klein:
                    gefunden.append(Meldung(
                        spieler_id=spieler_id,
                        text=sauber[:HOECHSTLAENGE],
                        quelle=quelle))
        return gefunden
