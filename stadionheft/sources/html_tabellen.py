"""Ganz normale HTML-Tabellen lesen.

Warum das noetig wurde
======================

:mod:`stadionheft.sources.html_daten` holt **eingebettetes JSON** aus einer
Seite. Das passt zu modernen Portalen wie FuPa oder BFV, die ihre Daten als
JSON mitliefern und erst im Browser zu einer Tabelle machen.

Eine Vereinswebsite tut genau das nicht. Sie liefert eine fertige Tabelle::

    <table>
      <tr><th>Pl.</th><th>Mannschaft</th><th>Sp.</th><th>Tore</th><th>Pkt.</th></tr>
      <tr><td>9.</td><td>SV Wörnitzstein-Berg</td><td>7</td><td>11:6</td><td>10</td></tr>
    </table>

Davon verstand das Programm bisher nichts -- die eigene Vereinsseite war
damit die einzige Quelle, die es nicht lesen konnte, obwohl sie die
zugaenglichste von allen ist.

Dieses Modul macht aus jeder Tabelle eine Liste von Zuordnungen, in der die
Kopfzeile die Schluessel stellt. Danach greift dieselbe Struktur-Erkennung
wie bei allem anderen (:mod:`stadionheft.sources.erkennung`): Ob die Spalte
``Pkt.``, ``Punkte`` oder ``points`` heisst, ist ihr egal.

Bewusst ohne zusaetzliche Bibliothek: ``html.parser`` steckt in Python drin.
Eine Abhaengigkeit weniger ist eine Fehlerquelle weniger -- und auf der NAS
eine Sache weniger, die beim Bauen schiefgehen kann.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from ..logging_setup import logger

#: Tabellen, die zum Seitenlayout gehoeren statt Daten zu tragen, haben
#: wenige Zeilen oder eine einzige Spalte. Sie werden uebersprungen.
MINDEST_ZEILEN = 2
MINDEST_SPALTEN = 2

#: Mehr als das liest keine Vereinsseite -- und schuetzt vor einer Seite,
#: die aus Versehen riesig ist.
HOECHSTENS_TABELLEN = 40
HOECHSTENS_ZEILEN = 400

_LEERRAUM = re.compile(r"\s+")

#: Tags, deren Inhalt kein sichtbarer Text ist.
_STUMM = {"script", "style", "noscript"}


class _TabellenLeser(HTMLParser):
    """Sammelt Tabellen, Rahmenseiten (iframes) und deren Adressen ein."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tabellen: list[list[list[str]]] = []
        self.rahmen: list[str] = []

        self._stapel: list[list[list[str]]] = []   # verschachtelte Tabellen
        self._zeile: list[str] | None = None
        self._zelle: list[str] | None = None
        self._kopfzelle = False
        self._kopfzeilen: list[set[int]] = []
        self._stumm = 0

    # -- Aufbau -------------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _STUMM:
            self._stumm += 1
            return
        if tag == "iframe":
            quelle = dict(attrs).get("src") or ""
            if quelle:
                self.rahmen.append(quelle)
            return
        if tag == "table":
            self._stapel.append([])
            self._kopfzeilen.append(set())
            return
        if not self._stapel:
            return
        if tag == "tr":
            self._zeile = []
        elif tag in ("td", "th"):
            if self._zeile is None:        # Zelle ohne <tr> -- kommt vor
                self._zeile = []
            self._zelle = []
            self._kopfzelle = tag == "th"
        elif tag == "br" and self._zelle is not None:
            # Ein Umbruch in der Zelle trennt zwei Angaben, etwa
            # "15.10.2026<br>15:00". Ohne Leerzeichen klebten sie zusammen.
            self._zelle.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _STUMM:
            self._stumm = max(0, self._stumm - 1)
            return
        if tag == "table":
            if self._stapel:
                tabelle = self._stapel.pop()
                self._kopfzeilen.pop()
                if len(self.tabellen) < HOECHSTENS_TABELLEN:
                    self.tabellen.append(tabelle)
            return
        if not self._stapel:
            return
        if tag in ("td", "th"):
            if self._zelle is not None and self._zeile is not None:
                if self._kopfzelle:
                    self._kopfzeilen[-1].add(len(self._stapel[-1]))
                self._zeile.append(_sauber("".join(self._zelle)))
            self._zelle = None
            self._kopfzelle = False
        elif tag == "tr":
            if self._zeile:
                if len(self._stapel[-1]) < HOECHSTENS_ZEILEN:
                    self._stapel[-1].append(self._zeile)
            self._zeile = None

    def handle_data(self, daten: str) -> None:
        if self._stumm or self._zelle is None:
            return
        self._zelle.append(daten)


def _sauber(text: str) -> str:
    """Sichtbarer Text einer Zelle: Leerraum zusammenfassen, Rand abschneiden."""
    return _LEERRAUM.sub(" ", (text or "").replace("\xa0", " ")).strip()


# ---------------------------------------------------------------------------
# Oeffentliche Schnittstelle
# ---------------------------------------------------------------------------

def tabellen_aus_html(text: str) -> list[list[dict]]:
    """Jede brauchbare Tabelle der Seite als Liste von Zuordnungen.

    Die Kopfzeile stellt die Schluessel. Gibt es keine erkennbare Kopfzeile,
    werden die Spalten durchnummeriert (``spalte1`` ...) -- die
    Struktur-Erkennung kommt damit zwar nicht weit, aber eine Tabelle ohne
    Kopf ist ohnehin selten.
    """
    leser = _TabellenLeser()
    try:
        leser.feed(text or "")
        leser.close()
    except Exception as fehler:            # noqa: BLE001 - kaputtes HTML
        logger().debug("HTML nicht vollstaendig lesbar: %s", fehler)

    ergebnis: list[list[dict]] = []
    for roh in leser.tabellen:
        zeilen = _zu_zuordnungen(roh)
        if zeilen:
            ergebnis.append(zeilen)

    if ergebnis:
        logger().debug("HTML-Tabellen gelesen: %d (%s Zeilen)", len(ergebnis),
                       ", ".join(str(len(t)) for t in ergebnis))
    return ergebnis


def rahmenseiten_aus_html(text: str, basis: str = "") -> list[str]:
    """Adressen eingebetteter Rahmenseiten (``<iframe src=...>``).

    Vereinsseiten binden Tabelle und Spielplan oft als Widget eines Portals
    ein. Dann steht auf der Seite selbst nichts -- die Daten liegen eine
    Adresse weiter. Diese Adressen sind es wert, mitgeholt zu werden.
    """
    leser = _TabellenLeser()
    try:
        leser.feed(text or "")
        leser.close()
    except Exception as fehler:            # noqa: BLE001
        logger().debug("HTML nicht vollstaendig lesbar: %s", fehler)

    gesehen: set[str] = set()
    adressen: list[str] = []
    for quelle in leser.rahmen:
        voll = urljoin(basis, quelle) if basis else quelle
        if voll.startswith(("http://", "https://")) and voll not in gesehen:
            gesehen.add(voll)
            adressen.append(voll)
    return adressen


# ---------------------------------------------------------------------------
# Aus Zellen werden Zuordnungen
# ---------------------------------------------------------------------------

def _zu_zuordnungen(zeilen: list[list[str]]) -> list[dict]:
    if len(zeilen) < MINDEST_ZEILEN:
        return []

    kopf, daten = _kopf_und_daten(zeilen)
    if len(kopf) < MINDEST_SPALTEN or not daten:
        return []

    namen = _spaltennamen(kopf)
    ergebnis: list[dict] = []
    for zeile in daten:
        if not any(z.strip() for z in zeile):
            continue
        eintrag = {namen[i]: wert
                   for i, wert in enumerate(zeile) if i < len(namen)}
        if eintrag:
            ergebnis.append(eintrag)
    return ergebnis if len(ergebnis) >= MINDEST_ZEILEN - 1 else []


def _kopf_und_daten(zeilen: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Welche Zeile ist die Ueberschrift?

    Erst nach einer Zeile suchen, die wie eine Ueberschrift aussieht: kurze
    Eintraege, kaum Zahlen. Vereinsseiten setzen Kopfzeilen oft mit ``<td>``
    statt ``<th>`` -- nur auf das Tag zu schauen genuegt also nicht.
    """
    erste = zeilen[0]
    if _sieht_nach_kopf_aus(erste) and len(zeilen) > 1:
        return erste, zeilen[1:]

    # Keine Kopfzeile: Spalten durchnummerieren.
    breite = max(len(z) for z in zeilen)
    return [f"spalte{i + 1}" for i in range(breite)], zeilen


def _sieht_nach_kopf_aus(zeile: list[str]) -> bool:
    gefuellt = [z for z in zeile if z.strip()]
    if len(gefuellt) < MINDEST_SPALTEN:
        return False
    zahlen = sum(1 for z in gefuellt if re.fullmatch(r"[\d.:\-/ ]+", z))
    # Eine Datenzeile besteht ueberwiegend aus Zahlen, eine Kopfzeile nicht.
    return zahlen <= len(gefuellt) / 2


def _spaltennamen(kopf: list[str]) -> list[str]:
    namen: list[str] = []
    for nummer, roh in enumerate(kopf, 1):
        name = roh.strip() or f"spalte{nummer}"
        # Gleiche Ueberschrift zweimal (z. B. zwei Spalten "Tore"): Die
        # zweite bekommt eine Nummer, sonst ginge sie verloren.
        if name in namen:
            name = f"{name}_{nummer}"
        namen.append(name)
    return namen
